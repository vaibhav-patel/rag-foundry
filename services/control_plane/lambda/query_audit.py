"""DynamoDB item shape for RAG query audit (time-ordered SK, optional GSI2, optional TTL)."""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any


def _iso_utc_millis() -> str:
    dt = datetime.now(timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def question_sha256(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _ttl_epoch_seconds() -> int | None:
    raw = (os.environ.get("QUERY_AUDIT_TTL_DAYS") or "").strip()
    if not raw:
        return None
    try:
        days = int(raw, 10)
    except ValueError:
        return None
    if days <= 0:
        return None
    return int(time.time()) + days * 86400


def build_query_audit_item(
    *,
    tenant_id: str,
    kb_id: str,
    question: str,
    answer_text: str,
    model_id: str,
    latency_ms: float,
    hit_ids: list[str],
    prompt_sha256: str,
    audit_stub: str,
    guardrails_id: str | None,
    guardrails_version: str | None,
) -> dict[str, Any]:
    """Return a DynamoDB ``Item`` map for ``put_item`` (PK/SK + sparse GSI2 + metrics)."""

    iso = _iso_utc_millis()
    uid = str(uuid.uuid4())
    sk = f"QUERYAUDIT#{iso}#{uid}"
    gsi2_pk = f"TENANT#{tenant_id}#QUERYAUDIT"
    gsi2_sk = f"{iso}#{uid}"

    q_hash = question_sha256(question)
    hits_trimmed = [hid[:2048] for hid in hit_ids[:100]]

    item: dict[str, Any] = {
        "PK": {"S": f"TENANT#{tenant_id}"},
        "SK": {"S": sk},
        "GSI2PK": {"S": gsi2_pk},
        "GSI2SK": {"S": gsi2_sk},
        "kb_id": {"S": kb_id[:2048]},
        "question_sha256": {"S": q_hash},
        "answer_length": {"N": str(len(answer_text))},
        "model_id": {"S": model_id[:2048]},
        "latency_ms": {"N": str(max(0, int(round(latency_ms))))},
        "hit_ids": {"L": [{"S": h} for h in hits_trimmed]},
        "prompt_sha256": {"S": prompt_sha256},
        "audit_stub_next": {"S": audit_stub[:256]},
    }
    if guardrails_id:
        item["guardrails_id"] = {"S": guardrails_id[:256]}
    if guardrails_id and guardrails_version:
        item["guardrails_version"] = {"S": str(guardrails_version)[:64]}

    ttl = _ttl_epoch_seconds()
    if ttl is not None:
        item["expires_at"] = {"N": str(ttl)}

    return item
