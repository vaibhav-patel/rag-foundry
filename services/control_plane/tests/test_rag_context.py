"""Unit tests for RAG prompt context shaping."""

from __future__ import annotations

import pytest
from rag_context import format_rag_context, parse_context_char_budget, parse_context_k


def test_parse_context_char_budget_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTEXT_CHAR_BUDGET", raising=False)
    assert parse_context_char_budget() == 12000


def test_parse_context_char_budget_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_CHAR_BUDGET", "4096")
    assert parse_context_char_budget() == 4096


def test_parse_context_k_from_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_K_DEFAULT", "5")
    assert parse_context_k({}) == 5
    assert parse_context_k({"context_k": 3}) == 3


def test_format_rag_context_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_K_DEFAULT", "8")
    hits = [
        {"id": "a", "score": 1.0, "text": "x" * 200, "metadata": None},
        {"id": "b", "score": 1.0, "text": "y" * 200, "metadata": None},
    ]
    blob, cites = format_rag_context(hits, context_k=parse_context_k({}), char_budget=80)
    assert len(blob) <= 80
    assert len(cites) == 2
    assert cites[0]["id"] == "a"


def test_parse_context_k_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_K_DEFAULT", "99")
    assert parse_context_k({}) == 50
