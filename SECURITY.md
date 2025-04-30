# Security policy

## Supported versions

We support the latest minor release on `main`. Older tags are best-effort.

## Reporting a vulnerability

Please email **security@example.invalid** (replace with your org contact) with:

- Description and impact
- Steps to reproduce
- Affected components (API, worker, web, infra)

Do not open public issues for undisclosed vulnerabilities.

## Handling of secrets

Never commit AWS keys, GitHub PATs, or third-party API keys. Use AWS Secrets Manager / SSM and GitHub Actions OIDC. See [docs/credentials.md](docs/credentials.md).
