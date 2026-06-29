from __future__ import annotations

from dataclasses import dataclass, field

from core.protocols import ImageBundle


class ProviderTransientError(Exception):
    """timeout, 429, 503 — retry same model ≤3 times, then fallback"""


class ProviderPermanentError(Exception):
    """400 bad request, 401/403 auth, wrong modality — fail immediately"""


class MalformedResponseError(Exception):
    """response received but unparseable — retry once, then fail"""


@dataclass
class LLMRequest:
    prompt: str
    task_type: str  # brand_extraction | copy_generation | image_prompt_generation | image_generation | image_edit
    system_prompt: str | None = None
    images: ImageBundle | None = None
    temperature: float = 0.7
    metadata: dict | None = None  # aspect_ratio, step, edit_history, source_ad, etc.


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: int
    cost: float = 0.0
    raw: dict | None = None


@dataclass
class ImageResponse:
    image_bytes: bytes
    model: str
    latency_ms: int
    cost: float = 0.0


class BaseLLM:
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def generate_image(self, request: LLMRequest) -> ImageResponse:
        raise NotImplementedError
