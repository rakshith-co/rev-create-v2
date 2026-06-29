import logging
from fastapi import APIRouter, Depends, HTTPException

from auth import require_auth
from schemas import ChatRequest, ChatResponse
from services.chat_agent import process_chat_turn

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.chat")

@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest):
    """
    Handles a true chat workflow. It accepts the conversation history,
    uses the Gemini LLM as a conversational agent, and if necessary,
    calls OpenAI to generate ad images based on the flow.
    """
    logger.info("Received chat request with %d messages.", len(request.messages))
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")
        
    messages_dict = [msg.model_dump() for msg in request.messages]
    
    try:
        result = await process_chat_turn(messages_dict)
        return ChatResponse(**result)
    except Exception as e:
        logger.error("Chat agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
