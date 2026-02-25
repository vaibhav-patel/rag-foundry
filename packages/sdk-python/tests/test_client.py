"""Offline checks for ControlPlaneClient."""

from __future__ import annotations

from rag_foundry_sdk.client import ControlPlaneClient


def test_client_normalizes_base_url() -> None:
    c = ControlPlaneClient("https://api.example.com/", "jwt")
    assert c.base_url == "https://api.example.com"
