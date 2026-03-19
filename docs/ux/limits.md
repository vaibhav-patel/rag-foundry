# Limits and throttles (defaults)

This document records **default** control-plane limits. Production values should be tuned from traffic, SLOs, and account concurrency caps.

## API Gateway HTTP API (edge throttling)

Throttling is applied on the **`$default`** stage to **specific routes** (not the whole API). Steady rate is **requests per second (RPS)**; burst allows short spikes.

| Route | Method | Throttling rate limit (RPS) | Burst limit |
|-------|--------|----------------------------:|-------------:|
| `/v1/kbs/{kbId}/query` | `POST` | **20** | **40** |
| `/v1/kbs/{kbId}/search` | `POST` | **60** | **120** |

Constants live in `infra/rag_foundry_infra/stacks/rag_foundry_stack.py` as `_HTTP_THROTTLE_QUERY_*` and `_HTTP_THROTTLE_SEARCH_*`.

When API Gateway throttles a client, it returns **HTTP 429** (before the Lambda runs for that request).

## Lambda reserved concurrency (optional)

Reserved concurrency removes executions from the **regional** unreserved pool and assigns them to one function. It is **off by default** so stacks do not unexpectedly starve other Lambdas in the same account.

To enable, set CDK **context** (e.g. in `cdk.json` or `cdk.context.json`):

| Context key | Applies to | Effect |
|-------------|------------|--------|
| `controlPlaneReservedConcurrency` | Control plane Lambda (`ControlPlaneFn`) | Positive integer → `reserved_concurrent_executions` |
| `workerReservedConcurrency` | Ingest worker Lambda (`WorkerFn`) | Positive integer → `reserved_concurrent_executions` |

**Alignment:** If you reserve control-plane concurrency, keep it **at or above** the steady API Gateway RPS you allow for `/query` and `/search` (plus other routes on the same Lambda), or throttles will reject traffic while capacity sits unused in the reserve. Bursts need extra headroom above steady RPS.

## Per-tenant daily quota (application layer)

Separate from API Gateway: DynamoDB conditional counters per tenant per UTC day (`SK=QUOTA#YYYY-MM-DD`). See Lambda env **`TENANT_REQUESTS_PER_DAY`** (default **100000** in CDK) and tenant **`SETTINGS#tenant`** overrides (`quota_exempt`, `requests_per_day_limit`).

## Related

- OpenAPI `DailyQuotaExceeded` and route **429** responses describe the tenant quota body shape.
- API Gateway **429** responses from throttling use API Gateway’s standard error format (not necessarily the same JSON body as application quotas).
