# ADR 0003: Tenancy on DynamoDB single-table

## Status

Accepted

## Decision

Store tenant-scoped rows under `PK = TENANT#{tenant_id}` with typed sort keys (`SK = KB#{id}`, etc.). Use Cognito `sub` (or `custom:tenant_id`) as tenant identifier for MVP.

## Consequences

- Cross-tenant reads must always include PK scoped to caller claims.
- GSIs back secondary access patterns (e.g. jobs by status).
