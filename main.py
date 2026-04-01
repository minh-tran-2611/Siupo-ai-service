import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.controller.chat_controller import router as chat_router
from app.memory.sqlite_memory import init_db
from app.rag.retriever import init_collection
from app.rag.embedder import init_embedder
from app.scheduler.consolidate_scheduler import start_scheduler, stop_scheduler

# Configure loguru
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    # Startup
    logger.info("Starting AI Service...")

    # Initialize embedder
    init_embedder()
    logger.info("Embedder initialized")

    # Initialize Turso database
    await init_db()
    logger.info("Turso database initialized")

    # Initialize Qdrant collection
    await init_collection()
    logger.info("Qdrant collection initialized")

    # Start consolidation scheduler
    start_scheduler()
    logger.info("Consolidation scheduler started")

    logger.info("AI Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down AI Service...")
    stop_scheduler()
    logger.info("AI Service shut down")


app = FastAPI(
    title="Restaurant AI Service",
    description="AI-powered assistant for restaurant management",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router, prefix="/api", tags=["Chat"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
