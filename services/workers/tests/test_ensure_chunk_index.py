"""Unit tests for ensure_chunk_index (no OpenSearch cluster)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opensearchpy.exceptions import RequestError

from ensure_chunk_index import ensure_chunk_index


def test_no_op_when_client_none() -> None:
    ensure_chunk_index(None)
    ensure_chunk_index(None, index_name="custom")


@pytest.fixture()
def rag_mapping_min() -> dict:
    """Subset contract fields used to assert PUT body wiring."""
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {"chunk_text": {"type": "text"}}},
    }


def test_skip_when_index_exists(
    monkeypatch: pytest.MonkeyPatch,
    rag_mapping_min: dict,
) -> None:
    monkeypatch.setenv("OPENSEARCH_INDEX_NAME", "rag-foundry-chunks")
    monkeypatch.setattr(
        "ensure_chunk_index._create_body_from_contract",
        lambda: rag_mapping_min,
    )
    client = MagicMock()
    client.indices.exists.return_value = True
    ensure_chunk_index(client)
    client.indices.exists.assert_called_once_with(index="rag-foundry-chunks")
    client.indices.create.assert_not_called()


def test_create_when_missing(monkeypatch: pytest.MonkeyPatch, rag_mapping_min: dict) -> None:
    monkeypatch.delenv("OPENSEARCH_INDEX_NAME", raising=False)
    monkeypatch.setattr(
        "ensure_chunk_index._create_body_from_contract",
        lambda: rag_mapping_min,
    )
    client = MagicMock()
    client.indices.exists.return_value = False
    ensure_chunk_index(client)
    client.indices.exists.assert_called_once_with(index="rag-foundry-chunks")
    client.indices.create.assert_called_once_with(
        index="rag-foundry-chunks",
        body=rag_mapping_min,
    )


def test_explicit_index_name(monkeypatch: pytest.MonkeyPatch, rag_mapping_min: dict) -> None:
    monkeypatch.setattr(
        "ensure_chunk_index._create_body_from_contract",
        lambda: rag_mapping_min,
    )
    client = MagicMock()
    client.indices.exists.return_value = False
    ensure_chunk_index(client, index_name="custom-idx")
    client.indices.exists.assert_called_once_with(index="custom-idx")
    client.indices.create.assert_called_once_with(index="custom-idx", body=rag_mapping_min)


def test_race_resource_already_exists(
    monkeypatch: pytest.MonkeyPatch,
    rag_mapping_min: dict,
) -> None:
    monkeypatch.setattr(
        "ensure_chunk_index._create_body_from_contract",
        lambda: rag_mapping_min,
    )
    client = MagicMock()
    client.indices.exists.return_value = False
    client.indices.create.side_effect = RequestError(
        400,
        "resource_already_exists_exception",
        {},
    )
    ensure_chunk_index(client)
    client.indices.create.assert_called_once()
