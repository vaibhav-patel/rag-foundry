import importlib.util
import os

_path = os.path.join(os.path.dirname(__file__), "..", "lambda", "vector_stub.py")
_spec = importlib.util.spec_from_file_location("vector_stub", _path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_mod)


def test_dense_search_stub_shape():
    r = _mod.dense_search_stub(endpoint="https://x", collection_name="c", query_text="q")
    assert r["hits"] == []
    assert r["backend"] == "opensearch-serverless-stub"
