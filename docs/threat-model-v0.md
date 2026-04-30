# Threat model v0 (STRIDE sketch)

| Area | Threat | Mitigation (directional) |
|------|--------|---------------------------|
| Auth | Token forgery | API Gateway JWT authorizer + Cognito |
| Data | Cross-tenant read | PK scoping + tests on all read paths |
| Plugins | Malicious code | Sandboxing, no default egress, artifact hash |
| Ops | Secret leak | Gitleaks CI, no secrets in git |
