# When to use the web UI vs the CLI

| Persona | Use |
|---------|-----|
| No-code admins configuring KBs | **Web** (`web/`) |
| Operators / CI smoke tests | **CLI** (`rag-foundry` Typer) |
| Product integrations | **HTTP API** directly |

Both UI and CLI call the same control-plane API. Machine-to-machine auth should use scoped credentials (ADR in `docs/adr/`).
