"""Load ``packages/contracts`` JSON Schemas mirrored under ``lambda/schemas/``."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

_SCHEMA_DIR_OVERRIDE = os.environ.get("RAG_CONTRACT_SCHEMA_DIR")


def schema_dir() -> Path:
    if _SCHEMA_DIR_OVERRIDE:
        return Path(_SCHEMA_DIR_OVERRIDE)
    return Path(__file__).resolve().parent / "schemas"


@lru_cache(maxsize=8)
def _registry() -> Any:
    reg: Any = Registry()
    d = schema_dir()
    if not d.is_dir():
        return reg
    for path in sorted(d.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        uri = data.get("$id")
        if not uri:
            continue
        resource = DRAFT202012.create_resource(data)
        reg = reg.with_resource(uri, resource)
    return reg


@lru_cache(maxsize=8)
def _validator_for(want_uri: str) -> Draft202012Validator:
    for path in sorted(schema_dir().glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("$id") == want_uri:
            return Draft202012Validator(data, registry=_registry())
    raise FileNotFoundError(f"no schema with $id {want_uri!r} under {schema_dir()}")


RAG_QUERY_SCHEMA_URI = "https://rag-foundry/contracts/schemas/rag-query-request.schema.json"
DENSE_SEARCH_BODY_SCHEMA_URI = "https://rag-foundry/contracts/schemas/dense-search-post-body.schema.json"
KB_MUTATION_SCHEMA_URI = "https://rag-foundry/contracts/schemas/knowledge-base-mutation.schema.json"


def schema_validation_errors(schema_uri_root_id: str, instance: dict[str, Any]) -> list[str]:
    """Return human-readable validation messages (empty if valid)."""

    v = _validator_for(schema_uri_root_id)
    errors: list[str] = []
    for err in sorted(v.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        loc = "/" + "/".join(str(x) for x in err.absolute_path) if err.absolute_path else "/"
        errors.append(f"{loc}: {err.message}")
    return errors


def format_schema_error_response(messages: list[str]) -> dict[str, Any]:
    return {
        "title": "Bad Request",
        "detail": "Request body failed JSON Schema validation",
        "schema_errors": [{"message": m} for m in messages],
    }
