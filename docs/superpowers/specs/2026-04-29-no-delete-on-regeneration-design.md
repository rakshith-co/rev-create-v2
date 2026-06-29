# Design: No-Delete on Creative Regeneration

**Date:** 2026-04-29
**Status:** Approved

## Problem

When size variants are regenerated (or a project is regenerated), existing creative documents are deleted from MongoDB before new ones are inserted. This causes three issues:

- **History loss** — the previous generation is unrecoverable once the doc is deleted
- **Unsafe regeneration** — if the new generation fails, there is no fallback; the old result is already gone
- **Frontend flicker** — the `_id` disappears briefly, causing the UI to lose its reference to the creative

## Solution

Replace all `delete_one` / `delete_many` calls on the regeneration paths with `update_one` / `update_many` that reset the doc in place. The `_id` and `s3_key` are preserved. The new image overwrites the S3 object at the same key only on successful generation.

## Data Model

No schema changes. Existing fields are reused:

| Field | On regeneration trigger | On generation success |
|---|---|---|
| `_id` | unchanged | unchanged |
| `s3_key` | unchanged | unchanged (S3 object overwritten) |
| `status` | `"pending"` | `"done"` |
| `error_message` | `null` | `null` |
| `created_at` | updated to now | unchanged |

## Affected Code

### 1. `backend/routers/images.py` — `request_size_variants` (line ~681)

**Before:**
```python
if existing:
    await db.creatives.delete_one({"_id": existing["_id"]})
new_id = str(uuid.uuid4())
...
await db.creatives.insert_one({...})
```

**After:**
```python
if existing:
    new_id = str(existing["_id"])
    await db.creatives.update_one(
        {"_id": new_id},
        {"$set": {"status": "pending", "error_message": None, "created_at": now}},
    )
else:
    new_id = str(uuid.uuid4())
    await db.creatives.insert_one({...})
```

The `s3_key` on the existing doc is left unchanged. The background task uploads the new image to that same key, overwriting the old S3 object only on success.

### 2. `backend/routers/projects.py` — `regenerate_project` (line ~285)

**Before:**
```python
await db.creatives.delete_many(
    {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
)
```

**After:**
```python
await db.creatives.update_many(
    {"associations": {"$elemMatch": {"type": "project", "id": project_id}}},
    {"$set": {"status": "pending", "error_message": None, "created_at": now}},
)
```

### 3. `DELETE /api/creatives/{creative_id}` — no change

The explicit single-creative delete endpoint is intentional and unaffected.

### 4. `DELETE /api/projects/{project_id}` — no change

Project deletion cascades to creatives intentionally and is unaffected.

## Safety Properties

- The old S3 image at `s3_key` is only overwritten when a new generation **succeeds**. A failed generation leaves the old S3 object intact.
- If the background task fails, the doc status goes to `"failed"` but the old S3 image is still accessible at `s3_key`.
- The in-flight reuse branch (`status in ("pending", "generating", "retrying")`) in `request_size_variants` is already correct and unchanged.

## Out of Scope

- Surfacing the previous image in the UI when a regeneration is in-flight or failed (can be added later once the doc is stable)
- Multi-generation history (history array) — deferred; single-level safety is sufficient for now
- S3 lifecycle / cleanup rules for orphaned objects
