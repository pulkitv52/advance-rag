import uuid
from typing import List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()

_client: Optional[AsyncQdrantClient] = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=True,
        )
    return _client


async def ensure_collection_exists() -> None:
    """Create the Qdrant collection if it doesn't already exist."""
    client = get_qdrant_client()
    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]

    if settings.QDRANT_COLLECTION not in existing:
        await client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=settings.QDRANT_VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Qdrant collection '{settings.QDRANT_COLLECTION}' created.")
    else:
        logger.info(f"Qdrant collection '{settings.QDRANT_COLLECTION}' already exists.")


async def upsert_chunks(
    chunks: List[dict],
    embeddings: List[List[float]],
    document_id: str,
    filename: str,
    object_key: str,
) -> int:
    """
    Upsert document chunks with their embeddings into Qdrant.

    Args:
        chunks: List of dicts with 'text', 'chunk_index', optional 'page'.
        embeddings: Parallel list of embedding vectors.
        document_id: UUID of the parent document.
        filename: Original filename for metadata.
        object_key: Minio object key for retrieval.

    Returns:
        Number of points upserted.
    """
    client = get_qdrant_client()

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "document_id": document_id,
                "filename": filename,
                "object_key": object_key,
                "text": chunk["text"],
                "chunk_index": chunk.get("chunk_index", i),
                "page": chunk.get("page"),
                "element_type": chunk.get("element_type", "text"),
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    await client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    logger.info(f"Upserted {len(points)} chunks for document '{filename}' (id={document_id})")
    return len(points)


async def search_chunks(
    query_embedding: List[float],
    top_k: int = 10,
    document_ids: Optional[List[str]] = None,
) -> List[dict]:
    """
    Search for the most relevant chunks by vector similarity.

    Args:
        query_embedding: The query vector.
        top_k: Number of results to return.
        document_ids: Optionally filter by a list of documents.

    Returns:
        List of result dicts with 'text', 'score', and metadata.
    """
    client = get_qdrant_client()

    query_filter = None
    if document_ids:
        from qdrant_client.models import MatchAny

        query_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=document_ids),
                )
            ]
        )

    # Search for relevant chunks
    try:
        results = await client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_embedding,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        hits = results.points
    except AttributeError:
        # Fallback for older versions of qdrant-client if needed, though error suggested newer
        results = await client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        hits = results

    return [
        {
            "text": hit.payload.get("text", ""),
            "score": hit.score if hasattr(hit, "score") else 0.0,
            "document_id": hit.payload.get("document_id"),
            "filename": hit.payload.get("filename"),
            "object_key": hit.payload.get("object_key"),
            "chunk_index": hit.payload.get("chunk_index"),
            "page": hit.payload.get("page"),
            "element_type": hit.payload.get("element_type"),
        }
        for hit in hits
    ]

    logger.info(f"Deleted all chunks for document_id={document_id}")


async def purge_collection() -> None:
    """Drop and recreate the entire Qdrant collection to remove all stale data."""
    client = get_qdrant_client()
    try:
        await client.delete_collection(collection_name=settings.QDRANT_COLLECTION)
        logger.info(f"Dropped Qdrant collection '{settings.QDRANT_COLLECTION}'")
        await ensure_collection_exists()
    except Exception as e:
        logger.error(f"Failed to purge Qdrant collection: {e}")
        # Re-ensure collection exists even if delete fails (e.g. didn't exist)
        await ensure_collection_exists()
