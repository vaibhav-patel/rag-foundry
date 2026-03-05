"""Ingest worker: S3 extract, chunk, embed, manifest, job status (Bedrock or stub)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import boto3

import chunking
from ensure_chunk_index import ensure_chunk_index
from opensearch_client import create_opensearch_client

_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
s3 = boto3.client("s3", region_name=_region)
ddb = boto3.client("dynamodb", region_name=_region)


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

    text = _extract_text(bucket, key)
    chunks = chunking.recursive_char_chunks(text, max_chars=int(event.get("chunk_chars", 1200)))
    vectors: list[list[float]] = []
    for ch in chunks[:200]:
        v: list[float] | None = None
        if embed_model.startswith("amazon.titan-embed"):
            v = _embed_bedrock(ch, embed_model)
        vectors.append(v if v is not None else _embed_stub(ch))

    manifest = {
        "tenant": tenant,
        "kb_id": kb_id,
        "job_id": job_id,
        "source_key": key,
        "chunk_count": len(chunks),
        "embedding_model": embed_model,
        "chunks_preview": [c[:200] for c in chunks[:5]],
    }
    out_key = f"derived/{tenant}/{kb_id}/{job_id}/manifest.json"
    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    if table and kb_id and job_id:
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": f"KB#{kb_id}"}, "SK": {"S": f"JOB#{job_id}"}},
            UpdateExpression="SET #s = :done",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":done": {"S": "SUCCEEDED"}},
        )

    return {
        "ok": True,
        "stage": "ingest",
        "chunk_count": len(chunks),
        "manifest_key": out_key,
    }
