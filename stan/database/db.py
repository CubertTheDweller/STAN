"""SQLAlchemy engine, session factory, and DB initialisation."""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from stan.config import DB_PATH
from stan.database.models import Base

# SQLite WAL mode for better concurrent read/write
_connect_args = {"check_same_thread": False}

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args=_connect_args,
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, _connection_record):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables and the FTS5 search index if they don't exist."""
    Base.metadata.create_all(bind=engine)

    # FTS5 virtual table for full-text news search.
    # content= keeps the FTS index in sync via an AFTER INSERT trigger below.
    with engine.connect() as conn:
        conn.execute(text(
            """CREATE VIRTUAL TABLE IF NOT EXISTS news_fts
               USING fts5(headline, description,
                          content=news_articles, content_rowid=id)"""
        ))
        # Trigger to auto-index every new article at insert time
        conn.execute(text(
            """CREATE TRIGGER IF NOT EXISTS news_articles_ai
               AFTER INSERT ON news_articles BEGIN
                 INSERT INTO news_fts(rowid, headline, description)
                 VALUES (new.id,
                         COALESCE(new.headline, ''),
                         COALESCE(new.description, ''));
               END"""
        ))
        # Back-fill any rows that pre-date the trigger
        conn.execute(text(
            """INSERT INTO news_fts(rowid, headline, description)
               SELECT id,
                      COALESCE(headline, ''),
                      COALESCE(description, '')
               FROM   news_articles
               WHERE  id NOT IN (SELECT rowid FROM news_fts)"""
        ))
        conn.commit()


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
