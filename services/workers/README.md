# Workers

- **`lambda_stub/`** — Lambda deployment used by Step Functions “Extract” task (text pull from S3).
- **`Dockerfile`** — Python 3.12 base for future Fargate tasks (same handler entrypoint pattern).

Build (from this directory):

```bash
docker build -t rag-foundry-worker:dev .
```
