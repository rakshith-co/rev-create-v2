# revCreate API Reference

All routes are prefixed `/api`. Authentication is via API key header on all routes except admin token management.

```
Authorization: Bearer <api_key>
```

---

## Common Types

### CreativeOut

```json
{
  "id": "uuid",
  "source": "generated | uploaded",
  "metadata": {
    "type": "image | video",
    "subtype": "CreativeSubtype (e.g. feed_square, story, fb_banner)",
    "size_specs": {
      "width": 1080,
      "height": 1080,
      "aspect_ratio": "1:1"
    }
  },
  "client_id": "revspot",
  "associations": [{ "type": "project", "id": "uuid" }],
  "name": "Creative name",
  "status": "pending | generating | retrying | done | failed | uploaded",
  "s3_key": "creatives/uuid.png",
  "creative_url": "https://presigned-s3-url",
  "error_message": null,
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
    "campaign_tag": "q1-2025"
  },
  "ad_copy": {
    "headline": "...",
    "body_copy": "...",
    "cta": "...",
    "platforms": {
      "meta": {
        "primary_text": "...",
        "headline": "...",
        "description": "...",
        "call_to_action": "..."
      }
    }
  },
  "created_at": "2025-01-01T00:00:00Z"
}
```

### AsyncAccepted (202 response)

```json
{ "job_id": "uuid" }
```

All async endpoints return this immediately. Poll `/api/jobs/{job_id}` to track progress.

### Creative Status Lifecycle

```
pending → generating → done
                    ↘ retrying → done
                               ↘ failed
```

---

## Images API — `/api/images`

### GET `/api/images`

List generated creatives.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `client_id` | string | — | Filter by client |
| `page` | int | 1 | Page number |
| `limit` | int | 50 | Items per page |

**Response** `200` — `list[CreativeOut]`

---

### GET `/api/images/{image_id}`

Get a single creative by ID.

**Response** `200` — `CreativeOut`

---

### GET `/api/images/{image_id}/download`

Download the raw image bytes. Creative must have `status: done`.

**Response** `200` — `image/png` binary

---

### POST `/api/images/{image_id}/edit`

Edit an existing creative using a natural language instruction. Creative must have `status: done`.

**Request body** (`multipart/form-data`)

| Field | Type | Required | Description |
|---|---|---|---|
| `instruction` | string | Yes | The natural language edit instruction |
| `provider` | string | No | Optional LLM provider override (e.g. `"gemini"`) |
| `ref_images` | file[] | No | Optional reference images (can be sent multiple times) |

**Response** `202` — `AsyncAccepted`

```json
{ "job_id": "uuid" }
```

**Polling:** `GET /api/jobs/{job_id}` — poll until `status` is `done` or `failed`.

---

### POST `/api/images/{image_id}/regenerate`

Regenerate a creative using the same prompt and source images, bumping the version number.

**Request body** — none

**Response** `202` — `CreativeOut` (new creative doc, status `pending`)

> Note: Unlike other async endpoints, this returns the new `CreativeOut` directly (not a job). Poll `GET /api/images/{new_id}` for completion.

---

### POST `/api/images/batch-regenerate`

Regenerate multiple creatives at once. Each gets a new version.

**Request body** (JSON)

```json
{ "image_ids": ["uuid1", "uuid2"] }
```

**Response** `202` — `AsyncAccepted`

**Polling:** `GET /api/jobs/{job_id}`

---

### POST `/api/images/{image_id}/size-variants`

Generate platform-specific size variants from an existing creative. Creative must have `status: done`.

**Request body** (JSON)

```json
{
  "platform": "meta",
  "creative_id": "uuid",
  "sizes": ["1080x1080", "1200x628"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `platform` | `"meta"` \| `"google"` | Yes | Target platform |
| `creative_id` | string | No | Override source (defaults to `image_id` in URL) |
| `sizes` | list[string] | No | Filter to specific dimensions; omit for all platform sizes |

**Available sizes by platform**

| Platform | Label | Dimensions | Aspect Ratio |
|---|---|---|---|
| `meta` | Feed Square | 1080x1080 | 1:1 |
| `meta` | Feed Landscape | 1200x628 | 16:9 |
| `meta` | Story / Reels | 1080x1920 | 9:16 |
| `google` | Horizontal | 1200x628 | 16:9 |
| `google` | Square | 600x600 | 1:1 |
| `google` | Logo Square | 1200x1200 | 1:1 |
| `google` | Logo Rectangular | 1200x300 | 4:1 |

**Response** `202` — `AsyncAccepted`

**Polling:** `GET /api/jobs/{job_id}` — poll until all creatives in the job are `done` or `failed`.

---

## Generate API — `/api/image`

### POST `/api/image/generate`

Generate ad creatives from scratch without a project. Runs the full pipeline (copy generation + image generation) asynchronously.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `product_name` | string | Yes | Product name |
| `description` | string | No | Product description / brief |
| `ad_format` | string | No | Dimensions e.g. `"1080x1080"` (default) |
| `subtype` | CreativeSubtype | No | Override creative subtype |
| `count` | int | No | Number of variations: `1` or `4` (default `4`) |
| `client_id` | string | No | Client identifier (default `"revspot"`) |
| `persona_info` | string | No | Target audience description |
| `creative_strategy` | string | No | Creative direction notes |
| `product_images` | file[] | No | Product images (JPEG/PNG/WEBP) |
| `ref_images` | file[] | No | Reference ad images (layout only) |
| `logo_images` | file[] | No | Brand logo images |

**Response** `202` — `AsyncAccepted`

**Polling:** `GET /api/jobs/{job_id}`

Job status progression:
1. `pending` — queued
2. `generating_copy` — LLM generating ad copy and image prompt
3. `processing` — images being generated
4. `done` — all creatives ready
5. `failed` — pipeline error

When `status: done`, the job response includes `headline`, `body_copy`, `generated_cta`, `image_prompt`, `ad_copy`, and fully-populated `creatives` array.

---

### POST `/api/image/fb-banner`

Generate a Facebook Lead Form banner (1200×444px) specifically designed for FB lead form placements.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `product_name` | string | Yes | Product name |
| `description` | string | No | Product description |
| `brand_tagline` | string | No | Brand tagline |
| `cta_text` | string | No | Call-to-action text |
| `color_scheme` | string | No | Colour palette guidance |
| `product_images` | file[] | No | Product images (JPEG/PNG/WEBP) |
| `logo_images` | file[] | No | Brand logo images (JPEG/PNG/WEBP) |

**Response** `202` — `AsyncAccepted`

**Polling:** `GET /api/jobs/{job_id}` — job has a single creative in `creative_ids`.

---

## Jobs API — `/api/jobs`

### GET `/api/jobs/{job_id}`

Poll the status of any async job.

**Response** `200` — `JobOut`

```json
{
  "id": "uuid",
  "type": "generate | size_variants | batch_regenerate | edit | fb_banner",
  "status": "pending | generating_copy | processing | done | failed | partial_failure",
  "creative_ids": ["uuid1", "uuid2"],
  "creatives": [ /* full CreativeOut objects with presigned URLs */ ],

  // Only present for type=generate
  "headline": "...",
  "body_copy": "...",
  "generated_cta": "...",
  "image_prompt": "...",
  "ad_copy": { /* CreativeAdCopy */ },

  "created_at": "2025-01-01T00:00:00Z"
}
```

**Job status values**

| Status | Meaning |
|---|---|
| `pending` | Not yet started |
| `generating_copy` | LLM is generating ad copy (generate jobs only) |
| `processing` | At least one creative is generating |
| `done` | All creatives are `done` |
| `failed` | All creatives failed (or pipeline error) |
| `partial_failure` | Mix of done and failed creatives |

**Recommended polling interval:** 2–3 seconds.

---

## Uploaded Creatives API — `/api/creatives/upload`

### POST `/api/creatives/upload`

Upload one or more creative files (images or videos) to the asset library.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `subtype` | CreativeSubtype | Yes | Creative subtype (e.g. `feed_square`, `story`) |
| `name` | string | Yes | Creative name / label |
| `client_id` | string | No | Client identifier (default `"revspot"`) |
| `campaign_tag` | string | No | Campaign grouping tag |
| `primary_text` | string | No | Meta ad primary text |
| `headline` | string | No | Meta ad headline |
| `description` | string | No | Meta ad description |
| `call_to_action` | string | No | Meta ad CTA |
| `files` | file[] | Yes | Files to upload (JPEG, PNG, WEBP, MP4, MOV, WEBM) |

**Response** `200` — `list[CreativeOut]`

All returned creatives have `source: "uploaded"` and `status: "uploaded"`.

---

### GET `/api/creatives/upload`

List uploaded creatives.

**Query params**

| Param | Type | Description |
|---|---|---|
| `client_id` | string | Filter by client |
| `campaign_tag` | string | Filter by campaign tag |
| `page` | int | Page number (default 1) |
| `limit` | int | Items per page (default 20) |

**Response** `200` — `list[CreativeOut]`

---

### GET `/api/creatives/upload/{creative_id}`

Get a single uploaded creative.

**Response** `200` — `CreativeOut`

---

### DELETE `/api/creatives/upload/{creative_id}`

Delete an uploaded creative.

**Response** `204` — No content

---

## Logs API — `/api/logs`

### GET `/api/logs`

List all generation logs (summaries, no prompts).

**Response** `200` — `list[LogSummary]`

```json
[
  {
    "id": "uuid",
    "project_id": "uuid",
    "project_name": "...",
    "inputs": {
      "product_name": "...",
      "description": "...",
      "ad_format": "1080x1080",
      "has_product_images": true,
      "has_ref_images": false
    },
    "ad_copy": {
      "headline": "...",
      "body_copy": "...",
      "cta": "..."
    },
    "eval": {
      "criteria": [
        { "name": "Brand Accuracy", "score": 4.5, "notes": "..." }
      ],
      "overall_notes": "..."
    },
    "image_count": 4,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/logs/{log_id}`

Get full log detail including prompts and associated creative images.

**Response** `200` — `LogOut`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "project_name": "...",
  "inputs": { /* LogInputs */ },
  "prompts": {
    "style_context": "...",
    "system_prompt": "...",
    "user_brief": "...",
    "image_prompt": "..."
  },
  "ad_copy": { /* LogAdCopy */ },
  "image_ids": ["uuid1", "uuid2"],
  "images": [ /* list[CreativeOut] */ ],
  "eval": { /* LogEval */ },
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

### PATCH `/api/logs/{log_id}/eval`

Update evaluation scores and notes for a log entry.

**Request body** (JSON)

```json
{
  "eval": {
    "criteria": [
      { "name": "Brand Accuracy", "score": 4.5, "notes": "Good colour match" },
      { "name": "Copy Clarity", "score": 3.0, "notes": "Headline too long" }
    ],
    "overall_notes": "Solid first pass, needs copy revision"
  }
}
```

**Response** `200` — full `LogOut`

---

## Admin: Token Management — `/api/admin/tokens`

All admin endpoints require `X-Admin-Secret: <admin_secret>` header instead of the standard API key.

### POST `/api/admin/tokens`

Create a new API token. The raw token is returned **once only**.

**Request body** (JSON)

```json
{ "name": "revCreate web" }
```

**Response** `201`

```json
{
  "token": "rc_...",
  "id": "uuid",
  "name": "revCreate web",
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

### GET `/api/admin/tokens`

List all API tokens (hashed — raw tokens not shown).

**Response** `200`

```json
[
  {
    "id": "uuid",
    "name": "revCreate web",
    "is_active": true,
    "created_at": "2025-01-01T00:00:00Z",
    "last_used_at": "2025-01-15T10:30:00Z"
  }
]
```

---

### DELETE `/api/admin/tokens/{token_id}`

Revoke (deactivate) an API token.

**Response** `204` — No content

---

## Polling Pattern

All async endpoints return `202 AsyncAccepted`:

```json
{ "job_id": "uuid" }
```

**Standard polling loop:**

```
POST /api/image/generate  →  { job_id: "abc" }

loop every 2-3s:
  GET /api/jobs/abc
  if status in [done, failed, partial_failure] → stop
  else → continue polling
```

**Terminal job statuses:** `done`, `failed`, `partial_failure`

**Terminal creative statuses:** `done`, `failed`, `uploaded`
