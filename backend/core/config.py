from __future__ import annotations

from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field

from core.protocols import PipelineInputs


class PipelineMode(str, Enum):
    GENERATE = "generate"
    REGENERATE = "regenerate"
    EDIT = "edit"
    SIZE_VARIANT = "size_variant"


class PipelineConfig(BaseModel):
    mode: PipelineMode = PipelineMode.GENERATE
    prompt_strategy: str = "v2"
    image_search: str = "web"
    post_processors: list[str] = Field(default_factory=list)
    provider: str | None = None  # "gemini" | "openai" | None (use DEFAULT_REGISTRY)


MODE_DEFAULTS: dict[PipelineMode, PipelineConfig] = {
    PipelineMode.GENERATE: PipelineConfig(mode=PipelineMode.GENERATE, post_processors=[]), # "compositor"
    PipelineMode.REGENERATE: PipelineConfig(mode=PipelineMode.REGENERATE, post_processors=[]),
    PipelineMode.EDIT: PipelineConfig(mode=PipelineMode.EDIT, post_processors=[]),
    PipelineMode.SIZE_VARIANT: PipelineConfig(mode=PipelineMode.SIZE_VARIANT, post_processors=["aspect_ratio_fill", "compositor"]),
}

POST_PROCESSOR_GUARDS: dict[str, Callable[[PipelineInputs], bool]] = {
    "compositor": lambda inputs: bool(inputs.rera_number or inputs.qr_code_bytes),
}
