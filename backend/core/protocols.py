from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from core.config import PipelineConfig

from services.creative_registry import CreativeSubtype


# ── Shared image container ────────────────────────────────────────────────────

@dataclass
class ImageBundle:
    product_images: list[tuple[bytes, str]] = field(default_factory=list)
    ref_images: list[tuple[bytes, str]] = field(default_factory=list)
    logo_images: list[tuple[bytes, str]] = field(default_factory=list)


# ── Brand + copy models ───────────────────────────────────────────────────────

class BrandInfo(BaseModel):
    company_name: str | None = None
    tagline: str | None = None
    brand_voice: str | None = None
    target_personas: list[str] = Field(default_factory=list)
    industry: str | None = None
    primary_color: str | None = None
    secondary_colors: list[str] = Field(default_factory=list)
    font_family: str | None = None
    font_style: str | None = None


class AdCopyVariation(BaseModel):
    headline: str
    body_copy: str
    visual_hint: str = ""


class AdCopy(BaseModel):
    headline: str
    body_copy: str
    cta: str
    variations: list[AdCopyVariation] = Field(default_factory=list)
    platforms: dict = Field(default_factory=dict)


# ── Pipeline I/O ──────────────────────────────────────────────────────────────

@dataclass
class CreativeContext:
    creative_id: str
    rera_number: str | None
    qr_code_bytes: bytes | None
    ad_format: str
    variation_index: int


@dataclass
class PipelineInputs:
    product_name: str
    description: str
    ad_format: str
    client_id: str
    name: str
    images: ImageBundle
    associations: list[dict]
    persona_info: str = ""
    creative_strategy: str = ""
    instructions: str = ""
    count: int = 4
    rera_number: str | None = None
    qr_code_bytes: bytes | None = None
    qr_s3_key: str | None = None
    ad_copy_data: dict | None = None
    product_image_keys: list[dict] = field(default_factory=list)
    ref_image_keys: list[dict] = field(default_factory=list)
    logo_image_keys: list[dict] = field(default_factory=list)
    # Pre-created creative IDs for regenerate/edit/size_variant modes
    existing_creative_ids: list[str] = field(default_factory=list)
    existing_prompts: list[str] = field(default_factory=list)
    # Edit mode fields
    edit_instruction: str | None = None
    edit_history: list[str] = field(default_factory=list)
    parent_s3_key: str | None = None
    # Size variant mode fields
    size_variant_platform: str | None = None
    size_variant_sizes: list[tuple[str, str, str]] = field(default_factory=list)  # (label, dims, aspect_ratio)
    parent_creative_s3_key: str | None = None


# ── Port interfaces ───────────────────────────────────────────────────────────

class PromptStrategy(Protocol):
    def build_copy_system_prompt(self, context: dict) -> str: ...
    def build_copy_user_brief(self, context: dict) -> str: ...
    def build_image_prompt_system(self, context: dict) -> str: ...
    def build_meta_copy_system(self, context: dict) -> str: ...
    def build_image_prompt_brief(self, context: dict) -> str: ...
    def build_image_gen_system(self, context: dict) -> str: ...
    def build_image_gen_prompt(self, base_prompt: str, ad_copy: "AdCopy | None", variation_index: int) -> str: ...
    def variation_hints(self) -> list[str]: ...


class ImageSearchStrategy(Protocol):
    async def find(
        self,
        product_name: str,
        description: str,
        ad_copy_text: str,
        persona_info: str,
        creative_strategy: str,
    ) -> tuple[bytes, str] | None: ...


class PostProcessor(Protocol):
    async def process(self, image_bytes: bytes, context: CreativeContext) -> bytes: ...


class OutputSerializer(Protocol):
    async def write_creative(
        self,
        creative_id: str,
        inputs: PipelineInputs,
        ad_copy: AdCopy,
        prompt_used: str,
        variation_index: int,
        subtype: CreativeSubtype,
    ) -> None: ...

    async def upload_image(self, creative_id: str, image_bytes: bytes) -> str: ...
    async def mark_done(self, creative_id: str) -> None: ...
    async def mark_failed(self, creative_id: str, error: str) -> None: ...


class InputDeserializer(Protocol):
    async def parse(self, *args, **kwargs) -> tuple[PipelineInputs, PipelineConfig]: ...
