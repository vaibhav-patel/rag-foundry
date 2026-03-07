"""Tests for bulk chunk indexing (mocked OpenSearch client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bulk_index_chunks import pad_embedding, run_chunk_bulk_index
from chunk_bulk_document import ChunkBulkDocument


def test_pad_embedding_exact() -> None:
    v = [0.1] * 1536
    assert len(pad_embedding(v, target_dim=1536)) == 1536


def test_pad_embedding_short() -> None:
    assert pad_embedding([1.0, 2.0], target_dim=4) == [1.0, 2.0, 0.0, 0.0]


def test_pad_embedding_long() -> None:
    assert pad_embedding([1.0, 2.0, 3.0], target_dim=2) == [1.0, 2.0]


def test_run_skipped_no_client() -> None:
    docs = [
        ChunkBulkDocument(
            tenant="t",
            kb_id="k",
            job_id="j",
            chunk_idx=0,
            s3_key="s",
            chunk_text="x",
            embedding=[0.0] * 1536,
            metadata=None,
        )
    ]
    out = run_chunk_bulk_index(None, index_name="idx", bulk_docs=docs, batch_size=10)
    assert out.skipped is True
    assert out.indexed_ok == 0


def test_run_skipped_empty_docs() -> None:
    out = run_chunk_bulk_index(MagicMock(), index_name="idx", bulk_docs=[], batch_size=10)
    assert out.skipped is True


def test_run_bulk_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "4")
    docs = [
        ChunkBulkDocument("t", "k", "j", 0, "s", "a", [1.0], None),
        ChunkBulkDocument("t", "k", "j", 1, "s", "b", [2.0], None),
    ]
    client = MagicMock()
    client.bulk.return_value = {
        "errors": False,
        "items": [
            {"index": {"status": 201, "_id": docs[0].document_id()}},
            {"index": {"status": 201, "_id": docs[1].document_id()}},
        ],
    }
    out = run_chunk_bulk_index(
        client, index_name="rag-foundry-chunks", bulk_docs=docs, batch_size=10
    )
    assert out.skipped is False
    assert out.indexed_ok == 2
    assert out.failed_ids == []
    client.bulk.assert_called_once()


def test_run_bulk_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    docs = [
        ChunkBulkDocument("t", "k", "j", i, "s", str(i), [float(i), 0.0], None) for i in range(3)
    ]
    client = MagicMock()
    client.bulk.side_effect = [
        {
            "errors": False,
            "items": [
                {"index": {"status": 201, "_id": docs[0].document_id()}},
                {"index": {"status": 201, "_id": docs[1].document_id()}},
            ],
        },
        {
            "errors": False,
            "items": [{"index": {"status": 201, "_id": docs[2].document_id()}}],
        },
    ]
    out = run_chunk_bulk_index(client, index_name="i", bulk_docs=docs, batch_size=2)
    assert client.bulk.call_count == 2
    assert out.indexed_ok == 3
    assert out.failed_ids == []


def test_run_bulk_partial_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    docs = [
        ChunkBulkDocument("t", "k", "j", 0, "s", "a", [1.0, 0.0], None),
        ChunkBulkDocument("t", "k", "j", 1, "s", "b", [2.0, 0.0], None),
    ]
    bad_id = docs[1].document_id()
    client = MagicMock()
    client.bulk.return_value = {
        "errors": True,
        "items": [
            {"index": {"status": 201, "_id": docs[0].document_id()}},
            {
                "index": {
                    "status": 400,
                    "_id": bad_id,
                    "error": {"type": "mapper_parsing_exception"},
                }
            },
        ],
    }
    out = run_chunk_bulk_index(client, index_name="i", bulk_docs=docs, batch_size=10)
    assert out.indexed_ok == 1
    assert bad_id in out.failed_ids
