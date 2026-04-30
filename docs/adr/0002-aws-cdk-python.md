# ADR 0002: AWS CDK (Python) for infrastructure

## Status

Accepted

## Decision

Use **AWS CDK in Python** (`infra/`) for all first-party AWS resources.

## Consequences

- One language ecosystem with application Lambdas (Python).
- Synth and tests run in CI without Node for CDK TypeScript.
