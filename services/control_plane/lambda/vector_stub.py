"""OpenSearch Serverless search stub (dense path to be wired to _search API)."""

from __future__ import annotations

from typing import Any


def dense_search_stub(
    *,
    endpoint: str,
    collection_name: str,
    query_text: str,
    top_k: int = 5,
) -> dict[str, Any]:
    _ = (endpoint, collection_name, query_text, top_k)
    return {
        "hits": [],
        "total": 0,
        "backend": "opensearch-serverless-stub",
    }
