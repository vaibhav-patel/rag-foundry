"""Lightweight routing tests without full API Gateway envelope."""

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
from botocore.exceptions import ClientError

spec = spec_from_file_location(
    "cp_handler",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
mod = module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


def test_health():
    out = mod.handler(
        {"rawPath": "/v1/health", "requestContext": {"http": {"method": "GET"}}}, None
    )
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["status"] == "ok"


def test_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.ddb_client, "get_item", MagicMock(return_value={}))
    out = mod.handler(
        {
            "rawPath": "/v1/unknown",
            "requestContext": {
                "http": {"method": "GET"},
                "authorizer": {"jwt": {"claims": {"sub": "u1"}}},
            },
        },
        None,
    )
    assert out["statusCode"] == 404


def test_quota_returns_429_before_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "2")
    monkeypatch.setattr(mod.ddb_client, "get_item", MagicMock(return_value={}))
    monkeypatch.setattr(
        mod.ddb_client,
        "update_item",
        MagicMock(
            side_effect=ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "c"}},
                "UpdateItem",
            ),
        ),
    )
    out = mod.handler(
        {
            "rawPath": "/v1/kbs",
            "requestContext": {
                "http": {"method": "GET"},
                "authorizer": {"jwt": {"claims": {"custom:tenant_id": "acme"}}},
            },
        },
        None,
    )
    assert out["statusCode"] == 429
    body = json.loads(out["body"])
    assert body["title"] == "Too Many Requests"
    assert body["limit"] == 2
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "0")
