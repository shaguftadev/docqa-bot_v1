from datetime import datetime, timezone

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import ApprovalRequest, WorkflowExecution
from app.agent.checkpointer import get_checkpointer
from app.embeddings.provider import get_embedder
from app.main import app
from app.rag.qdrant_store import get_vector_store


class EmptyDocumentSession:
    def __init__(self):
        self.records = []

    def scalars(self, statement):
        return iter(())

    def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        if entity is WorkflowExecution:
            return next((row for row in self.records if isinstance(row, WorkflowExecution)
                         and row.id == params.get("id_1") and row.tenant_id == params.get("tenant_id_1")), None)
        if entity is ApprovalRequest:
            return next((row for row in self.records if isinstance(row, ApprovalRequest)
                         and row.workflow_id == params.get("workflow_id_1")
                         and row.tenant_id == params.get("tenant_id_1")), None)
        return None

    def add(self, record):
        if isinstance(record, WorkflowExecution):
            record.created_at = datetime.now(timezone.utc)
            record.updated_at = record.created_at
        self.records.append(record)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_agent_run_escalates_sensitive_complaint():
    db = EmptyDocumentSession()
    checkpointer = InMemorySaver()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer
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
    assert body["status"] == "approval_pending"
    assert body["next_action"] == "human_review"
    assert body["workflow_id"]
    assert body["approval_id"]
    assert any(record.status == "waiting_approval" for record in db.records)

    workflow_id = body["workflow_id"]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer
    app.dependency_overrides[get_embedder] = lambda: object()
    app.dependency_overrides[get_vector_store] = lambda: object()
    with TestClient(app) as client:
        status = client.get(f"/agent/{workflow_id}?tenant_id=demo")
        approved = client.post(
            f"/agent/{workflow_id}/decision",
            json={"tenant_id": "demo", "decision": "approve", "edited_answer": "A specialist will contact you."},
        )
        duplicate = client.post(
            f"/agent/{workflow_id}/decision",
            json={"tenant_id": "demo", "decision": "reject"},
        )
    app.dependency_overrides.clear()
    assert status.status_code == 200
    assert status.json()["approval_status"] == "pending"
    assert status.json()["status"] == "approval_pending"
    assert status.json()["state"]["status"] == "approval_pending"
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["answer"] == "A specialist will contact you."
    assert duplicate.status_code == 409


def test_agent_run_knowledge_route_abstains_for_empty_tenant():
    app.dependency_overrides[get_db] = lambda: EmptyDocumentSession()
    app.dependency_overrides[get_checkpointer] = lambda: InMemorySaver()
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
