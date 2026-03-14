"""Integration-style tests for `/v1/kbs/{id}/query` retrieval + prompt assembly."""

from __future__ import annotations

import io
import json
import os
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import MagicMock

import boto3
import pytest
import rerank_hook

os.environ.setdefault("TABLE_NAME", "t")
os.environ.setdefault("RAW_BUCKET", "b")
os.environ.setdefault("ARTIFACTS_BUCKET", "a")
os.environ.setdefault("STATE_MACHINE_ARN", "")

_spec_h = spec_from_file_location(
    "cp_handler_query_rag",
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py"),
)
_mod = module_from_spec(_spec_h)
assert _spec_h.loader
_spec_h.loader.exec_module(_mod)


def _kb_ok(tenant: str, kb: str) -> dict:
    return {
        "Item": {
            "PK": {"S": f"TENANT#{tenant}"},
            "SK": {"S": f"KB#{kb}"},
            "GSI1SK": {"S": f"TENANT#{tenant}"},
            "name": {"S": "kb"},
        }
    }


@pytest.fixture(autouse=True)
def _reset_rerank_cache() -> None:
    rerank_hook._rerank_lambda_arn_cached = False  # type: ignore[attr-defined]
    yield
    rerank_hook._rerank_lambda_arn_cached = False  # type: ignore[attr-defined]


def test_query_stub_injected_hits_in_bedrock_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = "tenant-rag"
    kb = "kb-stub"
    monkeypatch.setenv("SEARCH_MODE", "stub")
    monkeypatch.setenv("CONTEXT_CHAR_BUDGET", "20000")
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.delenv("RERANK_URL", raising=False)

    monkeypatch.setenv(
        "RAG_STUB_DENSE_HITS_JSON",
        json.dumps(
            {
                "hits": [
                    {
                        "id": "chunk-alpha",
                        "score": 0.99,
                        "text": "Paris is France's capital.",
                        "metadata": {},
                    },
                    {
                        "id": "chunk-beta",
                        "score": 0.5,
                        "text": "Lyon is a city.",
                        "metadata": {},
                    },
                ],
                "total": 2,
            },
        ),
    )

    invokes: list[dict] = []

    mock_br = MagicMock()

    def _invoke(**kwargs: object) -> dict:
        invokes.append(kwargs)
        return {
            "body": io.BytesIO(
                json.dumps({"content": [{"type": "text", "text": "stub-answer"}]}).encode(),
            ),
        }

    mock_br.invoke_model.side_effect = _invoke

    def _client(service_name: str, **kw: object) -> object:
        if service_name == "bedrock-runtime":
            return mock_br
        # Control plane caches other boto clients on the handler module — not used here.
        return MagicMock()

    monkeypatch.setattr(boto3, "client", _client)

    monkeypatch.setattr(_mod.ddb_client, "put_item", MagicMock())
    monkeypatch.setattr(
        _mod.ddb_client,
        "get_item",
        lambda **kwargs: _kb_ok(tenant, kb),
    )

    ev = {
        "rawPath": f"/v1/kbs/{kb}/query",
        "body": json.dumps({"question": "Capital of France?", "context_k": 2}),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": tenant}}},
        },
    }
    out = _mod.handler(ev, None)
    assert len(invokes) == 1

    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["answer"] == "stub-answer"
    assert [c["id"] for c in body["citations"]] == ["chunk-alpha", "chunk-beta"]

    raw_body = invokes[0]["body"]
    if isinstance(raw_body, (bytes, bytearray)):
        payload_obj = json.loads(raw_body.decode())
    elif isinstance(raw_body, str):
        payload_obj = json.loads(raw_body)
    else:
        raise AssertionError(type(raw_body))
    prompt = payload_obj["messages"][0]["content"][0]["text"]
    assert "Context: (stub)" not in prompt
    assert "source_id:chunk-alpha" in prompt
    assert "Paris is France's capital." in prompt
    monkeypatch.delenv("RAG_STUB_DENSE_HITS_JSON", raising=False)
