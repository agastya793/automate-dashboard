"""
Database Session and Engine Configuration (Milestone 3)

Configures SQLAlchemy 2.x engine and session factory.
Supports local PostgreSQL (DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/reporting_db)
and falls back gracefully to SQLite for isolated unit testing.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Environment variable for database URL
# Default local PostgreSQL connection (bound to loopback 127.0.0.1)
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/reporting_db"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

# Check if using SQLite or PostgreSQL
is_sqlite = DATABASE_URL.startswith("sqlite")

# Engine options
engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
    "future": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL connection pooling
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "10"))
    engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "20"))

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()

_custom_session_factory: Optional[sessionmaker] = None


def set_session_factory(factory: Optional[sessionmaker]) -> None:
    """Set custom session factory (e.g. for isolated test suites or custom binds)."""
    global _custom_session_factory
    _custom_session_factory = factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    factory = _custom_session_factory or SessionLocal
    db = factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone workers / Celery tasks."""
    factory = _custom_session_factory or SessionLocal
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
