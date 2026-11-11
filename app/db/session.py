from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=5,
    connect_args={"connect_timeout": 3},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield one request-scoped SQLAlchemy session."""
    with SessionLocal() as session:
        yield session


def check_database() -> None:
    """Raise on database connection failure; used by readiness endpoint."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
