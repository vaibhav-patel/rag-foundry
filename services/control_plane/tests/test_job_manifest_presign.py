"""GET /v1/jobs/{id}/manifest presigns manifest_key in RAW_BUCKET."""

from __future__ import annotations

import json
import os
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("TABLE_NAME", "t")
os.environ.setdefault("RAW_BUCKET", "b")
os.environ.setdefault("ARTIFACTS_BUCKET", "a")
os.environ.setdefault("STATE_MACHINE_ARN", "")
os.environ.setdefault("TENANT_REQUESTS_PER_DAY", "0")

_spec = spec_from_file_location(
    "cp_manifest",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
_mod = module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_mod)


def _evt(*, job_id: str, sub: str, kb_id: str | None = None) -> dict:
    q = {"kb_id": kb_id} if kb_id else None
    return {
        "rawPath": f"/v1/jobs/{job_id}/manifest",
        "queryStringParameters": q,
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
    }


@pytest.fixture(autouse=True)
def stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_mod, "load_tenant_settings_item", MagicMock(return_value=None))


def test_manifest_404_when_no_manifest_key(monkeypatch: pytest.MonkeyPatch) -> None:
    item = {
        "tenant": {"S": "t1"},
        "kb_id": {"S": "kb1"},
        "status": {"S": "RUNNING"},
        "embedding_model_id": {"S": "m"},
        "bulk_indexed": {"N": "0"},
        "bulk_failed": {"N": "0"},
    }
    monkeypatch.setattr(_mod.ddb_client, "get_item", MagicMock(return_value={"Item": item}))
    out = _mod.handler(_evt(job_id="j1", sub="t1", kb_id="kb1"), None)
    assert out["statusCode"] == 404
    body = json.loads(out["body"])
    assert "Manifest not yet available" in body["detail"]


def test_manifest_presign(monkeypatch: pytest.MonkeyPatch) -> None:
    mk = "derived/t1/kb1/j1/manifest.json"
    item = {
        "tenant": {"S": "t1"},
        "kb_id": {"S": "kb1"},
        "status": {"S": "PARTIAL"},
        "manifest_key": {"S": mk},
        "embedding_model_id": {"S": "m"},
        "bulk_indexed": {"N": "1"},
        "bulk_failed": {"N": "1"},
        "ingest_errors": {"S": "[]"},
    }
    monkeypatch.setattr(_mod.ddb_client, "get_item", MagicMock(return_value={"Item": item}))
    monkeypatch.setattr(
        _mod.s3_client,
        "generate_presigned_url",
        MagicMock(return_value="https://s3.example/presigned"),
    )
    out = _mod.handler(_evt(job_id="j1", sub="t1", kb_id="kb1"), None)
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["manifest_url"] == "https://s3.example/presigned"
    assert body["manifest_key"] == mk
    assert body["expires_in"] >= 60
    _mod.s3_client.generate_presigned_url.assert_called_once()
    call_kw = _mod.s3_client.generate_presigned_url.call_args.kwargs
    assert call_kw["ClientMethod"] == "get_object"
    assert call_kw["Params"]["Bucket"] == "b"
    assert call_kw["Params"]["Key"] == mk
