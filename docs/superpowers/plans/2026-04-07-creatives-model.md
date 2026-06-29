# Creatives Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `images` and `static_creatives` MongoDB collections with a single `creatives` collection that carries explicit type/subtype/size metadata on every document.

**Architecture:** A new `services/creative_registry.py` defines the subtype enum and a size-spec lookup used by all write paths. `schemas.py` gains new Pydantic models (`CreativeOut`, `CreativeMetadata`, etc.) and an `ImageOut = CreativeOut` alias so existing callers don't break. Each router and the pipeline is updated to write the new document shape to `db.creatives`.

**Tech Stack:** FastAPI, Motor (async MongoDB), Pydantic v2, Boto3 (S3), Python 3.11+

**Spec:** `docs/superpowers/specs/2026-04-07-creatives-model-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Create** | `backend/services/creative_registry.py` | Subtype enum, size-spec registry, `ad_format` → subtype resolver |
| **Modify** | `backend/schemas.py` | Add new enums + models, `ImageOut = CreativeOut` alias, remove old models |
| **Modify** | `backend/db.py` | Add `creatives` collection, remove `static_creatives` |
| **Modify** | `backend/routers/static_creatives.py` | Write to `creatives`, add `subtype` form field, return `CreativeOut` |
| **Modify** | `backend/routers/fb_form_banner.py` | Persist to `creatives`, return `CreativeOut` |
| **Modify** | `backend/services/pipeline.py` | Write new document shape to `db.creatives` |
| **Modify** | `backend/routers/images.py` | Read/write `db.creatives`, new `_to_out` returning `CreativeOut` |

---

## Task 1: Create `services/creative_registry.py`

**Files:**
- Create: `backend/services/creative_registry.py`

- [ ] **Step 1: Write the file**

```python
# backend/services/creative_registry.py
from enum import Enum


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


# (width, height) → subtype — used to resolve ad_format strings at runtime
_DIM_TO_SUBTYPE: dict[tuple[int, int], CreativeSubtype] = {
    (1080, 1080): CreativeSubtype.FEED_SQUARE,
    (1200, 628):  CreativeSubtype.FEED_LANDSCAPE,
    (1080, 1920): CreativeSubtype.STORY,
    (1200, 1200): CreativeSubtype.LOGO_SQUARE,
    (1200, 300):  CreativeSubtype.LOGO_RECT,
    (1200, 444):  CreativeSubtype.FB_BANNER,
}

# Size specs stored inline so documents are self-describing
SUBTYPE_REGISTRY: dict[CreativeSubtype, dict] = {
    CreativeSubtype.FB_BANNER:      {"width": 1200, "height": 444,  "aspect_ratio": "2.7:1", "label": "Facebook Lead Ad Banner"},
    CreativeSubtype.FEED_SQUARE:    {"width": 1080, "height": 1080, "aspect_ratio": "1:1",   "label": "Feed Square"},
    CreativeSubtype.FEED_LANDSCAPE: {"width": 1200, "height": 628,  "aspect_ratio": "16:9",  "label": "Feed Landscape"},
    CreativeSubtype.STORY:          {"width": 1080, "height": 1920, "aspect_ratio": "9:16",  "label": "Story / Reels"},
    CreativeSubtype.LOGO_SQUARE:    {"width": 1200, "height": 1200, "aspect_ratio": "1:1",   "label": "Logo Square"},
    CreativeSubtype.LOGO_RECT:      {"width": 1200, "height": 300,  "aspect_ratio": "4:1",   "label": "Logo Rectangular"},
    CreativeSubtype.REEL:           {"width": 1080, "height": 1920, "aspect_ratio": "9:16",  "label": "Instagram/Facebook Reel"},
    CreativeSubtype.STORY_VIDEO:    {"width": 1080, "height": 1920, "aspect_ratio": "9:16",  "label": "Story Video"},
}


def get_size_specs(subtype: CreativeSubtype) -> dict:
    """Return size_specs dict for the given subtype."""
    return SUBTYPE_REGISTRY[subtype]


def subtype_from_ad_format(ad_format: str) -> CreativeSubtype:
    """Resolve a 'WxH' ad_format string to the closest CreativeSubtype.
    Falls back to FEED_SQUARE when no exact match exists.
    """
    try:
        w, h = ad_format.lower().split("x")
        return _DIM_TO_SUBTYPE.get((int(w.strip()), int(h.strip())), CreativeSubtype.FEED_SQUARE)
    except Exception:
        return CreativeSubtype.FEED_SQUARE


def build_metadata(subtype: CreativeSubtype) -> dict:
    """Return a complete metadata dict ready to embed in a MongoDB document."""
    entry = SUBTYPE_REGISTRY[subtype]
    return {
        "type": CreativeType.IMAGE.value if subtype != CreativeSubtype.REEL and subtype != CreativeSubtype.STORY_VIDEO else CreativeType.VIDEO.value,
        "subtype": subtype.value,
        "size_specs": entry,
    }
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd backend && python -c "from services.creative_registry import build_metadata, CreativeSubtype; print(build_metadata(CreativeSubtype.FB_BANNER))"
```

Expected output:
```
{'type': 'image', 'subtype': 'fb-banner', 'size_specs': {'width': 1200, 'height': 444, 'aspect_ratio': '2.7:1', 'label': 'Facebook Lead Ad Banner'}}
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/creative_registry.py
git commit -m "feat: add creative_registry with subtype enum and size-spec lookup"
```

---

## Task 2: Update `schemas.py`

**Files:**
- Modify: `backend/schemas.py`

- [ ] **Step 1: Add new imports at top of schemas.py**

Add after `from typing import Optional`:

```python
from enum import Enum
from services.creative_registry import CreativeType, CreativeSubtype, CreativeSource
```

- [ ] **Step 2: Add new Pydantic models after the `BrandInfo` class**

Insert the following block after the `BrandInfo` class and before `# ── API response shapes`:

```python
# ── creatives ─────────────────────────────────────────────────────────────────

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
    client_id: str = "revspot"
    project_id: Optional[str] = None
    name: Optional[str] = None
    status: str
    s3_key: str
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    generated: Optional[GeneratedFields] = None
    uploaded: Optional[UploadedFields] = None
    # Legacy size-variant fields kept for backward-compat with frontend
    platform: Optional[str] = None
    is_size_variant: bool = False
    created_at: datetime
```

- [ ] **Step 3: Replace `ImageOut` class with alias**

Find and replace the existing `ImageOut` class definition:

```python
# REMOVE this entire class:
class ImageOut(BaseModel):
    id: str
    project_id: str
    parent_id: Optional[str] = None
    version: int
    variation_index: int
    image_url: Optional[str] = None
    edit_instruction: Optional[str] = None
    status: str                         # pending | generating | done | failed
    error_message: Optional[str] = None
    created_at: datetime
    platform: Optional[str] = None      # "meta" | "google" — set for size variants
    size_label: Optional[str] = None    # e.g. "Feed Square", "Leaderboard"
    size_dimensions: Optional[str] = None  # e.g. "1080x1920" — stored directly for reliable display
    is_size_variant: bool = False

# REPLACE with:
# Backward-compatibility alias — ProjectOut and LogOut keep referencing ImageOut
ImageOut = CreativeOut
```

- [ ] **Step 4: Remove superseded schemas**

Delete the following classes entirely (they are replaced by `CreativeOut`):
- `StaticCreativeOut`
- `StaticCreativeListResponse`
- `FbFormBannerResponse`

- [ ] **Step 5: Verify schemas import cleanly**

```bash
cd backend && python -c "from schemas import CreativeOut, ImageOut, GeneratedFields, UploadedFields, CreativeMetadata; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py
git commit -m "feat: add CreativeOut model and ImageOut alias, remove old creative schemas"
```

---

## Task 3: Update `db.py`

**Files:**
- Modify: `backend/db.py`

- [ ] **Step 1: Add `creatives` collection, remove `static_creatives`**

Replace the entire `db.py` content with:

```python
import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "revCreate")

_client: AsyncMongoClient | None = None
projects: AsyncCollection | None = None
images: AsyncCollection | None = None   # kept temporarily — pipeline + images router migrate away in later tasks
creatives: AsyncCollection | None = None
logs: AsyncCollection | None = None
api_tokens: AsyncCollection | None = None


async def connect() -> None:
    global _client, projects, images, creatives, logs, api_tokens
    _client = AsyncMongoClient(MONGO_URI)
    _db = _client[DB_NAME]
    projects = _db["projects"]
    images = _db["images"]        # legacy — remove after pipeline + images.py fully migrated
    creatives = _db["creatives"]
    logs = _db["logs"]
    api_tokens = _db["api_tokens"]


async def close() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def _out(doc: dict | None) -> dict | None:
    """Rename _id → id for API responses."""
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc
```

- [ ] **Step 2: Verify server starts**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: `MongoDB connected` in logs, no import errors.

- [ ] **Step 3: Commit**

```bash
git add backend/db.py
git commit -m "feat: add creatives collection to db, keep images for migration"
```

---

## Task 4: Update `routers/static_creatives.py`

**Files:**
- Modify: `backend/routers/static_creatives.py`

- [ ] **Step 1: Rewrite the router to use `db.creatives` and accept `subtype`**

Replace the entire file content:

```python
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import db
from schemas import CreativeOut, CreativeMetadata, SizeSpecs, UploadedFields, CreativeListResponse
from services.creative_registry import CreativeSubtype, CreativeSource, build_metadata
from services.s3 import upload_bytes, presign_url

router = APIRouter(prefix="/api/image/upload", tags=["image"])
logger = logging.getLogger("revCreate.static_creatives")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key", "")
    meta = doc.get("metadata", {})
    size = meta.get("size_specs", {})
    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", "uploaded"),
        metadata=CreativeMetadata(
            type=meta.get("type", "image"),
            subtype=meta.get("subtype", "feed-square"),
            size_specs=SizeSpecs(**size) if size else SizeSpecs(width=0, height=0, aspect_ratio="1:1", label=""),
        ),
        client_id=doc.get("client_id", "revspot"),
        project_id=doc.get("project_id"),
        name=doc.get("name"),
        status=doc.get("status", "uploaded"),
        s3_key=s3_key,
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        uploaded=UploadedFields(
            original_filename=doc.get("uploaded", {}).get("original_filename", ""),
            mime_type=doc.get("uploaded", {}).get("mime_type", "image/png"),
            campaign_tag=doc.get("uploaded", {}).get("campaign_tag", ""),
        ) if doc.get("uploaded") else None,
        created_at=doc["created_at"],
    )


@router.post("", response_model=list[CreativeOut])
async def upload_static_creatives(
    name: str = Form(...),
    client_id: str = Form(default="revspot"),
    campaign_tag: str = Form(default=""),
    subtype: CreativeSubtype = Form(...),
    files: List[UploadFile] = File(...),
):
    now = datetime.now(timezone.utc)
    created = []
    metadata = build_metadata(subtype)

    for upload in files:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{upload.content_type}' for '{upload.filename}'. Allowed: JPEG, PNG, WEBP.",
            )

        doc_id = str(uuid.uuid4())
        ext = MIME_TO_EXT.get(upload.content_type, "png")
        s3_key = f"creatives/{doc_id}.{ext}"

        data = await upload.read()
        await upload_bytes(s3_key, data, content_type=upload.content_type)

        doc = {
            "_id": doc_id,
            "source": CreativeSource.UPLOADED.value,
            "client_id": client_id,
            "project_id": None,
            "name": name,
            "status": "uploaded",
            "s3_key": s3_key,
            "error_message": None,
            "created_at": now,
            "metadata": metadata,
            "uploaded": {
                "original_filename": upload.filename or "",
                "mime_type": upload.content_type,
                "campaign_tag": campaign_tag,
            },
        }
        await db.creatives.insert_one(doc)
        created.append(_to_out(doc))
        logger.info("Creative uploaded — id=%s subtype=%s client=%s", doc_id, subtype.value, client_id)

    return created


@router.get("", response_model=list[CreativeOut])
async def list_uploaded_creatives(
    client_id: Optional[str] = None,
    campaign_tag: Optional[str] = None,
    subtype: Optional[CreativeSubtype] = None,
    page: int = 1,
    limit: int = 20,
):
    query: dict = {"source": CreativeSource.UPLOADED.value}
    if client_id:
        query["client_id"] = client_id
    if campaign_tag:
        query["uploaded.campaign_tag"] = campaign_tag
    if subtype:
        query["metadata.subtype"] = subtype.value

    skip = (page - 1) * limit
    cursor = db.creatives.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_to_out(d) for d in docs]


@router.get("/{creative_id}", response_model=CreativeOut)
async def get_uploaded_creative(creative_id: str):
    doc = await db.creatives.find_one({"_id": creative_id, "source": CreativeSource.UPLOADED.value})
    if not doc:
        raise HTTPException(status_code=404, detail="Creative not found")
    return _to_out(doc)


@router.delete("/{creative_id}", status_code=204)
async def delete_uploaded_creative(creative_id: str):
    doc = await db.creatives.find_one({"_id": creative_id, "source": CreativeSource.UPLOADED.value})
    if not doc:
        raise HTTPException(status_code=404, detail="Creative not found")
    await db.creatives.delete_one({"_id": creative_id})
    logger.info("Creative deleted — id=%s", creative_id)
```

- [ ] **Step 2: Verify server starts with no import errors**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: no errors. Check `GET /docs` — `/api/image/upload` should show the `subtype` enum field in the POST schema.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/static_creatives.py
git commit -m "feat: static_creatives router writes to creatives collection with subtype metadata"
```

---

## Task 5: Update `routers/fb_form_banner.py`

**Files:**
- Modify: `backend/routers/fb_form_banner.py`

- [ ] **Step 1: Rewrite the router to persist to `db.creatives` and return `CreativeOut`**

Replace the entire file content:

```python
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import db
from schemas import CreativeOut, CreativeMetadata, SizeSpecs, GeneratedFields
from services.creative_registry import CreativeSubtype, CreativeSource, build_metadata, get_size_specs
from services.image_model import generate_image
from services.prompt_builder_fb import build_fb_banner_prompt
from services.s3 import presign_url, upload_bytes

router = APIRouter(prefix="/api/image", tags=["image"])
logger = logging.getLogger("revCreate.fb_form_banner")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
FB_BANNER_FORMAT = "1200x444"


def _to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key", "")
    meta = doc.get("metadata", {})
    size = meta.get("size_specs", {})
    gen = doc.get("generated", {})
    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", "generated"),
        metadata=CreativeMetadata(
            type=meta.get("type", "image"),
            subtype=meta.get("subtype", "fb-banner"),
            size_specs=SizeSpecs(**size),
        ),
        client_id=doc.get("client_id", "revspot"),
        project_id=doc.get("project_id"),
        name=doc.get("name"),
        status=doc.get("status", "done"),
        s3_key=s3_key,
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=GeneratedFields(
            prompt_used=gen.get("prompt_used", ""),
            variation_index=gen.get("variation_index", 1),
            version=gen.get("version", 1),
            parent_id=gen.get("parent_id"),
            edit_instruction=gen.get("edit_instruction"),
        ) if gen else None,
        created_at=doc["created_at"],
    )


@router.post("/fb-banner", response_model=CreativeOut)
async def generate_fb_form_banner(
    product_name: str = Form(...),
    client_id: str = Form(default="revspot"),
    description: str = Form(default=""),
    brand_tagline: str = Form(default=""),
    cta_text: str = Form(default=""),
    color_scheme: str = Form(default=""),
    product_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
):
    product_image_data: list[tuple[bytes, str]] = []
    for upload in product_images:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{upload.content_type}'. Allowed: JPEG, PNG, WEBP.",
            )
        product_image_data.append((await upload.read(), upload.content_type))

    logo_image_data: list[tuple[bytes, str]] = []
    for upload in logo_images:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{upload.content_type}'. Allowed: JPEG, PNG, WEBP.",
            )
        logo_image_data.append((await upload.read(), upload.content_type))

    prompt = build_fb_banner_prompt(
        product_name=product_name,
        description=description,
        brand_tagline=brand_tagline,
        cta_text=cta_text,
        color_scheme=color_scheme,
        has_product_images=bool(product_image_data),
        has_logo_images=bool(logo_image_data),
    )
    logger.info("FB banner prompt built — product=%r length=%d", product_name, len(prompt))

    try:
        result = await generate_image(
            prompt=prompt,
            ad_format=FB_BANNER_FORMAT,
            product_images=product_image_data or None,
            logo_images=logo_image_data or None,
        )
    except Exception as e:
        logger.error("FB banner image generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

    banner_id = str(uuid.uuid4())
    s3_key = f"creatives/{banner_id}.png"
    img_bytes = base64.b64decode(result["image_base64"])
    await upload_bytes(s3_key, img_bytes)
    logger.info("FB banner uploaded — s3_key=%s", s3_key)

    now = datetime.now(timezone.utc)
    doc = {
        "_id": banner_id,
        "source": CreativeSource.GENERATED.value,
        "client_id": client_id,
        "project_id": None,
        "name": product_name,
        "status": "done",
        "s3_key": s3_key,
        "error_message": None,
        "created_at": now,
        "metadata": build_metadata(CreativeSubtype.FB_BANNER),
        "generated": {
            "prompt_used": prompt,
            "variation_index": 1,
            "version": 1,
            "parent_id": None,
            "edit_instruction": None,
        },
    }
    await db.creatives.insert_one(doc)
    return _to_out(doc)
```

- [ ] **Step 2: Verify server starts**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: no errors. `POST /api/image/fb-banner` visible in `/docs`.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/fb_form_banner.py
git commit -m "feat: fb_form_banner persists to creatives collection, returns CreativeOut"
```

---

## Task 6: Update `services/pipeline.py`

**Files:**
- Modify: `backend/services/pipeline.py`

- [ ] **Step 1: Add import for registry at top of pipeline.py**

Add after existing imports:

```python
from services.creative_registry import CreativeSource, build_metadata, subtype_from_ad_format
```

- [ ] **Step 2: Replace placeholder insertion block (step 4 in pipeline)**

Find this block (around line 131):

```python
        # ── 4. Create 4 image placeholder documents ───────────────────────────
        now = datetime.now(timezone.utc)
        image_ids = []
        for i in range(4):
            img_id = str(uuid.uuid4())
            await db.images.insert_one(
                {
                    "_id": img_id,
                    "project_id": project_id,
                    "parent_id": None,
                    "version": 1,
                    "variation_index": i + 1,
                    "image_base64": None,
                    "edit_instruction": None,
                    "status": "pending",
                    "error_message": None,
                    "created_at": now,
                }
            )
            image_ids.append(img_id)
```

Replace with:

```python
        # ── 4. Create 4 creative placeholder documents ────────────────────────
        now = datetime.now(timezone.utc)
        _subtype = subtype_from_ad_format(project["ad_format"])
        _metadata = build_metadata(_subtype)
        image_ids = []
        for i in range(4):
            img_id = str(uuid.uuid4())
            await db.creatives.insert_one(
                {
                    "_id": img_id,
                    "source": CreativeSource.GENERATED.value,
                    "client_id": project.get("client_id", "revspot"),
                    "project_id": project_id,
                    "name": None,
                    "status": "pending",
                    "s3_key": None,
                    "error_message": None,
                    "created_at": now,
                    "metadata": _metadata,
                    "generated": {
                        "prompt_used": None,
                        "variation_index": i + 1,
                        "version": 1,
                        "parent_id": None,
                        "edit_instruction": None,
                    },
                }
            )
            image_ids.append(img_id)
```

- [ ] **Step 3: Replace all `db.images` references inside `_gen_one`**

In the `_gen_one` inner function, replace:
- `await db.images.update_one({"_id": img_id}, {"$set": {"status": "generating"}})` → `await db.creatives.update_one(...)`
- `await db.images.update_one({"_id": img_id}, {"$set": {"status": "retrying"}})` → `await db.creatives.update_one(...)`
- The final success update:

```python
# REMOVE:
                s3_key = f"images/{img_id}.png"
                await upload_bytes(s3_key, img_bytes)
                await db.images.update_one(
                    {"_id": img_id},
                    {
                        "$set": {
                            "status": "done",
                            "image_s3_key": s3_key,
                        }
                    },
                )

# REPLACE WITH:
                s3_key = f"creatives/{img_id}.png"
                await upload_bytes(s3_key, img_bytes)
                await db.creatives.update_one(
                    {"_id": img_id},
                    {
                        "$set": {
                            "status": "done",
                            "s3_key": s3_key,
                            "generated.prompt_used": prompt,
                        }
                    },
                )
```

- The failure update:

```python
# REMOVE:
                await db.images.update_one(
                    {"_id": img_id},
                    {"$set": {"status": "failed", "error_message": str(e)}},
                )

# REPLACE WITH:
                await db.creatives.update_one(
                    {"_id": img_id},
                    {"$set": {"status": "failed", "error_message": str(e)}},
                )
```

- [ ] **Step 4: Update the project query that looks up images for the log**

In step 6 (log creation), images are referenced by `image_ids` list — no change needed there. But update any `db.images.find` calls to `db.creatives`.

Search for remaining `db.images` in pipeline.py and replace all with `db.creatives`.

- [ ] **Step 5: Verify server starts**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/services/pipeline.py
git commit -m "feat: pipeline writes creatives documents with full metadata to db.creatives"
```

---

## Task 7: Update `routers/images.py`

**Files:**
- Modify: `backend/routers/images.py`

- [ ] **Step 1: Update imports**

Replace:

```python
from schemas import EditImageRequest, ImageOut, SizeVariantRequest
```

With:

```python
from schemas import (
    CreativeOut, CreativeMetadata, SizeSpecs, GeneratedFields,
    EditImageRequest, SizeVariantRequest,
)
from services.creative_registry import (
    CreativeSubtype, CreativeSource, build_metadata, subtype_from_ad_format, get_size_specs,
)
```

- [ ] **Step 2: Replace `_to_out`**

Replace the existing `_to_out` function with:

```python
def _to_out(doc: dict) -> CreativeOut:
    # Support both old field name (image_s3_key) and new (s3_key)
    s3_key = doc.get("s3_key") or doc.get("image_s3_key") or ""
    meta = doc.get("metadata", {})
    size = meta.get("size_specs", {})

    # Legacy documents without metadata block — derive from stored fields
    if not meta:
        subtype = CreativeSubtype.FEED_SQUARE
        size_specs = get_size_specs(subtype)
        metadata = CreativeMetadata(type="image", subtype=subtype, size_specs=SizeSpecs(**size_specs))
    else:
        metadata = CreativeMetadata(
            type=meta.get("type", "image"),
            subtype=meta.get("subtype", "feed-square"),
            size_specs=SizeSpecs(**size) if size else SizeSpecs(**get_size_specs(CreativeSubtype.FEED_SQUARE)),
        )

    gen = doc.get("generated")
    if gen:
        generated = GeneratedFields(**gen)
    elif doc.get("variation_index") is not None:
        generated = GeneratedFields(
            prompt_used=doc.get("prompt_used", ""),
            variation_index=doc.get("variation_index", 1),
            version=doc.get("version", 1),
            parent_id=doc.get("parent_id"),
            edit_instruction=doc.get("edit_instruction"),
        )
    else:
        generated = None

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED.value),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        project_id=doc.get("project_id"),
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key,
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        platform=doc.get("platform"),
        is_size_variant=doc.get("is_size_variant", False),
        created_at=doc["created_at"],
    )
```

- [ ] **Step 3: Replace all `db.images` with `db.creatives` throughout the file**

Global replace in `routers/images.py`:
- `db.images.find_one` → `db.creatives.find_one`
- `db.images.insert_one` → `db.creatives.insert_one`
- `db.images.update_one` → `db.creatives.update_one`
- `db.images.delete_many` → `db.creatives.delete_many`

- [ ] **Step 4: Update S3 key pattern in `_run_edit` and `_run_size_variants`**

In `_run_edit`, replace:
```python
s3_key = f"images/{image_id}.png"
```
With:
```python
s3_key = f"creatives/{image_id}.png"
```

In `_run_size_variants`, replace:
```python
s3_key = f"images/{image_id}.png"
```
With:
```python
s3_key = f"creatives/{image_id}.png"
```

Also in `_run_size_variants`, update the insert document to use new field `s3_key` instead of `image_s3_key`, and add minimal metadata:

In `request_size_variants`, the new document inserted for each size variant should include:

```python
        for size_label, dimensions, aspect_ratio in sizes:
            new_id = str(uuid.uuid4())
            _subtype = subtype_from_ad_format(dimensions)
            await db.creatives.insert_one({
                "_id": new_id,
                "source": CreativeSource.GENERATED.value,
                "client_id": project.get("client_id", "revspot"),
                "project_id": parent["project_id"],
                "name": None,
                "s3_key": None,
                "status": "pending",
                "error_message": None,
                "platform": platform,
                "is_size_variant": True,
                "created_at": now,
                "metadata": build_metadata(_subtype),
                "generated": {
                    "prompt_used": None,
                    "variation_index": parent["generated"]["variation_index"] if parent.get("generated") else parent.get("variation_index", 1),
                    "version": parent["generated"]["version"] if parent.get("generated") else parent.get("version", 1),
                    "parent_id": parent["_id"],
                    "edit_instruction": None,
                },
            })
            new_entries.append((new_id, size_label, dimensions, aspect_ratio))
```

And in `_run_size_variants` success path, update from `image_s3_key` to `s3_key`:

```python
            await db.creatives.update_one(
                {"_id": image_id},
                {"$set": {
                    "status": "done",
                    "s3_key": s3_key,
                    "generated.prompt_used": prompt,
                }},
            )
```

- [ ] **Step 5: Update type hint on `download_image` endpoint**

The `download_image` endpoint currently reads `doc.get("image_s3_key")`. Update to:

```python
@router.get("/{image_id}/download")
async def download_image(image_id: str):
    doc = await db.creatives.find_one({"_id": image_id})
    if not doc or not (doc.get("s3_key") or doc.get("image_s3_key")):
        raise HTTPException(status_code=404, detail="Image not found")
    if doc["status"] != "done":
        raise HTTPException(status_code=400, detail="Image not ready")
    img_bytes = await download_bytes(doc.get("s3_key") or doc["image_s3_key"])
    return Response(content=img_bytes, media_type="image/png")
```

- [ ] **Step 6: Verify server starts and docs load**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: no errors. `GET /docs` loads without schema errors.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/images.py
git commit -m "feat: images router reads/writes db.creatives, _to_out returns CreativeOut"
```

---

## Task 8: Cleanup

**Files:**
- Modify: `backend/db.py` — remove legacy `images` registration
- Modify: `backend/routers/projects.py` — verify `images` field in `_project_out` still works

- [ ] **Step 1: Search for remaining `db.images` references**

```bash
cd backend && grep -rn "db\.images" .
```

Expected: zero results. If any remain, fix them before proceeding.

- [ ] **Step 2: Remove `images` collection from `db.py`**

In `db.py`, remove:
- `images: AsyncCollection | None = None` module-level declaration
- `images = _db["images"]` line in `connect()`
- The `# legacy` comment

- [ ] **Step 3: Verify `projects.py` `_project_out` helper still works**

The `_project_out` helper queries images by `project_id`. Find that query and update it to use `db.creatives`:

```bash
grep -n "db\.images\|project_id" backend/routers/projects.py | head -20
```

Update any `db.images.find({"project_id": ...})` to `db.creatives.find({"project_id": ...})`.

- [ ] **Step 4: Final server start verification**

```bash
cd backend && uvicorn main:app --port 8000 --reload
```

Expected: `MongoDB connected`, no import or runtime errors.

- [ ] **Step 5: Commit**

```bash
git add backend/db.py backend/routers/projects.py
git commit -m "chore: remove legacy images collection, finalize creatives migration"
```
