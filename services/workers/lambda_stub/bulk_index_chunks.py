"""Batch OpenSearch bulk index for chunk documents (AoSS / opensearch-py)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException

from chunk_bulk_document import ChunkBulkDocument


def target_embedding_dimension() -> int:
    return int(os.environ.get("OPENSEARCH_EMBEDDING_DIM", "1536"))


def pad_embedding(vector: list[float], *, target_dim: int | None = None) -> list[float]:
    """Pad or truncate vectors so index knn_vector dimension matches mapping (default 1536)."""

    dim = target_dim if target_dim is not None else target_embedding_dimension()
    if len(vector) == dim:
        return list(vector)
    if len(vector) > dim:
        return list(vector[:dim])
    return list(vector) + [0.0] * (dim - len(vector))


@dataclass(frozen=True)
class BulkIndexOutcome:
    """``skipped`` is True when there is no client, no docs, or OpenSearch was not used."""

    indexed_ok: int
    failed_ids: list[str]
    skipped: bool
    transport_error: str | None


def run_chunk_bulk_index(
    client: OpenSearch | None,
    *,
    index_name: str,
    bulk_docs: list[ChunkBulkDocument],
    batch_size: int,
) -> BulkIndexOutcome:
    """Run ``bulk`` in batches; return counts and failed OpenSearch ``_id`` values."""

    if not bulk_docs:
        return BulkIndexOutcome(0, [], True, None)

    if client is None:
        return BulkIndexOutcome(0, [], True, None)

    bs = max(1, int(batch_size))
    ok_total = 0
    failed: list[str] = []
    target_dim = target_embedding_dimension()

    for start in range(0, len(bulk_docs), bs):
        batch = bulk_docs[start : start + bs]
        lines: list[str] = []
        for doc in batch:
            action, _src = doc.bulk_index_pair(index_name=index_name)
            src = dict(_src)
            src["embedding"] = pad_embedding(src["embedding"], target_dim=target_dim)
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(src, separators=(",", ":")))
        body = "\n".join(lines) + "\n"
        try:
            resp: dict[str, Any] = client.bulk(body=body)
        except OpenSearchException as exc:
            pending = [d.document_id() for d in bulk_docs[start:]]
            return BulkIndexOutcome(
                ok_total,
                failed + pending,
                False,
                str(exc),
            )

        for item in resp.get("items", []) or []:
            idx = item.get("index") or {}
            status = int(idx.get("status", 0) or 0)
            if status in (200, 201):
                ok_total += 1
            else:
                _id = idx.get("_id")
                if isinstance(_id, str) and _id:
                    failed.append(_id)

    return BulkIndexOutcome(ok_total, failed, False, None)
