"""Worker invoked from Step Functions: validate/extract text from S3 when keys present."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
s3 = boto3.client("s3", region_name=_region)


def _extract_text(bucket: str, key: str, max_bytes: int = 512_000) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read(max_bytes)
    if key.lower().endswith(".json"):
        return json.dumps(json.loads(body.decode("utf-8", errors="replace")), indent=2)[:8000]
    return body.decode("utf-8", errors="replace")[:8000]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    bucket = os.environ.get("RAW_BUCKET", "")
    key = ""
    if isinstance(event, dict):
        key = str(event.get("s3_key") or event.get("key") or "")

    text = ""
    err = None
    if bucket and key:
        try:
            text = _extract_text(bucket, key)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)

    return {
        "ok": err is None,
        "stage": "extract",
        "bytes": len(text.encode("utf-8")) if text else 0,
        "preview": text[:500],
        "error": err,
        "opensearch_collection": os.environ.get("OPENSEARCH_COLLECTION_NAME", ""),
    }
