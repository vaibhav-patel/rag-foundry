"""Optional dense-search reranking over the top retrieval candidates.

Contract (either transport — **exactly one** should be configured in practice):

**AWS Lambda sync invoke**
(`RERANK_LAMBDA_ARN`, or ARN loaded from ``RERANK_LAMBDA_ARN_PARAMETER`` SSM string):

- **Payload** (UTF-8 JSON): ``{\"q\": \"<query>\", \"k\": <int>, \"hits\": [<DenseSearchHit>...]}``.
  ``hits`` has at most 20 items (truncated server-side).

- **Successful response**: JSON ``{\"hits\": [...]}`` — ordered reranked list, length ``<= k``,
  entries shaped like ``DenseSearchHit`` (subset of fields acceptable; merging by ``id``).

  Alternatively JSON ``{\"ranked_ids\": [\"doc-id\", ...]}`` ordering the passed-in candidates.

**HTTP POST** (``RERANK_URL``, same JSON body).

If both Lambda ARN/url resolve and sentinel values disable them, behaves as rerank absent.
Failures fall back to the first ``k`` OpenSearch hits in original order (*no-op* semantics).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

import boto3
import requests
from botocore.exceptions import ClientError

_LOGGER = logging.getLogger(__name__)

RERANK_TOP_CANDIDATES = 20

_rerank_lambda_arn_cached: str | None | Literal[False] = False


def _value_active(v: str) -> bool:
    s = (v or "").strip()
    if not s:
        return False
    return s.strip().lower() not in {"-", "none", "(unset)", "disabled", "null"}


def resolve_rerank_lambda_arn() -> str | None:
    """ARN for sync ``lambda:InvokeFunction`` (prefer env ``RERANK_LAMBDA_ARN``)."""

    global _rerank_lambda_arn_cached
    if _rerank_lambda_arn_cached not in (False,):
        return _rerank_lambda_arn_cached if _rerank_lambda_arn_cached else None

    env_direct = (os.environ.get("RERANK_LAMBDA_ARN") or "").strip()
    if _value_active(env_direct):
        _rerank_lambda_arn_cached = env_direct
        return env_direct

    param_name = (os.environ.get("RERANK_LAMBDA_ARN_PARAMETER") or "").strip()
    if not param_name:
        _rerank_lambda_arn_cached = None
        return None

    try:
        ssm_cli = boto3.client("ssm")
        rsp = ssm_cli.get_parameter(Name=param_name)
        raw = (rsp.get("Parameter") or {}).get("Value") or ""
        raw = raw.strip()
        if _value_active(raw):
            _rerank_lambda_arn_cached = raw
            return raw
    except ClientError as exc:
        _LOGGER.warning("rerank_hook: cannot read %s (%s)", param_name, exc)

    _rerank_lambda_arn_cached = None
    return None


def rerank_http_url() -> str | None:
    u = (os.environ.get("RERANK_URL") or "").strip()
    return u if _value_active(u) else None


def rerank_pipeline_enabled() -> bool:
    return bool(resolve_rerank_lambda_arn() or rerank_http_url())


def dense_search_fetch_size(desired_top_k: int) -> int:
    """OpenSearch retrieve size — widen to rerank candidate pool when a reranker is wired."""

    k = max(1, min(100, int(desired_top_k)))
    if not rerank_pipeline_enabled():
        return k
    return min(100, max(k, RERANK_TOP_CANDIDATES))


def _merge_ordered_candidates(
    candidates: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    ordered_ids: list[str],
    *,
    want_k: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hid in ordered_ids:
        hit = by_id.get(hid)
        if hit is None:
            continue
        sid = str(hit.get("id", hid))
        if sid in seen:
            continue
        out.append(hit)
        seen.add(sid)
        if len(out) >= want_k:
            return out
    for h in candidates:
        hid = str(h.get("id", ""))
        if not hid or hid in seen:
            continue
        out.append(h)
        seen.add(hid)
        if len(out) >= want_k:
            break
    return out


def _normalize_reranked_hits(
    candidates: list[dict[str, Any]],
    rsp: dict[str, Any] | None,
    *,
    want_k: int,
) -> list[dict[str, Any]]:
    """Map reranker response into ``DenseSearchHit[]`` capped at ``want_k``."""

    if not rsp or not isinstance(rsp, dict):
        return candidates[:want_k]
    ranked_ids_raw = rsp.get("ranked_ids")
    hits_raw = rsp.get("hits")
    by_id = {str(h.get("id", "")): dict(h) for h in candidates if h.get("id") is not None}

    if isinstance(ranked_ids_raw, list) and all(isinstance(x, (str, int)) for x in ranked_ids_raw):
        ordered_ids = [str(x) for x in ranked_ids_raw]
        return _merge_ordered_candidates(list(candidates), by_id, ordered_ids, want_k=want_k)

    if isinstance(hits_raw, list) and hits_raw:
        out_ls: list[dict[str, Any]] = []
        seen_ls: set[str] = set()
        for h in hits_raw:
            if not isinstance(h, dict) or h.get("id") is None:
                continue
            sid = str(h["id"])
            if sid in seen_ls:
                continue
            base = by_id.get(sid, {})
            merged_hit = {
                **base,
                **{
                    kk: vv
                    for kk, vv in h.items()
                    if kk in ("score", "text", "metadata", "id")
                },
            }
            merged_hit.setdefault("id", sid)
            out_ls.append(merged_hit)
            seen_ls.add(sid)
            if len(out_ls) >= want_k:
                return out_ls[:want_k]
        if out_ls:
            return out_ls[:want_k]

    return candidates[:want_k]


def _invoke_lambda_rerank(arn: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    lam = boto3.client("lambda")
    raw = lam.invoke(
        FunctionName=arn,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    pl = raw.get("Payload") and raw["Payload"].read()
    err = raw.get("FunctionError")
    if err:
        _LOGGER.warning("rerank_hook: Lambda %s error=%s payload=%s", arn, err, (pl or b"")[:500])
        return None
    if not pl:
        return None
    try:
        return json.loads(pl.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _LOGGER.warning("rerank_hook: invalid JSON from Lambda (%s)", exc)
        return None


def _post_http_rerank(
    url: str,
    payload: dict[str, Any],
    timeout_s: float = 14.0,
) -> dict[str, Any] | None:
    try:
        r = requests.post(
            url,
            json=payload,
            timeout=timeout_s,
            headers={"content-type": "application/json"},
        )
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, dict) else None
    except requests.RequestException as exc:
        _LOGGER.warning("rerank_hook: HTTP rerank failed (%s)", exc)
        return None


def rerank_dense_hits_maybe(
    search_payload: dict[str, Any],
    *,
    query_text: str,
    desired_top_k: int,
) -> dict[str, Any]:
    """Truncate to ``desired_top_k``; optionally reorder via rerank Lambda or ``RERANK_URL``."""

    want_k = max(1, min(100, int(desired_top_k)))
    hits = search_payload.get("hits")
    if not isinstance(hits, list):
        return search_payload

    if not rerank_pipeline_enabled():
        out = dict(search_payload)
        out["hits"] = hits[:want_k]
        return out

    candidates = hits[:RERANK_TOP_CANDIDATES]
    payload = {"q": query_text or "", "k": want_k, "hits": candidates}

    rsp: dict[str, Any] | None = None
    arn = resolve_rerank_lambda_arn()
    if arn:
        rsp = _invoke_lambda_rerank(arn, payload)
        if rsp is not None:
            ordered = _normalize_reranked_hits(list(candidates), rsp, want_k=want_k)
            return {
                **search_payload,
                "hits": ordered,
                "reranked": True,
            }
        # fall through to HTTP if configured after Lambda fails
        _LOGGER.warning("rerank_hook: Lambda invoke failed or returned empty; retrying HTTP if set")

    url = rerank_http_url()
    if url:
        rsp = _post_http_rerank(url, payload)
        if rsp is not None:
            ordered = _normalize_reranked_hits(list(candidates), rsp, want_k=want_k)
            return {
                **search_payload,
                "hits": ordered,
                "reranked": True,
            }

    out = dict(search_payload)
    out["hits"] = hits[:want_k]
    return out
