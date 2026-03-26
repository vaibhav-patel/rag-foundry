# rag-foundry Python SDK

Thin **control-plane HTTP** wrapper (`stdlib` urllib) used by operators and tooling.

```python
from rag_foundry_sdk import ControlPlaneClient

c = ControlPlaneClient("https://your-control-plane.invalid", "jwt-or-empty-string")

# Untyped decoded JSON:
raw = c.search(kb_id, {"q": "hello", "k": 10})
raw_q = c.query(kb_id, {"question": "What is indexed?", "k": 10})

# Typed payloads (same HTTP calls):
dense = c.search_kb(kb_id, {"q": "hello", "k": 10})  # DenseSearchResponse
rag = c.query_kb(kb_id, {"question": "What is indexed?", "k": 10})  # RagQueryResponse
print(dense.hits[0].text, rag.answer)
```

Install editable from repo root: `pip install -e packages/sdk-python`.
