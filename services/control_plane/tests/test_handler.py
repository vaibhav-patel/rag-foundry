"""Lightweight routing tests without full API Gateway envelope."""

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


def test_health():
    out = mod.handler(
        {"rawPath": "/v1/health", "requestContext": {"http": {"method": "GET"}}}, None
    )
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["status"] == "ok"


def test_not_found():
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
