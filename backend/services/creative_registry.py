from enum import Enum
from pydantic import BaseModel
from typing import Dict


class CreativeType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class CreativeSubtype(str, Enum):
    FB_BANNER      = "fb-banner"
    FEED_SQUARE    = "feed-square"
    FEED_PORTRAIT  = "feed-portrait"
    FEED_LANDSCAPE = "feed-landscape"
    STORY          = "story"
    LOGO_SQUARE    = "logo-square"
    LOGO_RECT      = "logo-rect"
    REEL           = "reel"
    STORY_VIDEO    = "story-video"


class CreativeSource(str, Enum):
    GENERATED = "generated"
    UPLOADED  = "uploaded"


class SizeSpecs(BaseModel):
    width: int
    height: int
    aspect_ratio: str
    label: str


SUBTYPE_REGISTRY: Dict[CreativeSubtype, SizeSpecs] = {
    CreativeSubtype.FB_BANNER: SizeSpecs(width=1200, height=628, aspect_ratio="1.91:1", label="Facebook Lead Ad Banner"),
    CreativeSubtype.FEED_SQUARE: SizeSpecs(width=1080, height=1080, aspect_ratio="1:1", label="Feed Square"),
    CreativeSubtype.FEED_PORTRAIT: SizeSpecs(width=1080, height=1350, aspect_ratio="4:5", label="Feed Portrait"),
    CreativeSubtype.FEED_LANDSCAPE: SizeSpecs(width=1200, height=628, aspect_ratio="16:9", label="Feed Landscape"),
    CreativeSubtype.STORY: SizeSpecs(width=1080, height=1920, aspect_ratio="9:16", label="Story / Reels"),
    CreativeSubtype.LOGO_SQUARE: SizeSpecs(width=1200, height=1200, aspect_ratio="1:1", label="Logo Square"),
    CreativeSubtype.LOGO_RECT: SizeSpecs(width=1200, height=300, aspect_ratio="4:1", label="Logo Rectangular"),
    CreativeSubtype.REEL: SizeSpecs(width=1080, height=1920, aspect_ratio="9:16", label="Instagram/Facebook Reel"),
    CreativeSubtype.STORY_VIDEO: SizeSpecs(width=1080, height=1920, aspect_ratio="9:16", label="Story Video"),
}


def get_size_specs(subtype: CreativeSubtype) -> SizeSpecs:
    return SUBTYPE_REGISTRY[subtype]


def find_subtype_by_dimensions(dimensions: str) -> CreativeSubtype:
    """
    Matches dimensions (e.g. '1080x1080') or subtype name (e.g. 'fb-banner') against the registry.
    Returns CreativeSubtype.FEED_SQUARE as default if no match.
    """
    # Accept subtype name directly (e.g. "fb-banner")
    try:
        return CreativeSubtype(dimensions)
    except ValueError:
        pass
    for subtype, specs in SUBTYPE_REGISTRY.items():
        if f"{specs.width}x{specs.height}" == dimensions:
            return subtype
    return CreativeSubtype.FEED_SQUARE


def resolve_aspect_ratio(ad_format: str) -> str:
    """Return the canonical aspect ratio string for an ad_format (e.g. 'fb-banner' → '1.91:1')."""
    subtype = find_subtype_by_dimensions(ad_format)
    return SUBTYPE_REGISTRY[subtype].aspect_ratio
