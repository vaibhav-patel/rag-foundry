"""Unit tests for ``guardrails_resolve`` precedence."""

from __future__ import annotations

import pytest
from guardrails_resolve import resolve_guardrail_config


def kb_item_with_guard(gid: str, ver: str) -> dict:
    return {
        "PK": {"S": "TENANT#t"},
        "SK": {"S": "KB#k"},
        "bedrock_guardrail_id": {"S": gid},
        "bedrock_guardrail_version": {"S": ver},
    }


def tenant_settings_with_guard(gid: str, ver: str) -> dict:
    return {
        "PK": {"S": "TENANT#t"},
        "SK": {"S": "SETTINGS#tenant"},
        "bedrock_guardrail_id": {"S": gid},
        "bedrock_guardrail_version": {"S": ver},
    }


def test_body_fields_win_over_kb_tenant_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_GUARDRAILS_ID", "env-id")
    monkeypatch.setenv("BEDROCK_GUARDRAILS_VERSION", "env-ver")
    body = {"guardrails_id": "req-id", "guardrails_version": "req-ver"}
    gid, ver = resolve_guardrail_config(
        body=body,
        kb_item=kb_item_with_guard("kb-id", "kb-ver"),
        tenant_settings_item=tenant_settings_with_guard("ts-id", "ts-ver"),
    )
    assert gid == "req-id"
    assert ver == "req-ver"


def test_body_guardrail_identifier_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_GUARDRAILS_ID", raising=False)
    body = {"guardrailIdentifier": "alias-id", "guardrailVersion": "v9"}
    gid, ver = resolve_guardrail_config(body=body, kb_item=None, tenant_settings_item=None)
    assert gid == "alias-id"
    assert ver == "v9"


def test_kb_then_tenant_then_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_GUARDRAILS_ID", "env-id")
    monkeypatch.setenv("BEDROCK_GUARDRAILS_VERSION", "env-v")
    gid, ver = resolve_guardrail_config(
        body={},
        kb_item=kb_item_with_guard("kb-id", ""),
        tenant_settings_item=tenant_settings_with_guard("ts-id", "ts-v"),
    )
    assert gid == "kb-id"
    assert ver == "DRAFT"

    gid2, ver2 = resolve_guardrail_config(
        body={},
        kb_item=None,
        tenant_settings_item=tenant_settings_with_guard("ts-only", ""),
    )
    assert gid2 == "ts-only"
    assert ver2 == "DRAFT"

    gid3, ver3 = resolve_guardrail_config(body={}, kb_item=None, tenant_settings_item=None)
    assert gid3 == "env-id"
    assert ver3 == "env-v"


def test_no_guardrail_but_orphan_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_GUARDRAILS_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAILS_VERSION", raising=False)
    gid, ver = resolve_guardrail_config(
        body={},
        kb_item={
            "bedrock_guardrail_version": {"S": "orphan"},
        },
        tenant_settings_item=None,
    )
    assert gid is None
    assert ver == "orphan"
