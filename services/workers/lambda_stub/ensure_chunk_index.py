"""Idempotent create of the chunk index (HEAD → PUT mapping) before ingest."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import RequestError

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_NAME = "rag-foundry-chunks"


def _create_body_from_contract() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "chunk-index-v1-mapping.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ensure_chunk_index(
    client: OpenSearch | None,
    *,
    index_name: str | None = None,
) -> None:
    """If OpenSearch client is configured, ensure index exists using v1 contract mapping."""

    if client is None:
        logger.info("OpenSearch index ensure skipped (no endpoint / client)")
        return

    index = (index_name or os.environ.get("OPENSEARCH_INDEX_NAME") or _DEFAULT_INDEX_NAME).strip()

    exists = client.indices.exists(index=index)
    if exists:
        logger.info("OpenSearch index already exists, skip create: %s", index)
        return

    body = _create_body_from_contract()
    try:
        client.indices.create(index=index, body=body)
        logger.info("OpenSearch index created: %s", index)
    except RequestError as exc:
        if exc.status_code == 400 and exc.error == "resource_already_exists_exception":
            logger.info("OpenSearch index already exists (race), skip create: %s", index)
            return
        raise
