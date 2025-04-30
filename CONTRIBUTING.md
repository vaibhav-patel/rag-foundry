# Contributing

## Branches

- Use `feat/NNNN-short-slug` or `fix/NNNN-short-slug` when possible.
- Open PRs against `main`; keep commits focused.

## Commits

- Prefer imperative subject lines (`Add OpenAPI tenant schema`).
- Reference ADRs or issues when relevant.

## Checks

Run `make fmt lint test` and `cd infra && cdk synth` before pushing.
