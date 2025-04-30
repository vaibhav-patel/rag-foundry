"""Worker stub invoked from Step Functions (extract stage)."""

from __future__ import annotations

import json
from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "stage": "extract",
        "input_keys": list(event.keys()) if isinstance(event, dict) else [],
    }

