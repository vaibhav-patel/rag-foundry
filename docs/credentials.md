# Credentials and tokens

- **Never** commit personal access tokens (PATs), AWS keys, or API keys. If a token was ever pasted into chat or a ticket, **revoke it immediately** in GitHub (Settings → Developer settings → Personal access tokens) and create a new one.
- Prefer **`gh auth login`** for GitHub CLI, or short-lived tokens stored only in your shell environment.
- For AWS, use **OIDC** from GitHub Actions to assume a role; for local development, use `aws sso login` or named profiles—not long-lived access keys in the repo.
