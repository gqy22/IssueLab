# Contributing

Thanks for your interest in IssueLab. This guide keeps contributions consistent and easy to review.

## Quick Start

```bash
uv sync
uv run pytest tests/ --cov=issuelab
uv run ruff check src/ tests/
uv run mypy src/issuelab --ignore-missing-imports
```

## Development Workflow

1. Fork the repo and create a feature branch.
2. Make focused changes (avoid mixing unrelated refactors).
3. Add or update tests for behavioral changes.
4. Run formatting and lint checks.
5. Open a PR with a clear summary and rationale.

## Code Style

- Python 3.13+
- 4-space indentation
- Line length 120
- Ruff for lint + formatting

## Tests

- Use `uv run pytest tests/ --cov=issuelab` for full coverage.
- Use `uv run pytest tests/<file>.py -v` for a focused run.

## Commit Messages

Use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`.

## Pull Requests

- Keep PRs focused.
- Link relevant issues if available.
- Include evidence for behavior changes (logs, screenshots, or workflow output).

## Security

Please do not file public issues for security vulnerabilities.
See `SECURITY.md` for private reporting.
