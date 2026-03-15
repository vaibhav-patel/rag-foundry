"""Amazon Bedrock Converse / ConverseStream for RAG reply generation."""

from __future__ import annotations

import hashlib
import os
from typing import Any

# ── env resolution ─────────────────────────────────────────────────────────────


def canonical_prompt_sha256(system_text: str, user_text: str) -> str:
    """Deterministic fingerprint of prompts sent to the model (audit / dedupe)."""

    h = hashlib.sha256()
    h.update(b"system\x00")
    h.update(system_text.encode("utf-8"))
    h.update(b"\x00user\x00")
    h.update(user_text.encode("utf-8"))
    return h.hexdigest()


def resolve_model_id(body_model: str | None) -> str:
    """Prefer request ``model_id``; else ``GENERATION_MODEL_ID`` env."""

    if body_model and str(body_model).strip():
        return str(body_model).strip()
    return (
        os.environ.get("GENERATION_MODEL_ID") or "anthropic.claude-3-haiku-20240307-v1:0"
    ).strip()


def resolve_max_tokens() -> int:
    raw = os.environ.get("MAX_TOKENS", "512")
    try:
        return max(1, min(8192, int(str(raw).strip())))
    except (TypeError, ValueError):
        return 512


def resolve_temperature() -> float | None:
    raw = os.environ.get("TEMPERATURE")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return max(0.0, min(2.0, float(str(raw).strip())))
    except (TypeError, ValueError):
        return None


def use_converse_stream() -> bool:
    v = (os.environ.get("QUERY_USE_CONVERSE_STREAM") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def audit_extension_stub() -> str:
    """Placeholder for richer audit payloads (streaming metrics, quotas, …)."""

    return (os.environ.get("QUERY_AUDIT_EXTENSION_STUB") or "pending-2026-03-16").strip()[:256]


# ── Bedrock ────────────────────────────────────────────────────────────────────


def _infer_params(max_tokens: int, temperature: float | None) -> dict[str, Any]:
    cfg: dict[str, Any] = {"maxTokens": max_tokens}
    if temperature is not None:
        cfg["temperature"] = temperature
    return cfg


def _assistant_text_from_converse(resp: dict[str, Any]) -> str:
    out = resp.get("output") or {}
    msg = out.get("message") or {}
    chunks: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and "text" in block:
            chunks.append(str(block["text"]))
    return "".join(chunks)


def _event_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    nested = getattr(raw, "value", None)
    if isinstance(nested, dict):
        return nested
    return {}


def _collect_converse_stream(stream: Any) -> str:
    """Reduce ConverseStream events to plain assistant text (best-effort)."""

    parts: list[str] = []
    if stream is None:
        return ""
    for raw in stream:
        ev = _event_dict(raw)
        cb = ev.get("contentBlockDelta")
        if isinstance(cb, dict):
            delta = cb.get("delta") or {}
            if isinstance(delta, dict) and "text" in delta:
                parts.append(str(delta["text"]))
        chk = ev.get("chunk") or {}
        if isinstance(chk, dict) and chk.get("bytes"):
            try:
                parts.append(bytes(chk["bytes"]).decode("utf-8"))
            except (UnicodeDecodeError, TypeError, ValueError):
                pass
    return "".join(parts)


def generate_with_converse(
    br: Any,
    *,
    model_id: str,
    system_text: str,
    user_text: str,
    max_tokens: int,
    temperature: float | None,
    guardrail_id: str | None,
    guardrail_version: str,
) -> str:
    """Sync Converse unless ``QUERY_USE_CONVERSE_STREAM`` requests streaming."""

    msgs = [{"role": "user", "content": [{"text": user_text}]}]
    syss = [{"text": system_text}]
    infer = _infer_params(max_tokens, temperature)

    kr: dict[str, Any] = {
        "modelId": model_id,
        "messages": msgs,
        "system": syss,
        "inferenceConfig": infer,
    }
    if guardrail_id:
        kr["guardrailConfig"] = {
            "guardrailIdentifier": guardrail_id,
            "guardrailVersion": guardrail_version,
            "trace": "disabled",
        }

    if use_converse_stream():
        resp = br.converse_stream(**kr)
        return _collect_converse_stream(resp.get("stream"))

    resp = br.converse(**kr)
    return _assistant_text_from_converse(resp)
