"""Tests for opensearch_client (loaded from lambda/ without package prefix)."""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest

_path = os.path.join(os.path.dirname(__file__), "..", "lambda", "opensearch_client.py")
_spec = importlib.util.spec_from_file_location("opensearch_client", _path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_mod)


def test_returns_none_when_no_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENSEARCH_ENDPOINT", raising=False)
    assert _mod.create_opensearch_client(endpoint="") is None
    assert _mod.create_opensearch_client(endpoint=None) is None


def test_raises_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSEARCH_ENDPOINT", "https://xyz.us-east-1.aoss.amazonaws.com")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    sess = MagicMock()
    sess.get_credentials.return_value = None
    with patch.object(_mod.boto3, "Session", return_value=sess):
        with pytest.raises(RuntimeError, match="No AWS credentials"):
            _mod.create_opensearch_client()


def test_opensearch_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("OPENSEARCH_ENDPOINT", raising=False)

    sess = MagicMock()
    fc = MagicMock()
    fc.access_key = "A"
    fc.secret_key = "S"
    fc.token = "T"
    creds = MagicMock()
    creds.get_frozen_credentials.return_value = fc
    sess.get_credentials.return_value = creds

    fake_client = MagicMock()
    with patch.object(_mod.boto3, "Session", return_value=sess):
        with patch.object(_mod, "OpenSearch", return_value=fake_client) as osp:
            out = _mod.create_opensearch_client(endpoint="https://abc.us-east-1.aoss.amazonaws.com")
            assert out is fake_client
    kwargs = osp.call_args.kwargs
    assert kwargs["hosts"] == [{"host": "abc.us-east-1.aoss.amazonaws.com", "port": 443}]
    assert kwargs["use_ssl"] is True
    assert kwargs["connection_class"] is _mod.RequestsHttpConnection
