from fastapi.testclient import TestClient

from app.main import app
from app.rag.qdrant_store import SearchHit
from app.schemas.documents import SearchHitResponse
from uuid import uuid4


def test_upload_rejects_unsupported_file_before_database_use() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            data={"tenant_id": "demo"},
            files={"file": ("unsupported.docx", b"not a supported file", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert "Supported file extensions" in response.json()["detail"]


def test_search_validates_limit() -> None:
    with TestClient(app) as client:
        response = client.post("/knowledge/search", json={"query": "return policy", "limit": 11})

    assert response.status_code == 422


def test_search_hit_serializes_citation_fields() -> None:
    hit = SearchHit(
        chunk_id="doc-id:0",
        document_id=uuid4(),
        filename="returns.pdf",
        text="Damaged items should be reported within seven days.",
        score=0.87,
        page_number=2,
        section="Damaged items",
    )

    result = SearchHitResponse.model_validate(hit)

    assert result.filename == "returns.pdf"
    assert result.page_number == 2
    assert result.section == "Damaged items"
