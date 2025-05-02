"""Tenant isolation: KB GET must not leak across tenants."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TABLE_NAME", "t")
os.environ.setdefault("RAW_BUCKET", "b")
os.environ.setdefault("ARTIFACTS_BUCKET", "a")
os.environ.setdefault("STATE_MACHINE_ARN", "")

from importlib.util import module_from_spec, spec_from_file_location

spec = spec_from_file_location(
    "cp_handler",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
mod = module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


def _evt(path: str, tenant_sub: str):
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"jwt": {"claims": {"sub": tenant_sub}}},
        },
    }


def test_kb_get_wrong_tenant_returns_403(monkeypatch):
    """Item exists for tenant-a but caller is tenant-b via different GSI1SK."""

    def fake_get_item(**kwargs):
        assert kwargs["TableName"] == "t"
        return {
            "Item": {
                "PK": {"S": "TENANT#tenant-a"},
                "SK": {"S": "KB#kb1"},
                "GSI1SK": {"S": "TENANT#tenant-a"},
                "name": {"S": "secret"},
            }
        }

    monkeypatch.setattr(mod.ddb_client, "get_item", fake_get_item)
    out = mod.handler(_evt("/v1/kbs/kb1", "tenant-b"), None)
    assert out["statusCode"] == 403


def test_search_rejects_foreign_kb(monkeypatch):
    monkeypatch.setattr(
        mod.ddb_client,
        "get_item",
        lambda **kw: {
            "Item": {
                "PK": {"S": "TENANT#a"},
                "SK": {"S": "KB#x"},
                "GSI1SK": {"S": "TENANT#a"},
            }
        },
    )
    ev = {
        "rawPath": "/v1/kbs/x/search",
        "body": json.dumps({"q": "hi"}),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": "b"}}},
        },
    }
    out = mod.handler(ev, None)
    assert out["statusCode"] == 403
