"""POST/PATCH /v1/kbs JSON Schema validation and PATCH merge."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TABLE_NAME", "t")
os.environ.setdefault("RAW_BUCKET", "b")
os.environ.setdefault("ARTIFACTS_BUCKET", "a")
os.environ.setdefault("STATE_MACHINE_ARN", "")
os.environ.setdefault("TENANT_REQUESTS_PER_DAY", "0")

from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import MagicMock

import pytest

spec = spec_from_file_location(
    "cp_handler_kb",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
mod = module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


@pytest.fixture(autouse=True)
def _stub_tenant_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "load_tenant_settings_item", MagicMock(return_value=None))


def _evt(path: str, method: str, body: dict | None, tenant: str = "acme") -> dict:
    return {
        "rawPath": path,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"custom:tenant_id": tenant}}},
        },
    }


def test_post_kb_rejects_unknown_field(monkeypatch: pytest.MonkeyPatch) -> None:
    put = MagicMock()
    monkeypatch.setattr(mod.ddb_client, "put_item", put)
    out = mod.handler(_evt("/v1/kbs", "POST", {"name": "n", "oops": 1}), None)
    assert out["statusCode"] == 400
    body = json.loads(out["body"])
    assert body["title"] == "Bad Request"
    put.assert_not_called()


def test_post_kb_rejects_chunk_chars_too_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.ddb_client, "put_item", MagicMock())
    out = mod.handler(_evt("/v1/kbs", "POST", {"chunk_chars": 10}), None)
    assert out["statusCode"] == 400


def test_patch_kb_rejects_empty_body(monkeypatch: pytest.MonkeyPatch) -> None:
    out = mod.handler(_evt("/v1/kbs/kb-1", "PATCH", {}), None)
    assert out["statusCode"] == 400


def test_patch_kb_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = {
        "PK": {"S": "TENANT#acme"},
        "SK": {"S": "KB#kb-1"},
        "GSI1PK": {"S": "KB#kb-1"},
        "GSI1SK": {"S": "TENANT#acme"},
        "name": {"S": "old"},
        "embedding_model_id": {"S": "amazon.titan-embed-text-v1"},
    }
    monkeypatch.setattr(mod.ddb_client, "get_item", MagicMock(return_value={"Item": existing}))
    put = MagicMock()
    monkeypatch.setattr(mod.ddb_client, "put_item", put)
    out = mod.handler(
        _evt("/v1/kbs/kb-1", "PATCH", {"name": "new", "generation_model_id": "m1"}),
        None,
    )
    assert out["statusCode"] == 200
    put.assert_called_once()
    written = put.call_args.kwargs["Item"]
    assert written["name"]["S"] == "new"
    assert written["generation_model_id"]["S"] == "m1"
