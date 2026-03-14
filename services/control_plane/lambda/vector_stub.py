"""Search stub backend when ``SEARCH_MODE=stub`` — see ``dense_search.py`` for kNN/live."""

from __future__ import annotations

import json
import os
from typing import Any


def _normalize_stub_hit(raw: dict[str, Any]) -> dict[str, Any] | None:
    hid = raw.get("id")
    if hid is None:
        return None
    txt = raw.get("text")
    score = raw.get("score", 0.0)
    meta = raw.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        meta = None
    try:
        sc = float(score)
    except (TypeError, ValueError):
        sc = 0.0
    return {
        "id": str(hid),
        "score": sc,
        "text": "" if txt is None else str(txt),
        "metadata": meta,
    }


def dense_search_stub(
    *,
    endpoint: str,
    collection_name: str,
    query_text: str,
    top_k: int = 5,
) -> dict[str, Any]:
    raw = os.environ.get("RAG_STUB_DENSE_HITS_JSON")
    if raw and raw.strip():
        try:
            blob = json.loads(raw)
            if isinstance(blob, list):
                rows = blob
                total_hint = len(rows)
            elif isinstance(blob, dict):
                rows = blob.get("hits") or []
                total_hint = int(blob.get("total", len(rows)))
            else:
                rows = []
                total_hint = 0

            normalized: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                nh = _normalize_stub_hit(row)
                if nh is None:
                    continue
                normalized.append(nh)

            if not normalized:
                return {"hits": [], "total": 0, "backend": "opensearch-serverless-stub"}
            cap = max(1, min(100, int(top_k)))
            sliced = normalized[:cap]
            return {
                "hits": sliced,
                "total": max(total_hint, len(normalized)),
                "backend": "opensearch-serverless-stub-injected",
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    _ = endpoint, collection_name, query_text, top_k
    return {
        "hits": [],
        "total": 0,
        "backend": "opensearch-serverless-stub",
    }
