"""Resolve Bedrock guardrail id/version from request, KB row, tenant settings, then env."""

from __future__ import annotations

import os
from typing import Any


def _ddb_s(blob: dict[str, Any] | None) -> str | None:
    if not blob or not isinstance(blob, dict):
        return None
    s = blob.get("S")
    return str(s).strip() if isinstance(s, str) and s.strip() else None


def _first_nonempty(*vals: str | None) -> str | None:
    for v in vals:
        if v is None:
            continue
        stripped = str(v).strip()
        if stripped:
            return stripped
    return None


def resolve_guardrail_config(
    *,
    body: dict[str, Any],
    kb_item: dict[str, Any] | None,
    tenant_settings_item: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """Return `(guardrail_id_or_none, version_string)` suitable for Bedrock Converse.

    Id and version are chosen from the same precedence *layer* (body, KB row, tenant settings,
    env) so a KB-level guardrail id is not paired with a tenant-only version string.
    """

    layers: list[tuple[str | None, str | None]] = [
        (
            _first_nonempty(body.get("guardrails_id"), body.get("guardrailIdentifier")),
            _first_nonempty(body.get("guardrails_version"), body.get("guardrailVersion")),
        ),
        (
            _ddb_s((kb_item or {}).get("bedrock_guardrail_id")),
            _ddb_s((kb_item or {}).get("bedrock_guardrail_version")),
        ),
        (
            _ddb_s((tenant_settings_item or {}).get("bedrock_guardrail_id")),
            _ddb_s((tenant_settings_item or {}).get("bedrock_guardrail_version")),
        ),
        (
            _first_nonempty(os.environ.get("BEDROCK_GUARDRAILS_ID")),
            _first_nonempty(os.environ.get("BEDROCK_GUARDRAILS_VERSION")),
        ),
    ]

    for gid, ver in layers:
        if gid:
            return gid, ver or "DRAFT"

    # No guardrail id — version strings are still surfaced for auditing (precedence only on ver).
    orphan_ver = _first_nonempty(
        *(v for _, v in layers),
    )
    return None, orphan_ver or ""


def load_tenant_settings_item(*, table: str, tenant_id: str, ddb: Any) -> dict[str, Any] | None:
    """Tenant-wide defaults (`PK=TENANT#…`, ``SK=SETTINGS#tenant``)."""

    g = ddb.get_item(
        TableName=table,
        Key={"PK": {"S": f"TENANT#{tenant_id}"}, "SK": {"S": "SETTINGS#tenant"}},
    )
    item = g.get("Item")
    return item if isinstance(item, dict) else None
