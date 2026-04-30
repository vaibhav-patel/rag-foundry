# Data retention (stub)

- Raw documents: S3 lifecycle policies per environment (TBD).
- Derived chunks / vectors: follow vector index retention when KB deleted.
- **GDPR delete**: expose `DELETE /v1/tenant/data` in a future milestone; document legal hold exceptions here.
