"""Handler tests — JSON/schema validation for `/search` and `/query`."""

from __future__ import annotations

import json
import os
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import MagicMock

import boto3
import pytest

os.environ.setdefault("TABLE_NAME", "t")
os.environ.setdefault("RAW_BUCKET", "b")
os.environ.setdefault("ARTIFACTS_BUCKET", "a")
os.environ.setdefault("STATE_MACHINE_ARN", "")
os.environ.setdefault("TENANT_REQUESTS_PER_DAY", "0")

_spec = spec_from_file_location(
    "cp_handler_body_val",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
_mod = module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_mod)

_tenant = "tenant-val"
_kb = "kb-val"


def _kb_ok_item(tenant: str, kb: str) -> dict:
    return {
        "Item": {
            "PK": {"S": f"TENANT#{tenant}"},
            "SK": {"S": f"KB#{kb}"},
            "GSI1SK": {"S": f"TENANT#{tenant}"},
            "name": {"S": "kb"},
        }
    }


@pytest.fixture(autouse=True)
def _stub_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_MODE", "stub")
    monkeypatch.setenv(
        "RAG_STUB_DENSE_HITS_JSON",
        json.dumps({"hits": [], "total": 0}),
    )
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.delenv("RERANK_URL", raising=False)
    yield
    monkeypatch.delenv("RAG_STUB_DENSE_HITS_JSON", raising=False)


def _ddb_router_get_item(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    def _gi(**kwargs: object) -> dict:
        sk = kwargs["Key"]["SK"]["S"]  # type: ignore[index]
        if sk == "SETTINGS#tenant":
            return {}
        return _kb_ok_item(_tenant, _kb)

    m = MagicMock(side_effect=_gi)
    monkeypatch.setattr(_mod.ddb_client, "get_item", m)
    return m


@pytest.fixture(autouse=True)
def _generation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUERY_USE_CONVERSE_STREAM", raising=False)
    monkeypatch.setenv("GENERATION_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


def test_query_invalid_json_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _ddb_router_get_item(monkeypatch)

    ev = {
        "rawPath": f"/v1/kbs/{_kb}/query",
        "body": '{"question": ',
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": _tenant}}},
        },
    }
    out = _mod.handler(ev, None)
    assert out["statusCode"] == 400
    err = json.loads(out["body"])
    assert "/query" in err["detail"]


def test_query_schema_empty_question(monkeypatch: pytest.MonkeyPatch) -> None:
    _ddb_router_get_item(monkeypatch)
    mock_br = MagicMock()
    monkeypatch.setattr(boto3, "client", lambda name, **k: mock_br)

    ev = {
        "rawPath": f"/v1/kbs/{_kb}/query",
        "body": json.dumps({"question": "   "}),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": _tenant}}},
        },
    }
    out = _mod.handler(ev, None)
    assert out["statusCode"] == 400
    err = json.loads(out["body"])
    assert err.get("schema_errors")
    mock_br.converse.assert_not_called()


def test_search_schema_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _mod.ddb_client,
        "get_item",
        lambda **_: _kb_ok_item(_tenant, _kb),
    )

    ev = {
        "rawPath": f"/v1/kbs/{_kb}/search",
        "body": json.dumps({"k": "not-int"}),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": _tenant}}},
        },
    }
    out = _mod.handler(ev, None)
    assert out["statusCode"] == 400
    err = json.loads(out["body"])
    assert err.get("schema_errors")
