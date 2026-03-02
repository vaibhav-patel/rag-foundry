# ADR 0006: OpenSearch chunk index contract

## Status

Accepted

## Context

ADR [0004](0004-vector-backend-opensearch-serverless.md) chose OpenSearch Serverless. Workers and the control plane need a single, versioned **chunk document** schema before runtime wiring (index creates, bulk index, search).

## Decision

### Index naming

| Item | Convention |
|------|-------------|
| **Logical prefix** | `rag-foundry-chunks` (physical index name MAY include a `-vN` suffix when we rev mappings). |
| **Env var** | `OPENSEARCH_INDEX_NAME` defaults to **`rag-foundry-chunks`** on API + worker Lambdas (set in CDK alongside `OPENSEARCH_ENDPOINT`). |

### Routing / isolation

Routing is explicit in documents (no `_routing` reliance in v1):

- **`tenant_id`** (`keyword`): Cognito JWT tenant / `sub`-derived partition (same string as Dynamo `PK` suffix without prefix if applicable).
- **`kb_id`** (`keyword`): KB identifier from `/v1/kbs/{kbId}`.
- Queries always filter **`tenant_id` + `kb_id`** to enforce isolation at search time.

### Fields

| Field | OpenSearch type | Role |
|--------|-----------------|------|
| **`chunk_text`** | `text` | BM25 / `multi_match` body. |
| **`embedding`** | `knn_vector` | Dense retrieval; **`dimension`** must match KB `embedding_model_id` output (operators choose index template per model once multi-dim lands). |

### Embedding field name (`_knn_vector` clarified)

Historical AWS samples sometimes label the vector field logically as “knn\_vector”; the **property name we standardize on** is **`embedding`**, with OpenSearch **`type`** = **`knn_vector`**.

### Operational notes

- **No runtime wiring in this ADR commit** — this file plus the frozen JSON snippet are the agreement point for worker ingest and API search.
- **Mapping implementation** ships as **`packages/contracts/opensearch/chunk-index-v1-mapping.json`** (referenced from OpenAPI / worker docs paths when search is wired).

## Consequences

- Index-create + bulk payloads must populate `tenant_id`, `kb_id`, `chunk_text`, and `embedding` with this contract.
- Multi-model embedding dimensions imply either multiple index templates (`-v768`, `-1536`) or a single dimension per deployment until dynamic templates are evaluated.
