---
description: "Use when adding, modifying, or reviewing ORM models, the session factory, or database migrations in stan/database/. Covers DeclarativeBase style, naive-UTC storage, WAL setup, and safe insert patterns."
applyTo: "stan/database/**"
---

## ORM style — SQLAlchemy 2.0

Use `DeclarativeBase` — never `declarative_base()`:

```python
# correct
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class MyModel(Base):
    __tablename__ = "my_table"
    ...

# wrong
from sqlalchemy.orm import declarative_base
Base = declarative_base()
```

## Every new table needs a `UniqueConstraint` on its natural key

This makes repeated collector runs idempotent. Always add it to `__table_args__`:

```python
__table_args__ = (
    UniqueConstraint("article_id", "symbol", "interval_minutes", name="uq_my_table"),
)
```

Name constraints descriptively: `uq_<table>` or `uq_<table>_<key_cols>`.

## Datetime columns — naive UTC only

All `DateTime` columns store **naive UTC** (no `tzinfo`). Never store `tzinfo`-aware datetimes:

```python
# correct — strip tzinfo before storing
dt_naive = aware_dt.replace(tzinfo=None)

# correct — generate naive UTC
from datetime import UTC, datetime
datetime.now(UTC).replace(tzinfo=None)

# wrong — SQLite stores the tzinfo string but comparisons break
column_value = datetime.now(UTC)   # has tzinfo → do NOT store
```

When querying with a cutoff, strip tzinfo from the cutoff too:
```python
cutoff = datetime.now(UTC).replace(tzinfo=None)
db.query(Model).filter(Model.timestamp >= cutoff)
```

## WAL mode and `check_same_thread`

`db.py` sets WAL journal mode and `check_same_thread=False` via the engine event listener and `connect_args`. **Do not remove either setting** — background collector threads and FastAPI request threads share the same SQLite file concurrently.

## Safe insert patterns

| Pattern | When to use |
|---------|-------------|
| `sqlite_insert().on_conflict_do_nothing()` | Bulk idempotent inserts (e.g. price snapshots) |
| `db.merge(obj)` | Upsert a single object by primary key (e.g. seeding impact rows) |
| `db.add(obj)` + catch `IntegrityError` | One-off inserts where the conflict is genuinely unexpected |

```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

stmt = sqlite_insert(PriceSnapshot).values(rows).on_conflict_do_nothing()
db.execute(stmt)
db.commit()
```

## Do not call `Base.metadata.create_all()` outside `init_db()`

Table creation is centralised in `db.py::init_db()`, which is called once in the FastAPI lifespan. Tests use the same function with an in-memory engine — don't scatter `create_all` calls across the codebase.

## Migrations

There is no Alembic migration runner — schema changes are applied by wiping and recreating the DB in development:
```bash
kill $(lsof -ti:8000) 2>/dev/null; rm -f stan.db stan.db-wal stan.db-shm && .venv/bin/python run.py &
```
When adding or renaming columns, update `models.py` and include the wipe command in your instructions to the developer.
