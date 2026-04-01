import os
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
from loguru import logger

PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
REGION = os.getenv("GOOGLE_REGION", "us-central1")

_model: TextEmbeddingModel = None


def init_embedder():
    """Initialize the Vertex AI embedding model."""
    global _model
    aiplatform.init(project=PROJECT_ID, location=REGION)
    _model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    logger.info("Vertex AI embedder initialized")


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for a text string."""
    if _model is None:
        init_embedder()

    embeddings = _model.get_embeddings([text])
    return embeddings[0].values


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for multiple texts."""
    if _model is None:
        init_embedder()

    embeddings = _model.get_embeddings(texts)
    return [e.values for e in embeddings]
