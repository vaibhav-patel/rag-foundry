"""Tests for chunk bulk document ids and payloads (stdlib only)."""

from __future__ import annotations

from chunk_bulk_document import ChunkBulkDocument, chunk_document_id


def test_document_id_stable() -> None:
    a = chunk_document_id(tenant="t", kb_id="k", job_id="j", chunk_idx=0)
    b = chunk_document_id(tenant="t", kb_id="k", job_id="j", chunk_idx=0)
    assert a == b
    assert len(a) == 64


def test_document_id_sensitive_to_inputs() -> None:
    base = chunk_document_id(tenant="t", kb_id="k", job_id="j", chunk_idx=0)
    assert chunk_document_id(tenant="t2", kb_id="k", job_id="j", chunk_idx=0) != base
    assert chunk_document_id(tenant="t", kb_id="k", job_id="j", chunk_idx=1) != base


def test_logical_body_shape() -> None:
    d = ChunkBulkDocument(
        tenant="tenant-a",
        kb_id="kb1",
        job_id="job1",
        chunk_idx=2,
        s3_key="raw/x.txt",
        chunk_text="hello",
        embedding=[0.1, 0.2],
        metadata={"page": 1},
    )
    body = d.to_logical_body()
    assert body["tenant"] == "tenant-a"
    assert body["kb_id"] == "kb1"
    assert body["s3_key"] == "raw/x.txt"
    assert body["chunk_text"] == "hello"
    assert body["embedding"] == [0.1, 0.2]
    assert body["metadata"] == {"page": 1}


def test_logical_body_omits_metadata_when_none() -> None:
    d = ChunkBulkDocument(
        tenant="t",
        kb_id="k",
        job_id="j",
        chunk_idx=0,
        s3_key="k",
        chunk_text="x",
        embedding=[0.0],
        metadata=None,
    )
    assert "metadata" not in d.to_logical_body()


def test_opensearch_source_matches_index_contract() -> None:
    d = ChunkBulkDocument(
        tenant="tenant-a",
        kb_id="kb1",
        job_id="job1",
        chunk_idx=0,
        s3_key="path/to/doc.pdf",
        chunk_text="body",
        embedding=[0.0] * 8,
        metadata={"extra": True},
    )
    doc_id = d.document_id()
    src = d.to_opensearch_source()
    assert src["tenant_id"] == "tenant-a"
    assert src["kb_id"] == "kb1"
    assert src["job_id"] == "job1"
    assert src["chunk_id"] == doc_id
    assert src["source_s3_key"] == "path/to/doc.pdf"
    assert src["chunk_text"] == "body"
    assert src["embedding"] == [0.0] * 8
    assert src["metadata"] == {"extra": True}


def test_bulk_index_pair_alignment() -> None:
    d = ChunkBulkDocument(
        tenant="t",
        kb_id="k",
        job_id="j",
        chunk_idx=1,
        s3_key="s",
        chunk_text="c",
        embedding=[1.0],
        metadata=None,
    )
    action, src = d.bulk_index_pair(index_name="rag-foundry-chunks")
    assert action == {"index": {"_index": "rag-foundry-chunks", "_id": d.document_id()}}
    assert src == d.to_opensearch_source()
