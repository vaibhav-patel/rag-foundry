"""Unit tests for Bedrock Converse generation helpers."""

from __future__ import annotations

import pytest
from bedrock_generation import (
    _collect_converse_stream,
    canonical_prompt_sha256,
    resolve_max_tokens,
    resolve_model_id,
    resolve_temperature,
)


def test_prompt_sha_stable() -> None:
    assert len(canonical_prompt_sha256("s", "u")) == 64
    assert canonical_prompt_sha256("s", "u") != canonical_prompt_sha256("s", "v")


def test_resolve_model_id_prefers_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENERATION_MODEL_ID", raising=False)
    assert resolve_model_id("  x  ") == "x"
    assert resolve_model_id(None)[:7] == "anthrop"


def test_collect_converse_stream_deltas() -> None:
    evs = [
        {"contentBlockDelta": {"delta": {"text": "hel"}}},
        {"contentBlockDelta": {"delta": {"text": "lo"}}},
    ]
    assert _collect_converse_stream(evs) == "hello"


def test_infer_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_TOKENS", raising=False)
    monkeypatch.delenv("TEMPERATURE", raising=False)
    assert resolve_max_tokens() == 512
    assert resolve_temperature() is None
    monkeypatch.setenv("MAX_TOKENS", "256")
    monkeypatch.setenv("TEMPERATURE", "0.41")
    assert resolve_max_tokens() == 256
    assert resolve_temperature() == pytest.approx(0.41)
