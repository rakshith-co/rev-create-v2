# client_id Field + Projects List Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `client_id` field to the projects collection (defaulting to `"revspot"`) and add page/limit pagination to `GET /api/projects`.

**Architecture:** Two files change — `schemas.py` gets new/updated models, and `routers/projects.py` gets an updated list endpoint and create endpoint. No data migration is required; old docs without `client_id` are treated as `"revspot"` via a backwards-compatible MongoDB filter.

**Tech Stack:** FastAPI, Motor (async MongoDB), Pydantic v2

---

## File Map

| File | Change |
|---|---|
| `backend/schemas.py` | Add `client_id` to `ProjectSummary` + `ProjectOut`; add `ProjectListResponse` |
| `backend/routers/projects.py` | Update `list_projects` (query params, filter, pagination); update `create_project` (form field + store); update `_project_out` helper |

---

### Task 1: Update `schemas.py`

**Files:**
- Modify: `backend/schemas.py`

- [ ] **Step 1: Add `client_id` to `ProjectSummary`**

  Open `backend/schemas.py`. In the `ProjectSummary` class (currently lines 69–76), add `client_id` after `ad_format`:

  ```python
  class ProjectSummary(BaseModel):
      id: str
      name: str
      product_name: str
      status: str
      ad_format: str
      client_id: str = "revspot"
      created_at: datetime
      image_count: int = 0
      done_count: int = 0
  ```

- [ ] **Step 2: Add `client_id` to `ProjectOut`**

  In the `ProjectOut` class (currently lines 52–66), add `client_id` after `ad_format`:

  ```python
  class ProjectOut(BaseModel):
      id: str
      name: str
      product_name: str
      description: str
      ad_format: str
      client_id: str = "revspot"
      status: str                         # pending | generating_copy | generating_images | ready | failed
      headline: Optional[str] = None
      body_copy: Optional[str] = None
      generated_cta: Optional[str] = None
      image_prompt: Optional[str] = None
      error_message: Optional[str] = None
      created_at: datetime
      images: list[ImageOut] = []
      brand_info: Optional[BrandInfo] = None
  ```

- [ ] **Step 3: Add `ProjectListResponse`**

  Add `import math` at the top of `schemas.py` (after the existing imports). Then add `ProjectListResponse` after `ProjectSummary`:

  ```python
  class ProjectListResponse(BaseModel):
      items: list[ProjectSummary]
      total: int
      page: int
      limit: int
      total_pages: int
  ```

- [ ] **Step 4: Verify schemas parse correctly**

  Run from the `backend/` directory:

  ```bash
  python -c "from schemas import ProjectSummary, ProjectOut, ProjectListResponse; print('OK')"
  ```

  Expected output: `OK`

- [ ] **Step 5: Commit**

  ```bash
  git add backend/schemas.py
  git commit -m "feat: add client_id to project schemas and ProjectListResponse envelope"
  ```

---

### Task 2: Update `_project_out` helper to include `client_id`

**Files:**
- Modify: `backend/routers/projects.py` (lines 46–68)

- [ ] **Step 1: Add `client_id` to the `ProjectOut` construction in `_project_out`**

  In `_project_out`, the `ProjectOut(...)` call currently has no `client_id`. Add it using `doc.get` so old docs without the field fall back to `"revspot"`:

  ```python
  async def _project_out(project_id: str) -> ProjectOut | None:
      doc = await db.projects.find_one({"_id": project_id})
      if not doc:
          return None
      imgs = await db.images.find({"project_id": project_id}).to_list()
      imgs.sort(key=lambda d: (d["variation_index"], d["version"]))
      return ProjectOut(
          id=str(doc["_id"]),
          name=doc.get("name", str(doc["_id"])),
          product_name=doc.get("product_name", ""),
          description=doc.get("description") or "",
          ad_format=doc.get("ad_format", "1080x1080"),
          client_id=doc.get("client_id", "revspot"),
          status=doc.get("status", "pending"),
          headline=doc.get("headline"),
          body_copy=doc.get("body_copy"),
          generated_cta=doc.get("generated_cta"),
          image_prompt=doc.get("image_prompt"),
          error_message=doc.get("error_message"),
          created_at=doc["created_at"],
          images=[_img_doc_to_out(i) for i in imgs],
          brand_info=BrandInfo(**doc["brand_info"]) if doc.get("brand_info") else None,
      )
  ```

- [ ] **Step 2: Verify import is in place**

  `schemas.py` already exports `ProjectOut`. The import at line 13 of `projects.py` is:
  ```python
  from schemas import BrandInfo, ImageOut, ProjectOut, ProjectSummary
  ```
  Update it to also import `ProjectListResponse`:
  ```python
  from schemas import BrandInfo, ImageOut, ProjectListResponse, ProjectOut, ProjectSummary
  ```

- [ ] **Step 3: Add `import math` to `routers/projects.py`**

  At the top of `backend/routers/projects.py`, after the existing imports, add:
  ```python
  import math
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add backend/routers/projects.py
  git commit -m "feat: propagate client_id through _project_out helper"
  ```

---

### Task 3: Update `list_projects` — filter + pagination

**Files:**
- Modify: `backend/routers/projects.py` (lines 73–95)

- [ ] **Step 1: Replace the `list_projects` function**

  Replace the entire `list_projects` function with the version below. Key changes: new query params, backwards-compatible filter, skip/limit pagination, `ProjectListResponse` return type, and `doc.get("client_id", "revspot")` in `ProjectSummary` construction.

  ```python
  @router.get("", response_model=ProjectListResponse)
  async def list_projects(
      client_id: str | None = None,
      page: int = 1,
      limit: int = 20,
  ):
      if client_id == "revspot":
          query = {"$or": [{"client_id": "revspot"}, {"client_id": {"$exists": False}}]}
      elif client_id:
          query = {"client_id": client_id}
      else:
          query = {}

      total = await db.projects.count_documents(query)
      total_pages = math.ceil(total / limit) if total else 1

      docs = await db.projects.find(
          query, {"product_images": 0, "ref_images": 0}
      ).sort("created_at", -1).skip((page - 1) * limit).limit(limit).to_list()

      result = []
      for doc in docs:
          pid = str(doc["_id"])
          image_total = await db.images.count_documents({"project_id": pid})
          done = await db.images.count_documents({"project_id": pid, "status": "done"})
          result.append(
              ProjectSummary(
                  id=pid,
                  name=doc.get("name", pid),
                  product_name=doc.get("product_name", ""),
                  status=doc.get("status", "pending"),
                  ad_format=doc.get("ad_format", "1080x1080"),
                  client_id=doc.get("client_id", "revspot"),
                  created_at=doc.get("created_at", ""),
                  image_count=image_total,
                  done_count=done,
              )
          )

      return ProjectListResponse(
          items=result,
          total=total,
          page=page,
          limit=limit,
          total_pages=total_pages,
      )
  ```

- [ ] **Step 2: Start the server and verify the list endpoint**

  ```bash
  cd backend && uvicorn main:app --reload --port 8000
  ```

  In a second terminal, test with no filter (returns all):
  ```bash
  curl -s "http://localhost:8000/api/projects?page=1&limit=5" \
    -H "x-api-key: <your-key>" | python3 -m json.tool
  ```

  Expected: JSON object with keys `items`, `total`, `page`, `limit`, `total_pages`.

  Test `revspot` filter (returns existing docs + new ones with `client_id=revspot`):
  ```bash
  curl -s "http://localhost:8000/api/projects?client_id=revspot&limit=5" \
    -H "x-api-key: <your-key>" | python3 -m json.tool
  ```

  Expected: same shape; `items` contains all old projects (no `client_id` in DB) plus any with `client_id=revspot`.

- [ ] **Step 3: Commit**

  ```bash
  git add backend/routers/projects.py
  git commit -m "feat: add client_id filter and page/limit pagination to list_projects"
  ```

---

### Task 4: Update `create_project` — accept and store `client_id`

**Files:**
- Modify: `backend/routers/projects.py` (lines 98–154)

- [ ] **Step 1: Add `client_id` form field to `create_project`**

  In the `create_project` function signature, add `client_id` after `ref_images`:

  ```python
  @router.post("", response_model=ProjectOut)
  async def create_project(
      background_tasks: BackgroundTasks,
      product_name: str = Form(...),
      description: str = Form(default=""),
      ad_format: str = Form(default="1080x1080"),
      client_id: str = Form(default="revspot"),
      product_images: List[UploadFile] = File(default=[]),
      ref_images: List[UploadFile] = File(default=[]),
      logo_images: List[UploadFile] = File(default=[]),
  ):
  ```

- [ ] **Step 2: Store `client_id` in the MongoDB document**

  In the `db.projects.insert_one(...)` call, add `"client_id": client_id` alongside the existing fields:

  ```python
  await db.projects.insert_one(
      {
          "_id": project_id,
          "name": name,
          "product_name": product_name,
          "description": description,
          "ad_format": ad_format,
          "client_id": client_id,
          "product_images": product_images_data,
          "ref_images": ref_images_data,
          "logo_images": logo_images_data,
          "status": "pending",
          "headline": None,
          "body_copy": None,
          "generated_cta": None,
          "image_prompt": None,
          "error_message": None,
          "created_at": now,
      }
  )
  ```

- [ ] **Step 3: Verify creation stores `client_id`**

  Create a project with a custom client_id:
  ```bash
  curl -s -X POST "http://localhost:8000/api/projects" \
    -H "x-api-key: <your-key>" \
    -F "product_name=Test Product" \
    -F "client_id=acme" | python3 -m json.tool
  ```

  Expected: response JSON includes `"client_id": "acme"`.

  Create one without `client_id`:
  ```bash
  curl -s -X POST "http://localhost:8000/api/projects" \
    -H "x-api-key: <your-key>" \
    -F "product_name=Default Product" | python3 -m json.tool
  ```

  Expected: response JSON includes `"client_id": "revspot"`.

  Verify filtering works for the new client:
  ```bash
  curl -s "http://localhost:8000/api/projects?client_id=acme" \
    -H "x-api-key: <your-key>" | python3 -m json.tool
  ```

  Expected: `items` contains only the `acme` project; `total` is 1.

- [ ] **Step 4: Commit**

  ```bash
  git add backend/routers/projects.py
  git commit -m "feat: accept and persist client_id on project creation"
  ```
