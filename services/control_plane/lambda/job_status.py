"""Canonical DynamoDB ingest job statuses and GSI1 access helpers."""

from __future__ import annotations

import json
from typing import Any

# Persisted job lifecycle (KB# partition, JOB# sort key + GSI1).
JOB_STATUS_QUEUE = "QUEUED"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_SUCCEEDED = "SUCCEEDED"
JOB_STATUS_PARTIAL = "PARTIAL"
JOB_STATUS_FAILED = "FAILED"

JOB_STATUSES_CANONICAL: frozenset[str] = frozenset(
    {
        JOB_STATUS_QUEUE,
        JOB_STATUS_RUNNING,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_PARTIAL,
        JOB_STATUS_FAILED,
    },
)

# GSI partition name is historical (“RUNNING”) but kept for backwards compatibility —
# stores all ingest jobs regardless of semantic status unless we migrate data.
JOB_GSI1_PARTITION_PK = "JOB#RUNNING"


def gsi_sort_key_for_tenant_job(*, tenant: str, job_id: str) -> str:
    """GSI1SK value written at job creation (`TENANT#{tenant}#{job_id}`)."""

    return f"TENANT#{tenant}#{job_id}"


def normalize_job_status_for_read(raw: str | None) -> str:
    """Return canonical uppercase status; unknown legacy values pass through unchanged."""

    if raw is None or not str(raw).strip():
        return "UNKNOWN"
    s = str(raw).strip().upper()
    return s


def job_item_to_api_body(job_id: str, item: dict[str, Any]) -> dict[str, Any]:
    """Shape stored job item into GET /jobs response."""

    raw_st = item.get("status", {}).get("S")
    st = normalize_job_status_for_read(raw_st)

    body: dict[str, Any] = {
        "id": job_id,
        "status": st,
        "kb_id": item.get("kb_id", {}).get("S"),
        "manifest_key": item.get("manifest_key", {}).get("S"),
        "bulk_indexed": int(item.get("bulk_indexed", {}).get("N", "0")),
        "bulk_failed": int(item.get("bulk_failed", {}).get("N", "0")),
        "errors": [],
    }
    err_raw = item.get("ingest_errors", {}).get("S")
    if err_raw:
        try:
            body["errors"] = json.loads(err_raw)
        except json.JSONDecodeError:
            body["errors"] = []
    return body
