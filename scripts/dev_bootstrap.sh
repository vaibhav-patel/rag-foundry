#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip ruff pytest
pip install -e "infra/[dev]"
pip install -e "services/control_plane/[dev]"
pip install -e "packages/contracts"
pip install -e "packages/sdk-python"
pip install -e "cli/[dev]"
echo "Bootstrap complete. Activate: source .venv/bin/activate"
