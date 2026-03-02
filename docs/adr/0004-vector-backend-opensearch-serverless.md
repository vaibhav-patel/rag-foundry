# ADR 0004: Vector backend — Amazon OpenSearch Serverless

## Status

Accepted

## Decision

Use **OpenSearch Serverless** vector collection for dense + BM25 hybrid search in later milestones. Aurora `pgvector` remains a documented alternative if cost or SQL semantics win.

## Consequences

- Data access policies must list Lambda execution roles.
- Collection endpoint is injected into Lambdas as `OPENSEARCH_ENDPOINT`.
- Chunk index field layout and **`OPENSEARCH_INDEX_NAME`** are fixed in ADR **[0006](0006-opensearch-chunk-index-contract.md)** plus `packages/contracts/opensearch/chunk-index-v1-mapping.json`.
