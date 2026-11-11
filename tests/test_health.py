from fastapi.testclient import TestClient

from app.api import health
from app.main import app


def test_liveness_returns_ok_and_correlation_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "demo-check-123"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Correlation-ID"] == "demo-check-123"


def test_readiness_returns_ok_when_database_is_reachable(monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: None)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_returns_503_when_database_fails(monkeypatch) -> None:
    from sqlalchemy.exc import OperationalError

    def fail_database_check() -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(health, "check_database", fail_database_check)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "not_ready", "dependency": "database"}}
