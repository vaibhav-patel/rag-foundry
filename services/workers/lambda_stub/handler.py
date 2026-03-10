"""Ingest worker: S3 extract, chunk, embed, manifest, job status (Bedrock or stub)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import boto3

import chunking
from bulk_index_chunks import run_chunk_bulk_index
from chunk_bulk_document import ChunkBulkDocument
from ensure_chunk_index import ensure_chunk_index
from opensearch_client import create_opensearch_client

_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
s3 = boto3.client("s3", region_name=_region)
ddb = boto3.client("dynamodb", region_name=_region)


def _set_job_status_runtime(*, table: str, kb_id: str, job_id: str, status: str) -> None:
    if not (table and kb_id and job_id):
        return
    ddb.update_item(
        TableName=table,
        Key={"PK": {"S": f"KB#{kb_id}"}, "SK": {"S": f"JOB#{job_id}"}},
        UpdateExpression="SET #s = :st",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":st": {"S": status}},
    )


def _extract_text(bucket: str, key: str, max_bytes: int = 512_000) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read(max_bytes)
    if key.lower().endswith(".json"):
        return json.dumps(json.loads(body.decode("utf-8", errors="replace")), indent=2)[:8000]
    return body.decode("utf-8", errors="replace")[:8000]


def _embed_stub(text: str, dim: int = 64) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    vec: list[float] = []
    for i in range(dim):
        vec.append((((h[i % len(h)] + i) % 255) / 255.0 - 0.5) * 0.02)
    return vec


def _embed_bedrock(text: str, model_id: str) -> list[float] | None:
    try:
        br = boto3.client("bedrock-runtime", region_name=_region)
        body = json.dumps({"inputText": text[:8000]})
        resp = br.invoke_model(
            modelId=model_id,
            body=body.encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        out = json.loads(resp["body"].read().decode("utf-8"))
        emb = out.get("embedding")
        if isinstance(emb, list):
            return [float(x) for x in emb]
    except Exception:
        return None
    return None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    bucket = os.environ.get("RAW_BUCKET", "")
    table = os.environ.get("TABLE_NAME", "")
    tenant = str(event.get("tenant", ""))
    kb_id = str(event.get("kb_id", ""))
    job_id = str(event.get("job_id", ""))
    key = str(event.get("s3_key", ""))
    embed_model = str(event.get("embedding_model_id", "stub"))

    if not key or not bucket:
        return {"ok": False, "error": "missing s3_key or RAW_BUCKET"}

    ensure_chunk_index(create_opensearch_client())
    _set_job_status_runtime(table=table, kb_id=kb_id, job_id=job_id, status="RUNNING")

    text = _extract_text(bucket, key)
    chunks = chunking.recursive_char_chunks(text, max_chars=int(event.get("chunk_chars", 1200)))
    bulk_docs: list[ChunkBulkDocument] = []
    for i, ch in enumerate(chunks[:200]):
        v: list[float] | None = None
        if embed_model.startswith("amazon.titan-embed"):
            v = _embed_bedrock(ch, embed_model)
        vec = v if v is not None else _embed_stub(ch)
        bulk_docs.append(
            ChunkBulkDocument(
                tenant=tenant,
                kb_id=kb_id,
                job_id=job_id,
                chunk_idx=i,
                s3_key=key,
                chunk_text=ch,
                embedding=vec,
                metadata=None,
            )
        )

    manifest: dict[str, Any] = {
        "tenant": tenant,
        "kb_id": kb_id,
        "job_id": job_id,
        "source_key": key,
        "chunk_count": len(chunks),
        "embedding_model": embed_model,
        "chunks_preview": [c[:200] for c in chunks[:5]],
        "first_chunk_document_id": bulk_docs[0].document_id() if bulk_docs else None,
        "bulk_schema": "chunk-v1",
        "errors": [],
    }
    out_key = f"derived/{tenant}/{kb_id}/{job_id}/manifest.json"
    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    index_name = os.environ.get("OPENSEARCH_INDEX_NAME", "rag-foundry-chunks")
    try:
        batch_size = int(os.environ.get("BULK_BATCH_SIZE", "50"))
    except ValueError:
        batch_size = 50
    os_client = create_opensearch_client()
    bulk_out = run_chunk_bulk_index(
        os_client,
        index_name=index_name,
        bulk_docs=bulk_docs,
        batch_size=batch_size,
    )
    err_ids = bulk_out.failed_ids[:500]
    manifest["errors"] = err_ids
    manifest["bulk_indexed"] = bulk_out.indexed_ok
    manifest["bulk_failed"] = len(bulk_out.failed_ids)
    manifest["opensearch_bulk_skipped"] = bulk_out.skipped
    if bulk_out.transport_error:
        manifest["bulk_transport_error"] = bulk_out.transport_error[:2000]

    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    n_docs = len(bulk_docs)
    if bulk_out.skipped or n_docs == 0:
        job_status = "SUCCEEDED"
    elif bulk_out.transport_error and bulk_out.indexed_ok == 0:
        job_status = "FAILED"
    elif bulk_out.transport_error and bulk_out.indexed_ok > 0:
        job_status = "PARTIAL"
    elif bulk_out.indexed_ok == n_docs and not err_ids:
        job_status = "SUCCEEDED"
    elif bulk_out.indexed_ok > 0:
        job_status = "PARTIAL"
    else:
        job_status = "FAILED"

    if table and kb_id and job_id:
        ingest_errors = json.dumps(err_ids[:2000])
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": f"KB#{kb_id}"}, "SK": {"S": f"JOB#{job_id}"}},
            UpdateExpression=(
                "SET #s = :st, manifest_key = :mk, bulk_indexed = :bi, "
                "bulk_failed = :bf, ingest_errors = :ie, chunk_count = :cc"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":st": {"S": job_status},
                ":mk": {"S": out_key},
                ":bi": {"N": str(bulk_out.indexed_ok)},
                ":bf": {"N": str(len(bulk_out.failed_ids))},
                ":ie": {"S": ingest_errors[:350_000]},
                ":cc": {"N": str(len(chunks))},
            },
        )

    out: dict[str, Any] = {
        "ok": job_status != "FAILED",
        "stage": "ingest",
        "job_status": job_status,
        "chunk_count": len(chunks),
        "manifest_key": out_key,
        "bulk_indexed": bulk_out.indexed_ok,
        "bulk_failed": len(bulk_out.failed_ids),
        "errors": err_ids,
    }
    if bulk_out.transport_error:
        out["bulk_transport_error"] = bulk_out.transport_error[:500]
    return out
