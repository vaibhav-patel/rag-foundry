"""Minimal control-plane HTTP client (stdlib only)."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rag_foundry_sdk.types import (
    DenseSearchResponse,
    RagQueryResponse,
    dense_search_response_from_json,
    rag_query_response_from_json,
)


class ControlPlaneClient:
    """Call rag-foundry HTTP API (same paths as the web app / CLI)."""

    def __init__(self, base_url: str, token: str = "", *, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout_s = timeout_s

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {raw}") from e
        if not raw:
            return None
        return json.loads(raw)

    def health(self) -> Any:
        return self._request("GET", "/v1/health", auth=False)

    def list_kbs(self) -> Any:
        return self._request("GET", "/v1/kbs")

    def create_kb(self, name: str) -> Any:
        return self._request("POST", "/v1/kbs", body={"name": name})

    def create_job(self, kb_id: str, s3_key: str, **extra: Any) -> Any:
        payload: dict[str, Any] = {"s3_key": s3_key, **extra}
        return self._request("POST", f"/v1/kbs/{kb_id}/jobs", body=payload)

    def search(self, kb_id: str, body: dict[str, Any] | None = None) -> Any:
        """POST ``/v1/kbs/{kbId}/search`` — dense / hybrid retrieval (stub or live OpenSearch).

        Omit ``body`` or pass ``{}`` to accept API defaults after schema merge.
        """
        return self._request(
            "POST",
            f"/v1/kbs/{kb_id}/search",
            body=body if body is not None else {},
        )

    def query(self, kb_id: str, body: dict[str, Any]) -> Any:
        """POST ``/v1/kbs/{kbId}/query`` — retrieval + bounded context + Bedrock generation."""
        return self._request("POST", f"/v1/kbs/{kb_id}/query", body=body)

    def search_kb(
        self,
        kb_id: str,
        body: dict[str, Any] | None = None,
    ) -> DenseSearchResponse:
        """Same as ``search`` but coerces HTTP 200 JSON into ``DenseSearchResponse``."""
        return dense_search_response_from_json(self.search(kb_id, body))

    def query_kb(self, kb_id: str, body: dict[str, Any]) -> RagQueryResponse:
        """Same as ``query`` but coerces HTTP 200 JSON into ``RagQueryResponse``."""
        return rag_query_response_from_json(self.query(kb_id, body))
