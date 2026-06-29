import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import ValidationError

from repos import creatives as creatives_repo, jobs as jobs_repo
from core.config import PipelineConfig, PipelineMode

_PLATFORM_LABELS = {
    "meta": "Meta (Facebook & Instagram)",
    "google": "Google Display Network",
}
from core.protocols import (
    AdCopy,
    BrandInfo,
    CreativeContext,
    ImageSearchStrategy,
    OutputSerializer,
    PipelineInputs,
    PostProcessor,
    PromptStrategy,
)
from core.queue import image_semaphore, pipeline_semaphore
from core.observability import trace, histogram
from llm.base import LLMRequest
from llm.router import LLMRouter
from services.creative_registry import find_subtype_by_dimensions, resolve_aspect_ratio

logger = logging.getLogger("revCreate.core.pipeline")


class PipelineState(str, Enum):
    QUEUED = "queued"
    EXTRACTING_BRAND = "extracting_brand"
    GENERATING_COPY = "generating_copy"
    GENERATING_META_COPY = "generating_meta_copy"
    GENERATING_IMAGE_PROMPT = "generating_image_prompt"
    SEARCHING_IMAGES = "searching_images"
    GENERATING_IMAGES = "generating_images"
    EDITING = "editing"
    POST_PROCESSING = "post_processing"
    SERIALIZING = "serializing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelledError(Exception):
    pass


@dataclass
class PipelineContext:
    state: PipelineState
    inputs: PipelineInputs
    config: PipelineConfig
    router: LLMRouter
    strategy: PromptStrategy
    search: ImageSearchStrategy
    post_processors: list[PostProcessor]
    serializer: OutputSerializer
    
    # Accumulated results
    brand_info: BrandInfo | None = None
    ad_copy: AdCopy | None = None
    image_prompt: str | None = None
    effective_product_images: list[tuple[bytes, str]] = field(default_factory=list)
    creative_ids: list[str] = field(default_factory=list)
    job_id: str | None = None
    total_cost: float = 0.0
    cancel_flag: asyncio.Event | None = None

    # Internal tracking for pipeline state memory
    _image_bytes_map: dict[str, bytes] = field(default_factory=dict)
    _prompt_used_map: dict[str, str] = field(default_factory=dict)
    _variation_index_map: dict[str, int] = field(default_factory=dict)
    _creative_format_map: dict[str, str] = field(default_factory=dict)


class PipelineRunner:
    def __init__(self, context: PipelineContext):
        self.context = context
        # Generate creative IDs if missing
        if not self.context.creative_ids:
            if self.context.inputs.existing_creative_ids:
                self.context.creative_ids = self.context.inputs.existing_creative_ids
            else:
                self.context.creative_ids = [
                    str(uuid.uuid4()) for _ in range(self.context.inputs.count)
                ]
        self.job_id = self.context.job_id or str(uuid.uuid4())
        self._step_start_times: dict[str, float] = {}
        self._pipeline_start: float = 0.0

    async def _log_state(
        self,
        state: PipelineState,
        error: str | None = None,
        model_selected: str | None = None,
        fallback_chain: list[str] | None = None,
    ):
        self.context.state = state
        mono_now = time.monotonic()
        now = datetime.now(timezone.utc)

        # Per-step elapsed timing
        key = state.value
        total_ms = 0
        if state in (PipelineState.DONE, PipelineState.FAILED):
            total_ms = int((mono_now - self._pipeline_start) * 1000)
            if state == PipelineState.DONE:
                logger.info("PIPELINE [DONE] — total_elapsed_ms=%d cost=$%.5f job=%s", total_ms, self.context.total_cost, self.job_id)
            else:
                logger.info(
                    "PIPELINE [FAILED] — error=%s total_elapsed_ms=%d cost=$%.5f job=%s",
                    error, total_ms, self.context.total_cost, self.job_id,
                )
        elif key in self._step_start_times:
            elapsed_ms = int((mono_now - self._step_start_times[key]) * 1000)
            model_part = f" model={model_selected}" if model_selected else ""
            logger.info(
                "PIPELINE [%s] done — elapsed_ms=%d%s job=%s",
                key.upper(), elapsed_ms, model_part, self.job_id,
            )
        else:
            self._step_start_times[key] = mono_now
            logger.info("PIPELINE [%s] start — job=%s", key.upper(), self.job_id)
        
        # Update the main job document status
        try:
            update_data = {"status": state.value}
            if state in (PipelineState.DONE, PipelineState.FAILED):
                update_data["total_time_ms"] = total_ms
                update_data["total_cost"] = self.context.total_cost
            await jobs_repo.update(self.job_id, update_data)
        except Exception as e:
            logger.error("Failed to update job status to %s: %s", state.value, e)

        # Log the transition for observability
        log_record = {
            "job_id": self.job_id,
            "creative_ids": self.context.creative_ids,
            "state": state.value,
            "entered_at": now,
            "prompt_strategy": self.context.config.prompt_strategy,
            "post_processors": self.context.config.post_processors,
        }
        if model_selected is not None:
            log_record["model_selected"] = model_selected
        if fallback_chain is not None:
            log_record["fallback_chain"] = fallback_chain
        if error is not None:
            log_record["error"] = error

        # Datadog span per state transition
        with trace(
            "pipeline.state", resource=state.value,
            **{
                "pipeline.creative_id": ",".join(self.context.creative_ids),
                "pipeline.prompt_strategy": self.context.config.prompt_strategy,
                **({"pipeline.model_selected": model_selected} if model_selected else {}),
                **({"pipeline.error": error} if error else {}),
            },
        ):
            pass

        # Push state into creative documents so the frontend can show real progress.
        if self.context.creative_ids:
            try:
                if state == PipelineState.FAILED:
                    # On failure, mark all creatives as failed if they aren't already done
                    await creatives_repo.update_many_by_ids(
                        self.context.creative_ids,
                        {"status": state.value, "error_message": error},
                    )
                elif state != PipelineState.DONE:
                    # Let the serializer handle DONE. For everything else, update the creatives.
                    await creatives_repo.update_many_by_ids(
                        self.context.creative_ids,
                        {"status": state.value},
                    )
            except Exception as e:
                logger.error("Failed to update creative status to %s: %s", state.value, e)

    def _check_cancelled(self):
        if self.context.cancel_flag and self.context.cancel_flag.is_set():
            raise JobCancelledError(f"Job {self.job_id} was cancelled")

    async def _garbage_collect(self):
        from services.s3 import delete_object
        tasks = [delete_object(f"creatives/{c_id}.png") for c_id in self.context.creative_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("GC complete — deleted %d creative S3 objects for job=%s", len(tasks), self.job_id)

    async def run(self):
        self._pipeline_start = time.monotonic()
        await self._log_state(PipelineState.QUEUED)

        async with pipeline_semaphore:
            status = "failed"
            try:
                mode = self.context.config.mode

                if mode == PipelineMode.GENERATE:
                    await self._extract_brand()
                    self._check_cancelled()
                    await self._generate_meta_copy()
                    self._check_cancelled()
                    await self._generate_copy()
                    self._check_cancelled()
                    await self._generate_image_prompt()
                    self._check_cancelled()
                    await self._search_images()
                    self._check_cancelled()
                    await self._generate_images()
                    await self._post_processing()
                    await self._serializing()
                elif mode in (PipelineMode.REGENERATE, PipelineMode.SIZE_VARIANT):
                    if self.context.inputs.ad_copy_data:
                        try:
                            self.context.ad_copy = AdCopy.model_validate(self.context.inputs.ad_copy_data)
                        except Exception:
                            pass
                    self._check_cancelled()
                    self.context.effective_product_images = list(self.context.inputs.images.product_images)
                    await self._generate_images()
                    await self._post_processing()
                    await self._serializing()
                elif mode == PipelineMode.EDIT:
                    if self.context.inputs.ad_copy_data:
                        try:
                            self.context.ad_copy = AdCopy.model_validate(self.context.inputs.ad_copy_data)
                        except Exception:
                            pass
                    self._check_cancelled()
                    self.context.effective_product_images = list(self.context.inputs.images.product_images)
                    await self._edit_images()
                    await self._post_processing()
                    await self._serializing()
                else:
                    raise ValueError(f"Unknown mode: {mode}")

                await self._log_state(PipelineState.DONE)
                status = "done"
            except JobCancelledError:
                logger.info("Pipeline cancelled — job=%s", self.job_id)
                await jobs_repo.update(self.job_id, {"status": PipelineState.CANCELLED.value})
                await creatives_repo.update_many_by_ids(
                    self.context.creative_ids, {"status": PipelineState.CANCELLED.value}
                )
                await self._garbage_collect()
                status = "cancelled"
            except Exception as e:
                logger.error("Pipeline failed: %s", e, exc_info=True)
                await self._log_state(PipelineState.FAILED, error=str(e))
            finally:
                histogram(
                    "pipeline.duration",
                    (time.monotonic() - self._pipeline_start) * 1000,
                    tags=[f"mode:{self.context.config.mode.value}", f"status:{status}"],
                )

    def _clean_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
        return text.strip()

    def _build_prompt_context(self) -> dict:
        return {
            "product_name": self.context.inputs.product_name,
            "description": self.context.inputs.description,
            "ad_format": self.context.inputs.ad_format,
            "has_product_images": bool(self.context.inputs.images.product_images),
            "has_logo_images": bool(self.context.inputs.images.logo_images),
            "has_ref_images": bool(self.context.inputs.images.ref_images),
            "brand_info": self.context.brand_info.model_dump() if self.context.brand_info else None,
            "persona_info": self.context.inputs.persona_info,
            "creative_strategy": self.context.inputs.creative_strategy,
            "instructions": self.context.inputs.instructions,
            "headline": self.context.ad_copy.headline if self.context.ad_copy else "",
            "body_copy": self.context.ad_copy.body_copy if self.context.ad_copy else "",
            "cta": self.context.ad_copy.cta if self.context.ad_copy else "",
            "meta_ad_copy": (
                self.context.ad_copy.platforms.get("meta") if self.context.ad_copy else None
            ),
        }

    async def _extract_brand(self):
        await self._log_state(PipelineState.EXTRACTING_BRAND)
        req = LLMRequest(
            task_type="brand_extraction",
            prompt=f"Product: {self.context.inputs.product_name}\nDesc: {self.context.inputs.description}",
        )
        resp = await self.context.router.route(req)
        self.context.total_cost += resp.cost
        
        text = self._clean_json(resp.text)
        try:
            self.context.brand_info = BrandInfo.model_validate_json(text)
        except ValidationError:
            # Fallback to empty if model fails to generate valid json
            self.context.brand_info = BrandInfo()
            
        await self._log_state(PipelineState.EXTRACTING_BRAND, model_selected=resp.model)

    async def _generate_copy(self):
        await self._log_state(PipelineState.GENERATING_COPY)
        ctx = self._build_prompt_context()
        sys_prompt = self.context.strategy.build_copy_system_prompt(ctx)
        if not sys_prompt:
            self.context.ad_copy = AdCopy(headline="", body_copy="", cta="")
            await self._log_state(PipelineState.GENERATING_COPY)
            return

        user_brief = self.context.strategy.build_copy_user_brief(ctx)
        req = LLMRequest(
            task_type="copy_generation",
            system_prompt=sys_prompt,
            prompt=user_brief,
            images=self.context.inputs.images if self.context.inputs.images.ref_images else None,
        )
        resp = await self.context.router.route(req)
        self.context.total_cost += resp.cost

        text = self._clean_json(resp.text)
        prev_platforms = self.context.ad_copy.platforms if self.context.ad_copy else {}
        self.context.ad_copy = AdCopy.model_validate_json(text)
        if prev_platforms:
            self.context.ad_copy.platforms.update(prev_platforms)
        # Deduplicate variations — LLMs sometimes return identical copy for multiple slots
        seen: set[tuple[str, str]] = set()
        unique_variations = []
        for v in self.context.ad_copy.variations:
            key = (v.headline.strip().lower(), v.body_copy.strip().lower())
            if key not in seen:
                seen.add(key)
                unique_variations.append(v)
        self.context.ad_copy.variations = unique_variations
        await self._log_state(PipelineState.GENERATING_COPY, model_selected=resp.model)

    async def _generate_meta_copy(self):
        await self._log_state(PipelineState.GENERATING_META_COPY)
        ctx = self._build_prompt_context()
        sys_prompt = self.context.strategy.build_meta_copy_system(ctx)
        if not sys_prompt:
            await self._log_state(PipelineState.GENERATING_META_COPY)
            return

        user_brief = self.context.strategy.build_copy_user_brief(ctx)
        req = LLMRequest(
            task_type="meta_copy_generation",
            system_prompt=sys_prompt,
            prompt=user_brief,
        )
        resp = await self.context.router.route(req)
        self.context.total_cost += resp.cost

        text = self._clean_json(resp.text)
        try:
            meta_copy = json.loads(text)
            if self.context.ad_copy is None:
                self.context.ad_copy = AdCopy(headline="", body_copy="", cta="")
            self.context.ad_copy.platforms["meta"] = meta_copy
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse meta copy JSON: %s", e)

        await self._log_state(PipelineState.GENERATING_META_COPY, model_selected=resp.model)

    async def _generate_image_prompt(self):
        await self._log_state(PipelineState.GENERATING_IMAGE_PROMPT)
        ctx = self._build_prompt_context()
        sys_prompt = self.context.strategy.build_image_prompt_system(ctx)
        brief = self.context.strategy.build_image_prompt_brief(ctx)
        
        req = LLMRequest(
            task_type="image_prompt_generation",
            system_prompt=sys_prompt,
            prompt=brief,
        )
        resp = await self.context.router.route(req)
        self.context.total_cost += resp.cost
        img_prompt = resp.text.strip()
        
        # Apply RERA scrubbing inline if no RERA number is provided
        if not self.context.inputs.rera_number:
            cleaned = re.sub(
                r"RERA\s*(?:No\.?|Number|Registration|#|:)?[\s:.\-]*[A-Z0-9/\-]*",
                "",
                img_prompt,
                flags=re.IGNORECASE,
            ).strip()
            img_prompt = cleaned
            
        self.context.image_prompt = img_prompt
        await self._log_state(PipelineState.GENERATING_IMAGE_PROMPT, model_selected=resp.model)

    async def _search_images(self):
        await self._log_state(PipelineState.SEARCHING_IMAGES)
        if self.context.inputs.images.product_images:
            self.context.effective_product_images = list(self.context.inputs.images.product_images)
        else:
            ad_copy_text = f"Headline: {self.context.ad_copy.headline}" if self.context.ad_copy else ""
            found = await self.context.search.find(
                product_name=self.context.inputs.product_name,
                description=self.context.inputs.description,
                ad_copy_text=ad_copy_text,
                persona_info=self.context.inputs.persona_info,
                creative_strategy=self.context.inputs.creative_strategy,
            )
            if found:
                self.context.effective_product_images.append(found)
                
        await self._log_state(PipelineState.SEARCHING_IMAGES)

    def _build_size_variant_prompt(self, size_label: str, dims: str, ar: str, platform: str) -> str:
        platform_label = _PLATFORM_LABELS.get(platform, platform)
        is_story = ar == "9:16" or "story" in size_label.lower() or "reel" in size_label.lower()
        story_extra = (
            "\n• STORY / REELS FORMAT: Keep only the hero headline, CTA, and max 10 words from body copy — "
            "remove all other text. Hero visual must dominate. ALL text must be placed strictly within the "
            "TOP 50% of the canvas. Text must occupy max 20% of the canvas area."
            if is_story else ""
        )
        return (
            f"PLATFORM: {platform_label}\n"
            f"PLACEMENT: {size_label} ({dims}px, aspect ratio {ar})\n\n"
            f"=== TASK: ADAPT SOURCE AD ===\n"
            f"Adapt the SOURCE AD composition to the {size_label} placement.\n\n"
            f"RULES:\n"
            f"• PRESERVE EVERYTHING: Hero visual, background scene, colour palette, graphic elements, "
            f"dividers, typography hierarchy, ad copy text, logo — reproduce all exactly.\n"
            f"• RECOMPOSE ONLY: Reflow zones to fit naturally within the {dims}px canvas.\n"
            f"• EXACT RATIO: Output canvas MUST be {ar} — no crop, pad, or letter-box.\n"
            f"• NO WHITESPACE: No padding, borders, or extra whitespace outside the composition.\n"
            f"• RERA / LEGAL TEXT: Do NOT render any RERA number or legal disclaimer — added as overlay after generation."
            f"{story_extra}"
        )

    async def _generate_images(self):
        await self._log_state(PipelineState.GENERATING_IMAGES)
        ctx = self._build_prompt_context()

        sys_prompt = self.context.strategy.build_image_gen_system(ctx)
        is_size_variant = (
            self.context.config.mode == PipelineMode.SIZE_VARIANT
            and bool(self.context.inputs.size_variant_sizes)
        )

        async def _gen_one(i: int, c_id: str):
            self._check_cancelled()
            async with image_semaphore:
                if is_size_variant and i < len(self.context.inputs.size_variant_sizes):
                    size_label, dims, ar = self.context.inputs.size_variant_sizes[i]
                    full_prompt = self._build_size_variant_prompt(
                        size_label, dims, ar, self.context.inputs.size_variant_platform or ""
                    )
                    metadata: dict = {"aspect_ratio": ar}
                    # Pass the parent image as source_ad for the adapter
                    if self.context.inputs.images.product_images:
                        metadata["source_ad"] = self.context.inputs.images.product_images[0]
                    req = LLMRequest(
                        task_type="image_generation",
                        prompt=full_prompt,
                        system_prompt=sys_prompt if sys_prompt else None,
                        images=self.context.inputs.images,
                        metadata=metadata,
                    )
                else:
                    base_prompt = (
                        self.context.inputs.existing_prompts[i]
                        if self.context.inputs.existing_prompts
                        else (self.context.image_prompt or "")
                    )
                    full_prompt = self.context.strategy.build_image_gen_prompt(
                        base_prompt, self.context.ad_copy, i
                    )
                    req = LLMRequest(
                        task_type="image_generation",
                        prompt=full_prompt,
                        system_prompt=sys_prompt if sys_prompt else None,
                        images=self.context.inputs.images,
                        metadata={"aspect_ratio": resolve_aspect_ratio(self.context.inputs.ad_format)},
                    )

                    if self.context.effective_product_images and req.images:
                        req.images.product_images = self.context.effective_product_images

                resp = await self.context.router.route_image(req)
                self.context.total_cost += resp.cost
                self.context._image_bytes_map[c_id] = resp.image_bytes
                self.context._prompt_used_map[c_id] = full_prompt
                self.context._variation_index_map[c_id] = i + 1
                if is_size_variant and i < len(self.context.inputs.size_variant_sizes):
                    _, dims, _ = self.context.inputs.size_variant_sizes[i]
                    self.context._creative_format_map[c_id] = dims

        tasks = [_gen_one(i, cid) for i, cid in enumerate(self.context.creative_ids)]
        await asyncio.gather(*tasks)
        await self._log_state(PipelineState.GENERATING_IMAGES)

    async def _edit_images(self):
        await self._log_state(PipelineState.EDITING)
        ctx = self._build_prompt_context()

        sys_prompt = self.context.strategy.build_image_gen_system(ctx)

        async def _edit_one(i: int, c_id: str):
            async with image_semaphore:
                metadata: dict = {
                    "aspect_ratio": self.context.inputs.ad_format,
                    "edit_history": self.context.inputs.edit_history,
                    "description": self.context.inputs.description,
                    "persona_info": self.context.inputs.persona_info,
                    "creative_strategy": self.context.inputs.creative_strategy,
                }

                req = LLMRequest(
                    task_type="image_edit",
                    prompt=self.context.inputs.edit_instruction or "Edit image",
                    system_prompt=sys_prompt if sys_prompt else None,
                    images=self.context.inputs.images,
                    metadata=metadata,
                )
                resp = await self.context.router.route_image(req)
                self.context.total_cost += resp.cost
                self.context._image_bytes_map[c_id] = resp.image_bytes
                self.context._prompt_used_map[c_id] = self.context.inputs.edit_instruction or "Edit"
                self.context._variation_index_map[c_id] = i + 1

        tasks = [_edit_one(i, cid) for i, cid in enumerate(self.context.creative_ids)]
        await asyncio.gather(*tasks)
        await self._log_state(PipelineState.EDITING)

    async def _post_processing(self):
        if not self.context.post_processors:
            return

        await self._log_state(PipelineState.POST_PROCESSING)

        async def _process_one(c_id: str):
            img_bytes = self.context._image_bytes_map[c_id]
            creative_ctx = CreativeContext(
                creative_id=c_id,
                rera_number=self.context.inputs.rera_number,
                qr_code_bytes=self.context.inputs.qr_code_bytes,
                ad_format=self.context._creative_format_map.get(c_id, self.context.inputs.ad_format),
                variation_index=self.context._variation_index_map.get(c_id, 1),
            )
            for pp in self.context.post_processors:
                _pp_start = time.monotonic()
                img_bytes = await pp.process(img_bytes, creative_ctx)
                histogram(
                    "postprocessor.duration",
                    (time.monotonic() - _pp_start) * 1000,
                    tags=[f"processor:{pp.__class__.__name__}"],
                )
            self.context._image_bytes_map[c_id] = img_bytes
            
        tasks = [_process_one(cid) for cid in self.context.creative_ids]
        await asyncio.gather(*tasks)
        await self._log_state(PipelineState.POST_PROCESSING)

    async def _serializing(self):
        await self._log_state(PipelineState.SERIALIZING)
        is_size_variant = (
            self.context.config.mode == PipelineMode.SIZE_VARIANT
            and bool(self.context.inputs.size_variant_sizes)
        )
        global_subtype = (
            None if is_size_variant
            else find_subtype_by_dimensions(self.context.inputs.ad_format)
        )

        async def _serialize_one(i: int, c_id: str):
            try:
                ad_copy = self.context.ad_copy or AdCopy(headline="", body_copy="", cta="")

                # Pin the meta copy variation to this creative's index so each
                # creative carries only its own variation rather than all four.
                # Size variants all derive from one parent, so they always use index 0.
                meta = ad_copy.platforms.get("meta") if ad_copy.platforms else None
                if meta and isinstance(meta, dict):
                    meta_idx = 0 if is_size_variant else i
                    def _pick(arr, idx):
                        return [arr[idx]] if isinstance(arr, list) and idx < len(arr) else (arr or [])
                    paired_meta = {
                        "primary_text": _pick(meta.get("primary_text", []), meta_idx),
                        "headline": _pick(meta.get("headline", []), meta_idx),
                        "description": _pick(meta.get("description", []), meta_idx),
                        "call_to_action": meta.get("call_to_action", ""),
                    }
                    ad_copy = ad_copy.model_copy(
                        update={"platforms": {**ad_copy.platforms, "meta": paired_meta}}
                    )

                if is_size_variant and i < len(self.context.inputs.size_variant_sizes):
                    _, dims, _ = self.context.inputs.size_variant_sizes[i]
                    subtype = find_subtype_by_dimensions(dims)
                else:
                    subtype = global_subtype

                await self.context.serializer.write_creative(
                    creative_id=c_id,
                    inputs=self.context.inputs,
                    ad_copy=ad_copy,
                    prompt_used=self.context._prompt_used_map.get(c_id, ""),
                    variation_index=self.context._variation_index_map.get(c_id, 1),
                    subtype=subtype,
                )
                await self.context.serializer.upload_image(
                    creative_id=c_id,
                    image_bytes=self.context._image_bytes_map[c_id],
                )
                await self.context.serializer.mark_done(c_id)
            except Exception as e:
                logger.error("Serialization failed for %s: %s", c_id, e)
                await self.context.serializer.mark_failed(c_id, str(e))

        tasks = [_serialize_one(i, cid) for i, cid in enumerate(self.context.creative_ids)]
        await asyncio.gather(*tasks)


async def run_pipeline(context: PipelineContext) -> None:
    """Initializes the runner and executes the pipeline state machine."""
    runner = PipelineRunner(context)
    await runner.run()
