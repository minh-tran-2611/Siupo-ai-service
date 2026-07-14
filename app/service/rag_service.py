from app.rag.retriever import upsert_document
from loguru import logger


async def add_document(title: str, content: str, **metadata) -> dict:
    """
    Add a document to the RAG knowledge base.
    Chunks the document and stores embeddings in Qdrant.
    """
    logger.info(f"RAG Service: Adding document '{title}'")

    # Ad-hoc documents are internal unless the caller explicitly classifies them.
    metadata.setdefault("source_type", "internal")
    result = await upsert_document(title=title, content=content, **metadata)

    logger.info(
        f"RAG Service: Document '{title}' {result['status']} "
        f"with {result['chunks']} chunks"
    )
    return result
