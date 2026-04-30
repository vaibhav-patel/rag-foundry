# Runbook: ingest failures

1. Check **Step Functions** execution history for the failed `job_id`.
2. Inspect **CloudWatch Logs** for `WorkerFn` and `ControlPlaneFn`.
3. If DLQ depth alarm fires, drain **SQS** messages and triage error payloads.
4. Re-run **reindex** job after fixing upstream document or plugin manifest.
