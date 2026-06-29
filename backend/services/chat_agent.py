import logging
import uuid
from datetime import datetime, timezone

from repos import creatives as creatives_repo
from core.dependencies import get_llm_router
from llm.base import LLMRequest
from services.s3 import upload_bytes, presign_url
from services.creative_registry import CreativeSource, CreativeType, CreativeSubtype

logger = logging.getLogger("revCreate.chat_agent")

async def process_chat_turn(messages: list[dict], client_id: str = "revspot") -> dict:
    """
    Processes a chat turn by generating an image from the latest user message.
    Routes through LLMRouter so model selection and fallback are handled centrally.
    """
    user_messages = [m for m in messages if m["role"] == "user"]
    if not user_messages:
        raise ValueError("No user messages found in history.")

    latest_prompt = user_messages[-1]["content"]
    logger.info("Executing chat image generation for prompt: %s", latest_prompt[:80])

    try:
        # 1. Execute actual generation
        router = get_llm_router()
        resp = await router.route_image(LLMRequest(task_type="image_generation", prompt=latest_prompt))
        img_bytes = resp.image_bytes
        
        # 2. Store in S3
        img_id = str(uuid.uuid4())
        s3_key = f"creatives/chat/{img_id}.png"
        await upload_bytes(s3_key, img_bytes, "image/png")
        
        # 3. Store in DB
        now = datetime.now(timezone.utc)
        await creatives_repo.insert({
            "_id": img_id,
            "source": CreativeSource.GENERATED,
            "client_id": client_id,
            "associations": [],
            "name": "Chat Generation",
            "status": "done",
            "s3_key": s3_key,
            "created_at": now,
            "metadata": {
                "type": CreativeType.IMAGE,
                "subtype": CreativeSubtype.FEED_SQUARE,
                "size_specs": {"width": 1080, "height": 1080, "aspect_ratio": "1:1", "label": "Feed Square"},
                "image_model": "openai/gpt-image-2-2026-04-21",
            },
            "generated": {
                "prompt_used": latest_prompt,
                "variation_index": 1,
                "version": 1,
            }
        })
        
        # 4. Return the presigned URL
        url = await presign_url(s3_key)
        
        return {
            "role": "assistant",
            "content": "", # No text, just the image
            "images": [url]
        }
        
    except Exception as e:
        logger.error("Direct OpenAI generation failed: %s", e)
        raise e
