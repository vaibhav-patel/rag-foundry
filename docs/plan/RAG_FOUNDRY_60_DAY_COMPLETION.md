# rag-foundry — 60-day completion plan (2026-03-02 → 2026-04-30)

One **logical step per calendar day**. Each row is **3–4 lines** of intended changes (design / files / behaviour). **Not started** — this document is the backlog only.

**Anchor:** “Today” = **2026-04-30** (plan ends with release-ready MVP + hardening).

---

### 2026-03-02 — OpenSearch index contract

- Define index name pattern, `_knn_vector` field name, `text` field for BM25, and tenant/KB routing in a small spec under `docs/adr/` or `packages/contracts/`.
- Add JSON mapping snippet (knn params, `ef_construction`) versioned beside OpenAPI notes.
- No runtime behaviour change yet; aligns worker + API on one schema.

### 2026-03-03 — IAM: index + bulk permissions

- Extend CDK data access policy JSON so worker + API roles may `aoss:WriteDocument`, `aoss:ReadDocument` on the vector index prefix (least privilege vs current broad stubs).
- Add condition keys or resource ARNs matching collection + index from ADR 0004.
- Output any new ARNs via `CfnOutput` for runbooks only if needed.

### 2026-03-04 — Python: opensearch-py + SigV4 client helper

- Add `opensearch-py` + `requests-aws4auth` (or `aws-requests-auth`) to control-plane and worker dependency sets (`pyproject.toml` / Lambda layers).
- New module `services/control_plane/lambda/opensearch_client.py` (and worker twin) building a signed client from `OPENSEARCH_ENDPOINT` + role credentials.
- Unit-test client factory with mocked `boto3` session (no live cluster).

### 2026-03-05 — Create index Lambda-side (idempotent)

- Worker or a tiny “ensure index” step: `HEAD` index → `PUT` with mapping if missing; safe on cold start and redeploy.
- Wire index name from env `OPENSEARCH_INDEX_NAME` default `rag-foundry-chunks`.
- Log create/skip at INFO for support.

### 2026-03-06 — Chunk document schema (bulk payload)

- Define `_id` = deterministic hash(tenant, kb_id, job_id, chunk_idx) to avoid duplicates on retry.
- Document body: `kb_id`, `tenant`, `s3_key`, `chunk_text`, `embedding` (knn_vector), optional `metadata` map.
- Add pydantic-style dict builder in worker shared helper (no new runtime dep if avoiding pydantic in Lambda).

### 2026-03-07 — Worker: bulk index after embed

- After manifest write, call OpenSearch `bulk` with N chunks per batch (configurable env `BULK_BATCH_SIZE`).
- Partial failure: record failed item ids in manifest `errors[]` and still transition job to `PARTIAL` vs `FAILED` (enum in DDB).
- Extend Step Functions or worker return payload so control plane can surface partial state.

### 2026-03-08 — Worker: Bedrock embed error paths

- Normalize throttling / `AccessDeniedException` into structured manifest field `embed_errors`.
- Exponential backoff wrapper (max attempts from env) around `invoke_model`.
- CloudWatch metric `EmbedFailure` count increment (embedded log metric filter or EMF stub).

### 2026-03-09 — DDB: job status enum + GSI query fix

- Formalize `QUEUED | RUNNING | SUCCEEDED | PARTIAL | FAILED` on job items; migration-safe for existing `QUEUED`/`SUCCEEDED`.
- Fix any job lookup paths to use PK/SK consistent with `KB#` + `JOB#` (already mostly true); add `GSI1SK` prefix query tests.
- OpenAPI + `packages/contracts` examples updated for job status.

### 2026-03-10 — API: `GET /v1/jobs/{id}` by PK/SK

- Replace or supplement GSI scan with direct `get_item` when `kb_id` is passed as query param, or store `kb_id` on job item for O(1) get (already have `kb_id` in Step Functions payload — persist on job `put_item`).
- Return `manifest_key`, `chunk_count`, `embed_model` in JSON for UI polling.
- Contract tests for handler shape.

### 2026-03-11 — `vector_stub` → real `dense_search`

- Implement `dense_search` using kNN query on `embedding` with `min_score` / `k` from request body.
- Map OpenSearch hits to `{id, score, text, metadata}` list for API response.
- Keep stub behind feature flag env `SEARCH_MODE=stub|live` for CI without AOSS.

### 2026-03-12 — Hybrid search (BM25 + vector)

- Build `bool` should: `multi_match` on `chunk_text` + `knn` on vector; combine scores (simple weighted sum first).
- Request body: `hybrid: true`, `bm25_weight`, `vector_weight`.
- Document latency trade-offs in `docs/runbooks/`.

### 2026-03-13 — Rerank hook (optional Lambda)

- Define interface `POST` internal URL or sync invoke for reranker; pass top 20 hits, return top `k`.
- CDK: optional SSM param `RERANK_LAMBDA_ARN`; no-op if unset.
- Control plane merges reranked order before response.

### 2026-03-14 — Query path: load chunks for RAG

- `POST /v1/kbs/{id}/query`: run search internally (reuse `dense_search`), take top `context_k`, truncate to token budget env `CONTEXT_CHAR_BUDGET`.
- Replace `"Context: (stub)"` with concatenated chunk excerpts + source ids.
- Add integration test with `SEARCH_MODE=stub` + fake hits injected.

### 2026-03-15 — Bedrock converse / ConverseStream for query

- Switch from raw `invoke_model` string to **Converse API** with system prompt + user message list for Claude / Titan Text where configured.
- Env `GENERATION_MODEL_ID`, `MAX_TOKENS`, `TEMPERATURE`.
- Store raw prompt hash + model id on audit item (next day) stub field.

### 2026-03-16 — Guardrails passthrough + validation

- Wire `guardrailIdentifier` / `guardrailVersion` from KB item or tenant defaults through to Bedrock calls.
- Validate request body JSON schema (reuse `packages/contracts` JSON Schema fragments).
- Return 400 with schema errors before calling Bedrock.

### 2026-03-17 — Query audit trail (DynamoDB)

- New item pattern `PK=TENANT#`, `SK=QUERYAUDIT#<iso>#<uuid>` or GSI for time-range queries.
- Persist: `kb_id`, `question` hash, `answer` length, `model_id`, `latency_ms`, `hit_ids`.
- TTL attribute optional for cost control.

### 2026-03-18 — Quotas: requests per tenant

- Table or in-memory Redis later — start with DDB conditional counters per tenant per day `QUOTA#<date>` item.
- Middleware in handler: increment + fail 429 when over limit (configurable default).
- Admin override flag on tenant record (future UI).

### 2026-03-19 — Rate limit API Gateway (throttle)

- CDK `throttleSettings` / `ThrottlingBurstLimit` on HTTP API routes for `/query` and `/search`.
- Align with Lambda concurrency reserved (optional `reserved_concurrent_executions` on hot Lambdas).
- Document default numbers in `docs/ux/limits.md`.

### 2026-03-20 — Web: OpenAPI-generated types for forms

- Add `openapi-typescript` or `@hey-api/openapi-ts` script in `web/package.json` generating `src/api/types.ts` from `packages/contracts/openapi/control-plane.yaml`.
- Replace hand-wired fetch bodies in KB wizard / Playground with typed payloads.
- CI job: `npm run generate` + fail on drift (`git diff --exit-code`).

### 2026-03-21 — Web: KB create/edit full schema

- Form fields for `embedding_model_id`, `chunk_chars`, `hybrid`, `generation_model_id`, `guardrail` ids.
- Validate against generated types client-side; show server 400 messages inline.
- TanStack Query mutations with optimistic disabled (server truth).

### 2026-03-22 — Web: job timeline live polling

- Poll `GET /v1/jobs/{id}` with exponential backoff cap; show `PARTIAL` / `FAILED` with manifest link (presigned GET for manifest in API — new route `GET /v1/jobs/{id}/manifest`).
- Presign short-lived GET on `derived/.../manifest.json` via same raw bucket policy.
- Empty state when no jobs.

### 2026-03-23 — Web: search results panel

- Dedicated component listing hits with score + snippet highlight (simple `<mark>` from query terms).
- “Send to query” button prefills Playground question.
- Accessibility: list roles / keyboard nav.

### 2026-03-24 — Web: query view streaming (optional)

- If API adds streaming, use `fetch` reader + incremental UI; else simulate with typing effect for non-streaming response.
- Cancel in-flight on unmount (AbortController).
- Error boundary for Bedrock failures with retry.

### 2026-03-25 — CLI: parity with new APIs

- `rag-foundry search`, `rag-foundry query` Typer commands using `ControlPlaneClient` (extend SDK with `search`, `query` methods).
- Shared `--json` output flag for CI smoke tests.
- Shell completion stub (`--help` examples in README).

### 2026-03-26 — SDK: search/query + types

- Extend `packages/sdk-python` with `search_kb`, `query_kb` returning typed dicts or dataclasses.
- Version bump minor; changelog entry.
- Pytest with `urllib` `Mock` for HTTP responses.

### 2026-03-27 — Plugin manifest execution (document processor)

- Define S3 or ECR image URI on plugin manifest; worker `extract` stage invokes plugin Lambda (async) or pulls container (Fargate path documented only).
- MVP: **invoke** plugin Lambda with payload `{s3_bucket, s3_key, tenant}`; merge returned text into pipeline.
- Timeout + DLQ for plugin invocation.

### 2026-03-28 — Plugin: chunker override

- If manifest declares `chunker`, call plugin with text + `chunk_chars`; else default `recursive_char_chunks`.
- Contract JSON schema for plugin response under `packages/contracts/jsonschemas/`.
- Golden-file test for chunker adapter.

### 2026-03-29 — Plugin: embedder override

- Same pattern as chunker; response must be `float[]` per chunk or batch.
- Fallback to Titan/hash stub on contract violation (log + metric).
- Document security: plugin role must trust worker role for `lambda:InvokeFunction`.

### 2026-03-30 — Retriever plugin hook (post-search)

- After OpenSearch hits, optional plugin receives hits + query; returns reordered ids.
- Wire similarly to rerank hook; unify “post-retrieval” pipeline in one internal function list.
- Feature flag per KB `plugins.retrieval_enabled`.

### 2026-03-31 — Step Functions: explicit branches

- ASL JSON: parallel embed batches → join → index → finalize; `Catch` to SNS on failure.
- Pass `manifest_key` between states; reduce Lambda payload size.
- CDK unit snapshot test for state machine definition fragment.

### 2026-04-01 — S3 lifecycle: raw + derived retention

- Lifecycle rules: transition `derived/` to IA after N days; expire old job manifests after TTL from KB config.
- Raw objects: optional legal hold flag documented only (no code until policy).
- Emit inventory metrics to dashboard.

### 2026-04-02 — KMS: envelope patterns for optional CMK

- If customer CMK for bucket: grant Lambda decrypt; document in `docs/credentials.md`.
- Default AWS-managed S3 encryption unchanged for MVP path.
- CDK condition on `use_customer_managed_key` param.

### 2026-04-03 — Cognito: groups → tenant claim

- Post-auth Lambda or Pre-Token trigger to inject `custom:tenant_id` claim; API authorizer maps to `tenant` (already `sub`-based — align doc vs code).
- Migration note for existing pools.
- Web: read tenant from JWT decode helper.

### 2026-04-04 — API keys / M2M (stub → basic)

- Optional `POST /v1/tokens` for API key issuance (DDB hashed secret + prefix id); separate from Cognito user JWT.
- Usage tracked in audit; revoke path `DELETE`.
- ADR update `docs/adr/` for M2M.

### 2026-04-05 — WAF on CloudFront (optional stack param)

- `WebStaticStack` optional `WAF` association via `CfnWebACL` minimal managed rule set (AWSManagedRulesCommonRuleSet).
- Cost callout in stack README output.
- Default off via `context` flag.

### 2026-04-06 — CloudFront: custom error pages for SPA

- `403`/`404` → `/index.html` for client routing; short TTL.
- Security headers response policy (CSP baseline, `X-Content-Type-Options`).
- Invalidate script in `Makefile` target `web-publish`.

### 2026-04-07 — GitHub Actions: deploy web artifact

- Workflow on tag: `npm ci && npm run build` in `web/`, sync to bucket + invalidation using OIDC role (no long-lived keys).
- Pass `VITE_API_URL` from GitHub environment at build time.
- Artifact retention 7 days.

### 2026-04-08 — GitHub Actions: CDK deploy to dev

- `cdk deploy RagFoundryStack RagFoundryWebStack` with `CDK_DEFAULT_ACCOUNT` from OIDC; use `cdk diff` on PR.
- Secrets: only via GitHub Environments / OIDC — update `docs/credentials.md`.
- Concurrency group `dev-deploy` to avoid races.

### 2026-04-09 — Synthetic canary (canary script)

- `cli` command or `scripts/smoke.sh`: health → create KB → upload small file → job wait → search → query; exit non-zero on failure.
- Run nightly in GitHub Actions `schedule`.
- Publish summary to workflow summary markdown.

### 2026-04-10 — Dashboards: search/query latency widgets

- CloudWatch dashboard JSON: p50/p99 from Lambda embedded metric or log insights queries on API Lambda.
- Separate widget for worker duration vs chunk count.
- Link dashboard URL in `README.md`.

### 2026-04-11 — Alarms: error rate + DLQ depth

- `AWS/Lambda` Errors > threshold; Step Functions `ExecutionsFailed`; SQS DLQ `ApproximateNumberOfMessagesVisible`.
- SNS topic `rag-foundry-alerts` subscription placeholder (email opt-in via param).
- Runbook links in alarm description.

### 2026-04-12 — Logging: structured JSON

- Control plane + worker: one JSON log line per request with `tenant`, `kb_id`, `route`, `latency_ms`.
- Subscription filter to optional Firehose (disabled by default).
- Ruff/format pass on touched files.

### 2026-04-13 — X-Ray optional enable

- `AWS_XRAY_TRACING_NAME` + `Tracing.ACTIVE` for Lambdas; API Gateway integration tracing.
- Sampling rate 5% default param.
- Document cost in ADR snippet.

### 2026-04-14 — GDPR delete: implement tenant purge job

- Replace stub doc: Step Function or batch job listing `PK=TENANT#` items, S3 prefix deletes, OpenSearch delete-by-query `tenant` field.
- Admin API `POST /v1/tenants/{id}/purge` (superuser role — Cognito group `platform-admin`).
- Completion report written to S3 audit bucket.

### 2026-04-15 — Data retention: enforce KB-level TTL

- KB item field `retention_days_raw`, `retention_days_derived`; S3 lifecycle tags set on upload.
- Scheduled Lambda daily to enqueue purge for expired docs.
- Metrics for objects deleted.

### 2026-04-16 — SBOM: real Syft output in CI

- Replace `scripts/sbom.sh` stub with `syft packages dir:. -o spdx-json > sbom.json` artifact upload.
- Pin syft version; cache install.
- Policy: block critical CVEs (Trivy scan optional next day).

### 2026-04-17 — Trivy filesystem scan on `infra/` + `services/`

- CI job fails on CRITICAL (configurable ignore file `.trivyignore` documented).
- Separate job for container image built from `services/workers/Dockerfile`.
- Badge in README (optional).

### 2026-04-18 — Dependabot grouping + auto-merge policy doc

- `dependabot.yml`: group AWS SDK + group dev-tools; document human review for CDK major bumps.
- No bot auto-merge until tests green (policy in `CONTRIBUTING.md`).
- Quarterly review checklist.

### 2026-04-19 — Load test harness (Locust or k6)

- `tests/load/k6_search.js` hitting `/search` with ramp; run locally documented only (not in PR CI by default).
- Capture baseline RPS/latency in `docs/perf/baseline.md`.
- Env file template for load endpoint + JWT.

### 2026-04-20 — Cost visibility: AWS Budgets snippet

- CDK optional `CfnBudget` monthly forecast alert at 80% of soft cap param.
- Tag strategy: `Application=rag-foundry`, `Environment`, `Tenant` on billable resources where supported.
- Export tag keys in deployment doc.

### 2026-04-21 — Multi-AZ / HA notes (no full MR)

- ADR: active-active deferred; document failover for OpenSearch Serverless (regional) + Dynamo global tables off.
- Runbook: “region down” customer comms template.
- No infra change unless trivial subnet comment.

### 2026-04-22 — Backup: Dynamo PITR + S3 versioning

- Enable PITR on catalog table param default true; S3 versioning on raw bucket (lifecycle noncurrent versions expire).
- Restore drill doc one-pager.
- CDK snapshot update.

### 2026-04-23 — Secrets rotation runbook

- Expand `docs/credentials.md` with Cognito app client secret rotation (if used), Bedrock access patterns, no keys in repo.
- Link to AWS rotation lambda patterns (optional).
- Gitleaks pre-commit hook suggestion.

### 2026-04-24 — E2E test in AWS (CodeBuild or manual script)

- One CodeBuild project or `scripts/e2e_aws.sh` using real stack outputs from SSM; gated behind `RUN_E2E=1`.
- Creates KB, uploads 1 KB text, waits job, asserts search hit count > 0.
- Tear-down optional flag.

### 2026-04-25 — OpenAPI: full paths + examples

- Expand `control-plane.yaml` with `/search` body schema, `/query`, `/jobs/{id}/manifest`, error models `Problem+json`.
- Example payloads for hybrid search + query.
- Regenerate web types + SDK docstrings from same source.

### 2026-04-26 — `README.md` “production checklist”

- Section: deploy order, smoke tests, rollback (`cdk rollback`), known limits (OpenSearch OCUs).
- Link to all ADRs + this 60-day plan.
- Badges: CI, license.

### 2026-04-27 — `CHANGELOG.md` 1.0.0-rc

- Aggregate features since monorepo init; semver bump packages (`contracts`, `sdk`, `cli` patch/minor aligned).
- Tag `v1.0.0-rc.1` process documented (GitHub Release notes template).
- Migration notes for anyone on stub-only search.

### 2026-04-28 — Security review pass

- STRIDE-lite checklist in `docs/security/review-2026-04.md`; tick S3 public access block, IAM boundary (if org requires), API authZ on every route.
- Fix any findings (e.g. missing `Condition` on IAM).
- Second pair review note placeholder.

### 2026-04-29 — Release candidate freeze + bugfix buffer

- No new features; only P0/P1 from E2E + load test; triage list in `docs/plan/RC_Triage.md` (empty template).
- Verify `SEARCH_MODE=live` path in staging for 24h soak.
- Roll-forward plan if RC blocked.

### 2026-04-30 — **GA / v1.0.0** tag + handoff

- Tag `v1.0.0`; GitHub Release with binaries N/A, PyPI optional deferred; **`docs/plan/RAG_FOUNDRY_60_DAY_COMPLETION.md` retired** to “completed” status line at top.
- Final `cdk synth` + `make lint test` green on `main`.
- Post-mortem: what moved to v1.1 (Fargate worker default, enterprise connectors).

---

## Summary

| Phase (approx.) | Days | Focus |
|-----------------|------|--------|
| OpenSearch + worker indexing | Mar 2–12 | Schema, IAM, client, bulk index, hybrid search |
| RAG query + guardrails + audit | Mar 14–18 | Context assembly, Bedrock Converse, audit, quotas |
| Web + CLI + SDK | Mar 20–26 | Types, UI, parity, plugins |
| Plugins + orchestration | Mar 27–31 | Pipeline hooks, Step Functions clarity |
| Ops + compliance | Apr 1–15 | S3/KMS, Cognito, WAF, GDPR, retention, SBOM |
| Hardening + release | Apr 16–30 | Load/cost/E2E, OpenAPI, RC, GA |

This is intentionally **dense**; some days may merge in practice, but each line above is a **trackable** unit of work for “everything” to a shippable v1.0.
