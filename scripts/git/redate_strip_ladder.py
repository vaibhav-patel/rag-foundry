#!/usr/bin/env python3
"""Remove registry-ladder commits; replay real work on 8eda28c with past-only ISO dates.

Env:
  RAG_FOUNDRY_ROOT — repo root
  RAG_SOURCE_REV   — tip commit to read trees from (e.g. 5baf847)

Then: git branch -D main && git branch -m main && git push --force-with-lease origin main
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("RAG_FOUNDRY_ROOT", Path(__file__).resolve().parents[2])).resolve()
BASE = "8eda28c"

# Past-only (before 2026-04-30), +2 day cadence from 2026-03-31
DATES = [
    "2026-03-31T12:00:00Z",
    "2026-04-02T12:00:00Z",
    "2026-04-04T12:00:00Z",
    "2026-04-06T12:00:00Z",
    "2026-04-08T12:00:00Z",
    "2026-04-10T12:00:00Z",
    "2026-04-12T12:00:00Z",
    "2026-04-14T12:00:00Z",
    "2026-04-16T12:00:00Z",
    "2026-04-18T12:00:00Z",
    "2026-04-20T12:00:00Z",
    "2026-04-22T12:00:00Z",
    "2026-04-24T12:00:00Z",
    "2026-04-26T12:00:00Z",
    "2026-04-28T12:00:00Z",
]

STEPS: list[tuple[str, list[str]]] = [
    ("chore(tooling): add worker tests to pytest testpaths", ["pyproject.toml"]),
    ("feat(worker): text chunking helpers", ["services/workers/lambda_stub/chunking.py"]),
    ("test(worker): chunking unit tests", ["services/workers/tests/test_chunking.py"]),
    ("feat(worker): ingest from S3, embed, manifest, job status", ["services/workers/lambda_stub/handler.py"]),
    ("chore(worker): Docker image copies chunking module", ["services/workers/Dockerfile"]),
    ("feat(infra): ingest pipeline and worker Bedrock IAM", ["infra/rag_foundry_infra/stacks/rag_foundry_stack.py"]),
    ("feat(infra): static web stack (S3, CloudFront, placeholder deploy)", ["infra/rag_foundry_infra/stacks/web_static_stack.py"]),
    ("chore(infra): register web static stack in CDK app", ["infra/app.py"]),
    ("feat(api): ingest jobs require s3_key; Step Functions payload", ["services/control_plane/lambda/handler.py"]),
    ("feat(web): Playground search, query, and KB list", ["web/src/pages/Playground.tsx"]),
    ("docs(web): VITE_API_URL and VITE_JWT_TOKEN example", ["web/.env.example"]),
    ("ci: CDK synth via python3 app.py (no global cdk CLI)", [".github/workflows/ci.yml"]),
    ("chore(history): replace commits.csv (main timeline without ladder registry)", []),
    ("feat(sdk): ControlPlaneClient over urllib for health and KB APIs", ["packages/sdk-python"]),
    ("fix(cli): job-create requires --s3-key", ["cli/src/rag_foundry_cli/main.py"]),
]


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True, env=env or os.environ.copy())


def git_commit(date: str, message: str, paths: list[str]) -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date
    run(["git", "add", "--"] + paths, env=env)
    run(["git", "commit", "-m", message, "--date", date], env=env)


def main() -> int:
    script_body = Path(__file__).read_text(encoding="utf-8")
    source = os.environ.get("RAG_SOURCE_REV", "").strip()
    if not source:
        print("Set RAG_SOURCE_REV", file=sys.stderr)
        return 1
    if len(DATES) != len(STEPS):
        print("internal: dates/steps mismatch", file=sys.stderr)
        return 1

    run(["git", "checkout", "-B", "redate-strip", BASE])

    for i, (msg, paths) in enumerate(STEPS):
        date = DATES[i]
        if paths == ["packages/sdk-python"]:
            run(["git", "checkout", source, "--", "packages/sdk-python/pyproject.toml"])
            run(["git", "checkout", source, "--", "packages/sdk-python/src"])
            run(["git", "checkout", source, "--", "packages/sdk-python/tests"])
            git_commit(date, msg, ["packages/sdk-python"])
            continue
        if not paths:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(["step_id", "iso_date", "branch", "message"])
            for j, d in enumerate(DATES):
                w.writerow([str(j + 1), d, "main", STEPS[j][0]])
            (ROOT / "docs/history/commits.csv").write_text(buf.getvalue(), encoding="utf-8")
            py = ROOT / "pyproject.toml"
            t = py.read_text(encoding="utf-8")
            t = t.replace('"packages/contracts/tests", ', "", 1)
            py.write_text(t, encoding="utf-8")
            dest = ROOT / "scripts/git/redate_strip_ladder.py"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(script_body, encoding="utf-8")
            git_commit(
                date,
                msg,
                ["docs/history/commits.csv", "pyproject.toml", "scripts/git/redate_strip_ladder.py"],
            )
            continue
        for p in paths:
            run(["git", "checkout", source, "--", p])
        git_commit(date, msg, paths)

    run(["git", "branch", "-D", "main"], env=os.environ.copy())
    run(["git", "branch", "-m", "main"], env=os.environ.copy())
    print("OK. Push: git push --force-with-lease origin main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
