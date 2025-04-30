# ADR 0004: Vector backend — Amazon OpenSearch Serverless

## Status

Accepted

## Decision

Use **OpenSearch Serverless** vector collection for dense + BM25 hybrid search in later milestones. Aurora `pgvector` remains a documented alternative if cost or SQL semantics win.

## Consequences

- Data access policies must list Lambda execution roles.
- Collection endpoint is injected into Lambdas as `OPENSEARCH_ENDPOINT`.
