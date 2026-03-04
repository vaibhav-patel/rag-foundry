"""OpenSearch Serverless client factory — SigV4 (service aoss).

See docs/adr/0006-opensearch-chunk-index-contract.md and infra env OPENSEARCH_*.
"""

from __future__ import annotations

import os

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


def _host_from_endpoint(endpoint: str) -> str:
    e = endpoint.strip().removeprefix("https://").removeprefix("http://")
    return e.split("/")[0].split(":")[0]


def aws_sigv4_aoss_auth(*, region: str) -> AWS4Auth:
    session = boto3.Session(region_name=region)
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("No AWS credentials available for SigV4 OpenSearch auth")
    frozen = creds.get_frozen_credentials()
    return AWS4Auth(
        frozen.access_key,
        frozen.secret_key,
        region,
        "aoss",
        session_token=frozen.token,
    )


def create_opensearch_client(
    *,
    endpoint: str | None = None,
    region: str | None = None,
) -> OpenSearch | None:
    """Return SigV4-signed OpenSearch-py client or None when endpoint unset (local tests)."""

    endpoint = endpoint if endpoint is not None else os.environ.get("OPENSEARCH_ENDPOINT") or ""
    if not endpoint.strip():
        return None
    region = (
        region
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    auth = aws_sigv4_aoss_auth(region=region)
    host = _host_from_endpoint(endpoint)

    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )
