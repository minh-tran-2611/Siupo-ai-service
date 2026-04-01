from fastapi import APIRouter, HTTPException
from loguru import logger

from app.request.chat_request import ChatRequest, DocumentRequest, ClearChatRequest
from app.response.chat_response import ChatResponse, DocumentResponse
from app.service.chat_service import chat
from app.service.rag_service import add_document
from app.memory.conversation_cache import clear_conversation, get_cache_stats

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint.
    Receives a user message and returns an AI response.
    """
    logger.info(f"Chat endpoint: userId={request.userId}, message={request.message[:50]}...")

    try:
        reply = await chat(request.userId, request.message)
        return ChatResponse(reply=reply)
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/clear")
async def clear_chat_endpoint(request: ClearChatRequest):
    """
    Clear conversation history for a user.
    Called when user clicks "New Chat" button.
    """
    logger.info(f"Clear chat: userId={request.userId}")
    clear_conversation(request.userId)
    return {"status": "ok", "message": "Conversation cleared"}


@router.get("/chat/stats")
async def chat_stats_endpoint():
    """Get conversation cache statistics."""
    return get_cache_stats()


@router.post("/documents", response_model=DocumentResponse)
async def documents_endpoint(request: DocumentRequest):
    """
    Document upload endpoint.
    Adds a document to the RAG knowledge base.
    """
    logger.info(f"Documents endpoint: title={request.title}")

    try:
        result = await add_document(request.title, request.content)
        return DocumentResponse(status=result["status"])
    except Exception as e:
        logger.error(f"Documents endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
