from __future__ import annotations

import base64
import io
import logging
import time
from typing import Any

import openai
from openai import AsyncOpenAI

from llm.base import (
    BaseLLM,
    LLMRequest,
    LLMResponse,
    ImageResponse,
    MalformedResponseError,
    ProviderPermanentError,
    ProviderTransientError,
)

logger = logging.getLogger("revCreate.llm.adapters.openai")

# Supported gpt-image-2 sizes
_LANDSCAPE = "1536x1024"
_PORTRAIT  = "1024x1536"
_SQUARE    = "1024x1024"

# Aspect-ratio string → OpenAI size
_RATIO_MAP: dict[str, str] = {
    "1:1":  _SQUARE,
    "4:3":  _LANDSCAPE,
    "3:2":  _LANDSCAPE,
    "16:9": _LANDSCAPE,
    "21:9": _LANDSCAPE,
    "4:1":  _LANDSCAPE,
    "2.7:1": _LANDSCAPE,
    "3:4":  _PORTRAIT,
    "2:3":  _PORTRAIT,
    "9:16": _PORTRAIT,
    "4:5":  _PORTRAIT,
}


def _map_size(aspect_ratio: str | None) -> str:
    """Map an aspect-ratio string OR 'WxH' dimensions string to an OpenAI image size."""
    if not aspect_ratio:
        return _SQUARE

    # Already a known ratio string
    if aspect_ratio in _RATIO_MAP:
        return _RATIO_MAP[aspect_ratio]

    # Try parsing "WxH" or "W:H"
    sep = "x" if "x" in aspect_ratio.lower() else ":"
    try:
        parts = aspect_ratio.lower().split(sep)
        ratio = float(parts[0]) / float(parts[1])
    except (ValueError, IndexError, ZeroDivisionError):
        return _SQUARE

    if ratio > 1.1:
        return _LANDSCAPE
    if ratio < 0.9:
        return _PORTRAIT
    return _SQUARE


def _to_file(img_bytes: bytes, mime_type: str) -> tuple[str, io.BytesIO, str]:
    ext = mime_type.split("/")[-1] or "png"
    return (f"image.{ext}", io.BytesIO(img_bytes), mime_type)


class OpenAIAdapter(BaseLLM):
    MODEL_TEXT = "gpt-4o"
    MODEL_IMAGE = "gpt-image-2-2026-04-21"

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    # ── Text generation ───────────────────────────────────────────────────────

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.time()

        # OpenAI Responses API requires the word "json" somewhere in the input
        # when text.format = json_object (checked against the `input` field).
        system = request.system_prompt or ""
        prompt = request.prompt
        if "json" not in prompt.lower():
            prompt = prompt + "\n\nRespond with valid JSON."

        kwargs: dict[str, Any] = dict(
            model=self.MODEL_TEXT,
            input=prompt,
            temperature=request.temperature,
            text={"format": {"type": "json_object"}},
        )
        if system:
            kwargs["instructions"] = system

        try:
            response = await self._client.responses.create(**kwargs)
        except openai.RateLimitError as exc:
            raise ProviderTransientError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code == 503:
                raise ProviderTransientError(str(exc)) from exc
            raise ProviderPermanentError(str(exc)) from exc
        except openai.BadRequestError as exc:
            raise ProviderPermanentError(str(exc)) from exc
        except openai.AuthenticationError as exc:
            raise ProviderPermanentError(str(exc)) from exc

        latency_ms = int((time.time() - start) * 1000)

        text = response.output_text or ""
        usage = response.usage

        cost = 0.0
        cached = 0
        if usage:
            cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
            non_cached = (usage.input_tokens or 0) - cached
            cost = (
                non_cached * 2.50 / 1_000_000
                + cached * 1.25 / 1_000_000
                + (usage.output_tokens or 0) * 10.00 / 1_000_000
            )

        logger.info(
            "TOKENS %s — input=%s(cached=%d) output=%s total=%s cost=$%.5f latency_ms=%d",
            request.task_type,
            usage.input_tokens if usage else "?",
            cached,
            usage.output_tokens if usage else "?",
            usage.total_tokens if usage else "?",
            cost,
            latency_ms,
        )

        return LLMResponse(text=text, model=self.MODEL_TEXT, latency_ms=latency_ms, cost=cost)

    # ── Image generation ──────────────────────────────────────────────────────

    async def generate_image(self, request: LLMRequest) -> ImageResponse:
        if request.task_type == "image_edit":
            return await self._image_edit(request)
        return await self._image_generation(request)

    async def _image_generation(self, request: LLMRequest) -> ImageResponse:
        start = time.time()
        metadata = request.metadata or {}
        size = _map_size(metadata.get("aspect_ratio"))
        images = request.images

        # Build full prompt: prepend system context if provided
        prompt_parts = []
        if request.system_prompt:
            prompt_parts.append(request.system_prompt)
        prompt_parts.append(request.prompt)
        full_prompt = "\n\n".join(prompt_parts)

        # Determine primary input image (source_ad > product > ref > logo)
        source_ad = metadata.get("source_ad")
        primary: tuple[bytes, str] | None = None
        if source_ad:
            primary = source_ad
        elif images and images.product_images:
            primary = images.product_images[0]
        elif images and images.ref_images:
            primary = images.ref_images[0]
        elif images and images.logo_images:
            primary = images.logo_images[0]

        try:
            if primary:
                img_bytes, mime_type = primary
                all_images = [_to_file(img_bytes, mime_type)]
                if images:
                    for rb, rm in images.ref_images:
                        if (rb, rm) != primary:
                            all_images.append(_to_file(rb, rm))
                    for lb, lm in images.logo_images:
                        if (lb, lm) != primary:
                            all_images.append(_to_file(lb, lm))

                response = await self._client.images.edit(
                    model=self.MODEL_IMAGE,
                    image=all_images if len(all_images) > 1 else all_images[0],
                    prompt=full_prompt,
                    size=size,
                )
            else:
                response = await self._client.images.generate(
                    model=self.MODEL_IMAGE,
                    prompt=full_prompt,
                    size=size,
                )
        except openai.RateLimitError as exc:
            raise ProviderTransientError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code == 503:
                raise ProviderTransientError(str(exc)) from exc
            raise ProviderPermanentError(str(exc)) from exc
        except openai.BadRequestError as exc:
            raise ProviderPermanentError(str(exc)) from exc
        except openai.AuthenticationError as exc:
            raise ProviderPermanentError(str(exc)) from exc

        latency_ms = int((time.time() - start) * 1000)
        image_data = response.data[0] if response.data else None
        if image_data is None or not image_data.b64_json:
            raise MalformedResponseError("No image data in OpenAI response")

        image_bytes = base64.b64decode(image_data.b64_json)

        usage = getattr(response, "usage", None)
        cost = 0.0
        text_in = img_in = out_tokens = 0
        if usage:
            details = getattr(usage, "input_tokens_details", None)
            text_in = getattr(details, "text_tokens", 0) or 0
            img_in = getattr(details, "image_tokens", 0) or 0
            out_tokens = getattr(usage, "output_tokens", 0) or 0
            cost = (
                text_in * 5.00 / 1_000_000
                + img_in * 8.00 / 1_000_000
                + out_tokens * 30.00 / 1_000_000
            )

        logger.info(
            "IMAGE %s — size=%s cost=$%.5f(text_in=%d img_in=%d out=%d) latency_ms=%d bytes=%d",
            request.task_type, size, cost, text_in, img_in, out_tokens, latency_ms, len(image_bytes),
        )
        return ImageResponse(image_bytes=image_bytes, model=self.MODEL_IMAGE, latency_ms=latency_ms, cost=cost)

    async def _image_edit(self, request: LLMRequest) -> ImageResponse:
        """image_edit — passes current image + flattened instruction context to images.edit()."""
        start = time.time()
        metadata = request.metadata or {}
        images = request.images
        size = _map_size(metadata.get("aspect_ratio"))

        # Build a comprehensive prompt from context + edit history + current instruction
        context_lines: list[str] = []
        if request.system_prompt:
            context_lines.append(request.system_prompt)

        description = metadata.get("description", "")
        persona_info = metadata.get("persona_info", "")
        creative_strategy = metadata.get("creative_strategy", "")
        ad_copy = metadata.get("ad_copy")
        meta_ad_copy = metadata.get("meta_ad_copy")
        edit_history: list[str] = metadata.get("edit_history", [])

        if description:
            context_lines.append(f"Product Description: {description}")
        if persona_info:
            context_lines.append(f"Target Persona: {persona_info}")
        if creative_strategy:
            context_lines.append(f"Creative Strategy: {creative_strategy}")
        if ad_copy:
            context_lines.append("Ad Copy on Image:")
            if ad_copy.get("headline"):
                context_lines.append(f"  Headline: {ad_copy['headline']}")
            if ad_copy.get("body_copy"):
                context_lines.append(f"  Body Copy: {ad_copy['body_copy']}")
            if ad_copy.get("cta"):
                context_lines.append(f"  CTA: {ad_copy['cta']}")
        if meta_ad_copy:
            context_lines.append("Meta Ad Copy:")
            if "headline" in meta_ad_copy:
                h = meta_ad_copy["headline"]
                context_lines.append(f"  Headline: {h[0] if isinstance(h, list) and h else h}")
            if "primary_text" in meta_ad_copy:
                p = meta_ad_copy["primary_text"]
                context_lines.append(f"  Primary Text: {p[0] if isinstance(p, list) and p else p}")
        if edit_history:
            context_lines.append("Prior edits applied (in order):")
            for i, past in enumerate(edit_history, 1):
                context_lines.append(f"  {i}. {past}")
        context_lines.append(f"Current edit instruction: {request.prompt}")

        full_prompt = "\n".join(context_lines)

        # Current image is in product_images[0]; ref_images are passed alongside for logo/asset swaps
        if not (images and images.product_images):
            raise ProviderPermanentError("image_edit requires a current image in product_images[0]")
        img_bytes, mime_type = images.product_images[0]
        all_images = [_to_file(img_bytes, mime_type)]
        if images:
            for rb, rm in images.ref_images:
                all_images.append(_to_file(rb, rm))
            for lb, lm in images.logo_images:
                all_images.append(_to_file(lb, lm))

        try:
            response = await self._client.images.edit(
                model=self.MODEL_IMAGE,
                image=all_images if len(all_images) > 1 else all_images[0],
                prompt=full_prompt,
                size=size,
            )
        except openai.RateLimitError as exc:
            raise ProviderTransientError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code == 503:
                raise ProviderTransientError(str(exc)) from exc
            raise ProviderPermanentError(str(exc)) from exc
        except openai.BadRequestError as exc:
            raise ProviderPermanentError(str(exc)) from exc
        except openai.AuthenticationError as exc:
            raise ProviderPermanentError(str(exc)) from exc

        latency_ms = int((time.time() - start) * 1000)
        image_data = response.data[0] if response.data else None
        if image_data is None or not image_data.b64_json:
            raise MalformedResponseError("No image data in OpenAI edit response")

        image_bytes = base64.b64decode(image_data.b64_json)

        usage = getattr(response, "usage", None)
        cost = 0.0
        text_in = img_in = out_tokens = 0
        if usage:
            details = getattr(usage, "input_tokens_details", None)
            text_in = getattr(details, "text_tokens", 0) or 0
            img_in = getattr(details, "image_tokens", 0) or 0
            out_tokens = getattr(usage, "output_tokens", 0) or 0
            cost = (
                text_in * 5.00 / 1_000_000
                + img_in * 8.00 / 1_000_000
                + out_tokens * 30.00 / 1_000_000
            )

        logger.info(
            "IMAGE %s — size=%s cost=$%.5f(text_in=%d img_in=%d out=%d) latency_ms=%d bytes=%d",
            request.task_type, size, cost, text_in, img_in, out_tokens, latency_ms, len(image_bytes),
        )
        return ImageResponse(image_bytes=image_bytes, model=self.MODEL_IMAGE, latency_ms=latency_ms, cost=cost)
