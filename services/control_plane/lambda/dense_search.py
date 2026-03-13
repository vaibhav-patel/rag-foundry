"""Dense / hybrid search over chunk index — live OpenSearch vs stub."""

from __future__ import annotations

import os
from typing import Any, cast

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


def parse_hybrid_requested(body: dict[str, Any]) -> bool:
    h = body.get("hybrid")
    if isinstance(h, bool):
        return h
    if isinstance(h, str):
        return h.strip().lower() in ("true", "1", "yes")
    if isinstance(h, int):
        return h == 1
    return False


def parse_weight(body: dict[str, Any], key: str, default: float = 1.0) -> float:
    if key not in body:
        return default
    try:
        return max(0.0, float(body[key]))
    except (TypeError, ValueError):
        return default


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


def _tenant_kb_filter(*, tenant_id: str, kb_id: str) -> list[dict[str, Any]]:
    return [
        {"term": {"tenant_id": tenant_id}},
        {"term": {"kb_id": kb_id}},
    ]


def _build_vector_only_query_body(
    *,
    vec: list[float],
    k: int,
    tenant_id: str,
    kb_id: str,
) -> dict[str, Any]:
    return {
        "query": {
            "bool": {
                "must": [{"knn": {"embedding": {"vector": vec, "k": k}}}],
                "filter": _tenant_kb_filter(tenant_id=tenant_id, kb_id=kb_id),
            }
        },
    }


def _build_hybrid_query_body(
    *,
    query_text: str,
    vec: list[float],
    k: int,
    tenant_id: str,
    kb_id: str,
    bm25_weight: float,
    vector_weight: float,
) -> dict[str, Any]:
    """Additive ``bool.should``: BM25 lexical + boosted kNN (weighted-sum style scoring)."""

    return {
        "query": {
            "bool": {
                "filter": _tenant_kb_filter(tenant_id=tenant_id, kb_id=kb_id),
                "should": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["chunk_text"],
                            "type": "best_fields",
                            "boost": bm25_weight,
                        },
                    },
                    {
                        "knn": {
                            "embedding": {
                                "vector": vec,
                                "k": k,
                                "boost": vector_weight,
                            },
                        },
                    },
                ],
                "minimum_should_match": 1,
            },
        },
    }


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
    fetch_size: int | None = None,
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

    hybrid = parse_hybrid_requested(body)
    qvec = coerce_query_embedding(body)

    bm25_w = parse_weight(body, "bm25_weight", 1.0)
    vec_w = parse_weight(body, "vector_weight", 1.0)
    qstrip = query_text.strip()

    if hybrid:
        if not qstrip:
            return (
                400,
                {
                    "title": "Bad Request",
                    "detail": "hybrid search requires non-empty `q` (BM25 branch) "
                    + "and `query_embedding` (vector branch)",
                },
            )
        if not qvec:
            return (
                400,
                {
                    "title": "Bad Request",
                    "detail": "`query_embedding` is required when hybrid=true "
                    + "(and non-empty `q` for lexical branch)",
                },
            )
        if bm25_w == 0.0 and vec_w == 0.0:
            return (
                400,
                {
                    "title": "Bad Request",
                    "detail": "bm25_weight and vector_weight cannot both be 0",
                },
            )
    elif not qvec:
        return (
            400,
            {
                "title": "Bad Request",
                "detail": (
                    "query_embedding (array of numbers) is required when SEARCH_MODE=live "
                    "(set hybrid=true with q+query_embedding for hybrid)"
                ),
            },
        )

    desired_k = parse_knn_k(body)
    ef = fetch_size if fetch_size is not None else desired_k
    ef = max(1, min(100, int(ef)))
    min_score = parse_min_score(body)
    vec = pad_query_vector(cast(list[float], qvec))

    inner: dict[str, Any]
    if hybrid:
        inner = _build_hybrid_query_body(
            query_text=qstrip,
            vec=vec,
            k=ef,
            tenant_id=tenant_id,
            kb_id=kb_id,
            bm25_weight=bm25_w,
            vector_weight=vec_w,
        )
        backend = "opensearch-serverless-hybrid"
    else:
        inner = _build_vector_only_query_body(
            vec=vec,
            k=ef,
            tenant_id=tenant_id,
            kb_id=kb_id,
        )
        backend = "opensearch-serverless-knn"

    search_body: dict[str, Any] = {
        "size": ef,
        "_source": ["chunk_text", "metadata", "chunk_id", "kb_id", "tenant_id"],
        **inner,
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
        "backend": backend,
    }
