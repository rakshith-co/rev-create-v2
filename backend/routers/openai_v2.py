import os
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from openai import AsyncOpenAI
from auth import require_api_key

# This router is a generic proxy for OpenAI image generation
# It does not use the rev-create S3 or MongoDB context.
router = APIRouter(prefix="/api/v2/openai", tags=["openai-v2"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger("revCreate.openai_v2")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
IMAGE_MODEL = "gpt-image-2-2026-04-21"

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client

class ChatMessage(BaseModel):
    role: str # "user" or "assistant"
    content: str
    image_url: Optional[str] = None # For potential history-based editing later

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    size: Optional[str] = "1024x1024"

@router.post("/chat")
async def openai_image_chat(request: ChatRequest):
    """
    A generic Chat-like API for OpenAI image generation.
    It takes a conversation history and uses the latest user message to generate an image.
    Returns the raw OpenAI response data (ephemeral URL or b64).
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")

    # Find the latest user instruction
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    
    latest_prompt = user_messages[-1].content
    
    logger.info("Direct OpenAI Chat Gen — model=%s prompt=%r", IMAGE_MODEL, latest_prompt[:50])

    try:
        # We call the generic OpenAI API directly
        # If there were previous images in history, we could theoretically use .edit() 
        # but for a "generic" generation turn, we use .generate()
        response = await _get_client().images.generate(
            model=IMAGE_MODEL,
            prompt=latest_prompt,
            size=request.size,
            n=1,
            response_format="url" # "url" for ephemeral link or "b64_json"
        )
        
        # Return a response format similar to what a client expects from a Chat/Claude API
        # but specifically tailored for this image-per-turn workflow.
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "image": response.data[0].url
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": getattr(response, "usage", {})
        }

    except Exception as e:
        logger.error("OpenAI direct call failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
