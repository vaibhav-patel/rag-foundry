"""Handler: GET /v1/jobs/{id}?kb_id= uses get_item (contract with DDB access pattern)."""

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
    "cp_handler_job_get",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
_mod = module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_mod)


def _auth_event(
    *,
    path: str,
    method: str,
    sub: str,
    query: dict[str, str] | None = None,
) -> dict:
    return {
        "rawPath": path,
        "queryStringParameters": query,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
    }


@pytest.fixture()
def mock_ddb(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    ddb = MagicMock()
    monkeypatch.setattr(_mod, "ddb_client", ddb)
    return ddb


def test_get_job_prefers_get_item_when_kb_id_query_param(
    mock_ddb: MagicMock,
) -> None:
    job_item = {
        "Item": {
            "tenant": {"S": "tenant-1"},
            "kb_id": {"S": "kb-99"},
            "status": {"S": "RUNNING"},
            "embedding_model_id": {"S": "stub"},
        }
    }

    def _gi(**kwargs: object) -> dict:
        sk = kwargs["Key"]["SK"]["S"]  # type: ignore[index]
        if sk == "SETTINGS#tenant":
            return {}
        return job_item

    mock_ddb.get_item.side_effect = _gi

    out = _mod.handler(
        _auth_event(
            path="/v1/jobs/j1",
            method="GET",
            sub="tenant-1",
            query={"kb_id": "kb-99"},
        ),
        None,
    )
    assert out["statusCode"] == 200
    assert mock_ddb.get_item.call_count == 2
    mock_ddb.query.assert_not_called()

    body = json.loads(out["body"])
    from job_status import JOB_POLL_BODY_KEYS

    assert set(body) == JOB_POLL_BODY_KEYS
    assert body["id"] == "j1"


def test_get_job_falls_back_to_gsi_without_kb_id(mock_ddb: MagicMock) -> None:
    picked = {
        "SK": {"S": "JOB#j2"},
        "tenant": {"S": "tenant-1"},
        "kb_id": {"S": "kb-1"},
        "status": {"S": "QUEUED"},
        "embedding_model_id": {"S": "amazon.titan-embed-text-v1"},
        "bulk_indexed": {"N": "0"},
        "bulk_failed": {"N": "0"},
    }

    def _gi(**kwargs: object) -> dict:
        sk = kwargs["Key"]["SK"]["S"]  # type: ignore[index]
        if sk == "SETTINGS#tenant":
            return {}
        return {}

    mock_ddb.get_item.side_effect = _gi
    mock_ddb.query.return_value = {"Items": [picked]}

    out = _mod.handler(
        _auth_event(path="/v1/jobs/j2", method="GET", sub="tenant-1", query=None),
        None,
    )
    assert out["statusCode"] == 200
    assert mock_ddb.get_item.call_count == 1
    mock_ddb.query.assert_called()
    body = json.loads(out["body"])
    assert body["id"] == "j2"
