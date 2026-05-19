---
description: "Scaffold a new background collector in stan/collectors/ and wire it into the scheduler"
argument-hint: "Collector name and what it collects (e.g. 'earnings — fetch quarterly earnings dates from Yahoo Finance')"
agent: "agent"
---

Scaffold a new background collector for STAN based on: **$ARGUMENTS**

## 1. Create `stan/collectors/<name>.py`

Follow the exact pattern used by [stan/collectors/impact.py](../../stan/collectors/impact.py):

- Module docstring describing what the collector does and when it runs.
- `import logging` + `logger = logging.getLogger(__name__)` at module level.
- One public function `collect_<name>() -> None` — no arguments; opens its own DB session.
- Session lifecycle:
  ```python
  db = SessionLocal()
  try:
      # ... work ...
      db.commit()
      logger.info("…")
  except Exception as exc:
      logger.error("collect_<name> error: %s", exc)
      db.rollback()
  finally:
      db.close()
  ```
- Use `db.merge()` for upsert-style inserts; use `sqlite_insert().on_conflict_do_nothing()` for bulk idempotent inserts.
- All `datetime` values must be **naive UTC** — strip `tzinfo` before storing: `dt.replace(tzinfo=None)`.
- Wrap every float from external sources with `_safe_float()` (or an equivalent inline guard) to convert `NaN → None`.

## 2. Add ORM models if needed

If new tables are required, add them to [stan/database/models.py](../../stan/database/models.py):
- Inherit from `Base` (`DeclarativeBase` style — no `declarative_base()` call).
- Add a `UniqueConstraint` for any natural key to allow safe re-runs.
- Do **not** rename or remove existing tables/columns.

## 3. Register the job in `stan/scheduler.py`

Add a new `scheduler.add_job(…)` block to [stan/scheduler.py](../../stan/scheduler.py) following the existing pattern:
```python
scheduler.add_job(
    collect_<name>,
    trigger=IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
    id="collect_<name>",
    name="<Human-readable description>",
    replace_existing=True,
    max_instances=1,
    misfire_grace_time=60,
)
```
Import the new function at the top of `scheduler.py` alongside the existing imports.

## 4. Update `stan/api/main.py` if an immediate first-run is needed

If the collector should fire immediately on startup (like `collect_stocks` and `collect_news`), add a `threading.Thread(target=collect_<name>, daemon=True).start()` call inside the lifespan startup block in [stan/api/main.py](../../stan/api/main.py).

## 5. Expose data via REST if needed

If the new data should be queryable:
- Add a route to the appropriate file in [stan/api/routes/](../../stan/api/routes/).
- **Static routes must be declared before any `/{param}` dynamic routes** in the same router to avoid FastAPI matching the wrong handler.
- Return naive UTC datetimes serialised as `dt.isoformat() + "Z"`.

## 6. Write tests

Add tests to [tests/test_collectors.py](../../tests/test_collectors.py):
- Use `unittest.mock.patch` to mock any external calls (yfinance, feedparser, httpx, etc.) — never make real network calls in tests.
- Use an in-memory SQLite session (`StaticPool` + `check_same_thread=False`) — see existing test setup in [tests/test_api.py](../../tests/test_api.py) for the fixture pattern.
- Assert rows were inserted/updated correctly.

## 7. Verify

After generating the files, run:
```bash
.venv/bin/ruff check .          # must exit 0
pytest tests/ -v                # all tests must pass
```
Fix any lint or test failures before finishing.
