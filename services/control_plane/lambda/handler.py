"""API Gateway HTTP API v2 handler for rag-foundry control plane (Python 3.12, boto3 in runtime)."""

from __future__ import annotations

import json
import os
import re
import time
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
from contracts_validate import (
    DENSE_SEARCH_BODY_SCHEMA_URI,
    KB_MUTATION_SCHEMA_URI,
    RAG_QUERY_SCHEMA_URI,
    format_schema_error_response,
    schema_validation_errors,
)
from dense_search import parse_knn_k, run_dense_search
from guardrails_resolve import load_tenant_settings_item, resolve_guardrail_config
from job_status import (
    JOB_GSI1_PARTITION_PK,
    JOB_STATUS_QUEUE,
    gsi_sort_key_for_tenant_job,
    job_item_to_api_body,
)
from query_audit import build_query_audit_item
from quota import try_consume_request_quota
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


def _parse_json_object(raw: str | None, *, endpoint: str) -> tuple[bool, dict[str, Any], dict]:
    """Return ``(ok, body, error_response_payload)``. ``body`` empty dict if malformed."""

    if raw is None or not str(raw).strip():
        return True, {}, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return (
            False,
            {},
            {
                "title": "Bad Request",
                "detail": f"Invalid JSON for {endpoint}: {exc}",
            },
        )
    if not isinstance(data, dict):
        return (
            False,
            {},
            {
                "title": "Bad Request",
                "detail": f"{endpoint} body must be a JSON object",
            },
        )
    return True, data, {}


def _claims(event: dict[str, Any]) -> dict[str, str]:
    ctx = event.get("requestContext") or {}
    auth = ctx.get("authorizer") or {}
    jwt = auth.get("jwt") or {}
    claims = jwt.get("claims") or {}
    return {str(k): str(v) for k, v in claims.items()}


def _tenant_id(claims: dict[str, str]) -> str:
    return claims.get("custom:tenant_id") or claims.get("sub", "unknown")


def _job_kb_query_param(event: dict[str, Any]) -> str:
    qs = event.get("queryStringParameters") or {}
    if not isinstance(qs, dict):
        return ""
    return str(qs.get("kb_id") or qs.get("kbId") or "").strip()


def _resolve_ingest_job_item(
    *,
    table: str,
    tenant: str,
    job_id: str,
    kb_q: str,
) -> tuple[dict[str, Any] | None, int | None, dict[str, Any] | None]:
    """Load tenant-scoped ingest job row. Success ``(item, None, None)`` or ``(None, status, err_body)``."""

    if kb_q:
        keyed = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"KB#{kb_q}"}, "SK": {"S": f"JOB#{job_id}"}},
        )
        if "Item" not in keyed:
            return None, 404, {"title": "Not found", "detail": "Job not found"}
        itq = keyed["Item"]
        if itq.get("tenant", {}).get("S") != tenant:
            return None, 403, {"title": "Forbidden", "detail": "Invalid job"}
        stored_kb = itq.get("kb_id", {}).get("S")
        if stored_kb not in (None, "") and stored_kb != kb_q:
            return None, 403, {"title": "Forbidden", "detail": "kb_id mismatch"}
        return itq, None, None

    qry = ddb_client.query(
        TableName=table,
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :pk AND GSI1SK = :sk",
        ExpressionAttributeValues={
            ":pk": {"S": JOB_GSI1_PARTITION_PK},
            ":sk": {"S": gsi_sort_key_for_tenant_job(tenant=tenant, job_id=job_id)},
        },
    )
    items = qry.get("Items") or []
    picked: dict[str, Any] | None = None
    for it in items:
        if it["SK"]["S"] == f"JOB#{job_id}" and it.get("tenant", {}).get("S") == tenant:
            picked = it
            break
    if not picked and items:
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
        return picked, None, None
    return None, 404, {"title": "Not found", "detail": "Job not found"}


def _kb_item_to_json(it: dict[str, Any], kb_id: str) -> dict[str, Any]:
    """Project a DynamoDB KB item to the control-plane JSON shape."""

    out: dict[str, Any] = {
        "id": kb_id,
        "name": it.get("name", {}).get("S", ""),
        "embedding_model_id": it.get("embedding_model_id", {}).get("S", ""),
    }
    cc = it.get("chunk_chars", {}).get("N")
    if cc is not None:
        try:
            out["chunk_chars"] = int(float(cc))
        except (TypeError, ValueError):
            pass
    if "hybrid" in it and "BOOL" in it["hybrid"]:
        out["hybrid"] = bool(it["hybrid"]["BOOL"])
    gen = it.get("generation_model_id", {}).get("S")
    if gen:
        out["generation_model_id"] = gen
    gid = it.get("bedrock_guardrail_id", {}).get("S")
    gver = it.get("bedrock_guardrail_version", {}).get("S")
    if gid:
        out["bedrock_guardrail_id"] = gid
    if gver:
        out["bedrock_guardrail_version"] = gver
    return out


def _kb_put_item_from_body(
    *,
    tenant: str,
    kb_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Build DynamoDB PutItem map for a KB row from a validated mutation body (POST defaults)."""

    name = str(body.get("name") or "kb")[:256]
    emb = str(body.get("embedding_model_id") or "amazon.titan-embed-text-v1")[:512]
    item: dict[str, Any] = {
        "PK": {"S": f"TENANT#{tenant}"},
        "SK": {"S": f"KB#{kb_id}"},
        "GSI1PK": {"S": f"KB#{kb_id}"},
        "GSI1SK": {"S": f"TENANT#{tenant}"},
        "name": {"S": name},
        "embedding_model_id": {"S": emb},
    }
    if "chunk_chars" in body:
        item["chunk_chars"] = {"N": str(int(body["chunk_chars"]))}
    if "hybrid" in body:
        item["hybrid"] = {"BOOL": bool(body["hybrid"])}
    gen_raw = str(body.get("generation_model_id") or "").strip()
    if gen_raw:
        item["generation_model_id"] = {"S": gen_raw[:512]}
    gid = str(
        body.get("bedrock_guardrail_id") or body.get("guardrailIdentifier") or "",
    ).strip()
    gver = str(
        body.get("bedrock_guardrail_version") or body.get("guardrailVersion") or "",
    ).strip()
    if gid:
        item["bedrock_guardrail_id"] = {"S": gid[:512]}
        if gver:
            item["bedrock_guardrail_version"] = {"S": gver[:64]}
    return item


def _kb_apply_patch(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge validated PATCH body onto an existing KB JSON dict (from _kb_item_to_json)."""

    out = {**existing}
    for key in ("name", "embedding_model_id", "chunk_chars", "hybrid"):
        if key in patch:
            out[key] = patch[key]
    if "generation_model_id" in patch:
        gv = str(patch.get("generation_model_id") or "").strip()
        out["generation_model_id"] = gv if gv else None
    id_touched = "bedrock_guardrail_id" in patch or "guardrailIdentifier" in patch
    ver_touched = "bedrock_guardrail_version" in patch or "guardrailVersion" in patch
    if id_touched:
        gid = str(
            patch.get("bedrock_guardrail_id") or patch.get("guardrailIdentifier") or "",
        ).strip()
        if gid:
            out["bedrock_guardrail_id"] = gid[:512]
            if ver_touched:
                gv = str(
                    patch.get("bedrock_guardrail_version") or patch.get("guardrailVersion") or "",
                ).strip()
                out["bedrock_guardrail_version"] = gv[:64] if gv else None
            elif not out.get("bedrock_guardrail_version"):
                out["bedrock_guardrail_version"] = None
        else:
            out["bedrock_guardrail_id"] = None
            out["bedrock_guardrail_version"] = None
    elif ver_touched and out.get("bedrock_guardrail_id"):
        gv = str(
            patch.get("bedrock_guardrail_version") or patch.get("guardrailVersion") or "",
        ).strip()
        out["bedrock_guardrail_version"] = gv[:64] if gv else None
    return out


def _kb_json_to_put_item(tenant: str, merged: dict[str, Any]) -> dict[str, Any]:
    """Convert merged KB JSON (with id) into a DynamoDB item for put_item."""

    kb_id = str(merged["id"])
    body: dict[str, Any] = {
        "name": merged.get("name") or "kb",
        "embedding_model_id": merged.get("embedding_model_id") or "amazon.titan-embed-text-v1",
    }
    if "chunk_chars" in merged and merged["chunk_chars"] is not None:
        body["chunk_chars"] = int(merged["chunk_chars"])
    if "hybrid" in merged:
        body["hybrid"] = bool(merged["hybrid"])
    if "generation_model_id" in merged:
        gv = str(merged.get("generation_model_id") or "").strip()
        if gv:
            body["generation_model_id"] = gv
    if merged.get("bedrock_guardrail_id"):
        body["bedrock_guardrail_id"] = str(merged["bedrock_guardrail_id"])
        if merged.get("bedrock_guardrail_version"):
            body["bedrock_guardrail_version"] = str(merged["bedrock_guardrail_version"])
    return _kb_put_item_from_body(tenant=tenant, kb_id=kb_id, body=body)


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

    tenant_settings: dict[str, Any] | None = None
    if tenant != "unknown":
        tenant_settings = load_tenant_settings_item(
            table=table, tenant_id=tenant, ddb=ddb_client
        )
        quota_err = try_consume_request_quota(
            ddb=ddb_client,
            table=table,
            tenant_id=tenant,
            settings=tenant_settings,
        )
        if quota_err is not None:
            return _json_response(429, quota_err)

    if path == "/v1/tenants" and method == "GET":
        return _json_response(200, {"items": [{"id": tenant, "name": tenant}]})

    m_kb = re.fullmatch(r"/v1/kbs/([^/]+)", path)
    if path == "/v1/kbs" and method == "POST":
        ok, body, err = _parse_json_object(event.get("body"), endpoint="POST /v1/kbs")
        if not ok:
            return _json_response(400, err)
        v_errs = schema_validation_errors(KB_MUTATION_SCHEMA_URI, body)
        if v_errs:
            return _json_response(400, format_schema_error_response(v_errs))
        kb_id = str(uuid.uuid4())
        item = _kb_put_item_from_body(tenant=tenant, kb_id=kb_id, body=body)
        ddb_client.put_item(TableName=table, Item=item)
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
        return _json_response(200, _kb_item_to_json(it, kb_id))

    if m_kb and method == "PATCH":
        kb_id = m_kb.group(1)
        ok, body, err = _parse_json_object(event.get("body"), endpoint="PATCH /v1/kbs/{kbId}")
        if not ok:
            return _json_response(400, err)
        if not body:
            return _json_response(
                400,
                {"title": "Bad Request", "detail": "PATCH body must include at least one field"},
            )
        v_errs = schema_validation_errors(KB_MUTATION_SCHEMA_URI, body)
        if v_errs:
            return _json_response(400, format_schema_error_response(v_errs))
        g = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g:
            return _json_response(404, {"title": "Not found", "detail": "KB not found"})
        it = g["Item"]
        if it.get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Tenant mismatch"})
        cur = _kb_item_to_json(it, kb_id)
        merged = _kb_apply_patch(cur, body)
        item = _kb_json_to_put_item(tenant, merged)
        ddb_client.put_item(TableName=table, Item=item)
        return _json_response(200, merged)

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
        kb_item = g["Item"]
        default_chars = 1200
        cc_attr = kb_item.get("chunk_chars", {}).get("N")
        if cc_attr is not None:
            try:
                default_chars = int(float(cc_attr))
            except (TypeError, ValueError):
                default_chars = 1200
        payload = {
            "tenant": tenant,
            "kb_id": kb_id,
            "job_id": job_id,
            "s3_key": s3_key,
            "embedding_model_id": resolved_embed,
            "chunk_chars": int(body.get("chunk_chars", default_chars)),
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

    m_job_manifest = re.fullmatch(r"/v1/jobs/([^/]+)/manifest", path)
    if m_job_manifest and method == "GET":
        job_mid = m_job_manifest.group(1)
        kb_m = _job_kb_query_param(event)
        item_m, st_m, body_m = _resolve_ingest_job_item(
            table=table, tenant=tenant, job_id=job_mid, kb_q=kb_m
        )
        if st_m is not None:
            return _json_response(st_m, body_m or {})
        mk = str(item_m.get("manifest_key", {}).get("S") or "").strip()
        if not mk:
            return _json_response(
                404,
                {
                    "title": "Not found",
                    "detail": "Manifest not yet available for this job",
                },
            )
        ttl = max(60, min(900, int(os.environ.get("MANIFEST_PRESIGN_TTL_SECONDS", "300"))))
        manifest_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": raw_bucket, "Key": mk},
            ExpiresIn=ttl,
        )
        return _json_response(
            200,
            {
                "manifest_url": manifest_url,
                "expires_in": ttl,
                "manifest_key": mk,
            },
        )

    m_job = re.fullmatch(r"/v1/jobs/([^/]+)", path)
    if m_job and method == "GET":
        job_id = m_job.group(1)
        kb_q = _job_kb_query_param(event)
        itj, st_j, body_j = _resolve_ingest_job_item(
            table=table, tenant=tenant, job_id=job_id, kb_q=kb_q
        )
        if st_j is not None:
            return _json_response(st_j, body_j or {})
        return _json_response(200, job_item_to_api_body(job_id, itj))

    m_search = re.fullmatch(r"/v1/kbs/([^/]+)/search", path)
    if m_search and method == "POST":
        kb_id = m_search.group(1)
        parsed_ok, body, j_err = _parse_json_object(event.get("body"), endpoint="/search")
        if not parsed_ok:
            return _json_response(400, j_err)
        errs = schema_validation_errors(DENSE_SEARCH_BODY_SCHEMA_URI, body)
        if errs:
            return _json_response(400, format_schema_error_response(errs))
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
        parsed_ok, body, j_err = _parse_json_object(event.get("body"), endpoint="/query")
        if not parsed_ok:
            return _json_response(400, j_err)
        errs = schema_validation_errors(RAG_QUERY_SCHEMA_URI, body)
        if errs:
            return _json_response(400, format_schema_error_response(errs))
        question = str(body.get("question", "") or "").strip()
        g_kb = ddb_client.get_item(
            TableName=table,
            Key={"PK": {"S": f"TENANT#{tenant}"}, "SK": {"S": f"KB#{kb_id}"}},
        )
        if "Item" not in g_kb or g_kb["Item"].get("GSI1SK", {}).get("S") != f"TENANT#{tenant}":
            return _json_response(403, {"title": "Forbidden", "detail": "Invalid KB"})
        ts_guard = tenant_settings
        if tenant == "unknown":
            ts_guard = load_tenant_settings_item(
                table=table, tenant_id=tenant, ddb=ddb_client
            )
        guard_gid, guard_ver = resolve_guardrail_config(
            body=body,
            kb_item=g_kb.get("Item"),
            tenant_settings_item=ts_guard,
        )

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

        t_gen0 = time.perf_counter()
        try:
            text = generate_with_converse(
                br,
                model_id=generation_model_id,
                system_text=system_prompt,
                user_text=user_message,
                max_tokens=resolve_max_tokens(),
                temperature=resolve_temperature(),
                guardrail_id=guard_gid,
                guardrail_version=guard_ver or "DRAFT",
            )
        except Exception as exc:  # noqa: BLE001
            text = f"[bedrock-unavailable] {exc}"
        latency_ms = (time.perf_counter() - t_gen0) * 1000.0
        hit_ids = [str(c.get("id", "") or "") for c in citations if c.get("id")]

        ddb_client.put_item(
            TableName=table,
            Item=build_query_audit_item(
                tenant_id=tenant,
                kb_id=kb_id,
                question=question,
                answer_text=text,
                model_id=generation_model_id,
                latency_ms=latency_ms,
                hit_ids=hit_ids,
                prompt_sha256=prompt_sha256,
                audit_stub=audit_stub,
                guardrails_id=guard_gid,
                guardrails_version=guard_ver if guard_gid else None,
            ),
        )
        return _json_response(
            200,
            {
                "answer": text,
                "citations": citations,
                "kb_id": kb_id,
                "guardrails_applied": bool(guard_gid),
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
