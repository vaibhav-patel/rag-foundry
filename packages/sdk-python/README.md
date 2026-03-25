# rag-foundry Python SDK

Thin **control-plane HTTP** wrapper (`stdlib` urllib) used by operators and tooling.

```python
from rag_foundry_sdk import ControlPlaneClient

c = ControlPlaneClient("https://your-control-plane.invalid", "jwt-or-empty-string")
hits = c.search(kb_id, {"q": "hello", "k": 10})
answer = c.query(kb_id, {"question": "What is indexed?", "k": 10})
```

Install editable from repo root: `pip install -e packages/sdk-python`.
