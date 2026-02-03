import importlib.util
import os

_path = os.path.join(os.path.dirname(__file__), "..", "lambda_stub", "chunking.py")
_spec = importlib.util.spec_from_file_location("chunking", _path)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(mod)


def test_fixed_char_chunks_overlap():
    t = "a" * 100
    parts = mod.fixed_char_chunks(t, max_chars=30, overlap=5)
    assert len(parts) >= 3
    assert "".join(parts)[:100] == t[:100]


def test_recursive_splits_on_newlines():
    t = "para one\n\npara two is longer " + "x" * 200
    parts = mod.recursive_char_chunks(t, max_chars=80)
    assert all(len(p) <= 80 for p in parts)
