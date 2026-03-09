"""job_status helpers + GSI key shape (deterministic assertions for DDB lookups)."""

from __future__ import annotations

from job_status import (
    JOB_GSI1_PARTITION_PK,
    gsi_sort_key_for_tenant_job,
    job_item_to_api_body,
    normalize_job_status_for_read,
)


def test_gsi_exact_query_shape() -> None:
    tenant = "user|sub-a"
    job_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    pk = JOB_GSI1_PARTITION_PK
    sk = gsi_sort_key_for_tenant_job(tenant=tenant, job_id=job_id)
    assert pk == "JOB#RUNNING"
    assert sk == f"TENANT#{tenant}#{job_id}"
    assert sk.startswith("TENANT#")
    assert sk.endswith(job_id)


def test_normalize_job_status_reads_uppercase_legacy() -> None:
    assert normalize_job_status_for_read("succeeded") == "SUCCEEDED"
    assert normalize_job_status_for_read("QUEUED") == "QUEUED"
    assert normalize_job_status_for_read(None) == "UNKNOWN"


def test_job_item_to_api_body_parses_errors() -> None:
    jid = "j1"
    item = {
        "status": {"S": "PARTIAL"},
        "kb_id": {"S": "kb1"},
        "manifest_key": {"S": "m1"},
        "bulk_indexed": {"N": "5"},
        "bulk_failed": {"N": "1"},
        "ingest_errors": {"S": '["deadbeef"]'},
    }
    body = job_item_to_api_body(jid, item)
    assert body["id"] == "j1"
    assert body["status"] == "PARTIAL"
    assert body["bulk_indexed"] == 5
    assert body["errors"] == ["deadbeef"]
