"""API Gateway HTTP API v2 handler for rag-foundry control plane (Python 3.12, boto3 in runtime)."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import boto3

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
                "embedding_model_id": {"S": body.get("embedding_model_id", "amazon.titan-embed-text-v1")},
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
                items.append({"id": sk.removeprefix("KB#"), "name": it.get("name", {}).get("S", "")})
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
            return _json_response(501, {"title": "Not configured", "detail": "STATE_MACHINE_ARN missing"})
        job_id = str(uuid.uuid4())
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"KB#{kb_id}"},
                "SK": {"S": f"JOB#{job_id}"},
                "GSI1PK": {"S": "JOB#RUNNING"},
                "GSI1SK": {"S": f"TENANT#{tenant}#{job_id}"},
                "tenant": {"S": tenant},
                "status": {"S": "QUEUED"},
            },
        )
        sfn_client.start_execution(
            stateMachineArn=sm_arn,
            name=job_id[:80],
            input=json.dumps({"tenant": tenant, "kb_id": kb_id, "job_id": job_id}),
        )
        return _json_response(202, {"id": job_id, "status": "QUEUED"})

    m_job = re.fullmatch(r"/v1/jobs/([^/]+)", path)
    if m_job and method == "GET":
        job_id = m_job.group(1)
        q = ddb_client.query(
            TableName=table,
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :sk)",
            ExpressionAttributeValues={
                ":pk": {"S": "JOB#RUNNING"},
                ":sk": {"S": f"TENANT#{tenant}#"},
            },
        )
        for it in q.get("Items", []):
            if it["SK"]["S"] == f"JOB#{job_id}" and it.get("tenant", {}).get("S") == tenant:
                return _json_response(
                    200,
                    {"id": job_id, "status": it.get("status", {}).get("S", "UNKNOWN")},
                )
        return _json_response(404, {"title": "Not found", "detail": "Job not found"})

    m_query = re.fullmatch(r"/v1/kbs/([^/]+)/query", path)
    if m_query and method == "POST":
        kb_id = m_query.group(1)
        body = json.loads(event.get("body") or "{}")
        question = body.get("question", "")
        br = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION"))
        model_id = body.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0")
        try:
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": f"Context: (stub). Question: {question}"}],
                    }
                ],
            }
            resp = br.invoke_model(
                modelId=model_id,
                body=json.dumps(payload).encode("utf-8"),
                contentType="application/json",
                accept="application/json",
            )
            out = json.loads(resp["body"].read().decode("utf-8"))
            text = ""
            for block in out.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
        except Exception as exc:  # noqa: BLE001
            text = f"[bedrock-unavailable] {exc}"
        ddb_client.put_item(
            TableName=table,
            Item={
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"AUDIT#QUERY#{uuid.uuid4()}"},
                "kb_id": {"S": kb_id},
                "question": {"S": question[:2000]},
            },
        )
        return _json_response(200, {"answer": text, "citations": [], "kb_id": kb_id})

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

