from uuid import uuid4
from unittest.mock import patch

from qdrant_client import QdrantClient

from app.core.config import Settings
from app.documents.chunking import DocumentChunk
from app.rag.qdrant_store import QdrantVectorStore


def test_qdrant_upsert_search_and_tenant_filter() -> None:
    settings = Settings(_env_file=None, qdrant_collection="test_chunks", embedding_dimension=3)
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(client, settings)
    with patch.object(client, "create_payload_index"):
        store.ensure_collection()
    doc_a, doc_b = uuid4(), uuid4()
    chunks = [DocumentChunk(0, "return window is 30 days", 2, "Returns", 0, 24)]
    vectors = [[1.0, 0.0, 0.0]]

    store.upsert_document(
        document_id=doc_a,
        tenant_id="tenant-a",
        filename="returns.pdf",
        content_type="application/pdf",
        checksum="a" * 64,
        chunks=chunks,
        vectors=vectors,
    )
    store.upsert_document(
        document_id=doc_b,
        tenant_id="tenant-b",
        filename="other.pdf",
        content_type="application/pdf",
        checksum="b" * 64,
        chunks=chunks,
        vectors=vectors,
    )

    hits = store.search(query_vector=[1.0, 0.0, 0.0], tenant_id="tenant-a", ready_document_ids=[doc_a, doc_b], limit=3)

    assert len(hits) == 1
    assert hits[0].document_id == doc_a
    assert hits[0].page_number == 2
    assert hits[0].section == "Returns"
    client.close()


def test_qdrant_document_delete_is_scoped_to_tenant() -> None:
    settings = Settings(_env_file=None, qdrant_collection="test_delete", embedding_dimension=2)
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(client, settings)
    with patch.object(client, "create_payload_index"):
        store.ensure_collection()
    document_a, document_b = uuid4(), uuid4()
    chunk = [DocumentChunk(0, "policy", None, None, 0, 6)]
    for tenant_id, document_id in (("tenant-a", document_a), ("tenant-b", document_b)):
        store.upsert_document(
            document_id=document_id,
            tenant_id=tenant_id,
            filename="policy.txt",
            content_type="text/plain",
            checksum="c" * 64,
            chunks=chunk,
            vectors=[[0.0, 1.0]],
        )

    store.delete_document(document_a, "tenant-a")
    remaining = store.search(
        query_vector=[0.0, 1.0], tenant_id="tenant-b", ready_document_ids=[document_b], limit=2
    )

    assert len(remaining) == 1
    assert remaining[0].document_id == document_b
    client.close()
