"""Control-plane client tests (``urllib.request.urlopen`` mocked)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from rag_foundry_sdk.client import ControlPlaneClient
from rag_foundry_sdk.types import (
    DenseSearchHit,
    DenseSearchResponse,
    RagQueryResponse,
    ResponseShapeError,
)


class _DummyCm:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _DummyCm:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _urlopen_factory(calls: list[tuple[Any, float]], body: bytes):
    def _opener(req: Any, timeout: float) -> _DummyCm:
        calls.append((req, timeout))
        return _DummyCm(body)

    return _opener


def test_client_normalizes_base_url() -> None:
    c = ControlPlaneClient("https://api.example.com/", "jwt")
    assert c.base_url == "https://api.example.com"


def test_search_posts_dense_payload_and_search_kb_returns_dataclasses() -> None:
    calls: list[tuple[Any, float]] = []
    api_body = {
        "kb_id": "my-kb",
        "hits": [{"id": "h1", "score": 0.25, "text": "chunk", "metadata": {"x": 1}}],
        "total": 1,
        "backend": "stub",
        "reranked": True,
    }
    opener = _urlopen_factory(calls, json.dumps(api_body).encode())

    client = ControlPlaneClient("https://api.example.com", "")
    with patch("rag_foundry_sdk.client.urlopen", side_effect=opener):
        out = client.search_kb("my-kb", {"q": "dogs", "k": 12})

    assert isinstance(out, DenseSearchResponse)
    assert out.kb_id == "my-kb"
    assert out.backend == "stub"
    assert out.total == 1
    assert out.reranked is True
    assert len(out.hits) == 1
    assert isinstance(out.hits[0], DenseSearchHit)
    assert out.hits[0].id == "h1"
    assert out.hits[0].score == pytest.approx(0.25)
    assert out.hits[0].text == "chunk"
    assert out.hits[0].metadata == {"x": 1}

    assert len(calls) == 1
    req, timeout = calls[0]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/v1/kbs/my-kb/search")
    sent = json.loads(req.data.decode("utf-8"))
    assert sent == {"q": "dogs", "k": 12}
    assert timeout == pytest.approx(client.timeout_s)


def test_search_empty_body_when_using_search_not_kb() -> None:
    calls: list[tuple[Any, float]] = []
    opener = _urlopen_factory(calls, b"{}")
    client = ControlPlaneClient("https://api.example.com", "")
    with patch("rag_foundry_sdk.client.urlopen", side_effect=opener):
        assert client.search("x") == {}

    req, _ = calls[0]
    sent = json.loads(req.data.decode("utf-8")) if req.data else {}
    assert sent == {}


def test_query_posts_rag_body_and_query_kb_returns_model() -> None:
    calls: list[tuple[Any, float]] = []
    body = {"question": "why?", "q": "why?", "k": 8}
    api_body = {
        "answer": "because",
        "citations": [{"id": "c1"}, {"id": "c2"}],
        "kb_id": "kb",
        "guardrails_applied": False,
    }
    opener = _urlopen_factory(calls, json.dumps(api_body).encode())
    client = ControlPlaneClient("https://api.example.com", "")
    with patch("rag_foundry_sdk.client.urlopen", side_effect=opener):
        out = client.query_kb("kb", body)

    assert isinstance(out, RagQueryResponse)
    assert out.answer == "because"
    assert out.kb_id == "kb"
    assert out.guardrails_applied is False
    assert [c.id for c in out.citations] == ["c1", "c2"]

    req, _ = calls[0]
    assert req.full_url.endswith("/v1/kbs/kb/query")
    assert json.loads(req.data.decode("utf-8")) == body


def test_search_kb_raises_response_shape_error_on_bad_hit() -> None:
    api_body = {
        "kb_id": "my-kb",
        "hits": ["not-an-object"],
        "total": 0,
        "backend": "stub",
    }
    client = ControlPlaneClient("https://api.example.com", "")
    body = json.dumps(api_body).encode()
    opener = _urlopen_factory([], body)
    with patch("rag_foundry_sdk.client.urlopen", side_effect=opener):
        with pytest.raises(ResponseShapeError, match="hits\\[0\\]"):
            client.search_kb("my-kb", {"q": "x"})


def test_search_kb_raises_on_non_object_payload() -> None:
    client = ControlPlaneClient("https://api.example.com", "")
    with patch(
        "rag_foundry_sdk.client.urlopen",
        side_effect=_urlopen_factory([], b'"string-not-object"'),
    ):
        with pytest.raises(ResponseShapeError, match="expected JSON object"):
            client.search_kb("my-kb", {})
