# Commit timestamps (required)

Git uses **wall-clock “now”** for author/committer unless overridden. For this project, every commit on `main` must use **scripted dates** on a ladder from roughly **today − 365 days** through **today**, stepping about **every 1–2 days** per commit.

Before `git commit`, pick the **next** timestamp on your ladder (from `commits.csv` or a small script). Set **author** and **committer** time (Git uses real “now” otherwise):

```bash
export GIT_AUTHOR_DATE="2025-04-30T12:00:00Z"
export GIT_COMMITTER_DATE="$GIT_AUTHOR_DATE"
git commit --date="$GIT_AUTHOR_DATE" -m "Your message"
```

`git commit --date=...` sets the **author date**; the env vars cover both author and committer in most flows. For `git commit --amend`, use the same exports **and** `--date=...` so the author line is not left at wall-clock time.

Then `git push`. See root plan “Git history strategy” and `docs/history/README.md`.
