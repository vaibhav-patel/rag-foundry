"""Typer CLI calling the control-plane HTTP API."""

from __future__ import annotations

import os

import httpx
import typer

app = typer.Typer(no_args_is_help=True)


def _client() -> httpx.Client:
    base = os.environ.get("RAG_FOUNDRY_API_URL", "http://localhost").rstrip("/")
    token = os.environ.get("RAG_FOUNDRY_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base, headers=headers, timeout=30.0)


@app.command()
def health() -> None:
    """GET /v1/health (no auth)."""
    base = os.environ.get("RAG_FOUNDRY_API_URL", "http://localhost").rstrip("/")
    r = httpx.get(f"{base}/v1/health", timeout=10.0)
    typer.echo(r.text)


@app.command("kb-list")
def kb_list() -> None:
    """List knowledge bases for the authenticated tenant."""
    with _client() as c:
        r = c.get("/v1/kbs")
        r.raise_for_status()
        typer.echo(r.text)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
