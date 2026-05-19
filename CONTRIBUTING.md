# Contributing to STAN

Thank you for your interest in contributing!

---

## Development setup

```bash
git clone https://github.com/your-org/stan.git
cd stan
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Run the server locally:

```bash
python run.py
```

---

## Coding standards

- **Python 3.11+** — use modern syntax (`match`, `X | Y` unions, `str | None`, etc.)
- **Line length** — 100 characters (configured in `pyproject.toml`)
- **Linting** — `ruff check .` must pass with zero errors before submitting a PR
- **Formatting** — `ruff format .`
- **Type hints** — add type hints to new public functions and return types
- **No secrets in code** — all configuration belongs in `.env` / `stan/config.py`

---

## Running tests

```bash
pytest tests/ -v
```

Tests use an in-memory SQLite database and mock network calls (yfinance / feedparser).
Add tests for any new collector logic or API endpoints. The four test modules map to
the main functional areas: `test_collectors.py`, `test_api.py`, `test_archive.py`.

---

## Branch naming

| Type | Pattern | Example |
|---|---|---|
| Feature | `feat/<short-description>` | `feat/websocket-live-updates` |
| Bug fix | `fix/<short-description>` | `fix/yfinance-multi-index` |
| Documentation | `docs/<short-description>` | `docs/api-reference` |
| Refactor | `refactor/<short-description>` | `refactor/collector-chunking` |

---

## Pull request checklist

Before opening a PR, confirm:

- [ ] `ruff check .` passes
- [ ] `pytest` passes
- [ ] New behaviour is covered by at least one test
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] PR description explains _what_ changed and _why_

---

## Reporting issues

Use the GitHub issue templates:

- **Bug report** — unexpected behaviour or errors
- **Feature request** — new ideas or improvements

Please search existing issues before filing a new one.
