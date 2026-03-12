"""Tests for dense_search (stub/live dispatch and OpenSearch mapping)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dense_search import coerce_query_embedding, pad_query_vector, parse_knn_k, run_dense_search


def test_stub_mode_uses_vector_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENSEARCH_ENDPOINT", raising=False)
    st, payload = run_dense_search(
        search_mode="STUB",
        os_client=None,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={"top_k": 3},
        query_text="hello",
    )
    assert st == 200
    assert payload["hits"] == []
    assert payload["total"] == 0
    assert payload["backend"] == "opensearch-serverless-stub"


@pytest.mark.parametrize(
    ("body", "want"),
    [
        ({}, 5),
        ({"k": "10"}, 10),
        ({"top_k": 2}, 2),
        ({"k": "200"}, 100),
        ({"k": "broken"}, 5),
    ],
)
def test_parse_knn_k(body: dict, want: int) -> None:
    assert parse_knn_k(body) == want


def test_coerce_embedding_valid() -> None:
    assert coerce_query_embedding({"query_embedding": [0.5, -1.0]}) == [0.5, -1.0]


def test_coerce_embedding_invalid() -> None:
    assert coerce_query_embedding({"query_embedding": [1, "z"]}) is None
    assert coerce_query_embedding({}) is None


def test_pad_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "4")
    assert pad_query_vector([1.0]) == [1.0, 0.0, 0.0, 0.0]
    assert pad_query_vector([1, 2, 3, 4]) == [1.0, 2.0, 3.0, 4.0]


def test_live_requires_client() -> None:
    st, err = run_dense_search(
        search_mode="live",
        os_client=None,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={"query_embedding": [0.0, 1.0]},
        query_text="",
    )
    assert st == 503
    assert err["title"]


def test_live_requires_query_embedding() -> None:
    cli = MagicMock()
    st, err = run_dense_search(
        search_mode="live",
        os_client=cli,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={},
        query_text="q",
    )
    assert st == 400
    assert "query_embedding" in err["detail"]
    cli.search.assert_not_called()


def test_live_hybrid_query_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    client = MagicMock()
    client.search.return_value = {"hits": {"total": 0, "hits": []}}
    st, payload = run_dense_search(
        search_mode="live",
        os_client=client,
        index_name="chunks",
        tenant_id="t1",
        kb_id="kb1",
        body={
            "hybrid": True,
            "query_embedding": [1.0, 0.0],
            "k": 8,
            "bm25_weight": 2,
            "vector_weight": 0.5,
            "min_score": 0.1,
        },
        query_text="  lexical q  ",
    )
    assert st == 200
    assert payload["backend"] == "opensearch-serverless-hybrid"
    sb = client.search.call_args.kwargs["body"]
    qb = sb["query"]["bool"]
    assert qb["filter"] == [{"term": {"tenant_id": "t1"}}, {"term": {"kb_id": "kb1"}}]
    assert qb["minimum_should_match"] == 1
    should = qb["should"]
    assert len(should) == 2
    mm = should[0]["multi_match"]
    assert mm["query"] == "lexical q"
    assert mm["fields"] == ["chunk_text"]
    assert mm["boost"] == 2.0
    knn_emb = should[1]["knn"]["embedding"]
    assert knn_emb["vector"] == [1.0, 0.0]
    assert knn_emb["k"] == 8
    assert knn_emb["boost"] == 0.5
    assert sb["min_score"] == 0.1


def test_live_hybrid_requires_nonempty_q() -> None:
    cli = MagicMock()
    st, err = run_dense_search(
        search_mode="live",
        os_client=cli,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={"hybrid": True, "query_embedding": [0.5, 0.5]},
        query_text="   ",
    )
    assert st == 400
    assert "non-empty" in err["detail"] and "`q`" in err["detail"]
    cli.search.assert_not_called()


def test_live_hybrid_requires_embedding() -> None:
    cli = MagicMock()
    st, err = run_dense_search(
        search_mode="live",
        os_client=cli,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={"hybrid": True},
        query_text="ok",
    )
    assert st == 400
    assert "query_embedding" in err["detail"]
    cli.search.assert_not_called()


def test_live_hybrid_weights_cannot_both_be_zero() -> None:
    cli = MagicMock()
    st, err = run_dense_search(
        search_mode="live",
        os_client=cli,
        index_name="idx",
        tenant_id="t1",
        kb_id="kb1",
        body={
            "hybrid": True,
            "query_embedding": [1.0, 2.0],
            "bm25_weight": 0,
            "vector_weight": 0,
        },
        query_text="x",
    )
    assert st == 400
    assert "both" in err["detail"].lower()
    cli.search.assert_not_called()


def test_live_maps_opensearch_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "hid1",
                    "_score": 0.9,
                    "_source": {
                        "chunk_text": "hello",
                        "metadata": {"page": 1},
                        "tenant_id": "t1",
                    },
                },
                {
                    "_id": "hid2",
                    "_score": 0.11,
                    "_source": {
                        "chunk_text": "",
                        "metadata": [],
                    },
                },
            ],
        }
    }

    st, payload = run_dense_search(
        search_mode="live",
        os_client=client,
        index_name="chunks",
        tenant_id="t1",
        kb_id="kb1",
        body={"query_embedding": [1.0, 0.0], "min_score": 0.05, "k": 5},
        query_text="",
    )
    assert st == 200
    sb = client.search.call_args.kwargs["body"]
    assert sb["query"]["bool"]["must"][0]["knn"]["embedding"]["vector"] == [1.0, 0.0]
    assert sb["min_score"] == 0.05
    assert len(payload["hits"]) == 2
    assert payload["hits"][0]["id"] == "hid1"
    assert payload["hits"][0]["text"] == "hello"
    assert payload["hits"][0]["score"] == 0.9
    assert payload["hits"][0]["metadata"] == {"page": 1}
    assert payload["hits"][1]["metadata"] is None
    assert payload["backend"] == "opensearch-serverless-knn"


def test_live_maps_plain_total(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    client = MagicMock()
    client.search.return_value = {"hits": {"total": 3, "hits": []}}
    st, payload = run_dense_search(
        search_mode="live",
        os_client=client,
        index_name="chunks",
        tenant_id="t1",
        kb_id="kb1",
        body={"query_embedding": [1.0, 0.0]},
        query_text="",
    )
    assert st == 200
    assert payload["total"] == 3


def test_live_opensearch_maps_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    from opensearchpy.exceptions import TransportError

    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIM", "2")
    client = MagicMock()
    client.search.side_effect = TransportError("GET", {}, None)
    st, payload = run_dense_search(
        search_mode="live",
        os_client=client,
        index_name="chunks",
        tenant_id="t",
        kb_id="k",
        body={"query_embedding": [1.0, 0.0]},
        query_text="",
    )
    assert st == 502
    assert "Search failed" in payload["title"]
