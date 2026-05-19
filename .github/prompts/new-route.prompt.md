---
description: "Add a new REST endpoint to an existing router in stan/api/routes/. Enforces static-before-dynamic route ordering, int path-parameter typing, and naive-UTC serialisation."
argument-hint: "Router file and endpoint description (e.g. 'news.py — GET /trending returns top 10 most-mentioned tickers in the last 24h')"
agent: "agent"
---

Add a new REST endpoint to a STAN router based on: **$ARGUMENTS**

## 1. Choose the right router file

| Data domain | File |
|-------------|------|
| Stock prices, candles, ticker list | [stan/api/routes/stocks.py](../../stan/api/routes/stocks.py) |
| News articles, markers, impact | [stan/api/routes/news.py](../../stan/api/routes/news.py) |
| New domain | Create a new `stan/api/routes/<name>.py` and register its router in [stan/api/main.py](../../stan/api/main.py) |

## 2. Insert the route in the correct position

**FastAPI matches routes in declaration order.** Static paths must be declared before any `/{param}` catch-all on the same router or the dynamic route will swallow them.

Canonical order in `news.py` — insert new static routes **above** `/{article_id}`:
```
GET  ""                       ← list / collection
GET  "/markers"               ← static named paths
GET  "/market-markers"        ← static named paths  ← insert new static routes here
GET  "/{article_id}/impact"   ← two-segment dynamic
GET  "/{article_id}"          ← catch-all — ALWAYS LAST
```

If the new route has a path parameter (e.g. `/{symbol}/summary`), place it above any shorter catch-all (`/{article_id}`) because Starlette will still match in declaration order.

## 3. Type path parameters correctly

Declare path parameters with their narrowest correct type. **Never use `str` for IDs that are integers** — doing so masks the route ordering bug and makes 422 errors look like 404s:

```python
# correct
@router.get("/{article_id}/impact")
def get_article_impact(article_id: int, db: Session = Depends(get_db)):

# wrong — hides ordering mistakes and accepts garbage input
@router.get("/{article_id}/impact")
def get_article_impact(article_id: str, ...):
```

Use `Query(...)` with a `pattern=` for string parameters that have a fixed value set (e.g. `period`):
```python
period: str = Query(default="1d", pattern="^(1d|5d|1mo|3mo)$")
```

## 4. Serialise datetimes correctly

All datetimes are stored as **naive UTC** in SQLite. Always append `"Z"` when serialising to JSON:

```python
# correct
"published_at": article.published_at.isoformat() + "Z" if article.published_at else None,

# wrong — returns a naive ISO string with no timezone indicator
"published_at": article.published_at.isoformat(),
```

Never return a `tzinfo`-aware datetime object directly from a route response.

## 5. Return a 404 for missing resources

```python
obj = db.query(Model).filter(Model.id == id).first()
if not obj:
    raise HTTPException(status_code=404, detail="<Resource> not found")
```

## 6. Expose new query parameters via `Query()`

Import `Query` from `fastapi` and declare query params with defaults and validation:
```python
from fastapi import APIRouter, Depends, HTTPException, Query

limit: int = Query(default=50, ge=1, le=200)
```

## 7. Write tests

Add endpoint tests to [tests/test_api.py](../../tests/test_api.py) using the existing `TestClient` + in-memory SQLite fixture pattern:
- Seed the required DB rows directly in the test function.
- Assert correct status code, response shape, and edge cases (missing resource → 404).
- Do **not** make real network calls.

## 8. Verify

After generating the files, run:
```bash
.venv/bin/ruff check .          # must exit 0
pytest tests/ -v                # all tests must pass
```
Fix any lint or test failures before finishing.
