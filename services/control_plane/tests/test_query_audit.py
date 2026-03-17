"""Unit tests for query audit DynamoDB item builder."""

from __future__ import annotations

import re
import time

import pytest
from query_audit import build_query_audit_item, question_sha256


def test_question_sha256_stable() -> None:
    assert len(question_sha256("hello")) == 64
    assert question_sha256("hello") != question_sha256("hallo")


def test_build_query_audit_item_shape() -> None:
    item = build_query_audit_item(
        tenant_id="t1",
        kb_id="kb1",
        question="What?",
        answer_text="Because.",
        model_id="anthropic.claude-v1",
        latency_ms=12.3,
        hit_ids=["a", "b"],
        prompt_sha256="f" * 64,
        audit_stub="stub",
        guardrails_id="g1",
        guardrails_version="DRAFT",
    )
    sk = item["SK"]["S"]
    assert sk.startswith("QUERYAUDIT#")
    assert re.match(
        r"^QUERYAUDIT#\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z#[0-9a-f-]{36}$",
        sk,
    )
    assert item["PK"]["S"] == "TENANT#t1"
    assert item["GSI2PK"]["S"] == "TENANT#t1#QUERYAUDIT"
    assert sk.removeprefix("QUERYAUDIT#") == item["GSI2SK"]["S"]
    assert item["question_sha256"]["S"] == question_sha256("What?")
    assert item["answer_length"]["N"] == "8"
    assert item["model_id"]["S"] == "anthropic.claude-v1"
    assert item["latency_ms"]["N"] == "12"
    assert [x["S"] for x in item["hit_ids"]["L"]] == ["a", "b"]
    assert "expires_at" not in item


def test_build_query_audit_item_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUERY_AUDIT_TTL_DAYS", "30")
    item = build_query_audit_item(
        tenant_id="t1",
        kb_id="kb1",
        question="q",
        answer_text="a",
        model_id="m",
        latency_ms=0.0,
        hit_ids=[],
        prompt_sha256="0" * 64,
        audit_stub="s",
        guardrails_id=None,
        guardrails_version=None,
    )
    assert "expires_at" in item
    assert int(item["expires_at"]["N"]) > int(time.time())
    monkeypatch.delenv("QUERY_AUDIT_TTL_DAYS", raising=False)
