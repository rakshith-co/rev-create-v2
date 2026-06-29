from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field

from repos import creatives as creatives_repo
from core.protocols import InputDeserializer, PipelineInputs, ImageBundle
from core.config import PipelineConfig, PipelineMode, MODE_DEFAULTS, POST_PROCESSOR_GUARDS
from services.s3 import download_bytes

class EditRequestParams(BaseModel):
    instruction: str
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ref_images: list[tuple[bytes, str]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

class EditDeserializer(InputDeserializer):
    async def parse(
        self,
        creative_id: str,
        params: EditRequestParams,
    ) -> tuple[PipelineInputs, PipelineConfig]:
        parent = await creatives_repo.get(creative_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Creative not found")

        s3_key = parent.get("s3_key") or parent.get("image_s3_key")
        if not s3_key:
            raise HTTPException(status_code=404, detail="Creative image not found in S3")

        parent_bytes = await download_bytes(s3_key)

        parent_gen = parent.get("generated", {})
        
        # Walk the parent chain to collect all past edit instructions (oldest first)
        raw_history: list[str] = []
        if parent_gen.get("edit_instruction"):
            raw_history.append(parent_gen["edit_instruction"])
        ancestor_id = parent_gen.get("parent_id")
        while ancestor_id:
            ancestor = await creatives_repo.get(ancestor_id, {"generated": 1})
            if not ancestor:
                break
            ancestor_gen = ancestor.get("generated") or {}
            if ancestor_gen.get("edit_instruction"):
                raw_history.append(ancestor_gen["edit_instruction"])
            ancestor_id = ancestor_gen.get("parent_id")
        edit_history = list(reversed(raw_history))  # oldest → newest

        metadata = parent.get("metadata", {})
        size_specs = metadata.get("size_specs", {})
        ad_format = f"{size_specs.get('width', 1080)}x{size_specs.get('height', 1080)}"
        
        gen_inputs = parent.get("generation_inputs", {})

        config = MODE_DEFAULTS[PipelineMode.EDIT].model_copy(
            update=params.pipeline.model_dump(exclude_unset=True)
        )

        inputs = PipelineInputs(
            product_name=gen_inputs.get("product_name", parent.get("name", "Product")),
            description=gen_inputs.get("description", ""),
            ad_format=ad_format,
            client_id=parent.get("client_id", "revspot"),
            name=parent.get("name", "Creative"),
            images=ImageBundle(
                product_images=[(parent_bytes, "image/png")],  # Parent image is passed in product_images for editing
                ref_images=params.ref_images,
                logo_images=[],
            ),
            associations=parent.get("associations", []),
            persona_info=gen_inputs.get("persona_info", ""),
            creative_strategy=gen_inputs.get("creative_strategy", ""),
            instructions=gen_inputs.get("instructions", ""),
            count=1,
            rera_number=gen_inputs.get("rera_number"),
            qr_code_bytes=None,
            existing_prompts=[parent_gen.get("prompt_used", "")],
            edit_instruction=params.instruction,
            edit_history=edit_history,
            parent_s3_key=s3_key,
            ad_copy_data=parent.get("ad_copy"),
        )

        config.post_processors = [
            p for p in config.post_processors
            if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
        ]

        return inputs, config
