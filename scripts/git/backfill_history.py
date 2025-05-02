#!/usr/bin/env python3
"""Replay commits from docs/history/commits.csv with GIT_AUTHOR_DATE / GIT_COMMITTER_DATE.

Dry-run: BACKFILL_DRY_RUN=1 python scripts/git/backfill_history.py
Main-only: python scripts/git/backfill_history.py --onto-main  (always commit on main; ignores branch column)
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "docs" / "history" / "commits.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--onto-main",
        action="store_true",
        help="Stay on main for every row (no git checkout -B per branch).",
    )
    args = ap.parse_args()

    dry = os.environ.get("BACKFILL_DRY_RUN", "") == "1"
    if not CSV.is_file():
        print(f"Missing {CSV}", file=sys.stderr)
        return 1
    with CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        date = row["iso_date"].strip()
        msg = row["message"].strip()
        branch = row.get("branch", "main").strip()
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
        if dry:
            print(f"would: {date} {branch} {msg}")
            continue
        if args.onto_main:
            subprocess.run(["git", "checkout", "main"], cwd=ROOT, env=env, check=True)
        else:
            subprocess.run(["git", "checkout", "-B", branch], cwd=ROOT, env=env, check=True)
        subprocess.run(["git", "add", "-A"], cwd=ROOT, env=env, check=True)
        subprocess.run(
            ["git", "commit", "-m", msg, "--allow-empty", "--date", date],
            cwd=ROOT,
            env=env,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
