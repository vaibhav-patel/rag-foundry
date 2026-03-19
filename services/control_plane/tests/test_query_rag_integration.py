"""Integration-style tests for `/v1/kbs/{id}/query` retrieval + prompt assembly."""

from __future__ import annotations

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
os.environ.setdefault("TENANT_REQUESTS_PER_DAY", "0")

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


@pytest.fixture(autouse=True)
def _generation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUERY_USE_CONVERSE_STREAM", raising=False)
    monkeypatch.setenv("GENERATION_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("MAX_TOKENS", "512")
    monkeypatch.setenv("TEMPERATURE", "0.1")
    monkeypatch.setenv("QUERY_AUDIT_EXTENSION_STUB", "pending-2026-03-16")


def test_query_stub_injected_hits_calls_converse_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    def _converse(**kwargs: object) -> dict:
        invokes.append(dict(kwargs))
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "stub-answer"}],
                },
            },
        }

    mock_br.converse.side_effect = _converse

    captured_put = MagicMock()

    def _client(service_name: str, **kw: object) -> object:
        if service_name == "bedrock-runtime":
            return mock_br
        return MagicMock()

    monkeypatch.setattr(boto3, "client", _client)

    monkeypatch.setattr(_mod.ddb_client, "put_item", captured_put)
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

    mock_br.invoke_model.assert_not_called()
    mock_br.converse_stream.assert_not_called()
    assert len(invokes) == 1
    assert invokes[0]["modelId"].startswith("anthropic.")
    msgs = invokes[0]["messages"]
    user_blob = msgs[0]["content"][0]["text"]
    assert "Paris is France's capital." in user_blob
    syss = invokes[0]["system"]
    assert "retrieved passages" in syss[0]["text"].lower()

    infer = invokes[0]["inferenceConfig"]
    assert infer["maxTokens"] == 512
    assert infer["temperature"] == pytest.approx(0.1)
    assert "guardrailConfig" not in invokes[0]

    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["answer"] == "stub-answer"
    assert [c["id"] for c in body["citations"]] == ["chunk-alpha", "chunk-beta"]

    audit_item = captured_put.call_args[1]["Item"]
    sk = audit_item["SK"]["S"]
    assert sk.startswith("QUERYAUDIT#")
    assert sk.count("#") >= 2
    assert audit_item["GSI2PK"]["S"] == f"TENANT#{tenant}#QUERYAUDIT"
    assert sk.removeprefix("QUERYAUDIT#") == audit_item["GSI2SK"]["S"]
    assert len(audit_item["question_sha256"]["S"]) == 64
    assert int(audit_item["answer_length"]["N"]) > 0
    assert audit_item["model_id"]["S"].startswith("anthropic.")
    assert int(audit_item["latency_ms"]["N"]) >= 0
    assert len(audit_item["hit_ids"]["L"]) == 2
    assert {e["S"] for e in audit_item["hit_ids"]["L"]} == {"chunk-alpha", "chunk-beta"}
    assert "prompt_sha256" in audit_item
    assert len(audit_item["prompt_sha256"]["S"]) == 64
    assert audit_item["audit_stub_next"]["S"] == "pending-2026-03-16"

    monkeypatch.delenv("RAG_STUB_DENSE_HITS_JSON", raising=False)


def test_query_body_guardrail_overrides_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = "tenant-gr"
    kb = "kb-gr"
    monkeypatch.setenv("SEARCH_MODE", "stub")
    monkeypatch.setenv(
        "RAG_STUB_DENSE_HITS_JSON",
        json.dumps({"hits": [], "total": 0}),
    )
    invokes: list[dict] = []

    def _gi(**kwargs: object) -> dict:
        sk = kwargs["Key"]["SK"]["S"]  # type: ignore[index]
        if sk == "SETTINGS#tenant":
            return {}
        return {
            "Item": {
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"KB#{kb}"},
                "GSI1SK": {"S": f"TENANT#{tenant}"},
                "bedrock_guardrail_id": {"S": "kb-guard"},
                "bedrock_guardrail_version": {"S": "1"},
            },
        }

    monkeypatch.setattr(_mod.ddb_client, "get_item", _gi)
    monkeypatch.setattr(_mod.ddb_client, "put_item", MagicMock())

    mock_br = MagicMock()

    def _converse(**kwargs: object) -> dict:
        invokes.append(dict(kwargs))
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "ok"}],
                },
            },
        }

    mock_br.converse.side_effect = _converse

    def _client(service_name: str, **kw: object) -> object:
        return mock_br if service_name == "bedrock-runtime" else MagicMock()

    monkeypatch.setattr(boto3, "client", _client)

    ev = {
        "rawPath": f"/v1/kbs/{kb}/query",
        "body": json.dumps(
            {
                "question": "hello",
                "guardrails_id": "body-guard",
                "guardrails_version": "2",
            },
        ),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": tenant}}},
        },
    }
    assert _mod.handler(ev, None)["statusCode"] == 200
    assert invokes[0]["guardrailConfig"]["guardrailIdentifier"] == "body-guard"
    assert invokes[0]["guardrailConfig"]["guardrailVersion"] == "2"
    monkeypatch.delenv("RAG_STUB_DENSE_HITS_JSON", raising=False)


def test_query_kb_guardrail_used_when_absent_from_body(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = "tenant-kb-gr"
    kb = "kb-kb-gr"
    monkeypatch.setenv("SEARCH_MODE", "stub")
    monkeypatch.delenv("BEDROCK_GUARDRAILS_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAILS_VERSION", raising=False)
    monkeypatch.setenv(
        "RAG_STUB_DENSE_HITS_JSON",
        json.dumps({"hits": [], "total": 0}),
    )
    invokes: list[dict] = []

    def _gi(**kwargs: object) -> dict:
        sk = kwargs["Key"]["SK"]["S"]  # type: ignore[index]
        if sk == "SETTINGS#tenant":
            return {}
        return {
            "Item": {
                "PK": {"S": f"TENANT#{tenant}"},
                "SK": {"S": f"KB#{kb}"},
                "GSI1SK": {"S": f"TENANT#{tenant}"},
                "bedrock_guardrail_id": {"S": "kb-only"},
                "bedrock_guardrail_version": {"S": ""},
            },
        }

    monkeypatch.setattr(_mod.ddb_client, "get_item", _gi)
    monkeypatch.setattr(_mod.ddb_client, "put_item", MagicMock())

    mock_br = MagicMock()

    mock_br.converse.side_effect = lambda **kw: invokes.append(dict(kw)) or {
        "output": {"message": {"role": "assistant", "content": [{"text": "x"}]}},
    }

    def _boto(name: str, **k: object) -> object:
        return mock_br if name == "bedrock-runtime" else MagicMock()

    monkeypatch.setattr(boto3, "client", _boto)

    ev = {
        "rawPath": f"/v1/kbs/{kb}/query",
        "body": json.dumps({"question": "hi"}),
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": tenant}}},
        },
    }
    assert _mod.handler(ev, None)["statusCode"] == 200
    assert invokes[0]["guardrailConfig"]["guardrailIdentifier"] == "kb-only"
    assert invokes[0]["guardrailConfig"]["guardrailVersion"] == "DRAFT"
    monkeypatch.delenv("RAG_STUB_DENSE_HITS_JSON", raising=False)
