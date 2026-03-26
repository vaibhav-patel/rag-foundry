"""Typed payloads for dense search and RAG query (matches control-plane OpenAPI)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DenseSearchHit:
    """``DenseSearchHit`` schema — retrieved chunk."""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class DenseSearchResponse:
    """``DenseSearchResponse`` schema."""

    kb_id: str
    hits: list[DenseSearchHit]
    total: int
    backend: str
    reranked: bool | None = None


@dataclass(frozen=True)
class RagCitation:
    """Citation chunk id embedded in ``RagQueryResponse.citations``."""

    id: str


@dataclass(frozen=True)
class RagQueryResponse:
    """``RagQueryResponse`` schema."""

    answer: str
    citations: list[RagCitation]
    kb_id: str
    guardrails_applied: bool


class ResponseShapeError(RuntimeError):
    """Response body matched HTTP 200 but could not be coerced into the expected model."""

    ...


def _require_map(data: Any, *, what: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ResponseShapeError(f"{what}: expected JSON object, got {type(data).__name__}")
    # Concrete dict for callers that need mutability-safe views
    return dict(data)


def dense_search_hit_from_dict(data: Mapping[str, Any]) -> DenseSearchHit:
    try:
        return DenseSearchHit(
            id=str(data["id"]),
            score=float(data["score"]),
            text=str(data["text"]),
            metadata=_coerce_optional_metadata(data.get("metadata")),
        )
    except KeyError as exc:
        key = getattr(exc, "args", ["?"])[0]
        raise ResponseShapeError(f"dense search hit: missing required field {key!r}") from exc


def dense_search_response_from_json(data: Any) -> DenseSearchResponse:
    d = _require_map(data, what="dense search response")
    hits_raw = d.get("hits")
    if not isinstance(hits_raw, list):
        raise ResponseShapeError("dense search response: 'hits' must be a JSON array")

    reranked_raw = d.get("reranked")
    reranked: bool | None
    if reranked_raw is None:
        reranked = None
    elif isinstance(reranked_raw, bool):
        reranked = reranked_raw
    else:
        raise ResponseShapeError("dense search response: 'reranked' must be boolean or omitted")

    hits_out: list[DenseSearchHit] = []
    for i, h in enumerate(hits_raw):
        if not isinstance(h, Mapping):
            raise ResponseShapeError(
                f"dense search response: hits[{i}] must be object, got {type(h).__name__}",
            )
        hits_out.append(dense_search_hit_from_dict(h))

    return DenseSearchResponse(
        kb_id=str(d["kb_id"]),
        hits=hits_out,
        total=int(d["total"]),
        backend=str(d["backend"]),
        reranked=reranked,
    )


def _coerce_optional_metadata(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return dict(raw)
    raise ResponseShapeError("dense search hit: metadata must be object or null")


def rag_citation_from_dict(data: Mapping[str, Any]) -> RagCitation:
    return RagCitation(id=str(data["id"]))


def rag_query_response_from_json(data: Any) -> RagQueryResponse:
    d = _require_map(data, what="rag query response")
    cites_raw = d.get("citations")
    if not isinstance(cites_raw, list):
        raise ResponseShapeError("rag query response: 'citations' must be a JSON array")
    citations: list[RagCitation] = []
    for i, c in enumerate(cites_raw):
        if not isinstance(c, Mapping):
            raise ResponseShapeError(f"rag query response: citation[{i}] must be object")
        citations.append(rag_citation_from_dict(c))
    return RagQueryResponse(
        answer=str(d["answer"]),
        citations=citations,
        kb_id=str(d["kb_id"]),
        guardrails_applied=bool(d["guardrails_applied"]),
    )
