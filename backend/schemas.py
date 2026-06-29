from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any

from services.creative_registry import CreativeType, CreativeSubtype, CreativeSource, SizeSpecs

# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    images: Optional[list[str]] = None

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

class ChatResponse(BaseModel):
    role: str
    content: str
    images: list[str] = []

# ── internal ──────────────────────────────────────────────────────────────────


class AdCopy(BaseModel):
    headline: str = ""
    body_copy: str = ""
    cta: str = ""
    image_prompt: str


class AdCopyOnly(BaseModel):
    headline: str
    body_copy: str
    cta: str
    variations: list["AdCopyVariation"] = Field(default_factory=list)


class AdCopyVariation(BaseModel):
    headline: str
    body_copy: str


class MetaAdCopyGeneration(BaseModel):
    primary_text: list[str]
    headline: list[str]
    description: list[str]
    call_to_action: str


class MetaAdCopy(BaseModel):
    primary_text: list[str]
    headline: list[str]
    description: list[str]
    call_to_action: str

    @field_validator("primary_text", "headline", "description", mode="before")
    @classmethod
    def coerce_str_to_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class ReraPlacement(BaseModel):
    corner: str          # "bottom-right" | "bottom-left" | "top-right" | "top-left"
    x: float             # left edge as fraction of canvas width  (0.0–1.0)
    y: float             # top  edge as fraction of canvas height (0.0–1.0)
    w: float             # box width  as fraction of canvas width
    h: float             # box height as fraction of canvas height


class ImagePromptResult(BaseModel):
    image_prompt: str


class BrandInfo(BaseModel):
    company_name: str
    tagline: Optional[str] = None
    brand_voice: Optional[str] = "professional"
    target_personas: Optional[list[str]] = []
    industry: Optional[str] = "general"

    @field_validator("brand_voice", "industry", mode="before")
    @classmethod
    def handle_none_strings(cls, v, info):
        if v is None:
            return "professional" if info.field_name == "brand_voice" else "general"
        return v

    @field_validator("target_personas", mode="before")
    @classmethod
    def handle_none_list(cls, v):
        return v or []


# ── Creative Model ────────────────────────────────────────────────────────────

class CreativeMetadata(BaseModel):
    type: CreativeType
    subtype: CreativeSubtype
    size_specs: SizeSpecs

class GeneratedFields(BaseModel):
    variation_index: int = 1
    version: int = 1
    parent_id: Optional[str] = None
    edit_instruction: Optional[str] = None

class UploadedFields(BaseModel):
    original_filename: str
    mime_type: str
    campaign_tag: str = ""

class Association(BaseModel):
    type: str   # "project" | "campaign" | "brand" | "client"
    id: str

class PlatformAdCopy(BaseModel):
    meta: Optional[MetaAdCopy] = None

class CreativeAdCopy(BaseModel):
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    cta: Optional[str] = None
    platforms: PlatformAdCopy = Field(default_factory=PlatformAdCopy)

class CreativeOut(BaseModel):
    id: str
    source: CreativeSource
    metadata: CreativeMetadata
    client_id: str
    associations: list[Association] = []
    name: Optional[str] = None
    status: str
    s3_key: str
    creative_url: Optional[str] = None
    error_message: Optional[str] = None
    generated: Optional[GeneratedFields] = None
    uploaded: Optional[UploadedFields] = None
    ad_copy: Optional[CreativeAdCopy] = None
    created_at: datetime

# Backward-compatibility alias
ImageOut = CreativeOut

# ── API response shapes ───────────────────────────────────────────────────────

class ProjectOut(BaseModel):
    id: str
    name: str
    product_name: str
    description: str
    ad_format: str
    client_id: str = "revspot"
    status: str                         # pending | generating_copy | generating_images | ready | failed
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    generated_cta: Optional[str] = None
    image_prompt: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    images: list[ImageOut] = []
    brand_info: Optional[BrandInfo] = None


class GenerationOut(BaseModel):
    headline: str
    body_copy: str
    generated_cta: str
    image_prompt: str
    ad_copy: Optional[CreativeAdCopy] = None
    images: list[CreativeOut]


class ProjectSummary(BaseModel):
    id: str
    name: str
    product_name: str
    status: str
    ad_format: str
    client_id: str = "revspot"
    created_at: datetime
    image_count: int = 0
    done_count: int = 0


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int
    page: int
    limit: int
    total_pages: int


class GenerateResponse(BaseModel):
    headline: str
    body_copy: str
    cta: str
    image_prompt: str
    creative_url: Optional[str] = None
    image_base64: Optional[str] = None


# ── logs ──────────────────────────────────────────────────────────────────────

class EvalCriterion(BaseModel):
    name: str
    score: Optional[float] = None
    notes: str = ""


class LogEval(BaseModel):
    criteria: list[EvalCriterion] = []
    overall_notes: str = ""


class LogInputs(BaseModel):
    product_name: str
    description: str
    ad_format: str
    has_product_images: bool
    has_ref_images: bool


class LogPrompts(BaseModel):
    style_context: str
    system_prompt: str
    user_brief: str
    image_prompt: str


class LogAdCopy(BaseModel):
    headline: str
    body_copy: str
    cta: str


class LogSummary(BaseModel):
    id: str
    project_id: str
    project_name: str
    inputs: LogInputs
    ad_copy: LogAdCopy
    eval: LogEval
    image_count: int
    created_at: datetime


class LogOut(BaseModel):
    id: str
    project_id: str
    project_name: str
    inputs: LogInputs
    prompts: LogPrompts
    ad_copy: LogAdCopy
    image_ids: list[str]
    images: list[ImageOut] = []
    eval: LogEval
    created_at: datetime


# ── request bodies ────────────────────────────────────────────────────────────

class EditImageRequest(BaseModel):
    instruction: str
    provider: Optional[str] = None  # "gemini" | "openai" | None


class SizeVariantRequest(BaseModel):
    platform: str  # "meta" | "google"
    creative_id: Optional[str] = None
    sizes: Optional[list[str]] = None  # Optional list of dimensions (e.g., ["1080x1080", "1200x628"])
    use_latest: bool = True  # If True, resolve to the most recent edited version; if False, use the exact creative passed
    provider: Optional[str] = None  # "gemini" | "openai" | None


class RegenerateRequest(BaseModel):
    provider: Optional[str] = None  # "gemini" | "openai" | None


class BatchRegenerateRequest(BaseModel):
    image_ids: list[str]
    provider: Optional[str] = None  # "gemini" | "openai" | None


class UpdateEvalRequest(BaseModel):
    eval: LogEval


# ── Jobs ─────────────────────────────────────────────────────────────────────

class JobOut(BaseModel):
    id: str
    type: str                            # "generate" | "size_variants" | "batch_regenerate" | "edit"
    status: str                          # derived
    creative_ids: list[str]
    creatives: list[CreativeOut]         # full creative docs with presigned URLs

    # Ad copy — only populated for type=generate
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    generated_cta: Optional[str] = None
    image_prompt: Optional[str] = None
    ad_copy: Optional[CreativeAdCopy] = None

    # Edit context — populated for type=edit
    edit_history: Optional[list[str]] = None
    edit_instruction: Optional[str] = None

    created_at: datetime


class AsyncAccepted(BaseModel):
    job_id: str
