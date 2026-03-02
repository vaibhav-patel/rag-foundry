# OpenSearch artefacts

| File | Purpose |
|------|--------|
| [chunk-index-v1-mapping.json](chunk-index-v1-mapping.json) | Frozen **`mappings`** (+ index `settings`) for ADR **0006** chunk index (`rag-foundry-chunks`). |

Regenerate or bump `v1` when field types or `knn_vector` `method` / `ef_construction` change; keep OpenAPI + worker code in sync.
