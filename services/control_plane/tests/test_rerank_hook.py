"""Tests for optional dense-search rerank hook."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import rerank_hook


@pytest.fixture(autouse=True)
def _reset_rerank_arn_cache() -> None:
    rerank_hook._rerank_lambda_arn_cached = False  # type: ignore[attr-defined]
    yield
    rerank_hook._rerank_lambda_arn_cached = False  # type: ignore[attr-defined]


def test_dense_search_fetch_size_no_rerank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.delenv("RERANK_URL", raising=False)
    assert rerank_hook.dense_search_fetch_size(5) == 5
    assert rerank_hook.dense_search_fetch_size(100) == 100


def test_dense_search_fetch_size_with_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.setenv("RERANK_URL", "https://internal.example/rerank")
    assert rerank_hook.dense_search_fetch_size(5) == 20
    assert rerank_hook.dense_search_fetch_size(50) == 50


def test_rerank_dense_hits_ranked_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.setenv("RERANK_URL", "https://internal.example/rerank")
    payload = {
        "hits": [
            {"id": "a", "score": 0.9, "text": "first", "metadata": None},
            {"id": "b", "score": 0.1, "text": "second", "metadata": None},
        ],
        "total": 2,
        "backend": "opensearch-serverless-knn",
    }
    with patch.object(
        rerank_hook,
        "_post_http_rerank",
        return_value={"ranked_ids": ["b", "a"]},
    ):
        out = rerank_hook.rerank_dense_hits_maybe(
            payload,
            query_text="q",
            desired_top_k=2,
        )
    assert out["reranked"] is True
    assert [h["id"] for h in out["hits"]] == ["b", "a"]


def test_rerank_dense_hits_truncates_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERANK_LAMBDA_ARN", raising=False)
    monkeypatch.delenv("RERANK_LAMBDA_ARN_PARAMETER", raising=False)
    monkeypatch.delenv("RERANK_URL", raising=False)
    payload = {
        "hits": [
            {"id": str(i), "score": 1.0, "text": "t", "metadata": None}
            for i in range(15)
        ],
        "total": 15,
        "backend": "x",
    }
    out = rerank_hook.rerank_dense_hits_maybe(payload, query_text="", desired_top_k=3)
    assert "reranked" not in out
    assert len(out["hits"]) == 3
    assert out["hits"][0]["id"] == "0"
