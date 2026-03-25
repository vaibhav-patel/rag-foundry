"""Typer CLI smoke tests (mocked HTTP via ControlPlaneClient)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from rag_foundry_cli.main import app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def test_health_json_compact(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MagicMock()
    mock.health.return_value = {"status": "ok"}
    monkeypatch.setattr("rag_foundry_cli.main._sdk", lambda: mock)
    res = runner.invoke(app, ["--json", "health"], env={"RAG_FOUNDRY_API_URL": "http://example.invalid"})
    assert res.exit_code == 0
    assert res.stdout.strip() == '{"status":"ok"}'
    mock.health.assert_called_once()


def test_search_forwards_body(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MagicMock()
    mock.search.return_value = {"hits": [], "total": 0, "backend": "stub"}
    monkeypatch.setattr("rag_foundry_cli.main._sdk", lambda: mock)
    res = runner.invoke(
        app,
        ["--json", "search", "kb-1", "hello", "--k", "3", "--hybrid"],
        env={"RAG_FOUNDRY_API_URL": "http://example.invalid"},
    )
    assert res.exit_code == 0
    mock.search.assert_called_once_with("kb-1", {"q": "hello", "k": 3, "hybrid": True})


def test_query_forwards_body(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MagicMock()
    mock.query.return_value = {
        "answer": "x",
        "citations": [],
        "kb_id": "kb-1",
        "guardrails_applied": False,
    }
    monkeypatch.setattr("rag_foundry_cli.main._sdk", lambda: mock)
    res = runner.invoke(
        app,
        ["query", "kb-1", "What is up?"],
        env={"RAG_FOUNDRY_API_URL": "http://example.invalid"},
    )
    assert res.exit_code == 0
    mock.query.assert_called_once_with(
        "kb-1",
        {"question": "What is up?", "q": "What is up?", "k": 5},
    )
    assert "\n" in res.stdout  # pretty-printed default
