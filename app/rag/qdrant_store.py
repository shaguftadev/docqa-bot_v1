from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import QdrantClient, models

from app.core.config import Settings, get_settings
from app.documents.chunking import DocumentChunk


class VectorStoreError(RuntimeError):
    """Raised when Qdrant cannot complete an indexing or search operation."""


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    document_id: UUID
    filename: str
    text: str
    score: float
    page_number: int | None
    section: str | None


class QdrantVectorStore:
    def __init__(self, client: QdrantClient, settings: Settings) -> None:
        self.client = client
        self.collection = settings.qdrant_collection
        self.dimension = settings.embedding_dimension

    def ensure_collection(self) -> None:
        try:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE),
                )
            collection_info = self.client.get_collection(self.collection)
            vectors = collection_info.config.params.vectors
            if not isinstance(vectors, models.VectorParams) or vectors.size != self.dimension:
                raise VectorStoreError(
                    f"Collection {self.collection!r} has an incompatible vector configuration; "
                    "use a new collection name when changing embedding models"
                )
            payload_schema = collection_info.payload_schema or {}
            for field_name in ("tenant_id", "document_id"):
                if field_name not in payload_schema:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                        wait=True,
                    )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Could not initialize the Qdrant collection") from exc

    def upsert_document(
        self,
        *,
        document_id: UUID,
        tenant_id: str,
        filename: str,
        content_type: str,
        checksum: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("The number of chunks must match the number of vectors")
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self.dimension:
                raise ValueError(f"Vector dimension must be {self.dimension}")
            chunk_id = f"{document_id}:{chunk.index}"
            points.append(
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, chunk_id)),
                    vector=vector,
                    payload={
                        "chunk_id": chunk_id,
                        "document_id": str(document_id),
                        "tenant_id": tenant_id,
                        "filename": filename,
                        "content_type": content_type,
                        "checksum": checksum,
                        "text": chunk.text,
                        "page_number": chunk.page_number,
                        "section": chunk.section,
                        "chunk_index": chunk.index,
                    },
                )
            )
        if not points:
            raise ValueError("Cannot index a document without text chunks")
        try:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError("Qdrant failed to store document chunks") from exc

    def delete_document(self, document_id: UUID, tenant_id: str) -> None:
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id))),
                            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Qdrant failed to remove document chunks") from exc

    def search(
        self,
        *,
        query_vector: list[float],
        tenant_id: str,
        ready_document_ids: list[UUID],
        limit: int,
    ) -> list[SearchHit]:
        if not ready_document_ids:
            return []
        try:
            response = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchAny(any=[str(document_id) for document_id in ready_document_ids]),
                        ),
                    ]
                ),
                with_payload=True,
                limit=limit,
            )
        except Exception as exc:
            raise VectorStoreError("Qdrant search failed") from exc

        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            try:
                hits.append(
                    SearchHit(
                        chunk_id=str(payload["chunk_id"]),
                        document_id=UUID(str(payload["document_id"])),
                        filename=str(payload["filename"]),
                        text=str(payload["text"]),
                        score=float(point.score),
                        page_number=payload.get("page_number"),
                        section=payload.get("section"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise VectorStoreError("Qdrant returned a point with incomplete citation metadata") from exc
        return hits


@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=5,
    )
    return QdrantVectorStore(client, settings)
