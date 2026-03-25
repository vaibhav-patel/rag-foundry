"""Offline checks for ControlPlaneClient."""

from __future__ import annotations

from unittest.mock import patch

from rag_foundry_sdk.client import ControlPlaneClient


def test_client_normalizes_base_url() -> None:
    c = ControlPlaneClient("https://api.example.com/", "jwt")
    assert c.base_url == "https://api.example.com"


def test_search_posts_dense_body() -> None:
    client = ControlPlaneClient("https://api.example.com", "")
    with patch.object(client, "_request", return_value={"hits": []}) as rq:
        client.search("my-kb", {"q": "dogs", "k": 12})
        rq.assert_called_once_with("POST", "/v1/kbs/my-kb/search", body={"q": "dogs", "k": 12})


def test_search_empty_body_when_omitted() -> None:
    client = ControlPlaneClient("https://api.example.com", "")
    with patch.object(client, "_request", return_value={}) as rq:
        client.search("x")
        rq.assert_called_once_with("POST", "/v1/kbs/x/search", body={})


def test_query_posts_rag_body() -> None:
    client = ControlPlaneClient("https://api.example.com", "")
    body = {"question": "why?", "q": "why?", "k": 8}
    with patch.object(client, "_request", return_value={}) as rq:
        client.query("kb", body)
        rq.assert_called_once_with("POST", "/v1/kbs/kb/query", body=body)
