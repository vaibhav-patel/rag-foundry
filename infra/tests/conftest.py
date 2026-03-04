"""Skip Docker Lambda bundling in infra tests only."""

from __future__ import annotations

import os

os.environ.setdefault("RAG_FOUNDRY_SYNTH_SKIP_LAMBDA_BUNDLING", "1")
