from fastapi.testclient import TestClient

from app.db.session import get_db
from app.embeddings.provider import get_embedder
from app.main import app
from app.rag.qdrant_store import get_vector_store


class EmptyDocumentSession:
    def scalars(self, statement):
        return iter(())


def test_agent_run_escalates_sensitive_complaint():
    app.dependency_overrides[get_db] = lambda: EmptyDocumentSession()
    app.dependency_overrides[get_embedder] = lambda: object()
    app.dependency_overrides[get_vector_store] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/agent/run",
                json={"tenant_id": "demo", "message": "I want to make a complaint about fraud"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "complaint"
    assert body["priority"] == "urgent"
    assert body["status"] == "escalation_required"
    assert body["next_action"] == "human_review"


def test_agent_run_knowledge_route_abstains_for_empty_tenant():
    app.dependency_overrides[get_db] = lambda: EmptyDocumentSession()
    app.dependency_overrides[get_embedder] = lambda: object()
    app.dependency_overrides[get_vector_store] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/agent/run",
                json={"tenant_id": "empty-shop", "message": "How do I return a product?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "return_refund"
    assert body["route"] == "knowledge_lookup"
    assert body["status"] == "insufficient_evidence"
    assert body["citations"] == []
