#!/usr/bin/env bash
set -euo pipefail
# Lightweight grep for common secret patterns (CI also runs Gitleaks).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if rg -n --hidden --glob '!.git' \
  'ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN RSA PRIVATE KEY' .; then
  echo "Possible secret pattern found. Remove before commit." >&2
  exit 1
fi
echo "OK: no obvious secret patterns."
