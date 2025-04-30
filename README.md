# rag-foundry

No-code **RAG** (retrieval-augmented generation) platform on **AWS**: standard pipelines for ingest, chunking, embeddings, retrieval, and generation, with **optional user-provided plugins** at each stage. Primary experience is a **web admin UI**; an **operator CLI** calls the same HTTP API.

## Vision

- Tenants configure knowledge bases without writing glue code.
- Every RAG stage has curated defaults (Bedrock, OpenSearch Serverless, hybrid search, etc.) and a **plugin contract** for advanced users.
- Data plane runs in your AWS account (CDK Python).

## Non-goals (v0)

- Full enterprise SaaS connectors (SharePoint, Google Drive) beyond stubs.
- On-premises deployment.

## Repository layout

| Path | Purpose |
|------|---------|
| `infra/` | AWS CDK (Python) stacks |
| `services/control_plane/` | API Lambda (HTTP API → Lambda) |
| `services/workers/` | Ingest / extract / chunk / embed / index worker image |
| `packages/contracts/` | OpenAPI + shared schemas |
| `web/` | Vite + React admin SPA |
| `cli/` | Typer operator CLI |
| `docs/` | ADRs, runbooks, UX notes |

## Security

Report vulnerabilities per [SECURITY.md](SECURITY.md). Do not commit secrets; see [docs/credentials.md](docs/credentials.md).

## Local development

```bash
./scripts/dev_bootstrap.sh
make lint test
cd infra && cdk synth
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
