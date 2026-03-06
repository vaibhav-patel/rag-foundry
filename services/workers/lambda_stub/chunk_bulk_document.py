"""Chunk document schema for bulk index: deterministic `_id` and OpenSearch v1 `_source` shape."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def chunk_document_id(*, tenant: str, kb_id: str, job_id: str, chunk_idx: int) -> str:
    """Stable ``_id`` for OpenSearch: same tuple ⇒ same SHA-256 hex (retries/idempotent).

    Canonical JSON (sorted keys) is hashed.
    """

    canonical = json.dumps(
        {
            "chunk_idx": int(chunk_idx),
            "job_id": str(job_id),
            "kb_id": str(kb_id),
            "tenant": str(tenant),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ChunkBulkDocument:
    """Pydantic-style payload for one chunk row (stdlib ``dataclass`` only — no Pydantic in Lambda).

    Logical fields mirror API language; ``to_opensearch_source`` maps onto ADR 0006 index fields.
    """

    tenant: str
    kb_id: str
    job_id: str
    chunk_idx: int
    s3_key: str
    chunk_text: str
    embedding: list[float]
    metadata: dict[str, Any] | None = None

    def document_id(self) -> str:
        return chunk_document_id(
            tenant=self.tenant,
            kb_id=self.kb_id,
            job_id=self.job_id,
            chunk_idx=self.chunk_idx,
        )

    def to_logical_body(self) -> dict[str, Any]:
        """Serializable chunk row: tenant/kb/s3_key/text/embedding (+ optional metadata)."""

        out: dict[str, Any] = {
            "kb_id": self.kb_id,
            "tenant": self.tenant,
            "s3_key": self.s3_key,
            "chunk_text": self.chunk_text,
            "embedding": self.embedding,
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata
        return out

    def to_opensearch_source(self) -> dict[str, Any]:
        """Index ``_source`` for ``chunk-index-v1`` (``tenant_id``, ``source_s3_key``, …)."""

        doc_id = self.document_id()
        src: dict[str, Any] = {
            "chunk_id": doc_id,
            "chunk_text": self.chunk_text,
            "embedding": self.embedding,
            "job_id": self.job_id,
            "kb_id": self.kb_id,
            "source_s3_key": self.s3_key,
            "tenant_id": self.tenant,
        }
        if self.metadata is not None:
            src["metadata"] = self.metadata
        return src

    def bulk_index_pair(
        self,
        *,
        index_name: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """``(action_line, source_line)`` pair for OpenSearch bulk API."""

        _id = self.document_id()
        action = {"index": {"_index": index_name, "_id": _id}}
        return action, self.to_opensearch_source()
