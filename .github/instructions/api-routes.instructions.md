---
description: "Use when adding, reordering, or modifying FastAPI routes in stan/api/routes/. Covers static-before-dynamic route ordering and path-parameter type coercion."
applyTo: "stan/api/routes/**"
---

## Route declaration order

FastAPI (Starlette) matches routes **in the order they are declared**. Static paths must come before parameterised paths on the same router or the dynamic route wins.

Current canonical order in `news.py` — preserve it when adding new routes:
```
GET  ""                    ← list
GET  "/markers"            ← static
GET  "/market-markers"     ← static  ← must be ABOVE /{article_id}
GET  "/{article_id}/impact"
GET  "/{article_id}"       ← catch-all — always last
```

**Wrong** (new static route added after the catch-all):
```python
@router.get("/{article_id}")           # declared first — wins
...
@router.get("/market-markers")         # never reached
```

**Right**:
```python
@router.get("/market-markers")         # declared first — wins
...
@router.get("/{article_id}")           # catch-all last
```

## `int` path-parameter coercion gotcha

When a path parameter is typed `int` (e.g. `article_id: int`), FastAPI returns **422 "Input should be a valid integer"** — not 404 — if a misplaced static route is matched as that parameter:

```python
# GET /api/news/market-markers → 422, input="market-markers"  ← wrong order
@router.get("/{article_id}")
def get_article(article_id: int, ...):
```

Fix: move the static route above the `/{article_id}` handler. Do not change the parameter type to `str` as a workaround.

## Datetime serialisation

Return naive UTC datetimes with an explicit `Z` suffix:
```python
dt.isoformat() + "Z"   # correct — ISO 8601 Zulu
```
Never return `tzinfo`-aware datetime objects directly from a route; SQLAlchemy stores them naive.
