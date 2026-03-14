"""Turn dense-search hits into a bounded context block for Bedrock prompts."""

from __future__ import annotations

import os
from typing import Any


def parse_context_char_budget() -> int:
    """Rough token proxy: clamped character ceiling from ``CONTEXT_CHAR_BUDGET``."""

    raw = os.environ.get("CONTEXT_CHAR_BUDGET", "12000")
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return 12000
    return max(64, min(500_000, v))


def parse_context_k(body: dict[str, Any]) -> int:
    """Max chunks concatenated before char budget truncation."""

    raw = os.environ.get("CONTEXT_K_DEFAULT", "8")
    default = 8
    try:
        default = int(str(raw).strip())
    except (TypeError, ValueError):
        pass
    default = max(1, min(50, default))

    if "context_k" not in body or body["context_k"] is None:
        return default
    try:
        ck = int(body["context_k"])
    except (TypeError, ValueError):
        return default
    return max(1, min(50, ck))


def format_rag_context(
    hits: list[dict[str, Any]],
    *,
    context_k: int,
    char_budget: int,
) -> tuple[str, list[dict[str, str]]]:
    """Join top ``context_k`` hit texts with source ids; hard-truncate to ``char_budget``.

    ``citations`` IDs match ``hits[:context_k]`` order (included even when text is clipped).
    """

    if not hits:
        return "(No passages retrieved.)", []

    fragments: list[str] = []
    citations: list[dict[str, str]] = []

    for hit in hits[:context_k]:
        hid = str(hit.get("id", "") or "").strip() or "(unknown)"
        excerpt = str(hit.get("text", "") or "").strip()
        citations.append({"id": hid})
        fragments.append(f"[source_id:{hid}]\n{excerpt}")

    sep = "\n---\n"
    full = sep.join(fragments)
    budget = max(0, int(char_budget))

    if len(full) <= budget:
        return full, citations

    clipped = full[:budget]
    if budget > 1:
        clipped = clipped[:-1] + "…"
    return clipped, citations
