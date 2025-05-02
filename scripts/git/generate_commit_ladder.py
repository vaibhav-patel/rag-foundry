#!/usr/bin/env python3
"""Emit docs/history/commits.csv rows: one row per day (or step days) from start to end (UTC)."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs" / "history" / "commits.csv"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365, help="Span in days ending at --end")
    p.add_argument("--step", type=int, default=2, help="Days between commit timestamps")
    p.add_argument("--end", default=None, help="ISO end date UTC (default: now)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    end = (
        datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        if args.end
        else datetime.now(timezone.utc)
    )
    start = end - timedelta(days=args.days)
    rows = []
    cur = start
    i = 0
    while cur <= end:
        rows.append(
            {
                "step_id": str(i + 1),
                "iso_date": cur.strftime("%Y-%m-%dT12:00:00Z"),
                "branch": "main",
                "message": f"chore(history): ladder slot {i + 1} (replace with real work)",
            }
        )
        cur += timedelta(days=args.step)
        i += 1

    if args.dry_run:
        for r in rows[:5]:
            print(r)
        print("...", len(rows), "rows")
        return 0

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["step_id", "iso_date", "branch", "message"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
