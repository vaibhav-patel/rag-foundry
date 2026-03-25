"""Typer CLI calling the control-plane HTTP API via ControlPlaneClient (stdlib urllib in SDK)."""

from __future__ import annotations

import json
import os
from typing import Any

import typer
from rag_foundry_sdk import ControlPlaneClient

app = typer.Typer(no_args_is_help=True)


def _sdk() -> ControlPlaneClient:
    base = os.environ.get("RAG_FOUNDRY_API_URL", "http://localhost").rstrip("/")
    token = os.environ.get("RAG_FOUNDRY_TOKEN", "")
    return ControlPlaneClient(base, token)


def _present(ctx: typer.Context, data: Any, *, stderr: bool = False) -> None:
    """Pretty JSON by default; compact JSON with global ``--json`` (CI pipes)."""
    compact = bool(ctx.obj and ctx.obj.get("json_output"))
    if compact:
        txt = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    else:
        txt = json.dumps(data, indent=2, ensure_ascii=False)
    typer.echo(txt, err=stderr)


@app.callback()
def _global_opts(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Compact JSON on stdout (scripts and CI smoke pipes).",
    ),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output


@app.command()
def health(ctx: typer.Context) -> None:
    """GET /v1/health (no auth)."""
    try:
        data = _sdk().health()
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


@app.command("kb-list")
def kb_list(ctx: typer.Context) -> None:
    """List knowledge bases for the authenticated tenant."""
    try:
        data = _sdk().list_kbs()
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


@app.command("kb-create")
def kb_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Knowledge base display name"),
) -> None:
    """POST /v1/kbs"""
    try:
        data = _sdk().create_kb(name)
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


@app.command("job-create")
def job_create(
    ctx: typer.Context,
    kb_id: str = typer.Argument(..., help="Knowledge base id"),
    s3_key: str = typer.Option(..., "--s3-key", help="Raw object key from POST .../uploads"),
) -> None:
    """POST /v1/kbs/{kbId}/jobs (requires s3_key from presigned upload)."""
    try:
        data = _sdk().create_job(kb_id, s3_key=s3_key)
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


@app.command()
def search(
    ctx: typer.Context,
    kb_id: str = typer.Argument(..., help="Target knowledge base id"),
    q: str = typer.Argument(..., help="Dense search text (passed as JSON field `q`)"),
    k: int = typer.Option(5, "--k", help="Maximum hits (`k`)."),
    hybrid: bool = typer.Option(False, "--hybrid", help="Enable hybrid BM25 + vector search."),
) -> None:
    """POST /v1/kbs/{kbId}/search."""
    payload: dict[str, Any] = {"q": q, "k": k}
    if hybrid:
        payload["hybrid"] = True
    try:
        data = _sdk().search(kb_id, payload)
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


@app.command()
def query(
    ctx: typer.Context,
    kb_id: str = typer.Argument(..., help="Target knowledge base id"),
    question: str = typer.Argument(..., help="User question sent to RagQueryRequest.question"),
    k: int = typer.Option(5, "--k", help="Top-K for internal dense search."),
    hybrid: bool = typer.Option(False, "--hybrid", help="Enable hybrid BM25 + vector search."),
) -> None:
    """POST /v1/kbs/{kbId}/query."""
    payload: dict[str, Any] = {"question": question, "q": question, "k": k}
    if hybrid:
        payload["hybrid"] = True
    try:
        data = _sdk().query(kb_id, payload)
    except RuntimeError as e:
        _present(ctx, {"error": str(e)}, stderr=True)
        raise typer.Exit(code=2) from e
    _present(ctx, data if data is not None else {})


def main() -> None:
    app()


if __name__ == "__main__":
    main()
