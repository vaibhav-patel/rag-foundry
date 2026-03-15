"""API Gateway HTTP API v2 handler for rag-foundry control plane (Python 3.12, boto3 in runtime)."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import boto3
from bedrock_generation import (
    audit_extension_stub,
    canonical_prompt_sha256,
    generate_with_converse,
    resolve_max_tokens,
    resolve_model_id,
    resolve_temperature,
)
from dense_search import parse_knn_k, run_dense_search
from job_status import (
    JOB_GSI1_PARTITION_PK,
    JOB_STATUS_QUEUE,
    gsi_sort_key_for_tenant_job,
    job_item_to_api_body,
)
from rag_context import format_rag_context, parse_context_char_budget, parse_context_k
from rerank_hook import dense_search_fetch_size, rerank_dense_hits_maybe

from opensearch_client import create_opensearch_client

_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
ddb_client = boto3.client("dynamodb", region_name=_region)
s3_client = boto3.client("s3", region_name=_region)
sfn_client = boto3.client("stepfunctions", region_name=_region)


def _json_response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _claims(event: dict[str, Any]) -> dict[str, str]:
    ctx = event.get("requestContext") or {}
    auth = ctx.get("authorizer") or {}
    jwt = auth.get("jwt") or {}
    claims = jwt.get("claims") or {}
    return {str(k): str(v) for k, v in claims.items()}


def _tenant_id(claims: dict[str, str]) -> str:
    return claims.get("custom:tenant_id") or claims.get("sub", "unknown")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    path = event.get("rawPath") or "/"
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET").upper()

    if path == "/v1/health" and method == "GET":
        return _json_response(
            200,
            {"status": "ok", "version": os.environ.get("BUILD_VERSION", "dev")},
        )

    claims = _claims(event)
    tenant = _tenant_id(claims)

    table = os.environ["TABLE_NAME"]
    raw_bucket = os.environ["RAW_BUCKET"]
    sm_arn = os.environ.get("STATE_MACHINE_ARN", "")

    if path == "/v1/tenants" and method == "GET":
        return _json_response(200, {"items": [{"id": tenant, "name": tenant}]})

    m_kb = re.fullmatch(r"/v1/kbs/([^/]+)", path)
    if path == "/v1/kbs" and method == "POST":
        body = json.loads(event.get("body") or "{}")
        kb_id = str(uuid.uuid4())
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"KB#{kb_id}"},
                "GSI1PK": {"S": f"KB#{kb_id}"},
                "GSI1SK": {"S": f"TENANT#{tenant}"},
                "name": {"S": body.get("name", "kb")},
                "embedding_model_id": {
                    "S": body.get("embedding_model_id", "amazon.titan-embed-text-v1")
                },
            },
        )
        return _json_response(201, {"id": kb_id, "tenant_id": tenant})

    if path == "/v1/kbs" and method == "GET":
        q = ddb_client.query(
            TableName=table,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
            ExpressionAttributeValues={
                ":pk": {"S": f"TENANT#{tenant}"},
                ":sk": {"S": "KB#"},
            },
        )
        items = []
        for it in q.get("Items", []):
            sk = it["SK"]["S"]
            if sk.startswith("KB#"):
                items.append(
                    {"id": sk.removeprefix("KB#"), "name": it.get("name", {}).get("S", "")}
                )
        return _json_response(200, {"items": items})

    if m_kb and method == "GET":
        kb_id = m_kb.group(1)
        g = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g:
            return _json_response(404, {"title": "Not found", "detail": "KB not found"})
        it = g["Item"]
        if it.get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Tenant mismatch"})
        return _json_response(
            200,
            {
                "id": kb_id,
                "name": it.get("name", {}).get("S", ""),
                "embedding_model_id": it.get("embedding_model_id", {}).get("S", ""),
            },
        )

    m_upload = re.fullmatch(r"/v1/kbs/([^/]+)/uploads", path)
    if m_upload and method == "POST":
        kb_id = m_upload.group(1)
        g = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g or g["Item"].get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid KB"})
        doc_id = str(uuid.uuid4())
        key = f"{tenant}/{kb_id}/{doc_id}/raw"
        url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": raw_bucket, "Key": key},
            ExpiresIn=3600,
        )
        return _json_response(200, {"document_id": doc_id, "upload_url": url, "key": key})

    m_jobs = re.fullmatch(r"/v1/kbs/([^/]+)/jobs", path)
    if m_jobs and method == "POST":
        kb_id = m_jobs.group(1)
        if not sm_arn:
            return _json_response(
                501, {"title": "Not configured", "detail": "STATE_MACHINE_ARN missing"}
            )
        body = json.loads(event.get("body") or "{}")
        s3_key = str(body.get("s3_key", "")).strip()
        if not s3_key:
            return _json_response(
                400,
                {
                    "title": "Bad Request",
                    "detail": (
                        "s3_key required (use POST /v1/kbs/{id}/uploads then pass returned key)"
                    ),
                },
            )
        g = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g or g["Item"].get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid KB"})
        emb = g["Item"].get("embedding_model_id", {}).get("S", "amazon.titan-embed-text-v1")
        resolved_embed = str(body.get("embedding_model_id") or emb).strip() or emb
        job_id = str(uuid.uuid4())
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"KB#{kb_id}"},
                "SK": {"S": f"JOB#{job_id}"},
                "GSI1PK": {"S": JOB_GSI1_PARTITION_PK},
                "GSI1SK": {"S": gsi_sort_key_for_tenant_job(tenant=tenant, job_id=job_id)},
                "tenant": {"S": tenant},
                "kb_id": {"S": kb_id},
                "embedding_model_id": {"S": resolved_embed},
                "status": {"S": JOB_STATUS_QUEUE},
            },
        )
        payload = {
            "tenant": tenant,
            "kb_id": kb_id,
            "job_id": job_id,
            "s3_key": s3_key,
            "embedding_model_id": resolved_embed,
            "chunk_chars": int(body.get("chunk_chars", 1200)),
        }
        sfn_client.start_execution(
            stateMachineArn=sm_arn,
            name=job_id[:80],
            input=json.dumps(payload),
        )
        return _json_response(202, {"id": job_id, "status": JOB_STATUS_QUEUE, "s3_key": s3_key})

    m_kb_job = re.fullmatch(r"/v1/kbs/([^/]+)/jobs/([^/]+)", path)
    if m_kb_job and method == "GET":
        kb_id_job = m_kb_job.group(1)
        job_id_kb = m_kb_job.group(2)
        gjob = ddb_client.get_item(
            TableName=table,
            Key={
                "PK": {"S": f"KB#{kb_id_job}"},
                "SK": {"S": f"JOB#{job_id_kb}"},
            },
        )
        if "Item" not in gjob:
            return _json_response(404, {"title": "Not found", "detail": "Job not found"})
        itj = gjob["Item"]
        if itj.get("tenant", {}).get("S") != tenant:
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid job"})
        return _json_response(200, job_item_to_api_body(job_id_kb, itj))

    m_job = re.fullmatch(r"/v1/jobs/([^/]+)", path)
    if m_job and method == "GET":
        job_id = m_job.group(1)
        qs_param = event.get("queryStringParameters") or {}
        kb_q = ""
        if isinstance(qs_param, dict):
            kb_q = str(qs_param.get("kb_id") or qs_param.get("kbId") or "").strip()
        if kb_q:
            keyed = ddb_client.get_item(
                TableName=table,
                Key={"PK": {"S": f"KB#{kb_q}"}, "SK": {"S": f"JOB#{job_id}"}},
            )
            if "Item" not in keyed:
                return _json_response(404, {"title": "Not found", "detail": "Job not found"})
            itq = keyed["Item"]
            if itq.get("tenant", {}).get("S") != tenant:
                return _json_response(403, {"title": "Forbidden", "detail": "Invalid job"})
            stored_kb = itq.get("kb_id", {}).get("S")
            if stored_kb not in (None, "") and stored_kb != kb_q:
                return _json_response(403, {"title": "Forbidden", "detail": "kb_id mismatch"})
            return _json_response(200, job_item_to_api_body(job_id, itq))

        q = ddb_client.query(
            TableName=table,
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk AND GSI1SK = :sk",
            ExpressionAttributeValues={
                ":pk": {"S": JOB_GSI1_PARTITION_PK},
                ":sk": {"S": gsi_sort_key_for_tenant_job(tenant=tenant, job_id=job_id)},
            },
        )
        items = q.get("Items") or []
        picked: dict[str, Any] | None = None
        for it in items:
            if it["SK"]["S"] == f"JOB#{job_id}" and it.get("tenant", {}).get("S") == tenant:
                picked = it
                break
        if not picked and items:
            # Legacy safety: malformed GSI1SK — fall back to prefix scan (migration / bad rows).
            q2 = ddb_client.query(
                TableName=table,
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
                ExpressionAttributeValues={
                    ":pk": {"S": JOB_GSI1_PARTITION_PK},
                    ":sk": {"S": f"TENANT#{tenant}#"},
                },
            )
            for it in q2.get("Items", []) or []:
                if it["SK"]["S"] == f"JOB#{job_id}" and it.get("tenant", {}).get("S") == tenant:
                    picked = it
                    break
        if picked:
            return _json_response(200, job_item_to_api_body(job_id, picked))
        return _json_response(404, {"title": "Not found", "detail": "Job not found"})

    m_search = re.fullmatch(r"/v1/kbs/([^/]+)/search", path)
    if m_search and method == "POST":
        kb_id = m_search.group(1)
        body = json.loads(event.get("body") or "{}")
        g = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g or g["Item"].get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid KB"})
        qtext = str(body.get("q", ""))
        search_mode = os.environ.get("SEARCH_MODE", "stub")
        k_desired = parse_knn_k(body)
        fetch_sz = dense_search_fetch_size(k_desired)
        http_st, search_payload = run_dense_search(
            search_mode=search_mode,
            os_client=create_opensearch_client(),
            index_name=os.environ.get("OPENSEARCH_INDEX_NAME", "rag-foundry-chunks"),
            tenant_id=tenant,
            kb_id=kb_id,
            body=body,
            query_text=qtext,
            fetch_size=fetch_sz,
        )
        if http_st != 200:
            return _json_response(http_st, search_payload)
        search_payload = rerank_dense_hits_maybe(
            search_payload,
            query_text=qtext,
            desired_top_k=k_desired,
        )
        return _json_response(200, {"kb_id": kb_id, **search_payload})

    m_query = re.fullmatch(r"/v1/kbs/([^/]+)/query", path)
    if m_query and method == "POST":
        kb_id = m_query.group(1)
        body = json.loads(event.get("body") or "{}")
        question = str(body.get("question", "") or "")
        guardrails_id = body.get("guardrails_id") or os.environ.get("BEDROCK_GUARDRAILS_ID", "")
        g_kb = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g_kb or g_kb["Item"].get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid KB"})

        search_mode = os.environ.get("SEARCH_MODE", "stub")
        ctx_k = parse_context_k(body)
        retrieval_k = max(parse_knn_k(body), ctx_k)
        merged_search_body = dict(body)
        merged_search_body["k"] = retrieval_k
        q_for_search = str(body.get("q") or question or "")
        fetch_sz = dense_search_fetch_size(retrieval_k)
        http_st, search_payload = run_dense_search(
            search_mode=search_mode,
            os_client=create_opensearch_client(),
            index_name=os.environ.get("OPENSEARCH_INDEX_NAME", "rag-foundry-chunks"),
            tenant_id=tenant,
            kb_id=kb_id,
            body=merged_search_body,
            query_text=q_for_search,
            fetch_size=fetch_sz,
        )
        if http_st != 200:
            return _json_response(http_st, search_payload)

        search_payload = rerank_dense_hits_maybe(
            search_payload,
            query_text=q_for_search,
            desired_top_k=retrieval_k,
        )
        hits = search_payload.get("hits") or []
        ctx_block, citations = format_rag_context(
            hits,
            context_k=ctx_k,
            char_budget=parse_context_char_budget(),
        )

        br = boto3.client("bedrock-runtime", region_name=_region)
        system_prompt = (
            "Answer using only the retrieved passages included in the user message below. "
            "If those passages are insufficient, say that you do not know. "
            "Be concise and accurate."
        )
        user_message = f"{ctx_block}\n\nQuestion:\n{question}"

        generation_model_id = resolve_model_id(body.get("model_id"))
        prompt_sha256 = canonical_prompt_sha256(system_prompt, user_message)
        audit_stub = audit_extension_stub()
        guard_ver = str(body.get("guardrails_version", "DRAFT"))

        try:
            text = generate_with_converse(
                br,
                model_id=generation_model_id,
                system_text=system_prompt,
                user_text=user_message,
                max_tokens=resolve_max_tokens(),
                temperature=resolve_temperature(),
                guardrail_id=guardrails_id if guardrails_id else None,
                guardrail_version=guard_ver,
            )
        except Exception as exc:  # noqa: BLE001
            text = f"[bedrock-unavailable] {exc}"
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"AUDIT#QUERY#{uuid.uuid4()}"},
                "kb_id": {"S": kb_id},
                "question": {"S": question[:2000]},
                "prompt_sha256": {"S": prompt_sha256},
                "generation_model_id": {"S": generation_model_id[:2048]},
                "audit_stub_next": {"S": audit_stub[:256]},
                **({"guardrails_id": {"S": str(guardrails_id)[:256]}} if guardrails_id else {}),
            },
        )
        return _json_response(
            200,
            {
                "answer": text,
                "citations": citations,
                "kb_id": kb_id,
                "guardrails_applied": bool(guardrails_id),
            },
        )

    if path == "/v1/plugins/manifest" and method == "POST":
        body = json.loads(event.get("body") or "{}")
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"PLUGIN#{body.get('name', 'unknown')}"},
                "semver": {"S": str(body.get("version", "0.1.0"))},
                "type": {"S": str(body.get("type", "chunker"))},
            },
        )
        return _json_response(201, {"ok": True})

    return _json_response(404, {"title": "Not found", "path": path, "method": method})
