# Generate Endpoint & Creatives Association Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy generate routes with a unified `POST /api/image/generate` backed by a shared `run_pipeline_core`, and replace the `project_id` field on creatives with a typed `associations` array.

**Architecture:** `PipelineInputs` decouples the pipeline from the project document — both `run_pipeline` (project flow) and the new generate endpoint build a `PipelineInputs` and call `run_pipeline_core`, which returns a `PipelineResult`. Creatives gain an `associations: [{type, id}]` array; backward compatibility with legacy `project_id` documents is handled in the `_to_out` helpers without a bulk migration.

**Tech Stack:** FastAPI, Motor (async MongoDB), Pydantic v2, Python dataclasses, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/schemas.py` | Modify | Add `Association`, `GenerationOut`; update `CreativeOut` |
| `backend/services/pipeline.py` | Modify | Add `PipelineInputs`, `PipelineResult`, `run_pipeline_core`; thin wrapper |
| `backend/db.py` | Modify | Add associations compound index |
| `backend/routers/projects.py` | Modify | Backward compat + new association queries |
| `backend/routers/images.py` | Modify | `_to_out` + `request_edit` + `request_size_variants` |
| `backend/routers/static_creatives.py` | Modify | Remove `project_id`, add `associations` |
| `backend/routers/fb_form_banner.py` | Modify | Remove `project_id`, add `associations` |
| `backend/routers/generate.py` | Create | New `POST /api/image/generate` endpoint |
| `backend/main.py` | Modify | Swap `generate_v2_router` for new `generate_router` |
| `backend/routers/generate_v2.py` | Delete | Replaced by new generate.py |
| `frontend/src/types.ts` | Modify | Replace `project_id` with `associations` on `ImageOut` |
| `backend/tests/test_schemas.py` | Create | Unit tests for Association + backward compat |

---

## Task 1: Update `schemas.py` — Association, GenerationOut, CreativeOut

**Files:**
- Modify: `backend/schemas.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
import pytest
from datetime import datetime, timezone
from schemas import Association, CreativeOut, GenerationOut
from services.creative_registry import (
    CreativeType, CreativeSubtype, CreativeSource, SizeSpecs
)


def _make_creative_out(**kwargs):
    defaults = dict(
        id="abc",
        source=CreativeSource.GENERATED,
        metadata={
            "type": CreativeType.IMAGE,
            "subtype": CreativeSubtype.FEED_SQUARE,
            "size_specs": SizeSpecs(width=1080, height=1080, aspect_ratio="1:1", label="Feed Square"),
        },
        client_id="revspot",
        status="done",
        s3_key="creatives/abc.png",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return CreativeOut(**defaults)


def test_association_model():
    a = Association(type="project", id="proj-1")
    assert a.type == "project"
    assert a.id == "proj-1"


def test_creative_out_has_associations_not_project_id():
    c = _make_creative_out(associations=[Association(type="campaign", id="camp-1")])
    assert c.associations[0].type == "campaign"
    assert not hasattr(c, "project_id")


def test_creative_out_associations_defaults_to_empty():
    c = _make_creative_out()
    assert c.associations == []


def test_generation_out():
    c = _make_creative_out()
    g = GenerationOut(
        headline="Test",
        body_copy="Body",
        generated_cta="Click",
        image_prompt="prompt",
        images=[c],
    )
    assert len(g.images) == 1
    assert g.headline == "Test"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && python -m pytest tests/test_schemas.py -v
```

Expected: `ImportError` — `Association` and `GenerationOut` not yet defined.

- [ ] **Step 3: Update `schemas.py`**

Replace the existing `CreativeOut` class and add `Association` + `GenerationOut`. Find the `# ── Creative Model` section:

```python
# ── Creative Model ────────────────────────────────────────────────────────────

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

class Association(BaseModel):
    type: str   # "project" | "campaign" | "brand" | "client"
    id: str

class CreativeOut(BaseModel):
    id: str
    source: CreativeSource
    metadata: CreativeMetadata
    client_id: str
    associations: list[Association] = []
    name: Optional[str] = None
    status: str
    s3_key: str
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    generated: Optional[GeneratedFields] = None
    uploaded: Optional[UploadedFields] = None
    created_at: datetime

# Backward-compatibility alias
ImageOut = CreativeOut
```

Add `GenerationOut` in the `# ── API response shapes` section, after `ProjectOut`:

```python
class GenerationOut(BaseModel):
    headline: str
    body_copy: str
    generated_cta: str
    image_prompt: str
    images: list[CreativeOut]
```

- [ ] **Step 4: Create `backend/tests/__init__.py`** (empty file)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_schemas.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/tests/
git commit -m "feat: add Association model, GenerationOut, update CreativeOut"
```

---

## Task 2: Add `PipelineInputs` and `PipelineResult` to `pipeline.py`

**Files:**
- Modify: `backend/services/pipeline.py` (top section only — dataclasses only, no logic changes yet)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_schemas.py`:

```python
from services.pipeline import PipelineInputs, PipelineResult
from services.creative_registry import CreativeSubtype


def test_pipeline_inputs_defaults():
    inputs = PipelineInputs(
        product_name="Test Product",
        description="",
        ad_format="1080x1080",
        client_id="revspot",
        name="Test",
        product_images=[],
        ref_images=[],
        logo_images=[],
        associations=[],
    )
    assert inputs.count == 4
    assert inputs.subtype_override is None
    assert inputs.persona_info == ""
    assert inputs.creative_strategy == ""


def test_pipeline_inputs_subtype_override():
    inputs = PipelineInputs(
        product_name="X",
        description="",
        ad_format="1080x1080",
        client_id="revspot",
        name="X",
        product_images=[],
        ref_images=[],
        logo_images=[],
        associations=[],
        subtype_override=CreativeSubtype.FB_BANNER,
        count=1,
    )
    assert inputs.subtype_override == CreativeSubtype.FB_BANNER
    assert inputs.count == 1


def test_pipeline_result_fields():
    result = PipelineResult(
        creative_ids=["id1", "id2"],
        headline="Headline",
        body_copy="Body",
        generated_cta="CTA",
        image_prompt="prompt",
    )
    assert result.creative_ids == ["id1", "id2"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && python -m pytest tests/test_schemas.py::test_pipeline_inputs_defaults -v
```

Expected: `ImportError` — `PipelineInputs` not yet defined.

- [ ] **Step 3: Add dataclasses to the top of `pipeline.py`**

Add after the existing imports, before `logger = ...`:

```python
from dataclasses import dataclass, field
from typing import Optional

from services.creative_registry import CreativeSubtype


@dataclass
class PipelineInputs:
    product_name: str
    description: str
    ad_format: str
    client_id: str
    name: str
    product_images: list[tuple[bytes, str]]
    ref_images: list[tuple[bytes, str]]
    logo_images: list[tuple[bytes, str]]
    associations: list[dict]
    persona_info: str = ""
    creative_strategy: str = ""
    count: int = 4
    subtype_override: Optional[CreativeSubtype] = None


@dataclass
class PipelineResult:
    creative_ids: list[str]
    headline: str
    body_copy: str
    generated_cta: str
    image_prompt: str
```

Note: `pipeline.py` already imports `from services.creative_registry import CreativeType, CreativeSource, find_subtype_by_dimensions, get_size_specs` — add `CreativeSubtype` to that import line instead of a new import. Remove the `Optional` and `dataclass` imports from the block above and add them to the existing imports at the top of the file: `from dataclasses import dataclass, field` and `from typing import Optional`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_schemas.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/pipeline.py backend/tests/test_schemas.py
git commit -m "feat: add PipelineInputs and PipelineResult dataclasses"
```

---

## Task 3: Extract `run_pipeline_core` and refactor `run_pipeline`

**Files:**
- Modify: `backend/services/pipeline.py`

- [ ] **Step 1: Add `run_pipeline_core` function**

Add this new function before the existing `run_pipeline`. It contains all the generation logic extracted from the current `run_pipeline`, adapted to use `PipelineInputs`:

```python
async def run_pipeline_core(inputs: PipelineInputs) -> PipelineResult:
    """
    Core generation logic. Writes to db.creatives only.
    Does not touch db.projects or db.logs.
    Returns PipelineResult with copy fields and created creative IDs.
    """
    # ── 1. Extract brand info ─────────────────────────────────────────────────
    brand_info = await extract_brand_info(
        product_name=inputs.product_name,
        description=inputs.description,
    )

    # ── 2. Generate copy ──────────────────────────────────────────────────────
    copy_system_prompt = build_copy_system_prompt_v2(
        has_ref_images=bool(inputs.ref_images),
        has_logo_images=bool(inputs.logo_images),
        persona_info=inputs.persona_info,
        creative_strategy=inputs.creative_strategy,
    )
    user_brief = build_user_brief_v2(
        product_name=inputs.product_name,
        description=inputs.description,
        ad_format=inputs.ad_format,
        has_product_images=bool(inputs.product_images),
        has_logo_images=bool(inputs.logo_images),
        brand_info=brand_info,
        persona_info=inputs.persona_info,
        creative_strategy=inputs.creative_strategy,
    )
    ad_copy_only, copy_usage = generate_copy(
        system_prompt=copy_system_prompt,
        user_brief=user_brief,
        ref_images=inputs.ref_images or None,
    )
    logger.info("Copy generated — headline=%r", ad_copy_only.headline)

    # ── 3. Generate image prompt ──────────────────────────────────────────────
    img_prompt_system = build_image_prompt_system_prompt_v2(
        has_ref_images=bool(inputs.ref_images),
        has_logo_images=bool(inputs.logo_images),
        has_product_images=bool(inputs.product_images),
        persona_info=inputs.persona_info,
        creative_strategy=inputs.creative_strategy,
    )
    img_prompt_brief = build_image_prompt_brief(
        headline=ad_copy_only.headline,
        body_copy=ad_copy_only.body_copy,
        cta=ad_copy_only.cta,
        ad_format=inputs.ad_format,
        has_product_images=bool(inputs.product_images),
        has_logo_images=bool(inputs.logo_images),
        has_ref_images=bool(inputs.ref_images),
        brand_info=brand_info,
    )
    img_prompt_result, ip_usage = generate_image_prompt(
        system_prompt=img_prompt_system,
        brief=img_prompt_brief,
        product_images=inputs.product_images or None,
        ref_images=inputs.ref_images or None,
        logo_images=inputs.logo_images or None,
    )
    logger.info("Image prompt generated — length=%d", len(img_prompt_result.image_prompt))

    # ── 4. Determine subtype ──────────────────────────────────────────────────
    subtype = inputs.subtype_override or find_subtype_by_dimensions(inputs.ad_format)
    size_specs = get_size_specs(subtype)

    # ── 5. Create creative placeholder documents ──────────────────────────────
    now = datetime.now(timezone.utc)
    image_ids = []
    for i in range(inputs.count):
        img_id = str(uuid.uuid4())
        await db.creatives.insert_one(
            {
                "_id": img_id,
                "source": CreativeSource.GENERATED,
                "client_id": inputs.client_id,
                "associations": inputs.associations,
                "name": f"{inputs.name} Var {i+1}",
                "status": "pending",
                "s3_key": f"creatives/{img_id}.png",
                "error_message": None,
                "created_at": now,
                "metadata": {
                    "type": CreativeType.IMAGE,
                    "subtype": subtype,
                    "size_specs": size_specs.model_dump(),
                },
                "generated": {
                    "prompt_used": img_prompt_result.image_prompt,
                    "variation_index": i + 1,
                    "version": 1,
                    "parent_id": None,
                    "edit_instruction": None,
                },
            }
        )
        image_ids.append(img_id)

    # ── 6. Generate images concurrently ──────────────────────────────────────
    image_token_log: list[dict] = []

    async def _gen_one(img_id: str, variation_index: int) -> None:
        await db.creatives.update_one({"_id": img_id}, {"$set": {"status": "generating"}})
        # Apply variation hints only when generating 4 images
        hint = _VARIATION_HINTS[variation_index - 1] if inputs.count == 4 else ""
        prompt = img_prompt_result.image_prompt + hint

        async def _before_sleep(retry_state) -> None:
            logger.warning(
                "Retrying variation %d (attempt %d) — %s",
                variation_index,
                retry_state.attempt_number,
                retry_state.outcome.exception(),
            )
            await db.creatives.update_one({"_id": img_id}, {"$set": {"status": "retrying"}})

        try:
            result = None
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                before_sleep=_before_sleep,
                reraise=True,
            ):
                with attempt:
                    result = await generate_image(
                        prompt=prompt,
                        ad_format=inputs.ad_format,
                        product_images=inputs.product_images or None,
                        ref_images=inputs.ref_images or None,
                        logo_images=inputs.logo_images or None,
                    )
            img_bytes = base64.b64decode(result["image_base64"])
            s3_key = f"creatives/{img_id}.png"
            await upload_bytes(s3_key, img_bytes)
            await db.creatives.update_one({"_id": img_id}, {"$set": {"status": "done"}})
            image_token_log.append({
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            })
            logger.info("Variation %d done", variation_index)
        except Exception as e:
            logger.error("Variation %d failed — %s", variation_index, e)
            await db.creatives.update_one(
                {"_id": img_id},
                {"$set": {"status": "failed", "error_message": str(e)}},
            )

    await asyncio.gather(*[_gen_one(img_id, i + 1) for i, img_id in enumerate(image_ids)])

    # ── 7. Cost summary ───────────────────────────────────────────────────────
    _COPY_IN  = 0.10 / 1_000_000
    _COPY_OUT = 0.40 / 1_000_000
    _IMG_IN   = 0.50 / 1_000_000
    _IMG_OUT  = 60.0 / 1_000_000

    copy_cost = copy_usage["input_tokens"] * _COPY_IN + copy_usage["output_tokens"] * _COPY_OUT
    ip_cost   = ip_usage["input_tokens"]   * _COPY_IN + ip_usage["output_tokens"]   * _COPY_OUT
    img_in    = sum(t["input_tokens"]  for t in image_token_log)
    img_out   = sum(t["output_tokens"] for t in image_token_log)
    img_cost  = img_in * _IMG_IN + img_out * _IMG_OUT
    logger.info(
        "COST copy=$%.4f img_prompt=$%.4f images(%d)=$%.4f TOTAL=$%.4f",
        copy_cost, ip_cost, len(image_token_log), img_cost,
        copy_cost + ip_cost + img_cost,
    )

    return PipelineResult(
        creative_ids=image_ids,
        headline=ad_copy_only.headline,
        body_copy=ad_copy_only.body_copy,
        generated_cta=ad_copy_only.cta,
        image_prompt=img_prompt_result.image_prompt,
    )
```

- [ ] **Step 2: Update the imports at the top of `pipeline.py`**

Add `build_copy_system_prompt_v2`, `build_image_prompt_system_prompt_v2`, `build_user_brief_v2` to imports:

```python
from services.prompt_builder import (
    build_image_prompt_brief,
)
from services.prompt_builder_v2 import (
    build_copy_system_prompt_v2,
    build_image_prompt_system_prompt_v2,
    build_user_brief_v2,
)
```

Remove the old prompt builder imports: `build_copy_system_prompt`, `build_image_prompt_system_prompt`, `build_user_brief` (these are now only called from prompt_builder_v2 internally).

Add `CreativeSubtype` to the creative_registry import line:
```python
from services.creative_registry import CreativeType, CreativeSource, CreativeSubtype, find_subtype_by_dimensions, get_size_specs
```

Add at the top with other stdlib imports:
```python
from dataclasses import dataclass
from typing import Optional
```

- [ ] **Step 3: Replace `run_pipeline` with a thin wrapper**

Replace the entire existing `run_pipeline` function with:

```python
async def run_pipeline(project_id: str) -> None:
    logger.info("Pipeline started — project=%s", project_id)
    try:
        project = await db.projects.find_one({"_id": project_id})
        if not project:
            logger.error("Project not found: %s", project_id)
            return

        ref_image_data: list[tuple[bytes, str]] = [
            (await download_bytes(r["s3_key"]), r["mime_type"])
            for r in project.get("ref_images", [])
        ]
        product_image_data: list[tuple[bytes, str]] = [
            (await download_bytes(r["s3_key"]), r["mime_type"])
            for r in project.get("product_images", [])
        ]
        logo_image_data: list[tuple[bytes, str]] = [
            (await download_bytes(r["s3_key"]), r["mime_type"])
            for r in project.get("logo_images", [])
        ]

        inputs = PipelineInputs(
            product_name=project["product_name"],
            description=project.get("description", ""),
            ad_format=project["ad_format"],
            client_id=project.get("client_id", "revspot"),
            name=project.get("name", project_id),
            product_images=product_image_data,
            ref_images=ref_image_data,
            logo_images=logo_image_data,
            associations=[{"type": "project", "id": project_id}],
            count=4,
        )

        await db.projects.update_one(
            {"_id": project_id}, {"$set": {"status": "generating_copy"}}
        )
        result = await run_pipeline_core(inputs)

        # Check if user stopped the project while pipeline was running
        final = await db.projects.find_one({"_id": project_id}, {"status": 1})
        if final and final.get("status") != "stopped":
            await db.projects.update_one(
                {"_id": project_id},
                {
                    "$set": {
                        "headline": result.headline,
                        "body_copy": result.body_copy,
                        "generated_cta": result.generated_cta,
                        "image_prompt": result.image_prompt,
                        "status": "ready",
                    }
                },
            )
        logger.info("Pipeline complete — project=%s", project_id)

    except Exception as e:
        logger.error("Pipeline failed — project=%s error=%s", project_id, e)
        await db.projects.update_one(
            {"_id": project_id},
            {"$set": {"status": "failed", "error_message": str(e)}},
        )
```

- [ ] **Step 4: Verify the server starts cleanly**

```bash
cd backend && python -c "from services.pipeline import run_pipeline, run_pipeline_core, PipelineInputs, PipelineResult; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/services/pipeline.py
git commit -m "refactor: extract run_pipeline_core, add PipelineInputs/PipelineResult, remove log writes"
```

---

## Task 4: Add associations index to `db.py`

**Files:**
- Modify: `backend/db.py`

- [ ] **Step 1: Add index creation to `connect()`**

```python
async def connect() -> None:
    global _client, projects, creatives, images, logs, api_tokens
    _client = AsyncMongoClient(MONGO_URI)
    _db = _client[DB_NAME]
    projects = _db["projects"]
    creatives = _db["creatives"]
    images = _db["images"]  # Keep temporarily for migration
    logs = _db["logs"]
    api_tokens = _db["api_tokens"]
    # Compound index for association queries:
    # find({"associations": {"$elemMatch": {"type": "campaign", "id": X}}})
    await creatives.create_index(
        [("associations.type", 1), ("associations.id", 1)],
        name="associations_type_id",
    )
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "import db; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/db.py
git commit -m "feat: add associations compound index to creatives collection"
```

---

## Task 5: Update `routers/projects.py` for associations

**Files:**
- Modify: `backend/routers/projects.py`

- [ ] **Step 1: Update `_img_doc_to_out` to synthesize `associations` from legacy `project_id`**

Replace the existing `_img_doc_to_out` function:

```python
def _img_doc_to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key")
    if "image_s3_key" in doc and not s3_key:
        s3_key = doc["image_s3_key"]

    generated = doc.get("generated")
    if not generated and "variation_index" in doc:
        generated = {
            "prompt_used": doc.get("image_prompt", ""),
            "variation_index": doc.get("variation_index", 1),
            "version": doc.get("version", 1),
            "parent_id": doc.get("parent_id"),
            "edit_instruction": doc.get("edit_instruction"),
        }

    metadata = doc.get("metadata")
    if not metadata:
        dims = doc.get("size_dimensions") or "1080x1080"
        subtype = find_subtype_by_dimensions(dims)
        specs = get_size_specs(subtype)
        metadata = {
            "type": CreativeType.IMAGE,
            "subtype": subtype,
            "size_specs": specs.model_dump(),
        }

    # Backward compat: synthesize associations from legacy project_id field
    associations = doc.get("associations")
    if associations is None:
        project_id = doc.get("project_id")
        associations = [{"type": "project", "id": project_id}] if project_id else []

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        associations=associations,
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key or "",
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        uploaded=doc.get("uploaded"),
        created_at=doc["created_at"],
    )
```

Add `Association` to the schemas import line:
```python
from schemas import BrandInfo, ImageOut, CreativeOut, Association, ProjectListResponse, ProjectOut, ProjectSummary
```

- [ ] **Step 2: Update `_project_out` to query by associations**

Replace the `imgs = await db.creatives.find(...)` line inside `_project_out`:

```python
imgs = await db.creatives.find(
    {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
).to_list()
```

- [ ] **Step 3: Update `stop_project` to use associations query**

Replace the `db.creatives.update_many` call in `stop_project`:

```python
await db.creatives.update_many(
    {
        "associations": {"$elemMatch": {"type": "project", "id": project_id}},
        "status": {"$in": ["pending", "generating", "retrying"]},
    },
    {"$set": {"status": "failed", "error_message": "Stopped by user"}},
)
```

- [ ] **Step 4: Update `regenerate_project` to use associations query**

Replace the `db.creatives.delete_many` call in `regenerate_project`:

```python
await db.creatives.delete_many(
    {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
)
```

- [ ] **Step 5: Update `delete_project` to use associations query**

Replace the `db.creatives.delete_many` call in `delete_project`:

```python
await db.creatives.delete_many(
    {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
)
```

- [ ] **Step 6: Update `download_project` to use associations query**

Replace `query = {"project_id": project_id, "status": "done"}` in `download_project`:

```python
query = {
    "associations": {"$elemMatch": {"type": "project", "id": project_id}},
    "status": "done",
}
```

Also update the count queries in `list_projects`:

```python
image_total = await db.creatives.count_documents(
    {"associations": {"$elemMatch": {"type": "project", "id": pid}}}
)
done = await db.creatives.count_documents(
    {"associations": {"$elemMatch": {"type": "project", "id": pid}}, "status": "done"}
)
```

- [ ] **Step 7: Verify import**

```bash
cd backend && python -c "from routers.projects import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/routers/projects.py
git commit -m "feat: update projects router to use associations array instead of project_id"
```

---

## Task 6: Update `routers/images.py` for associations

**Files:**
- Modify: `backend/routers/images.py`

- [ ] **Step 1: Update `_to_out` helper**

Replace the existing `_to_out` function:

```python
def _to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key")
    if "image_s3_key" in doc and not s3_key:
        s3_key = doc["image_s3_key"]

    generated = doc.get("generated")
    if not generated and "variation_index" in doc:
        generated = {
            "prompt_used": doc.get("image_prompt", ""),
            "variation_index": doc.get("variation_index", 1),
            "version": doc.get("version", 1),
            "parent_id": doc.get("parent_id"),
            "edit_instruction": doc.get("edit_instruction"),
        }

    metadata = doc.get("metadata")
    if not metadata:
        dims = doc.get("size_dimensions") or "1080x1080"
        subtype = find_subtype_by_dimensions(dims)
        specs = get_size_specs(subtype)
        metadata = {
            "type": CreativeType.IMAGE,
            "subtype": subtype,
            "size_specs": specs.model_dump(),
        }

    # Backward compat: synthesize associations from legacy project_id field
    associations = doc.get("associations")
    if associations is None:
        project_id = doc.get("project_id")
        associations = [{"type": "project", "id": project_id}] if project_id else []

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        associations=associations,
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key or "",
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        uploaded=doc.get("uploaded"),
        created_at=doc["created_at"],
    )
```

- [ ] **Step 2: Update `request_edit` to propagate `associations`**

Replace the `db.creatives.insert_one` call inside `request_edit`:

```python
await db.creatives.insert_one(
    {
        "_id": new_id,
        "source": CreativeSource.GENERATED,
        "client_id": parent.get("client_id", "revspot"),
        "associations": parent.get("associations", []),
        "name": f"{parent.get('name', 'Creative')} (Edit)",
        "status": "pending",
        "s3_key": f"creatives/{new_id}.png",
        "error_message": None,
        "created_at": now,
        "metadata": parent.get("metadata"),
        "generated": {
            "prompt_used": parent_gen.get("prompt_used", ""),
            "variation_index": variation_index,
            "version": version,
            "parent_id": image_id,
            "edit_instruction": body.instruction,
        },
    }
)
```

Replace the `background_tasks.add_task` call (remove the `parent["project_id"]` argument):

```python
background_tasks.add_task(
    _run_edit,
    new_id,
    s3_key,
    body.instruction,
)
```

- [ ] **Step 3: Update `_run_edit` signature — remove `project_id`**

```python
async def _run_edit(
    image_id: str, parent_s3_key: str, instruction: str
) -> None:
    await db.creatives.update_one({"_id": image_id}, {"$set": {"status": "generating"}})
    img_bytes = await download_bytes(parent_s3_key)

    async def _before_sleep(retry_state) -> None:
        logger.warning(
            "Retrying edit (attempt %d) — image=%s error=%s",
            retry_state.attempt_number,
            image_id,
            retry_state.outcome.exception(),
        )
        await db.creatives.update_one({"_id": image_id}, {"$set": {"status": "retrying"}})

    try:
        result = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            before_sleep=_before_sleep,
            reraise=True,
        ):
            with attempt:
                result = await edit_image(image_bytes=img_bytes, instruction=instruction)
        edited_bytes = base64.b64decode(result["image_base64"])
        s3_key = f"creatives/{image_id}.png"
        await upload_bytes(s3_key, edited_bytes)
        await db.creatives.update_one(
            {"_id": image_id},
            {"$set": {"status": "done"}},
        )
        logger.info("Edit done — image=%s", image_id)
    except Exception as e:
        logger.error("Edit failed — image=%s error=%s", image_id, e)
        await db.creatives.update_one(
            {"_id": image_id},
            {"$set": {"status": "failed", "error_message": str(e)}},
        )
```

- [ ] **Step 4: Update `request_size_variants` to use associations**

Replace the project lookup:

```python
# Look up project via associations for fetching input images
project_assoc = next(
    (a for a in parent.get("associations", []) if a.get("type") == "project"),
    None,
)
if not project_assoc:
    raise HTTPException(
        status_code=400,
        detail="Size variants require a project-originated creative (no project association found)",
    )
project = await db.projects.find_one({"_id": project_assoc["id"]})
if not project:
    raise HTTPException(status_code=404, detail="Project not found")
```

Replace the two `db.creatives.insert_one` calls inside the loop to use `associations` instead of `project_id`:

```python
await db.creatives.insert_one({
    "_id": new_id,
    "source": CreativeSource.GENERATED,
    "client_id": parent.get("client_id", "revspot"),
    "associations": parent.get("associations", []),
    "name": f"{parent.get('name', 'Creative')} ({size_label})",
    "status": "pending",
    "s3_key": f"creatives/{new_id}.png",
    "error_message": None,
    "created_at": now,
    "metadata": {
        "type": CreativeType.IMAGE,
        "subtype": subtype,
        "size_specs": size_specs.model_dump(),
        "platform": platform,
        "size_label": size_label,
    },
    "generated": {
        "prompt_used": parent_gen.get("prompt_used", ""),
        "variation_index": variation_index,
        "version": version,
        "parent_id": image_id,
        "edit_instruction": None,
    },
})
```

Update the `background_tasks.add_task` call — replace `parent["project_id"]` with `project_assoc["id"]`:

```python
background_tasks.add_task(
    _run_size_variants,
    new_entries,
    parent_s3_key,
    project.get("image_prompt", ""),
    platform,
    project_assoc["id"],
    product_image_data,
    ref_image_data,
    logo_image_data,
)
```

- [ ] **Step 5: Verify import**

```bash
cd backend && python -c "from routers.images import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/routers/images.py
git commit -m "feat: update images router to use associations instead of project_id"
```

---

## Task 7: Update `static_creatives.py` and `fb_form_banner.py`

**Files:**
- Modify: `backend/routers/static_creatives.py`
- Modify: `backend/routers/fb_form_banner.py`

- [ ] **Step 1: Update `static_creatives.py` — `_to_out` helper**

Replace `_to_out` in `static_creatives.py`:

```python
def _to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key", "")
    associations = doc.get("associations", [])
    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.UPLOADED),
        metadata=doc["metadata"],
        client_id=doc.get("client_id", "revspot"),
        associations=associations,
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key,
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        uploaded=doc.get("uploaded"),
        created_at=doc["created_at"],
    )
```

- [ ] **Step 2: Update `upload_static_creatives` — replace `project_id` with `associations`**

In the `doc = {...}` dict inside `upload_static_creatives`, replace `"project_id": None` with `"associations": []`.

Remove `CreativeSource, CreativeType, CreativeSubtype` from `schemas` import if they are no longer needed there (they come from `services.creative_registry` already). Keep only what's actually used.

- [ ] **Step 3: Update `fb_form_banner.py` — replace `project_id` with `associations`**

In the `doc = {...}` dict inside `generate_fb_form_banner`, replace `"project_id": None` with `"associations": []`.

Update the `CreativeOut(...)` return at the bottom to remove `project_id` and add nothing (since `associations` defaults to `[]` in the schema):

```python
return CreativeOut(
    id=banner_id,
    source=CreativeSource.GENERATED,
    metadata=doc["metadata"],
    client_id=doc["client_id"],
    associations=[],
    name=doc["name"],
    status=doc["status"],
    s3_key=s3_key,
    image_url=presign_url(s3_key),
    generated=doc["generated"],
    created_at=now,
)
```

- [ ] **Step 4: Verify both imports**

```bash
cd backend && python -c "from routers.static_creatives import router; from routers.fb_form_banner import router as r2; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/static_creatives.py backend/routers/fb_form_banner.py
git commit -m "feat: update static_creatives and fb_form_banner to use associations"
```

---

## Task 8: Create `routers/generate.py` — `POST /api/image/generate`

**Files:**
- Create: `backend/routers/generate.py`

- [ ] **Step 1: Write the file**

```python
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends

from auth import require_api_key
import db
from schemas import GenerationOut, CreativeOut, Association
from services.creative_registry import CreativeSubtype, CreativeSource, get_size_specs
from services.pipeline import PipelineInputs, run_pipeline_core
from services.s3 import presign_url

router = APIRouter(prefix="/api/image", tags=["image"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger("revCreate.generate")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _doc_to_creative_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key", "")
    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=doc["metadata"],
        client_id=doc.get("client_id", "revspot"),
        associations=[Association(**a) for a in doc.get("associations", [])],
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key,
        image_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=doc.get("generated"),
        uploaded=doc.get("uploaded"),
        created_at=doc["created_at"],
    )


@router.post("/generate", response_model=GenerationOut)
async def generate(
    product_name: str = Form(...),
    description: str = Form(default=""),
    ad_format: str = Form(default="1080x1080"),
    subtype: Optional[CreativeSubtype] = Form(default=None),
    count: int = Form(default=4),
    client_id: str = Form(default="revspot"),
    persona_info: str = Form(default=""),
    creative_strategy: str = Form(default=""),
    product_images: List[UploadFile] = File(default=[]),
    ref_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
):
    """
    Generate ad creatives (4 by default, or 1) without creating a project.
    Synchronous — blocks until all images are done (~30-60s for 4 images).
    Generated creatives have empty associations; attach to campaigns/brands via
    separate API calls after creation.
    """
    if count not in (1, 4):
        raise HTTPException(status_code=400, detail="count must be 1 or 4")

    async def _read_images(uploads: List[UploadFile]) -> list[tuple[bytes, str]]:
        result = []
        for upload in uploads:
            if upload.filename and upload.content_type in ALLOWED_IMAGE_TYPES:
                result.append((await upload.read(), upload.content_type))
        return result

    product_image_data = await _read_images(product_images)
    ref_image_data = await _read_images(ref_images)
    logo_image_data = await _read_images(logo_images)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    name = f"{product_name} — {now.strftime('%b %d, %H:%M')}"

    inputs = PipelineInputs(
        product_name=product_name,
        description=description,
        ad_format=ad_format,
        client_id=client_id,
        name=name,
        product_images=product_image_data,
        ref_images=ref_image_data,
        logo_images=logo_image_data,
        associations=[],
        persona_info=persona_info,
        creative_strategy=creative_strategy,
        count=count,
        subtype_override=subtype,
    )

    logger.info(
        "Standalone generate — product=%r format=%s count=%d subtype=%s",
        product_name, ad_format, count, subtype,
    )

    try:
        result = await run_pipeline_core(inputs)
    except Exception as e:
        logger.error("Standalone generate failed — %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    docs = [await db.creatives.find_one({"_id": cid}) for cid in result.creative_ids]
    images = [_doc_to_creative_out(d) for d in docs if d]

    return GenerationOut(
        headline=result.headline,
        body_copy=result.body_copy,
        generated_cta=result.generated_cta,
        image_prompt=result.image_prompt,
        images=images,
    )
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "from routers.generate import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/routers/generate.py
git commit -m "feat: add POST /api/image/generate endpoint backed by run_pipeline_core"
```

---

## Task 9: Update `main.py` — swap routers

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Swap `generate_v2_router` for new `generate_router`**

Replace:
```python
from routers.generate_v2 import router as generate_v2_router
```
With:
```python
from routers.generate import router as generate_router
```

Replace:
```python
app.include_router(generate_v2_router)
```
With:
```python
app.include_router(generate_router)
```

- [ ] **Step 2: Verify the app loads**

```bash
cd backend && python -c "import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: register new generate router, remove generate_v2 router"
```

---

## Task 10: Delete dead files

**Files:**
- Delete: `backend/routers/generate_v2.py`
- Delete: `backend/routers/generate.py` (old, synchronous, not-imported version — if it exists as a pre-existing legacy file distinct from the new one you just created)

> **Note:** The new `routers/generate.py` was created in Task 8. The file to delete here is the **old** `routers/generate_v2.py`. If there was a pre-existing `routers/generate.py` before Task 8, that was already overwritten. Nothing extra to delete unless `generate_v2.py` still exists.

- [ ] **Step 1: Delete `generate_v2.py`**

```bash
git rm backend/routers/generate_v2.py
```

- [ ] **Step 2: Verify no remaining imports**

```bash
cd backend && grep -r "generate_v2" . --include="*.py"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: delete generate_v2.py (replaced by routers/generate.py)"
```

---

## Task 11: Update `frontend/src/types.ts`

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Find and update `ImageOut` / creative type**

Open `frontend/src/types.ts` and find the `ImageOut` or equivalent interface. Replace `project_id` with `associations`:

```typescript
export interface Association {
  type: string;  // "project" | "campaign" | "brand" | "client"
  id: string;
}

export interface ImageOut {
  id: string;
  source: string;
  metadata: CreativeMetadata;
  client_id: string;
  associations: Association[];  // replaces project_id
  name?: string;
  status: string;
  s3_key: string;
  image_url?: string;
  error_message?: string;
  generated?: GeneratedFields;
  uploaded?: UploadedFields;
  created_at: string;
}
```

Also add a `GenerationOut` interface if the frontend will consume the new generate endpoint:

```typescript
export interface GenerationOut {
  headline: string;
  body_copy: string;
  generated_cta: string;
  image_prompt: string;
  images: ImageOut[];
}
```

- [ ] **Step 2: Fix any references to `project_id` on `ImageOut` in components**

```bash
cd frontend && grep -r "project_id" src/ --include="*.tsx" --include="*.ts"
```

For each occurrence on a `ImageOut`/creative object, either remove it or replace with an associations lookup:
```typescript
// Old:
creative.project_id
// New (get project association id):
creative.associations.find(a => a.type === "project")?.id
```

- [ ] **Step 3: TypeScript build check**

```bash
cd frontend && npm run build
```

Expected: no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/
git commit -m "feat: update frontend types — replace project_id with associations on ImageOut"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Replace `project_id` with `associations` array | Tasks 1, 5, 6, 7 |
| `client_id` stays top-level | Tasks 1, 6, 7, 8 — `client_id` unchanged |
| Backward compat via `_img_doc_to_out` helper | Tasks 5, 6 |
| MongoDB compound index | Task 4 |
| `PipelineInputs` dataclass | Task 2 |
| `PipelineResult` dataclass | Task 2 |
| `run_pipeline_core` | Task 3 |
| `run_pipeline` thin wrapper | Task 3 |
| Remove log writes | Task 3 — `db.logs` write removed |
| `persona_info` / `creative_strategy` in prompt builders | Task 3 — uses v2 prompt builders |
| `subtype_override` in pipeline | Tasks 2, 3 |
| `count` param (1 or 4) | Tasks 2, 3, 8 |
| Variation hints only when count=4 | Task 3 |
| `POST /api/image/generate` endpoint | Task 8 |
| Delete `generate_v2.py` | Task 10 |
| Update `main.py` | Task 9 |
| Frontend `types.ts` update | Task 11 |
| `project_id` field removed from generate endpoint response | Task 8 — `GenerationOut` has no `project_id` |
