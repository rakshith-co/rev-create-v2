"""
Background task functions for FastAPI's BackgroundTasks.

All pipeline-backed async operations live here so error handling is
consistent and routers stay thin. Each function:
  1. Deserializes the request into PipelineInputs + PipelineConfig
  2. Builds a PipelineContext
  3. Runs the pipeline via the core queue execute_pipeline_task
  4. On failure: updates job state (DLQ handled by queue)
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from repos import jobs as jobs_repo
from repos import projects as projects_repo
from core.pipeline import PipelineContext, PipelineState, run_pipeline
from core.queue import execute_pipeline_task, handle_task_failure, register_cancel_flag, unregister_cancel_flag
from core.dependencies import get_llm_router, get_strategies, get_searches, get_post_processors, get_serializer
from core.config import PipelineMode, MODE_DEFAULTS, POST_PROCESSOR_GUARDS
from core.protocols import ImageBundle, PipelineInputs
from services.s3 import download_bytes
from llm.router import LLMRouter
from llm.registry import PROVIDER_REGISTRIES

logger = logging.getLogger("revCreate.tasks")


def _attach_cancel_flag(context: PipelineContext, job_id: str) -> None:
    context.cancel_flag = register_cancel_flag(job_id)


def _build_context(inputs, config) -> PipelineContext:
    strategies = get_strategies()
    searches = get_searches()
    pps = get_post_processors()
    base_router = get_llm_router()
    if config.provider and config.provider in PROVIDER_REGISTRIES:
        router = LLMRouter(models=base_router.models, registry=PROVIDER_REGISTRIES[config.provider])
    else:
        router = base_router
    return PipelineContext(
        state=PipelineState.QUEUED,
        inputs=inputs,
        config=config,
        router=router,
        strategy=strategies.get(config.prompt_strategy) or strategies["v2"],
        search=searches.get(config.image_search) or searches["none"],
        post_processors=[pps[p] for p in config.post_processors if p in pps],
        serializer=get_serializer(),
    )


# ── Generate ──────────────────────────────────────────────────────────────────

async def run_generate(
    job_id: str,
    params,  # GenerateRequestParams
    product_images: list,
    ref_images: list,
    logo_images: list,
    qr_code_bytes: Optional[bytes],
) -> None:
    try:
        from deserializers.generate import GenerateDeserializer
        inputs, config = await GenerateDeserializer().parse(
            params=params,
            product_images=product_images,
            ref_images=ref_images,
            logo_images=logo_images,
            qr_code_bytes=qr_code_bytes,
        )

        context = _build_context(inputs, config)
        context.job_id = job_id
        context.search = get_searches().get(config.image_search) or get_searches()["web"]
        _attach_cancel_flag(context, job_id)

        # Pre-generate creative IDs so they are consistent across updates
        context.creative_ids = [str(uuid.uuid4()) for _ in range(inputs.count)]

        await jobs_repo.update(
            job_id,
            {"status": "generating_copy", "creative_ids": context.creative_ids},
        )

        try:
            await execute_pipeline_task(job_id, "run_generate", context, run_pipeline(context))
        finally:
            unregister_cancel_flag(job_id)

        if context.state == PipelineState.DONE:
            await jobs_repo.update(
                job_id,
                {
                    "status": "done",
                    "creative_ids": context.creative_ids,
                    "headline": context.ad_copy.headline if context.ad_copy else "",
                    "body_copy": context.ad_copy.body_copy if context.ad_copy else "",
                    "generated_cta": context.ad_copy.cta if context.ad_copy else "",
                    "image_prompt": context.image_prompt,
                    "ad_copy": context.ad_copy.model_dump() if context.ad_copy else None,
                },
            )
        elif context.state not in (PipelineState.CANCELLED,):
            await jobs_repo.update(job_id, {"status": "failed"})

    except Exception as exc:
        logger.error("Generate task failed initially — job=%s error=%s", job_id, exc)
        await handle_task_failure(job_id, [], "run_generate", exc)
        await jobs_repo.update(job_id, {"status": "failed"})


# ── Edit ──────────────────────────────────────────────────────────────────────

async def run_edit(job_id: str, new_id: str, parent_id: str, instruction: str, provider: str | None = None, ref_images_data: list[tuple[bytes, str]] | None = None) -> None:
    try:
        from deserializers.edit import EditDeserializer, EditRequestParams
        from core.config import PipelineConfig
        inputs, config = await EditDeserializer().parse(
            creative_id=parent_id,
            params=EditRequestParams(instruction=instruction, pipeline=PipelineConfig(provider=provider), ref_images=ref_images_data or []),
        )
        inputs.existing_creative_ids = [new_id]

        context = _build_context(inputs, config)
        context.job_id = job_id
        _attach_cancel_flag(context, job_id)

        try:
            await execute_pipeline_task(job_id, "run_edit", context, run_pipeline(context))
        finally:
            unregister_cancel_flag(job_id)

        if context.state == PipelineState.DONE:
            await jobs_repo.update(job_id, {"status": "done"})
        elif context.state not in (PipelineState.CANCELLED,):
            await jobs_repo.update(job_id, {"status": "failed"})

    except Exception as exc:
        logger.error("Edit task failed initially — creative=%s error=%s", new_id, exc)
        await handle_task_failure(job_id, [new_id], "run_edit", exc)
        await jobs_repo.update(job_id, {"status": "failed"})


# ── Regenerate ────────────────────────────────────────────────────────────────

async def run_regeneration(job_id: str, new_id: str, original_id: str, provider: str | None = None) -> None:
    try:
        from deserializers.regenerate import RegenerateDeserializer, RegenerateRequestParams
        from core.config import PipelineConfig
        inputs, config = await RegenerateDeserializer().parse(
            creative_id=original_id,
            params=RegenerateRequestParams(pipeline=PipelineConfig(provider=provider)),
        )
        inputs.existing_creative_ids = [new_id]

        context = _build_context(inputs, config)
        context.job_id = job_id
        _attach_cancel_flag(context, job_id)

        try:
            await execute_pipeline_task(job_id, "run_regeneration", context, run_pipeline(context))
        finally:
            unregister_cancel_flag(job_id)

        if context.state == PipelineState.DONE:
            await jobs_repo.update(job_id, {"status": "done"})
        elif context.state not in (PipelineState.CANCELLED,):
            await jobs_repo.update(job_id, {"status": "failed"})

    except Exception as exc:
        logger.error("Regeneration task failed initially — creative=%s error=%s", new_id, exc)
        await handle_task_failure(job_id, [new_id], "run_regeneration", exc)
        await jobs_repo.update(job_id, {"status": "failed"})


# ── Size variants ─────────────────────────────────────────────────────────────

async def run_size_variants(
    job_id: str,
    entries: list[tuple[str, str, str, str]],  # (new_id, size_label, dims, aspect_ratio)
    parent_creative_id: str,
    platform: str,
    provider: str | None = None,
) -> None:
    new_ids = [e[0] for e in entries]
    dims_filter = [e[2] for e in entries]

    try:
        from deserializers.size_variant import SizeVariantDeserializer, SizeVariantRequestParams
        from core.config import PipelineConfig
        inputs, config = await SizeVariantDeserializer().parse(
            creative_id=parent_creative_id,
            params=SizeVariantRequestParams(platform=platform, sizes=dims_filter, use_latest=False, pipeline=PipelineConfig(provider=provider)),
        )
        inputs.existing_creative_ids = new_ids
        inputs.count = len(new_ids)

        context = _build_context(inputs, config)
        context.job_id = job_id
        _attach_cancel_flag(context, job_id)

        try:
            await execute_pipeline_task(job_id, "run_size_variants", context, run_pipeline(context))
        finally:
            unregister_cancel_flag(job_id)

        if context.state == PipelineState.DONE:
            await jobs_repo.update(job_id, {"status": "done"})
        elif context.state not in (PipelineState.CANCELLED,):
            await jobs_repo.update(job_id, {"status": "failed"})

    except Exception as exc:
        logger.error("Size variant task failed initially — parent=%s error=%s", parent_creative_id, exc)
        await handle_task_failure(job_id, new_ids, "run_size_variants", exc)
        await jobs_repo.update(job_id, {"status": "failed"})


# ── Project pipeline (legacy /api/projects surface) ───────────────────────────

async def run_project_pipeline(project_id: str, provider: str | None = None) -> None:
    """Reads a project document from MongoDB and runs it through the modular pipeline."""
    try:
        project = await projects_repo.get(project_id)
        if not project:
            logger.error("run_project_pipeline — project not found: %s", project_id)
            return

        async def _dl(records: list[dict]) -> list[tuple[bytes, str]]:
            result = []
            for r in records:
                try:
                    result.append((await download_bytes(r["s3_key"]), r["mime_type"]))
                except Exception as e:
                    logger.warning("Failed to download %s: %s", r.get("s3_key"), e)
            return result

        product_images = await _dl(project.get("product_images") or [])
        ref_images     = await _dl(project.get("ref_images") or [])
        logo_images    = await _dl(project.get("logo_images") or [])

        qr_code_bytes = None
        if project.get("qr_code") and project["qr_code"].get("s3_key"):
            try:
                qr_code_bytes = await download_bytes(project["qr_code"]["s3_key"])
            except Exception as e:
                logger.warning("Failed to download QR code: %s", e)

        inputs = PipelineInputs(
            product_name=project.get("product_name", ""),
            description=project.get("description", ""),
            ad_format=project.get("ad_format", "1080x1080"),
            client_id=project.get("client_id", "revspot"),
            name=project.get("name", project_id),
            images=ImageBundle(
                product_images=product_images,
                ref_images=ref_images,
                logo_images=logo_images,
            ),
            associations=[{"type": "project", "id": project_id}],
            rera_number=project.get("rera_number") or None,
            qr_code_bytes=qr_code_bytes,
            product_image_keys=project.get("product_images") or [],
            ref_image_keys=project.get("ref_images") or [],
            logo_image_keys=project.get("logo_images") or [],
        )

        config = MODE_DEFAULTS[PipelineMode.GENERATE].model_copy()
        config.provider = provider
        config.post_processors = [
            p for p in config.post_processors
            if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
        ]

        context = _build_context(inputs, config)

        await projects_repo.update(project_id, {"status": "generating"})
        await run_pipeline(context)

        # Respect user-initiated stop
        final = await projects_repo.get(project_id, {"status": 1})
        if final and final.get("status") == "stopped":
            return

        if context.state == PipelineState.DONE:
            patch: dict = {"status": "ready"}
            if context.ad_copy:
                patch.update({
                    "headline": context.ad_copy.headline,
                    "body_copy": context.ad_copy.body_copy,
                    "generated_cta": context.ad_copy.cta,
                    "image_prompt": context.image_prompt or "",
                })
            if context.brand_info:
                patch["brand_info"] = context.brand_info.model_dump()
            await projects_repo.update(project_id, patch)
        else:
            await projects_repo.update(project_id, {"status": "failed", "error_message": "Pipeline failed"})

    except Exception as exc:
        logger.error("run_project_pipeline failed — project=%s error=%s", project_id, exc)
        try:
            await projects_repo.update(project_id, {"status": "failed", "error_message": str(exc)})
        except Exception:
            pass
