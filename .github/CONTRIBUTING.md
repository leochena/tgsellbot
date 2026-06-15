# Contributing

Thanks for helping improve TGSellBot. Issues and pull requests are welcome.

## Before You Start

- Search existing issues and pull requests first.
- Keep changes focused and explain the user-visible behavior.
- Do not commit secrets, bot tokens, private keys, database dumps, or production logs.
- For security-sensitive reports, use the process in `SECURITY.md`.

## Pull Request Checklist

- Describe the problem and the fix.
- Add or update tests when behavior changes.
- Update documentation when setup, configuration, or user-facing behavior changes.
- Run the relevant tests locally before opening the pull request.

Useful commands:

```bash
pytest -q
git diff --check
```

## Development Notes

- Python code should follow the existing project style and use type hints where practical.
- Prefer small, reviewable pull requests.
- Keep generated files, local `.env` files, logs, coverage reports, and uploaded stock data out of git.
