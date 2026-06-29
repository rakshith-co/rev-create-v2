# Creatives Model Design

**Date:** 2026-04-07
**Branch:** feat/godrej-mvp
**Status:** Approved

---

## Problem

The codebase has three separate storage paths for ad creatives:

- `images` collection — AI-generated project variations (pipeline output)
- `static_creatives` collection — manually uploaded static ad images
- `FbFormBannerResponse` — FB banner generation result, not persisted to a collection

These three paths share no schema, have inconsistent field naming, and make it impossible to build a unified "all creatives" view. There is no explicit metadata about what type, subtype, or size a creative is.

---

## Decision

Replace all three with a single `creatives` MongoDB collection. Every creative — generated or uploaded, image or video, any format — is one document in this collection with a consistent shape and an explicit metadata block that encodes type, subtype, and size specs.

---

## Subtype Registry

Subtypes are fixed enums. The registry is the single source of truth for size specs — callers never supply dimensions directly.

Defined in `services/creative_registry.py`.

| subtype | type | width | height | aspect_ratio | label |
|---|---|---|---|---|---|
| `fb-banner` | image | 1200 | 444 | 2.7:1 | Facebook Lead Ad Banner |
| `feed-square` | image | 1080 | 1080 | 1:1 | Feed Square |
| `feed-landscape` | image | 1200 | 628 | 16:9 | Feed Landscape |
| `story` | image | 1080 | 1920 | 9:16 | Story / Reels |
| `logo-square` | image | 1200 | 1200 | 1:1 | Logo Square |
| `logo-rect` | image | 1200 | 300 | 4:1 | Logo Rectangular |
| `reel` | video | 1080 | 1920 | 9:16 | Instagram/Facebook Reel |
| `story-video` | video | 1080 | 1920 | 9:16 | Story Video |

---

## MongoDB Document Shape

```json
{
  "_id": "uuid",
  "source": "generated | uploaded",
  "client_id": "revspot",
  "project_id": "uuid | null",
  "name": "Godrej Reserve Banner",
  "status": "pending | generating | done | failed | uploaded",
  "s3_key": "creatives/{id}.png",
  "error_message": null,
  "created_at": "2026-04-07T00:00:00Z",

  "metadata": {
    "type": "image | video",
    "subtype": "fb-banner | feed-square | ...",
    "size_specs": {
      "width": 1200,
      "height": 444,
      "aspect_ratio": "2.7:1",
      "label": "Facebook Lead Ad Banner"
    }
  },

  "generated": {
    "prompt_used": "...",
    "variation_index": 1,
    "version": 1,
    "parent_id": null,
    "edit_instruction": null
  },

  "uploaded": {
    "original_filename": "banner.jpg",
    "mime_type": "image/jpeg",
    "campaign_tag": "summer-launch"
  }
}
```

Rules:
- `generated` sub-object is present only when `source == "generated"`, otherwise omitted.
- `uploaded` sub-object is present only when `source == "uploaded"`, otherwise omitted.
- `project_id` is null for standalone creatives (FB banner, static upload) and set for pipeline-generated variations.
- `status` is `"uploaded"` for completed uploads; `"done"` for completed generation.

---

## Pydantic Schemas (`schemas.py`)

```python
class CreativeType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"

class CreativeSubtype(str, Enum):
    FB_BANNER      = "fb-banner"
    FEED_SQUARE    = "feed-square"
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

class CreativeMetadata(BaseModel):
    type: CreativeType
    subtype: CreativeSubtype
    size_specs: SizeSpecs

class GeneratedFields(BaseModel):
    prompt_used: str
    variation_index: int = 1
    version: int = 1
    parent_id: Optional[str] = None
    edit_instruction: Optional[str] = None

class UploadedFields(BaseModel):
    original_filename: str
    mime_type: str
    campaign_tag: str = ""

class CreativeOut(BaseModel):
    id: str
    source: CreativeSource
    metadata: CreativeMetadata
    client_id: str
    project_id: Optional[str] = None
    name: Optional[str] = None
    status: str
    s3_key: str
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    generated: Optional[GeneratedFields] = None
    uploaded: Optional[UploadedFields] = None
    created_at: datetime

# Backward-compatibility alias — allows ProjectOut and LogOut to keep
# referencing ImageOut without immediate refactor.
ImageOut = CreativeOut
```

Remove from `schemas.py`: `StaticCreativeOut`, `StaticCreativeListResponse`, `FbFormBannerResponse`.

---

## File-by-File Changes

### `services/creative_registry.py` (new)
Defines `SUBTYPE_REGISTRY: dict[CreativeSubtype, SizeSpecs]` with all 8 entries.
Exposes `get_size_specs(subtype: CreativeSubtype) -> SizeSpecs`.

### `db.py`
- Add `creatives: AsyncCollection` — initialized as `_db["creatives"]` in `connect()`.
- Keep `images` registered temporarily until all references are migrated, then remove.
- Remove `static_creatives` registration.

### `services/pipeline.py`
- Replace all `db.images` with `db.creatives`.
- Each inserted creative document includes the full metadata block.
- Subtype is derived from the project's `ad_format` field at runtime by matching dimensions against the registry (e.g. `1080x1080` → `feed-square`, `1080x1920` → `story`, `1200x628` → `feed-landscape`). If no exact match exists, defaults to `feed-square`.
- All four variations share the same subtype (they differ only in compositional hint, not canvas size).
- All four are `source="generated"`, `project_id` set.

### `routers/images.py`
- All `db.images` → `db.creatives`.
- `_to_out()` returns `CreativeOut`.

### `routers/fb_form_banner.py`
- After generation, insert a `creatives` document: `source="generated"`, `subtype="fb-banner"`, `metadata` from registry, `generated.prompt_used` set.
- Endpoint returns `CreativeOut` (drop `FbFormBannerResponse`).

### `routers/static_creatives.py`
- Write to `db.creatives` instead of `db.static_creatives`.
- Caller supplies `subtype` as a form field (validated against `CreativeSubtype` enum).
- Document uses `source="uploaded"`, `uploaded` sub-object populated, `status="uploaded"`.
- Router prefix stays `/api/image/upload`.
- Returns `CreativeOut`.

### `main.py`
- No router changes needed — all three routers already registered.

### `schemas.py`
- Add all new enums and models.
- Add `ImageOut = CreativeOut` alias.
- Remove `StaticCreativeOut`, `StaticCreativeListResponse`, `FbFormBannerResponse`.

---

## S3 Key Convention

All creatives stored under `creatives/{id}.png` (or `.jpg`, `.webp` for uploads). The existing `images/{id}.png` and `static-creatives/{id}.{ext}` paths are legacy — new writes all go to `creatives/`.

---

## What Is Not Changing

- Pipeline orchestration logic (`run_pipeline`) — only the collection name and document shape change.
- Prompt builder logic, LLM calls, image generation calls.
- `ProjectOut` schema — `images: list[ImageOut]` continues to work via the alias.
- All existing API routes and their URL paths.
