# GitHub branch protection (manual)

On the GitHub repo settings:

- Require PR reviews before merging to `main` (at least 1).
- Require status checks: `lint`, `test`, `cdk-synth` (after CI is enabled).
- Require linear history optional; disallow force-push to `main`.
