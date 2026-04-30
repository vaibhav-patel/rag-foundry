# ADR 0005: User plugin execution model

## Status

Proposed

## Decision

User code ships as **versioned artifacts** in S3; workers run plugins in **subprocess or container** with CPU, memory, wall-clock, and network egress constrained by policy (defaults: deny public egress unless allowlisted).

## Consequences

- Plugin ABI must be versioned (`packages/contracts`).
- Security reviews focus on artifact integrity and sandbox escapes.
