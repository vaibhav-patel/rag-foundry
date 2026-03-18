"""Tests for per-tenant daily request quotas."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from quota import (
    tenant_quota_exempt,
    try_consume_request_quota,
)


def test_tenant_quota_exempt_bool() -> None:
    assert tenant_quota_exempt({"quota_exempt": {"BOOL": True}}) is True
    assert tenant_quota_exempt({"quota_exempt": {"BOOL": False}}) is False
    assert tenant_quota_exempt({"quota_exempt": {"S": "true"}}) is True
    assert tenant_quota_exempt(None) is False


def test_try_consume_skips_unknown_tenant() -> None:
    ddb = MagicMock()
    assert try_consume_request_quota(ddb=ddb, table="x", tenant_id="unknown", settings=None) is None
    ddb.update_item.assert_not_called()


def test_try_consume_skips_when_exempt() -> None:
    ddb = MagicMock()
    assert (
        try_consume_request_quota(
            ddb=ddb,
            table="x",
            tenant_id="t1",
            settings={"quota_exempt": {"BOOL": True}},
        )
        is None
    )
    ddb.update_item.assert_not_called()


def test_try_consume_skips_when_env_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "0")
    ddb = MagicMock()
    assert try_consume_request_quota(ddb=ddb, table="x", tenant_id="t1", settings=None) is None
    ddb.update_item.assert_not_called()
    monkeypatch.delenv("TENANT_REQUESTS_PER_DAY", raising=False)


def test_try_consume_calls_update_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "50")
    ddb = MagicMock()
    assert try_consume_request_quota(ddb=ddb, table="tbl", tenant_id="t1", settings=None) is None
    ddb.update_item.assert_called_once()
    kw = ddb.update_item.call_args[1]
    assert kw["TableName"] == "tbl"
    assert kw["Key"]["PK"]["S"] == "TENANT#t1"
    assert kw["Key"]["SK"]["S"].startswith("QUOTA#")
    assert kw["ExpressionAttributeValues"][":lim"]["N"] == "50"
    monkeypatch.delenv("TENANT_REQUESTS_PER_DAY", raising=False)


def test_try_consume_tenant_limit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "10")
    ddb = MagicMock()
    settings = {"requests_per_day_limit": {"N": "200"}}
    out = try_consume_request_quota(
        ddb=ddb, table="tbl", tenant_id="t1", settings=settings
    )
    assert out is None
    assert ddb.update_item.call_args[1]["ExpressionAttributeValues"][":lim"]["N"] == "200"
    monkeypatch.delenv("TENANT_REQUESTS_PER_DAY", raising=False)


def test_try_consume_429_on_conditional_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "3")
    ddb = MagicMock()
    ddb.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "m"}},
        "UpdateItem",
    )
    err = try_consume_request_quota(ddb=ddb, table="tbl", tenant_id="t1", settings=None)
    assert err is not None
    assert err["title"] == "Too Many Requests"
    assert err["limit"] == 3
    assert "quota_date" in err
    monkeypatch.delenv("TENANT_REQUESTS_PER_DAY", raising=False)


def test_try_consume_propagates_other_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_REQUESTS_PER_DAY", "5")
    ddb = MagicMock()
    ddb.update_item.side_effect = ClientError(
        {"Error": {"Code": "ValidationException", "Message": "x"}},
        "UpdateItem",
    )
    with pytest.raises(ClientError):
        try_consume_request_quota(ddb=ddb, table="tbl", tenant_id="t1", settings=None)
    monkeypatch.delenv("TENANT_REQUESTS_PER_DAY", raising=False)
