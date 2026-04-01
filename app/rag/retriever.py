import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http import models
from loguru import logger

from app.rag.embedder import get_embedding, get_embeddings_batch

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "restaurant_knowledge"
EMBEDDING_DIM = 768

_client: QdrantClient = None


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client."""
    global _client
    if _client is None:
        _client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY if QDRANT_API_KEY else None
        )
    return _client


async def init_collection():
    """Initialize Qdrant collection if not exists."""
    client = get_qdrant_client()
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE
            )
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")
    else:
        logger.info(f"Qdrant collection already exists: {COLLECTION_NAME}")


async def store_document(title: str, content: str, chunk_size: int = 500, overlap: int = 50):
    """
    Store a document by chunking and embedding it.
    chunk_size and overlap are in characters (approximation for tokens).
    """
    client = get_qdrant_client()

    # Simple chunking by character count
    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        chunks.append(chunk)
        start = end - overlap

    # Get embeddings for all chunks
    embeddings = await get_embeddings_batch(chunks)

    # Prepare points for Qdrant
    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "title": title,
                    "content": chunk,
                    "chunk_index": i
                }
            )
        )

    # Upsert to Qdrant
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info(f"Stored document '{title}' with {len(chunks)} chunks")
    return len(chunks)


async def retrieve_relevant_chunks(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve top-k relevant chunks for a query."""
    client = get_qdrant_client()

    # Get query embedding
    query_embedding = await get_embedding(query)

    # Search Qdrant
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        limit=top_k
    )

    chunks = []
    for result in results:
        chunks.append({
            "title": result.payload.get("title", ""),
            "content": result.payload.get("content", ""),
            "score": result.score
        })

    logger.info(f"Retrieved {len(chunks)} chunks for query")
    return chunks
