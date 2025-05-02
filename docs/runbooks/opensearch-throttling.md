# Runbook: OpenSearch Serverless throttling

1. Check **collection** capacity (OCU) in the AWS console; scale up if sustained `429` / `ThrottlingException`.
2. Reduce **bulk index** concurrency in the worker Step Functions branch.
3. Review **knn** `ef_search` and payload size per request; lower `top_k` in API defaults if needed.
4. If hybrid queries spike CPU, temporarily disable **RRF** weight tuning and fall back to dense-only for degraded mode.
