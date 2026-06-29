# Generate Endpoint & Creatives Association Model Design

**Date:** 2026-04-07
**Branch:** feat/godrej-mvp
**Status:** Approved

---

## Problem

Three issues converge:

1. `routers/generate.py` and `routers/generate_v2.py` duplicate pipeline logic outside of `run_pipeline`, including copy generation, image prompt generation, and image generation — with no retry logic, no DB persistence, no cost logging. They are dead weight.

2. `run_pipeline` is the correct ground truth for image generation but is tightly coupled to a project document. Standalone generation (not tied to a project) has no clean path through it.

3. The `creatives` collection uses a single `project_id` field for association. Creatives need to belong to multiple entities — campaigns, brands, clients, projects — and the current model cannot express this.

---

## Decision

1. Replace both generate routes with a single `POST /api/image/generate` endpoint backed by a shared `run_pipeline_core` function.
2. Refactor `run_pipeline` into a thin wrapper over `run_pipeline_core`, which accepts a `PipelineInputs` dataclass.
3. Replace `project_id` on creatives with a typed `associations` array.
4. Disconnect pipeline log writes — logs will be replaced by self-hosted Langfuse later.

---

## Association Model

### Creatives document (diff from current)

`project_id` is removed. A typed `associations` array replaces it.

```json
{
  "_id": "uuid",
  "source": "generated | uploaded",
  "client_id": "revspot",
  "associations": [
    {"type": "project",  "id": "project-uuid"},
    {"type": "campaign", "id": "campaign-uuid"},
    {"type": "brand",    "id": "brand-uuid"}
  ],
  "name": "...",
  "status": "...",
  ...
}
```

Rules:
- `client_id` stays top-level — it is on nearly every query and belongs at the root.
- A creative with an empty `associations` array is valid (standalone generate, not yet attached to any entity).
- Pipeline-generated creatives get `{"type": "project", "id": project_id}` in `associations` at creation time.
- Associations are append-only at creation for the pipeline. Attaching/detaching to campaigns or brands is handled by separate API calls (out of scope for this spec).
- No bulk migration script. The `_img_doc_to_out` helper synthesizes `associations` from the legacy `project_id` field when the array is absent.

### MongoDB index

```python
db.creatives.create_index([("associations.type", 1), ("associations.id", 1)])
```

Covers: `find({"associations": {"$elemMatch": {"type": "campaign", "id": X}}})`

### Pydantic schema

```python
class Association(BaseModel):
    type: str   # "project" | "campaign" | "brand" | "client"
    id: str

class CreativeOut(BaseModel):
    id: str
    source: CreativeSource
    metadata: CreativeMetadata
    client_id: str
    associations: list[Association] = []   # replaces project_id
    name: Optional[str] = None
    status: str
    s3_key: str
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    generated: Optional[GeneratedFields] = None
    uploaded: Optional[UploadedFields] = None
    created_at: datetime
```

---

## Pipeline Redesign

### `PipelineInputs` dataclass

Defined in `services/pipeline.py`.

```python
@dataclass
class PipelineInputs:
    product_name: str
    description: str
    ad_format: str
    client_id: str
    name: str                                      # used to name generated creatives
    product_images: list[tuple[bytes, str]]        # (raw bytes, mime_type)
    ref_images: list[tuple[bytes, str]]
    logo_images: list[tuple[bytes, str]]
    associations: list[dict]                       # e.g. [{"type": "project", "id": "..."}]
    persona_info: str = ""
    creative_strategy: str = ""
    count: int = 4                                 # 1 or 4
    subtype_override: Optional[CreativeSubtype] = None
```

### `PipelineResult` dataclass

```python
@dataclass
class PipelineResult:
    creative_ids: list[str]
    headline: str
    body_copy: str
    generated_cta: str
    image_prompt: str
```

Returned by `run_pipeline_core`. The `run_pipeline` wrapper uses `headline`, `body_copy`, `generated_cta`, `image_prompt` to update the project doc. The `image/generate` endpoint uses them to populate `GenerationOut`.

### `run_pipeline_core(inputs: PipelineInputs) -> PipelineResult`

New internal async function. Contains all generation logic currently in `run_pipeline`:

1. Extract brand info
2. Generate copy (`build_copy_system_prompt`, `build_user_brief`) — `persona_info` and `creative_strategy` passed through to prompt builders
3. Generate image prompt (`build_image_prompt_system_prompt`, `build_image_prompt_brief`)
4. Create `inputs.count` creative placeholder documents in `db.creatives` with `associations` set from `inputs.associations`
5. Generate images concurrently with retry logic (variation hints applied only when `count == 4`)
6. Upload to S3 under `creatives/{id}.png`
7. Update creative statuses

Does NOT write to `db.logs`. Does NOT update any project document.

Returns: `PipelineResult`.

### `run_pipeline(project_id: str)` — thin wrapper

```python
async def run_pipeline(project_id: str) -> None:
    project = await db.projects.find_one({"_id": project_id})

    # fetch images from S3
    product_images = [(await download_bytes(r["s3_key"]), r["mime_type"]) for r in project.get("product_images", [])]
    ref_images     = [(await download_bytes(r["s3_key"]), r["mime_type"]) for r in project.get("ref_images", [])]
    logo_images    = [(await download_bytes(r["s3_key"]), r["mime_type"]) for r in project.get("logo_images", [])]

    inputs = PipelineInputs(
        product_name=project["product_name"],
        description=project.get("description", ""),
        ad_format=project["ad_format"],
        client_id=project.get("client_id", "revspot"),
        name=project.get("name", project_id),
        product_images=product_images,
        ref_images=ref_images,
        logo_images=logo_images,
        associations=[{"type": "project", "id": project_id}],
        count=4,
    )

    # project status updates remain here, not in core
    await db.projects.update_one({"_id": project_id}, {"$set": {"status": "generating_copy"}})
    result = await run_pipeline_core(inputs)
    await db.projects.update_one(
        {"_id": project_id},
        {"$set": {
            "headline": result.headline,
            "body_copy": result.body_copy,
            "generated_cta": result.generated_cta,
            "image_prompt": result.image_prompt,
            "status": "ready",
        }}
    )
```

Project status transitions stay in this wrapper — not in `run_pipeline_core`. Note: the `generating_images` intermediate status is dropped. The project moves from `generating_copy` directly to `ready`. This is a minor simplification; the frontend polling loop is unaffected since it reads image statuses from `db.creatives` directly.

### Logs

`run_pipeline_core` does not write to `db.logs`. Log creation is removed from the pipeline entirely. Langfuse will replace it.

---

## API Endpoints

### `POST /api/image/generate`

Replaces `routers/generate.py` and `routers/generate_v2.py` (both deleted).

**Request** (multipart form):

| Field | Type | Default | Notes |
|---|---|---|---|
| `product_name` | str | required | |
| `description` | str | `""` | |
| `ad_format` | str | `"1080x1080"` | Ignored when `subtype` is set |
| `subtype` | CreativeSubtype \| None | `null` | Explicit subtype; skips dimension lookup |
| `count` | int | `4` | 1 or 4 |
| `client_id` | str | `"revspot"` | |
| `persona_info` | str | `""` | |
| `creative_strategy` | str | `""` | |
| `product_images` | list[UploadFile] | `[]` | |
| `ref_images` | list[UploadFile] | `[]` | |
| `logo_images` | list[UploadFile] | `[]` | |

**Response:** `GenerationOut` (synchronous — blocks until all images are done)

```python
class GenerationOut(BaseModel):
    headline: str
    body_copy: str
    generated_cta: str
    image_prompt: str
    images: list[CreativeOut]
```

**Behaviour:**
- Input images are read directly into memory from the upload — not pre-stored to S3.
- `subtype` takes priority over `ad_format`. If `subtype` is set, `PipelineInputs.subtype_override` is set and `run_pipeline_core` skips the dimension lookup.
- If `count=1`, only variation 1 is generated; variation hints are not applied.
- Generated creatives have `associations=[]` at creation (no project, no campaign yet).

### `POST /api/image/upload`

**Request** (multipart form):

| Field | Type | Default | Notes |
|---|---|---|---|
| `image` | UploadFile | required | |
| `subtype` | CreativeSubtype | required | |
| `client_id` | str | `"revspot"` | |
| `name` | str | `""` | |
| `headline` | str | `""` | |
| `body_copy` | str | `""` | |
| `cta` | str | `""` | |
| `campaign_tag` | str | `""` | |

**Response:** `CreativeOut`

Writes directly to `db.creatives`: `source="uploaded"`, `status="uploaded"`, `uploaded` sub-object populated, `associations=[]`. S3 key: `creatives/{id}.{ext}`.

---

## File-by-File Changes

### Deleted
- `backend/routers/generate.py`
- `backend/routers/generate_v2.py`

### `backend/services/pipeline.py`
- Add `PipelineInputs` dataclass
- Add `run_pipeline_core(inputs: PipelineInputs) -> list[str]`
- Refactor `run_pipeline(project_id)` to thin wrapper
- Remove log write (step 6 currently)

### `backend/routers/images.py`
- Add `POST /generate` endpoint
- Update `POST /upload` to write to `db.creatives`, return `CreativeOut`

### `backend/schemas.py`
- Add `Association(type: str, id: str)`
- Add `GenerationOut`
- Update `CreativeOut`: replace `project_id` with `associations: list[Association] = []`

### `backend/routers/projects.py`
- `_img_doc_to_out`: synthesize `associations` from legacy `project_id` if array absent
- `_project_out`: query creatives by `{"associations": {"$elemMatch": {"type": "project", "id": project_id}}}` instead of `{"project_id": project_id}`
- `stop_project`, `regenerate_project`, `delete_project`: update all `project_id` queries to use `$elemMatch` pattern

### `backend/main.py`
- Unregister `generate.py` and `generate_v2.py` routers

### `backend/services/prompt_builder_v2.py`
- Verify `persona_info` and `creative_strategy` parameters are already present in `build_copy_system_prompt_v2` and `build_image_prompt_system_prompt_v2` — reuse or consolidate into `prompt_builder.py`

---

## What Is Not Changing

- `run_pipeline` signature — callers (`routers/projects.py`) unchanged
- All existing API route URLs
- `creative_registry.py` — subtype/size spec lookup unchanged
- Frontend — `project_id` field removal from `CreativeOut` requires a frontend type update in `types.ts`
