import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health/live", summary="Process liveness")
def liveness() -> dict[str, str]:
    """Return success while the API process can handle requests."""
    return {"status": "ok"}


@router.get("/health/ready", summary="Dependency readiness")
def readiness() -> dict[str, str]:
    """Return success only when PostgreSQL accepts a lightweight query."""
    try:
        check_database()
    except SQLAlchemyError as exc:
        logger.warning("database readiness check failed", extra={"error_type": type(exc).__name__})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependency": "database"},
        ) from exc
    return {"status": "ok", "database": "ok"}
