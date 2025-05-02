# Commit history tooling

Some commits use **synthetic author/committer dates** on a ladder from about **one year ago → now** (~daily / every other day). Real code changes are genuine; timestamps are scripted for presentation. See `commits.csv`, `scripts/git/backfill_history.py` (`--onto-main` to stay on `main`), and `scripts/git/generate_commit_ladder.py` to (re)build the CSV scaffold.
