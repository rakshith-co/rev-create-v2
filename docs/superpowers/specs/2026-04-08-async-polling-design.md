# Async Polling Design for Image Generation APIs

**Date:** 2026-04-08  
**Branch:** feat/godrej-mvp  
**Status:** Approved

---

## Problem

Several image generation APIs are either fully synchronous (blocking 30–60s) or partially async (use BackgroundTasks but have no polling endpoint). Clients have no way to track progress or retrieve results without waiting on the HTTP connection.

The project pipeline already has the correct pattern: `POST /api/projects` returns immediately, client polls `GET /api/projects/{id}`. This spec extends that pattern to all remaining generation APIs.

---

## APIs and Their Required Changes

### No change needed
| API | Reason |
|-----|--------|
| `POST /api/creatives/upload` | S3 upload only, no generation, instant |
| `GET /api/images`, `GET /api/images/{id}/download` | Read-only |
| `GET /api/creatives/upload*` | Read-only |
| All `GET /api/logs*` | Read-only |
| All `GET/POST /api/projects*` | Already async + polling |

### Needs single-image polling endpoint
These already use `BackgroundTasks` and insert a creative with `status: "pending"`, returning it immediately. The data model is in place. Only missing piece: `GET /api/images/{id}`.

| API | Returns | Poll via |
|-----|---------|----------|
| `POST /api/images/{id}/edit` | `CreativeOut` (pending) | `GET /api/images/{id}` |
| `POST /api/images/{id}/regenerate` | `CreativeOut` (pending) | `GET /api/images/{id}` |
| `POST /api/image/fb-banner` | `CreativeOut` (pending) | `GET /api/images/{id}` |

### Needs batch job + batch polling endpoint
These produce multiple creatives or need to return ad copy alongside creative IDs.

| API | Returns | Poll via |
|-----|---------|----------|
| `POST /api/image/generate` | `{ job_id }` | `GET /api/jobs/{job_id}` |
| `POST /api/images/{id}/size-variants` | `{ job_id }` | `GET /api/jobs/{job_id}` |
| `POST /api/images/batch-regenerate` | `{ job_id }` | `GET /api/jobs/{job_id}` |

---

## New: `GET /api/images/{id}` (single creative polling)

Returns the current state of any creative document. No new DB fields required — `CreativeOut` already has `status`, `creative_url`, and `error_message`.

```
GET /api/images/{id}
→ 200 CreativeOut    (status: pending | generating | retrying | done | failed)
→ 404 if not found
```

This endpoint lives in `backend/routers/images.py`.

---

## New: `jobs` Collection + `GET /api/jobs/{job_id}`

### MongoDB document shape

```json
{
  "_id": "uuid",
  "type": "generate" | "size_variants" | "batch_regenerate",
  "creative_ids": ["uuid", "uuid", ...],

  // Only for type=generate — written once LLM step completes
  "headline": "string | null",
  "body_copy": "string | null",
  "generated_cta": "string | null",
  "image_prompt": "string | null",
  "meta_ad_copy": { ... } | null,

  "created_at": "datetime"
}
```

No `status` field is persisted — it is derived at poll time from the live statuses of `creative_ids` in the creatives collection.

### Derived job status logic

| Condition | Job status |
|-----------|------------|
| All creatives `pending` | `pending` |
| Any creative `generating` or `retrying` | `processing` |
| All creatives `done` | `done` |
| Mix of `done` and `failed` | `partial_failure` |
| All creatives `failed` | `failed` |

### `GET /api/jobs/{job_id}` response schema (`JobOut`)

```python
class JobOut(BaseModel):
    id: str
    type: str                            # "generate" | "size_variants" | "batch_regenerate"
    status: str                          # derived
    creative_ids: list[str]
    creatives: list[CreativeOut]         # full creative docs with presigned URLs

    # Ad copy — only populated for type=generate
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    generated_cta: Optional[str] = None
    image_prompt: Optional[str] = None
    meta_ad_copy: Optional[MetaAdCopy] = None

    created_at: datetime
```

This router lives in a new file: `backend/routers/jobs.py`.

---

## Changes to Existing APIs

### `POST /api/image/generate`
**Before:** Synchronous. Calls `run_pipeline_core`, blocks until all 4 images are done, returns `GenerationOut`.  
**After:** 
1. Uploads input images to S3 (sync — fast)
2. Inserts a `jobs` doc with `type=generate`, `creative_ids=[]`
3. Inserts `count` (1 or 4) pending creative docs (same as pipeline does today)
4. Updates job with the creative IDs
5. Kicks off background task: runs LLM copy generation, then 4 concurrent image generations
6. Background task writes ad copy fields to the job doc once LLM completes
7. Returns `{ job_id: "..." }` immediately with HTTP 202

### `POST /api/image/fb-banner`
**Before:** Synchronous. Calls `generate_image`, blocks until done, inserts + returns the creative.  
**After:**
1. Inserts a creative doc with `status: "pending"`
2. Kicks off background task: runs `generate_image`, uploads to S3, sets `status: "done"`
3. Returns `CreativeOut` (pending) immediately with HTTP 202

### `POST /api/images/{id}/size-variants`
**Before:** BackgroundTasks, returns list of pending `CreativeOut` docs.  
**After:**
1. Inserts all variant creative docs (same as today)
2. Inserts a `jobs` doc with `type=size_variants`, `creative_ids=[...]`
3. Kicks off background task (unchanged)
4. Returns `{ job_id: "..." }` immediately

### `POST /api/images/batch-regenerate`
**Before:** BackgroundTasks, returns list of pending `CreativeOut` docs.  
**After:**
1. Inserts all new creative docs (same as today)
2. Inserts a `jobs` doc with `type=batch_regenerate`, `creative_ids=[...]`
3. Kicks off background tasks (unchanged)
4. Returns `{ job_id: "..." }` immediately

### `POST /api/images/{id}/edit` and `POST /api/images/{id}/regenerate`
No change to implementation — already async. Just add `GET /api/images/{id}` as the polling endpoint.

---

## New Schemas (additions to `schemas.py`)

```python
class JobOut(BaseModel):
    id: str
    type: str
    status: str
    creative_ids: list[str]
    creatives: list[CreativeOut]
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    generated_cta: Optional[str] = None
    image_prompt: Optional[str] = None
    meta_ad_copy: Optional[MetaAdCopy] = None
    created_at: datetime

class AsyncAccepted(BaseModel):
    job_id: str
```

---

## New DB Collection

```python
# backend/db.py — add alongside existing collections
jobs = db["jobs"]
```

---

## File Changes Summary

| File | Change |
|------|--------|
| `backend/db.py` | Add `jobs` collection |
| `backend/schemas.py` | Add `JobOut`, `AsyncAccepted` |
| `backend/routers/jobs.py` | New file — `GET /api/jobs/{job_id}` |
| `backend/routers/images.py` | Add `GET /api/images/{id}`; update `size-variants` + `batch-regenerate` to return `job_id` |
| `backend/routers/generate.py` | Make `POST /api/image/generate` async, return `job_id` |
| `backend/routers/fb_form_banner.py` | Make `POST /api/image/fb-banner` async, return pending creative |
| `backend/main.py` | Register `jobs` router |

---

## What Does NOT Change

- Creative status lifecycle (`pending → generating → retrying → done | failed`) — unchanged
- Background task implementations (`_run_edit`, `_run_regeneration`, `_run_size_variants`) — unchanged
- `CreativeOut` schema — unchanged
- Project APIs — unchanged
