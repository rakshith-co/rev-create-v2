from __future__ import annotations

import json
import logging
import time
from typing import Any

from google import genai
from google.genai import types

from llm.base import (
    BaseLLM,
    LLMRequest,
    LLMResponse,
    ImageResponse,
    MalformedResponseError,
    ProviderPermanentError,
    ProviderTransientError,
)

logger = logging.getLogger("revCreate.llm.adapters.gemini")

_TRANSIENT_STATUSES = {429, 503}
_PERMANENT_STATUSES = {400, 401, 403}


class GeminiAdapter(BaseLLM):
    MODEL_TEXT = "gemini-2.5-flash"
    MODEL_IMAGE = "gemini-3-pro-image-preview"

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    # ── Text generation ───────────────────────────────────────────────────────

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.time()
        try:
            if request.task_type == "brand_extraction":
                response = await self._brand_extraction(request)
            else:
                response = await self._text_generation(request)
        except genai.errors.ClientError as exc:
            self._raise_mapped(exc)
        except Exception as exc:
            raise

        latency_ms = int((time.time() - start) * 1000)

        try:
            text = response.text
        except Exception as exc:
            raise MalformedResponseError(f"Could not read response text: {exc}") from exc

        u = response.usage_metadata
        logger.info(
            "TOKENS %s — input=%s output=%s total=%s latency_ms=%d",
            request.task_type,
            u.prompt_token_count if u else "?",
            u.candidates_token_count if u else "?",
            u.total_token_count if u else "?",
            latency_ms,
        )

        return LLMResponse(text=text, model=self.MODEL_TEXT, latency_ms=latency_ms)

    async def _text_generation(self, request: LLMRequest) -> Any:
        """copy_generation | image_prompt_generation — multimodal with JSON mode."""
        contents: list = []
        if request.images:
            for img_bytes, mime_type in request.images.product_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
            for img_bytes, mime_type in request.images.ref_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
            for img_bytes, mime_type in request.images.logo_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
        contents.append(request.prompt)

        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            response_mime_type="application/json",
            temperature=request.temperature
        )

        return await self._client.aio.models.generate_content(
            model=self.MODEL_TEXT,
            contents=contents,
            config=config,
        )

    async def _brand_extraction(self, request: LLMRequest) -> Any:
        """brand_extraction — text-only prompt, JSON mode, optional grounding retry."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=request.temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=0), # 0 for now, will increase once impl spec is clear
        )

        response = await self._client.aio.models.generate_content(
            model=self.MODEL_TEXT,
            contents=request.prompt,
            config=config,
        )

        # Check whether company_name is empty/unknown — if so, retry with grounding.
        try:
            parsed = json.loads(response.text)
            company_name = parsed.get("company_name")
            needs_grounding = (
                not company_name
                or str(company_name).strip().lower() in ("", "unknown", "null", "none")
            )
        except (json.JSONDecodeError, AttributeError):
            # Can't parse — return as-is and let caller handle it.
            return response

        if needs_grounding:
            logger.info("brand_extraction: company_name empty/unknown, retrying with Google Search grounding")
            grounded_config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=request.temperature,
            )
            grounded_response = await self._client.aio.models.generate_content(
                model=self.MODEL_TEXT,
                contents=request.prompt,
                config=grounded_config,
            )
            # Grounded response is plain text — extract JSON substring and merge.
            try:
                raw_text = grounded_response.text
                start_idx = raw_text.index("{")
                end_idx = raw_text.rindex("}") + 1
                grounded_parsed = json.loads(raw_text[start_idx:end_idx])
                merged = {**grounded_parsed, **{k: v for k, v in parsed.items() if v}}
                # Return a synthetic object that carries the merged JSON as .text
                return _TextWrapper(json.dumps(merged), grounded_response.usage_metadata)
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("brand_extraction: grounding retry parse failed: %s", exc)
                # Fall back to original response.
                return response

        return response

    # ── Image generation ──────────────────────────────────────────────────────

    async def generate_image(self, request: LLMRequest) -> ImageResponse:
        start = time.time()
        try:
            if request.task_type == "image_edit":
                response = await self._image_edit(request)
            else:
                response = await self._image_generation(request)
        except genai.errors.ClientError as exc:
            self._raise_mapped(exc)
        except Exception:
            raise

        latency_ms = int((time.time() - start) * 1000)

        u = response.usage_metadata
        logger.info(
            "TOKENS %s — input=%s output=%s total=%s latency_ms=%d",
            request.task_type,
            u.prompt_token_count if u else "?",
            u.candidates_token_count if u else "?",
            u.total_token_count if u else "?",
            latency_ms,
        )

        for part in response.parts:
            if part.inline_data is not None:
                return ImageResponse(
                    image_bytes=part.inline_data.data,
                    model=self.MODEL_IMAGE,
                    latency_ms=latency_ms,
                )

        raise MalformedResponseError("No image part in Gemini response")

    async def _image_generation(self, request: LLMRequest) -> Any:
        """image_generation — mirrors services/image_model.py::generate_image."""
        metadata = request.metadata or {}
        images = request.images

        aspect_ratio = self._map_aspect_ratio(metadata.get("aspect_ratio", "1:1"))

        contents: list = []

        # ── Source ad (size-variant mode) ─────────────────────────────────────
        source_ad = metadata.get("source_ad")
        if source_ad:
            img_bytes, mime_type = source_ad
            contents.append(
                "=== SOURCE AD — the fully rendered ad to adapt for this placement ===\n"
                "Preserve ALL of the following from this ad exactly:\n"
                "  • Overall composition, zone positions, and layout structure\n"
                "  • All graphic elements: dividers, panels, badges, borders, shapes, curves\n"
                "  • Typography: font weight hierarchy, size ratios, case treatment, letter spacing\n"
                "  • Colour palette: background, text, overlay, strip, and button colours\n"
                "  • Brand elements: logo position and size, CTA design\n"
                "  • Ad copy: headline, body copy, and CTA text — do not alter any wording\n"
                "  • Hero visual and background — the product shown in this ad MUST remain the hero/background.\n"
                "    Use the PRODUCT IMAGES provided to faithfully reconstruct the product at the new canvas size.\n"
                "Only change the canvas aspect ratio and recompose zones to fit the new dimensions naturally."
            )
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        # ── Reference images (Type B) ─────────────────────────────────────────
        if images and images.ref_images:
            contents.append(
                "=== IMAGE TYPE B: REFERENCE AD — LAYOUT WIREFRAME ONLY ===\n"
                "MANDATORY: Use this image ONLY as a template for layout structure and zones.\n"
                "Replicate the following EXACTLY from this reference ad:\n"
                "  ✓ Zone positions — logo, headline, body copy, CTA: exact corner, side, and vertical placement\n"
                "  ✓ Panel structure — split-panel proportions, solid colour blocks, full-bleed regions\n"
                "  ✓ Graphic elements — dividers/rules, geometric shapes, badges, borders, curves, and their colours\n"
                "  ✓ Typography hierarchy — weight, size ratio, case treatment, letter spacing, and alignment per text level\n"
                "  ✓ Colour palette — background, text, overlay, strip, and button colours\n"
                "  ✓ Overlay / tint — colour, opacity, and blend mode applied over the background image\n"
                "  ✓ Spacing rhythm — outer margins, inter-element gaps, strip heights\n"
                "FORBIDDEN: Do NOT use any visual content from this image.\n"
                "  → Background scene / environment → DISCARD COMPLETELY\n"
                "  → Hero visual / building / product shown → DISCARD COMPLETELY\n"
                "  → Logo / brand marks → DISCARD COMPLETELY\n"
                "BOTTOM-ZONE OVERRIDE (absolute — supersedes any layout in this reference ad):\n"
                "  Even if this reference ad places content or design elements in the bottom 20% of the canvas,\n"
                "  ignore that entirely. The bottom 20% of your output must be pure background only — no text,\n"
                "  no graphics, no icons, no strips, no overlays."
            )
            for img_bytes, mime_type in images.ref_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        # ── Product images (Type A) ───────────────────────────────────────────
        if images and images.product_images:
            if source_ad:
                contents.append(
                    "=== PRODUCT IMAGES — SUPPLEMENTARY VISUAL REFERENCE ===\n"
                    "These are provided for visual context only. The SOURCE AD above is the layout authority.\n"
                    "Use these only to fill or reconstruct visual areas (hero, background) that cannot be\n"
                    "faithfully reproduced from the source ad at the new canvas size.\n"
                    "Do NOT override any composition, colour, or typography decisions from the source ad."
                )
            else:
                contents.append(
                    "=== IMAGE TYPE A: PRODUCT IMAGES — PRIMARY VISUAL SOURCE ===\n"
                    "MANDATORY: Every visual element in the final ad MUST be sourced from these images.\n"
                    "Fill the layout provided by the Reference Ad (Type B) using ONLY these images for:\n"
                    "  • Background scene, sky, environment, and landscape\n"
                    "  • Hero visual (the main subject of the ad)\n"
                    "  • Brand logo — reproduce EXACTLY as it appears here\n"
                    "  • Colour palette\n"
                    "These images define 100% of the visual content. You MUST replace all visuals from Type B with these."
                )
            for img_bytes, mime_type in images.product_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        # ── Logo images (Type C) ──────────────────────────────────────────────
        if images and images.logo_images:
            logo_override = "Type A or Type B images" if (images and images.ref_images) else "product images"
            contents.append(
                "=== IMAGE TYPE C: BRAND LOGO — EXACT REPRODUCTION REQUIRED ===\n"
                "This is the official brand logo. Rules:\n"
                "  • Reproduce it EXACTLY as shown — do not alter colours, proportions, or typography\n"
                "  • Place it in the appropriate brand corner of the ad (top-left or top-right)\n"
                f"  • Do NOT use any logo from {logo_override} if this logo is provided"
            )
            for img_bytes, mime_type in images.logo_images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        contents.append(request.prompt)

        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size="1K",
            ),
        )

        return await self._client.aio.models.generate_content(
            model=self.MODEL_IMAGE,
            contents=contents,
            config=config,
        )

    def _map_aspect_ratio(self, requested: str) -> str:
        """
        Maps a requested aspect ratio (e.g. '2.7:1') to the closest Gemini-supported ratio.
        Supported: '1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9'.
        """
        supported = [
            "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4",
            "8:1", "9:16", "16:9", "21:9"
        ]

        # If already supported, return as-is
        if requested in supported:
            return requested

        # Try to parse "W:H"
        try:
            if ":" not in requested:
                return "1:1"
            w_str, h_str = requested.split(":", 1)
            req_val = float(w_str) / float(h_str)
        except (ValueError, ZeroDivisionError):
            return "1:1"

        best_match = "1:1"
        min_diff = float("inf")

        for s in supported:
            sw, sh = s.split(":")
            s_val = float(sw) / float(sh)
            diff = abs(req_val - s_val)
            if diff < min_diff:
                min_diff = diff
                best_match = s

        return best_match


    async def _image_edit(self, request: LLMRequest) -> Any:
        """image_edit — multi-turn conversation mirroring services/image_model.py::edit_image."""
        metadata = request.metadata or {}
        images = request.images
        edit_history: list[str] = metadata.get("edit_history", [])

        # ── Turn 1: context brief + current image ─────────────────────────────
        brief_parts: list = []

        context_lines: list[str] = []
        description = metadata.get("description", "")
        persona_info = metadata.get("persona_info", "")
        creative_strategy = metadata.get("creative_strategy", "")
        ad_copy = metadata.get("ad_copy")
        meta_ad_copy = metadata.get("meta_ad_copy")

        if description:
            context_lines.append(f"Product Description: {description}")
        if persona_info:
            context_lines.append(f"Target Persona: {persona_info}")
        if creative_strategy:
            context_lines.append(f"Creative Strategy: {creative_strategy}")
        if ad_copy:
            context_lines.append("Rendered Ad Copy (On Image):")
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
                h_str = h[0] if isinstance(h, list) and h else h
                context_lines.append(f"  Headline: {h_str}")
            if "primary_text" in meta_ad_copy:
                p = meta_ad_copy["primary_text"]
                p_str = p[0] if isinstance(p, list) and p else p
                context_lines.append(f"  Primary Text: {p_str}")

        if context_lines:
            brief_parts.append(types.Part.from_text(text="\n".join(context_lines)))

        # product_images[0] is the current image being edited.
        if images and images.product_images:
            img_bytes, mime_type = images.product_images[0]
            brief_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        contents: list = [types.Content(role="user", parts=brief_parts)]

        # ── Interleave past edit instructions ─────────────────────────────────
        for past_instruction in edit_history:
            contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text="Edit applied.")])
            )
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=past_instruction)])
            )

        # ── Close with model ack, then latest instruction (+ any ref images) ────
        contents.append(
            types.Content(role="model", parts=[types.Part.from_text(text="Ready for the next edit.")])
        )
        latest_parts: list = [types.Part.from_text(text=request.prompt)]
        if images and images.ref_images:
            latest_parts.append(types.Part.from_text(text="Reference image(s) provided for this edit:"))
            for ref_bytes, ref_mime in images.ref_images:
                latest_parts.append(types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime))
        contents.append(types.Content(role="user", parts=latest_parts))

        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            response_modalities=["TEXT", "IMAGE"],
        )

        return await self._client.aio.models.generate_content(
            model=self.MODEL_IMAGE,
            contents=contents,
            config=config,
        )

    # ── Error mapping ─────────────────────────────────────────────────────────

    def _raise_mapped(self, exc: genai.errors.ClientError) -> None:
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status in _TRANSIENT_STATUSES:
            raise ProviderTransientError(str(exc)) from exc
        if status in _PERMANENT_STATUSES:
            raise ProviderPermanentError(str(exc)) from exc
        raise exc


# ── Internal helper ───────────────────────────────────────────────────────────

class _TextWrapper:
    """Minimal wrapper so merged brand-extraction JSON looks like a Gemini response."""

    def __init__(self, text: str, usage_metadata: Any) -> None:
        self.text = text
        self.usage_metadata = usage_metadata
