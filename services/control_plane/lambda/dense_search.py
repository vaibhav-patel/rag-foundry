"""Dense kNN search over chunk index (live OpenSearch) or stub (CI / no endpoint)."""

from __future__ import annotations

import os
from typing import Any

import vector_stub
from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException


def _embedding_target_dim() -> int:
    return int(os.environ.get("OPENSEARCH_EMBEDDING_DIM", "1536"))


def pad_query_vector(vector: list[float]) -> list[float]:
    """Match index knn_vector dimension (same rule as ingest worker)."""

    dim = _embedding_target_dim()
    if len(vector) == dim:
        return list(vector)
    if len(vector) > dim:
        return list(vector[:dim])
    return list(vector) + [0.0] * (dim - len(vector))


def parse_knn_k(body: dict[str, Any]) -> int:
    raw = body.get("k", body.get("top_k", 5))
    try:
        k = int(raw)
    except (TypeError, ValueError):
        k = 5
    return max(1, min(100, k))


def parse_min_score(body: dict[str, Any]) -> float | None:
    v = body.get("min_score")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coerce_query_embedding(body: dict[str, Any]) -> list[float] | None:
    vec = body.get("query_embedding")
    if not isinstance(vec, list) or len(vec) == 0:
        return None
    out: list[float] = []
    for x in vec:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        out.append(float(x))
    return out


def _map_hit(hit: dict[str, Any]) -> dict[str, Any]:
    src = hit.get("_source") or {}
    meta = src.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        meta = None
    return {
        "id": str(hit.get("_id", "")),
        "score": float(hit.get("_score") or 0.0),
        "text": str(src.get("chunk_text", "")),
        "metadata": meta,
    }


def run_dense_search(
    *,
    search_mode: str,
    os_client: OpenSearch | None,
    index_name: str,
    tenant_id: str,
    kb_id: str,
    body: dict[str, Any],
    query_text: str,
) -> tuple[int, dict[str, Any]]:
    """Return ``(http_status, response_body)``.

    On **200**, body is ``hits``, ``total``, ``backend`` (merge with ``kb_id`` in handler).
    On **4xx/5xx**, body is API error object ``title`` / ``detail``.
    """

    mode = (search_mode or "stub").strip().lower()
    if mode != "live":
        stub = vector_stub.dense_search_stub(
            endpoint=os.environ.get("OPENSEARCH_ENDPOINT", ""),
            collection_name=os.environ.get("OPENSEARCH_COLLECTION_NAME", ""),
            query_text=query_text,
            top_k=parse_knn_k(body),
        )
        return 200, {**stub, "backend": "opensearch-serverless-stub"}

    if os_client is None:
        return (
            503,
            {
                "title": "Service Unavailable",
                "detail": "SEARCH_MODE=live requires OPENSEARCH_ENDPOINT and credentials",
            },
        )

    qvec = coerce_query_embedding(body)
    if not qvec:
        return (
            400,
            {
                "title": "Bad Request",
                "detail": "query_embedding (array of numbers) is required when SEARCH_MODE=live",
            },
        )

    k = parse_knn_k(body)
    min_score = parse_min_score(body)
    vec = pad_query_vector(qvec)

    search_body: dict[str, Any] = {
        "size": k,
        "query": {
            "bool": {
                "must": [{"knn": {"embedding": {"vector": vec, "k": k}}}],
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"kb_id": kb_id}},
                ],
            }
        },
        "_source": ["chunk_text", "metadata", "chunk_id", "kb_id", "tenant_id"],
    }
    if min_score is not None:
        search_body["min_score"] = min_score

    try:
        resp = os_client.search(index=index_name, body=search_body)
    except OpenSearchException as exc:
        return (
            502,
            {
                "title": "Search failed",
                "detail": str(exc)[:2000],
            },
        )

    raw_hits = (resp.get("hits") or {}).get("hits") or []
    hits = [_map_hit(h) for h in raw_hits]
    total_obj = (resp.get("hits") or {}).get("total")
    if isinstance(total_obj, dict):
        total = int(total_obj.get("value", len(hits)))
    else:
        total = int(total_obj) if total_obj is not None else len(hits)

    return 200, {
        "hits": hits,
        "total": total,
        "backend": "opensearch-serverless-knn",
    }
