# Design: client_id Field + Projects List Pagination

**Date:** 2026-04-07  
**Scope:** Backend only — `schemas.py`, `routers/projects.py`

---

## Overview

Add a `client_id` field to the projects collection to enable filtering projects by client. Projects created without a `client_id` default to `"revspot"`. Add page/limit pagination to the `GET /api/projects` list endpoint.

---

## Schema Changes (`schemas.py`)

### `ProjectSummary` and `ProjectOut`

Add `client_id: str = "revspot"` to both models. The Pydantic default ensures compatibility when serialising old docs that lack the field.

### New `ProjectListResponse` envelope

```python
class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int
    page: int
    limit: int
    total_pages: int
```

Returned by `GET /api/projects` instead of the current bare `list[ProjectSummary]`.

---

## `POST /api/projects` — Create Project

Add an optional form field:

```python
client_id: str = Form(default="revspot")
```

Store `client_id` in the MongoDB document alongside existing fields. No other changes to creation or pipeline logic.

---

## `GET /api/projects` — List Projects

### New signature

```python
async def list_projects(
    client_id: str | None = None,
    page: int = 1,
    limit: int = 20,
):
```

### Query filter (backwards-compatible)

Old documents have no `client_id` field. They are treated as `"revspot"` by using an existence check:

```python
if client_id == "revspot":
    filter = {"$or": [{"client_id": "revspot"}, {"client_id": {"$exists": False}}]}
elif client_id:
    filter = {"client_id": client_id}
else:
    filter = {}  # return all projects regardless of client
```

### Pagination

```python
total = await db.projects.count_documents(filter)
docs = await db.projects.find(filter, {"product_images": 0, "ref_images": 0}) \
    .sort("created_at", -1) \
    .skip((page - 1) * limit) \
    .limit(limit) \
    .to_list()
total_pages = math.ceil(total / limit) if total else 1
```

Return `ProjectListResponse(items=result, total=total, page=page, limit=limit, total_pages=total_pages)`.

### Image count queries

The two `count_documents` calls per project (total images, done images) are kept. They now run only over the current page of results rather than the full collection, so pagination naturally limits their cost.

---

## Reading `client_id` from existing docs

Wherever a project doc is converted to output (`list_projects`, `_project_out`), use:

```python
client_id=doc.get("client_id", "revspot")
```

This ensures old docs without the field are represented correctly without a data migration.

---

## No Migration Required

Existing documents are treated as `client_id="revspot"` at read time and via the filter logic above. No backfill script is needed.

---

## Files Changed

| File | Change |
|---|---|
| `backend/schemas.py` | Add `client_id` to `ProjectOut`, `ProjectSummary`; add `ProjectListResponse` |
| `backend/routers/projects.py` | Update `create_project` form field; update `list_projects` signature, filter, and pagination |
