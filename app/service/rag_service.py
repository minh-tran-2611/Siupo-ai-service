from app.rag.retriever import store_document
from loguru import logger


async def add_document(title: str, content: str) -> dict:
    """
    Add a document to the RAG knowledge base.
    Chunks the document and stores embeddings in Qdrant.
    """
    logger.info(f"RAG Service: Adding document '{title}'")

    chunk_count = await store_document(title, content)

    logger.info(f"RAG Service: Document '{title}' stored with {chunk_count} chunks")
    return {"status": "stored", "chunks": chunk_count}
