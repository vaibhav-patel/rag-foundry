# GDPR / tenant data deletion (stub)

Future control-plane endpoint (documented only here):

- `DELETE /v1/tenant/data` — async job to purge S3 prefixes, Dynamo keys for `TENANT#{id}`, and OpenSearch indexes for that tenant’s KBs.

Until implemented, process deletion requests manually via runbook checklist (S3 list + delete, DDB query + delete, index delete by pattern).
