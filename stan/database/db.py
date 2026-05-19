"""SQLAlchemy engine, session factory, and DB initialisation."""

from sqlalchemy import create_engine, event
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
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
