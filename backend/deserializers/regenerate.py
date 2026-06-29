import asyncio
from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field

from repos import creatives as creatives_repo
from repos import projects as projects_repo
from core.protocols import InputDeserializer, PipelineInputs, ImageBundle
from core.config import PipelineConfig, PipelineMode, MODE_DEFAULTS, POST_PROCESSOR_GUARDS
from services.s3 import download_bytes

class RegenerateRequestParams(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

async def _fetch_image_list(entries: list[dict]) -> list[tuple[bytes, str]]:
    """Download a list of {s3_key, mime_type} dicts from S3."""
    return [
        (await download_bytes(e["s3_key"]), e["mime_type"])
        for e in entries
    ]

class RegenerateDeserializer(InputDeserializer):
    async def parse(
        self,
        creative_id: str,
        params: RegenerateRequestParams,
    ) -> tuple[PipelineInputs, PipelineConfig]:
        original = await creatives_repo.get(creative_id)
        if not original:
            raise HTTPException(status_code=404, detail="Creative not found")

        # Resolve input sources
        input_sources = original.get("input_sources")
        if not input_sources:
            # Fallback to project association
            project_assoc = next(
                (a for a in original.get("associations", []) if a.get("type") == "project"),
                None,
            )
            if not project_assoc:
                raise HTTPException(
                    status_code=400,
                    detail="Creative missing input_sources and project association"
                )
            project = await projects_repo.get(project_assoc["id"])
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            
            input_sources = {
                "product_images": project.get("product_images", []),
                "ref_images": project.get("ref_images", []),
                "logo_images": project.get("logo_images", []),
            }

        product_keys = input_sources.get("product_images", [])
        ref_keys = input_sources.get("ref_images", [])
        logo_keys = input_sources.get("logo_images", [])

        product_images, ref_images, logo_images = await asyncio.gather(
            _fetch_image_list(product_keys),
            _fetch_image_list(ref_keys),
            _fetch_image_list(logo_keys),
        )

        metadata = original.get("metadata", {})
        size_specs = metadata.get("size_specs", {})
        ad_format = f"{size_specs.get('width', 1080)}x{size_specs.get('height', 1080)}"
        
        gen_inputs = original.get("generation_inputs", {})
        gen_data = original.get("generated", {})

        config = MODE_DEFAULTS[PipelineMode.REGENERATE].model_copy(
            update=params.pipeline.model_dump(exclude_unset=True)
        )

        inputs = PipelineInputs(
            product_name=gen_inputs.get("product_name", original.get("name", "Product")),
            description=gen_inputs.get("description", ""),
            ad_format=ad_format,
            client_id=original.get("client_id", "revspot"),
            name=original.get("name", "Creative"),
            images=ImageBundle(
                product_images=product_images,
                ref_images=ref_images,
                logo_images=logo_images,
            ),
            associations=original.get("associations", []),
            persona_info=gen_inputs.get("persona_info", ""),
            creative_strategy=gen_inputs.get("creative_strategy", ""),
            instructions=gen_inputs.get("instructions", ""),
            count=1, # One per ID
            rera_number=gen_inputs.get("rera_number"),
            qr_code_bytes=None, # Needs to be handled if we need it here, but generally regenerate doesn't change it
            product_image_keys=product_keys,
            ref_image_keys=ref_keys,
            logo_image_keys=logo_keys,
            existing_prompts=[gen_data.get("prompt_used", "")],
            ad_copy_data=original.get("ad_copy"),
        )

        config.post_processors = [
            p for p in config.post_processors
            if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
        ]

        return inputs, config
