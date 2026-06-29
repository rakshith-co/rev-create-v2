from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field

from repos import creatives as creatives_repo
from core.protocols import InputDeserializer, PipelineInputs, ImageBundle
from core.config import PipelineConfig, PipelineMode, MODE_DEFAULTS, POST_PROCESSOR_GUARDS
from services.s3 import download_bytes

PLATFORM_SIZES: dict[str, list[tuple[str, str, str]]] = {
    "meta": [
        ("Feed Square", "1080x1080", "1:1"),
        ("Feed Portrait", "1080x1350", "4:5"),
        ("Feed Landscape", "1200x628", "1.91:1"),
        ("Story / Reels", "1080x1920", "9:16"),
    ],
    "google": [
        ("Horizontal", "1200x628", "1.91:1"),
        ("Square", "600x600", "1:1"),
        ("Logo Square", "1200x1200", "1:1"),
        ("Logo Rectangular", "1200x300", "4:1"),
    ],
}

class SizeVariantRequestParams(BaseModel):
    platform: str
    sizes: list[str] = Field(default_factory=list)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    use_latest: bool = True

async def _resolve_latest_creative(creative_id: str) -> dict | None:
    doc = await creatives_repo.get(creative_id)
    if not doc:
        return None
    while True:
        child = await creatives_repo.find_latest_child(str(doc["_id"]))
        if not child:
            break
        doc = child
    return doc

class SizeVariantDeserializer(InputDeserializer):
    async def parse(
        self,
        creative_id: str,
        params: SizeVariantRequestParams,
    ) -> tuple[PipelineInputs, PipelineConfig]:
        if params.use_latest:
            parent = await _resolve_latest_creative(creative_id)
        else:
            parent = await creatives_repo.get(creative_id)
            
        if not parent:
            raise HTTPException(status_code=404, detail="Creative not found")

        platform = params.platform.lower()
        if platform not in PLATFORM_SIZES:
            raise HTTPException(
                status_code=400, detail=f"Unknown platform '{platform}'. Choose from: {list(PLATFORM_SIZES)}"
            )

        sizes = PLATFORM_SIZES[platform]
        if params.sizes:
            sizes = [s for s in sizes if s[1] in params.sizes]
            if not sizes:
                raise HTTPException(
                    status_code=400,
                    detail=f"None of the provided sizes {params.sizes} are valid for platform '{platform}'",
                )

        s3_key = parent.get("s3_key") or parent.get("image_s3_key")
        if not s3_key:
            raise HTTPException(status_code=404, detail="Creative image not found in S3")

        parent_bytes = await download_bytes(s3_key)

        gen_inputs = parent.get("generation_inputs", {})
        qr_code_bytes = None
        if gen_inputs.get("qr_s3_key"):
            try:
                qr_code_bytes = await download_bytes(gen_inputs["qr_s3_key"])
            except Exception:
                pass # Just ignore if we can't get it, same as router

        parent_gen = parent.get("generated", {})

        config = MODE_DEFAULTS[PipelineMode.SIZE_VARIANT].model_copy(
            update=params.pipeline.model_dump(exclude_unset=True)
        )

        inputs = PipelineInputs(
            product_name=gen_inputs.get("product_name", parent.get("name", "Product")),
            description=gen_inputs.get("description", ""),
            ad_format="", # Each variation will have its own ad_format
            client_id=parent.get("client_id", "revspot"),
            name=parent.get("name", "Creative"),
            images=ImageBundle(
                product_images=[(parent_bytes, "image/png")], # Pass parent here
                ref_images=[],
                logo_images=[],
            ),
            associations=parent.get("associations", []),
            persona_info=gen_inputs.get("persona_info", ""),
            creative_strategy=gen_inputs.get("creative_strategy", ""),
            instructions=gen_inputs.get("instructions", ""),
            count=len(sizes),
            rera_number=gen_inputs.get("rera_number"),
            qr_code_bytes=qr_code_bytes,
            existing_prompts=[parent_gen.get("prompt_used", "")],
            ad_copy_data=parent.get("ad_copy"),
            size_variant_platform=platform,
            size_variant_sizes=sizes,
            parent_creative_s3_key=s3_key,
        )

        config.post_processors = [
            p for p in config.post_processors
            if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
        ]

        return inputs, config
