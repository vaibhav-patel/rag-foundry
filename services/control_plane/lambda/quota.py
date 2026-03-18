"""Per-tenant daily request quotas via DynamoDB conditional counters (``QUOTA#<date>`` items)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError


def _utc_quota_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _ddb_truthy_flag(item: dict[str, Any] | None, key: str) -> bool:
    if not item:
        return False
    blob = item.get(key)
    if not blob or not isinstance(blob, dict):
        return False
    if "BOOL" in blob:
        return bool(blob["BOOL"])
    if "S" in blob and isinstance(blob["S"], str):
        return blob["S"].strip().lower() in ("1", "true", "yes", "on")
    return False


def tenant_quota_exempt(settings: dict[str, Any] | None) -> bool:
    """Admin override: ``quota_exempt`` on ``SETTINGS#tenant`` (BOOL or string)."""

    return _ddb_truthy_flag(settings, "quota_exempt")


def _effective_daily_limit(settings: dict[str, Any] | None) -> int | None:
    """Max requests per UTC day, or ``None`` if ``TENANT_REQUESTS_PER_DAY`` is ``0`` (disabled)."""

    raw = (os.environ.get("TENANT_REQUESTS_PER_DAY") or "100000").strip()
    try:
        env_lim = int(raw, 10)
    except ValueError:
        env_lim = 100_000
    if env_lim <= 0:
        return None

    if settings:
        tlim = settings.get("requests_per_day_limit")
        if tlim and isinstance(tlim, dict) and "N" in tlim:
            try:
                v = int(str(tlim["N"]).strip(), 10)
                if v > 0:
                    return v
            except ValueError:
                pass
    return env_lim


def try_consume_request_quota(
    *,
    ddb: Any,
    table: str,
    tenant_id: str,
    settings: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Atomically increment the tenant's daily counter; return a 429 body dict if over limit.

    Skips enforcement when ``quota_exempt`` is set on tenant settings, when the effective limit
    is unset (env ``0``), or when ``tenant_id`` is ``unknown`` (caller should skip before calling).
    """

    if tenant_id == "unknown":
        return None
    if tenant_quota_exempt(settings):
        return None
    limit = _effective_daily_limit(settings)
    if limit is None:
        return None

    day = _utc_quota_date()
    pk = f"TENANT#{tenant_id}"
    sk = f"QUOTA#{day}"

    try:
        ddb.update_item(
            TableName=table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            UpdateExpression="ADD request_count :one",
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":lim": {"N": str(limit)},
            },
            ConditionExpression="attribute_not_exists(request_count) OR request_count < :lim",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return {
                "title": "Too Many Requests",
                "detail": "Daily request quota for this tenant has been exceeded.",
                "quota_date": day,
                "limit": limit,
            }
        raise
    return None
