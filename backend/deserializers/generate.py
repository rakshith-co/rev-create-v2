import uuid
from typing import Optional, List
from fastapi import UploadFile
from pydantic import BaseModel, Field

from core.protocols import InputDeserializer, PipelineInputs, ImageBundle
from core.config import PipelineConfig, PipelineMode, MODE_DEFAULTS, POST_PROCESSOR_GUARDS
from services.creative_registry import CreativeSubtype, find_subtype_by_dimensions
from services.s3 import upload_bytes

_SINGLE_IMAGE_SUBTYPES = {CreativeSubtype.FB_BANNER}
_SUBTYPE_STRATEGY: dict[CreativeSubtype, str] = {
    CreativeSubtype.FB_BANNER: "fb",
}

class GenerateRequestParams(BaseModel):
    product_name: str
    description: str
    ad_format: str
    name: str
    client_id: str = "revspot"
    persona_info: str = ""
    creative_strategy: str = ""
    instructions: str = ""
    count: int = 4
    rera_number: str | None = None
    associations: list[dict] = Field(default_factory=list)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    brand: dict = Field(default_factory=dict)
    product_image_keys: list[dict] = Field(default_factory=list)
    ref_image_keys: list[dict] = Field(default_factory=list)
    logo_image_keys: list[dict] = Field(default_factory=list)


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class GenerateDeserializer(InputDeserializer):
    async def parse(
        self,
        params: GenerateRequestParams,
        product_images: List[UploadFile],
        ref_images: List[UploadFile],
        logo_images: List[UploadFile],
        qr_code_bytes: Optional[bytes] = None,
    ) -> tuple[PipelineInputs, PipelineConfig]:
        batch_id = str(uuid.uuid4())
        
        async def _upload_files(files: List[UploadFile], prefix: str) -> tuple[list[tuple[bytes, str]], list[dict]]:
            bytes_result = []
            keys_result = []
            for i, f in enumerate(files):
                if not f.filename:
                    continue
                data = await f.read()
                ctype = f.content_type
                if ctype in ALLOWED_IMAGE_TYPES:
                    ext = _MIME_EXT.get(ctype, "png")
                    key = f"inputs/{batch_id}/{prefix}_{i}.{ext}"
                    await upload_bytes(key, data, ctype)
                    bytes_result.append((data, ctype))
                    keys_result.append({"s3_key": key, "mime_type": ctype})
            return bytes_result, keys_result

        product_bytes, product_keys = await _upload_files(product_images, "product")
        ref_bytes, ref_keys = await _upload_files(ref_images, "ref")
        logo_bytes, logo_keys = await _upload_files(logo_images, "logo")

        from services.s3 import download_bytes
        async def _download_keys(keys: list[dict]) -> list[tuple[bytes, str]]:
            import asyncio
            async def _dl(k):
                return await download_bytes(k["s3_key"]), k.get("mime_type", "image/png")
            if not keys: return []
            return await asyncio.gather(*[_dl(k) for k in keys])

        dl_product_bytes = await _download_keys(params.product_image_keys)
        dl_ref_bytes = await _download_keys(params.ref_image_keys)
        dl_logo_bytes = await _download_keys(params.logo_image_keys)

        final_product_bytes = product_bytes + dl_product_bytes
        final_ref_bytes = ref_bytes + dl_ref_bytes
        final_logo_bytes = logo_bytes + dl_logo_bytes

        # Combine uploaded keys with existing keys from request
        final_product_keys = product_keys + params.product_image_keys
        final_ref_keys = ref_keys + params.ref_image_keys
        final_logo_keys = logo_keys + params.logo_image_keys

        qr_s3_key = None
        if qr_code_bytes:
            import puremagic
            try:
                mime = puremagic.magic_string(qr_code_bytes)[0].mime_type or "image/png"
            except Exception:
                mime = "image/png"
            ext = _MIME_EXT.get(mime, "png")
            qr_s3_key = f"inputs/{batch_id}/qr_code.{ext}"
            await upload_bytes(qr_s3_key, qr_code_bytes, mime)

        # Merge base config
        config = MODE_DEFAULTS[PipelineMode.GENERATE].model_copy(
            update=params.pipeline.model_dump(exclude_unset=True)
        )
        # ad_format is authoritative for strategy — always override
        subtype = find_subtype_by_dimensions(params.ad_format)
        if subtype in _SUBTYPE_STRATEGY:
            config.prompt_strategy = _SUBTYPE_STRATEGY[subtype]

        inputs = PipelineInputs(
            product_name=params.product_name,
            description=params.description,
            ad_format=params.ad_format,
            client_id=params.client_id,
            name=params.name,
            images=ImageBundle(
                product_images=final_product_bytes,
                ref_images=final_ref_bytes,
                logo_images=final_logo_bytes,
            ),
            associations=params.associations,
            persona_info=params.persona_info,
            creative_strategy=params.creative_strategy,
            instructions=params.instructions,
            count=1 if find_subtype_by_dimensions(params.ad_format) in _SINGLE_IMAGE_SUBTYPES else params.count,
            rera_number=params.rera_number,
            qr_code_bytes=qr_code_bytes,
            qr_s3_key=qr_s3_key,
            product_image_keys=final_product_keys,
            ref_image_keys=final_ref_keys,
            logo_image_keys=final_logo_keys,
        )

        # Post-processor pruning
        config.post_processors = [
            p for p in config.post_processors
            if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
        ]

        return inputs, config
