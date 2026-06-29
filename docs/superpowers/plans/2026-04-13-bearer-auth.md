# Bearer Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `X-API-Key` auth system with `Authorization: Bearer` supporting JWT (HS256 via `JWT_SECRET`) + API key fallback (lookup in `revv.clients` MongoDB collection), injecting `AuthContext` (with resolved `client` org name) into every route handler.

**Architecture:** A `require_auth(roles, require_client)` factory in `auth.py` returns a FastAPI async dependency that validates the Bearer token, resolves the caller's org (`client`), and returns an `AuthContext` dataclass. Every route handler declares `auth: AuthContext = Depends(require_auth())`. The `revv` database is accessed via a second handle on the existing `MONGO_URI`.

**Tech Stack:** FastAPI `Security`/`Depends`, `PyJWT` (HS256), `pymongo` async (`AsyncMongoClient`), Python `dataclasses`

---

## File Map

| Action | File |
|--------|------|
| Full replacement | `backend/auth.py` |
| Modify | `backend/db.py` |
| Modify | `backend/main.py` |
| Modify | `backend/requirements.txt` |
| Modify | `backend/routers/projects.py` |
| Modify | `backend/routers/images.py` |
| Modify | `backend/routers/creatives.py` |
| Modify | `backend/routers/generate.py` |
| Modify | `backend/routers/fb_form_banner.py` |
| Modify | `backend/routers/logs.py` |
| Modify | `backend/routers/jobs.py` |
| Delete | `backend/routers/tokens.py` |
| Delete | `backend/services/api_keys.py` |

---

### Task 1: Add PyJWT dependency and env var

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `.env` (local, not committed)

- [ ] **Step 1: Add PyJWT to requirements.txt**

Open `backend/requirements.txt` and add this line (alphabetical order, after `python-multipart`):
```
PyJWT==2.10.1
```

- [ ] **Step 2: Install it**

```bash
cd backend && pip install PyJWT==2.10.1
```

Expected output: `Successfully installed PyJWT-2.10.1` (or "already satisfied")

- [ ] **Step 3: Add JWT_SECRET to local .env**

In `backend/.env` (or project root `.env`), add:
```
JWT_SECRET=your-secret-here
REVV_DB_NAME=revv
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add PyJWT dependency for bearer auth"
```

---

### Task 2: Update db.py — add revv_clients, remove api_tokens

**Files:**
- Modify: `backend/db.py`

- [ ] **Step 1: Replace db.py with the new version**

Replace the entire contents of `backend/db.py`:

```python
import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "revCreate")
REVV_DB_NAME = os.getenv("REVV_DB_NAME", "revv")

_client: AsyncMongoClient | None = None
projects: AsyncCollection | None = None
creatives: AsyncCollection | None = None
images: AsyncCollection | None = None
jobs: AsyncCollection | None = None
logs: AsyncCollection | None = None
revv_clients: AsyncCollection | None = None


async def connect() -> None:
    global _client, projects, creatives, images, jobs, logs, revv_clients
    _client = AsyncMongoClient(MONGO_URI)
    _db = _client[DB_NAME]
    projects = _db["projects"]
    creatives = _db["creatives"]
    images = _db["images"]  # Keep temporarily for migration
    jobs = _db["jobs"]
    logs = _db["logs"]
    _revv_db = _client[REVV_DB_NAME]
    revv_clients = _revv_db["clients"]
    # Compound index for association queries:
    # find({"associations": {"$elemMatch": {"type": "campaign", "id": X}}})
    await creatives.create_index(
        [("associations.type", 1), ("associations.id", 1)],
        name="associations_type_id",
    )


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

- [ ] **Step 2: Verify Python parses it**

```bash
cd backend && python -c "import db; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/db.py
git commit -m "feat: add revv_clients collection, remove api_tokens from db"
```

---

### Task 3: Rewrite auth.py

**Files:**
- Full replacement: `backend/auth.py`

- [ ] **Step 1: Replace auth.py entirely**

```python
import logging
import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import db

logger = logging.getLogger("revCreate.auth")

JWT_SECRET = os.getenv("JWT_SECRET", "")

_http_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    client: str | None        # resolved org — None only when admin + require_client=False + no x-client
    company_name: str         # raw org from JWT/API key before client resolution
    is_admin: bool
    user: dict                # JWT payload or {'org_name': company_name} for API key path


def require_auth(roles: list[str] | None = None, require_client: bool = True):
    """
    Unified auth dependency factory. Returns a FastAPI async dependency.

    Args:
        roles: None → any authenticated caller. ['admin'] → revspot admin only.
        require_client: If True (default), admins must supply x-client header.
                        If False, admins without x-client get client=None.
                        Has no effect on regular users — they always get their org.

    The returned dependency resolves to AuthContext and also stores it on
    request.state.auth for middleware/logging access.
    """
    async def _dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
    ) -> AuthContext:
        if not credentials or not credentials.credentials:
            logger.error("[require_auth] No Authorization header present")
            raise HTTPException(status_code=401, detail="Missing Authorization header")

        token = credentials.credentials
        is_admin = False
        company_name = ""
        user: dict = {}

        # ── 1. Try JWT ────────────────────────────────────────────────────────
        jwt_succeeded = False
        try:
            if not JWT_SECRET:
                raise ValueError("JWT_SECRET not configured")
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            company_name = payload.get("org_name", "")
            if not company_name:
                logger.error("[require_auth] Empty org_name in JWT payload")
                raise HTTPException(status_code=401, detail="Invalid token: missing org_name")

            is_admin = company_name == "revspot_admin"
            user = payload
            jwt_succeeded = True
            logger.info("[require_auth] JWT auth successful: %s", company_name)

        except HTTPException:
            raise
        except Exception as e:
            logger.info("[require_auth] JWT validation failed, trying API key: %s", e)

        # ── 2. API key fallback ───────────────────────────────────────────────
        if not jwt_succeeded:
            client_doc = await db.revv_clients.find_one({"api_key": token})
            if not client_doc:
                logger.warning("[require_auth] API key not found")
                raise HTTPException(status_code=401, detail="Invalid or missing credentials")

            company_name = client_doc.get("company_name", "")
            if not company_name:
                logger.warning("[require_auth] API key doc missing company_name")
                raise HTTPException(status_code=401, detail="Invalid credentials")

            is_admin = company_name == "revspot"
            user = {"org_name": "revspot_admin" if is_admin else company_name}
            logger.info("[require_auth] API key auth successful: %s", company_name)

        # ── 3. Role check ─────────────────────────────────────────────────────
        if roles and "admin" in roles and not is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")

        # ── 4. Resolve client ─────────────────────────────────────────────────
        if is_admin:
            mimic_client = request.headers.get("x-client")
            if mimic_client:
                resolved_client = mimic_client
            elif require_client:
                raise HTTPException(status_code=400, detail="x-client header is required for admin access")
            else:
                resolved_client = None
        else:
            resolved_client = company_name

        ctx = AuthContext(
            client=resolved_client,
            company_name=company_name,
            is_admin=is_admin,
            user=user,
        )
        request.state.auth = ctx
        return ctx

    return _dependency
```

- [ ] **Step 2: Verify Python parses it**

```bash
cd backend && python -c "from auth import require_auth, AuthContext; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/auth.py
git commit -m "feat: rewrite auth with JWT + API key fallback and AuthContext"
```

---

### Task 4: Update main.py and delete removed files

**Files:**
- Modify: `backend/main.py`
- Delete: `backend/routers/tokens.py`
- Delete: `backend/services/api_keys.py`

- [ ] **Step 1: Remove tokens router from main.py**

In `backend/main.py`, remove these two lines:
```python
from routers.tokens import router as tokens_router
```
and:
```python
app.include_router(tokens_router)
```

- [ ] **Step 2: Delete the removed files**

```bash
rm backend/routers/tokens.py backend/services/api_keys.py
```

- [ ] **Step 3: Verify the app imports cleanly**

```bash
cd backend && python -c "import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git rm backend/routers/tokens.py backend/services/api_keys.py
git commit -m "feat: remove tokens router and api_keys service"
```

---

### Task 5: Update routers/projects.py

**Files:**
- Modify: `backend/routers/projects.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update router declaration**

Replace:
```python
router = APIRouter(prefix="/api/projects",
                   tags=["projects"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/projects", tags=["projects"])
```

- [ ] **Step 3: Update list_projects**

Replace:
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
```
With:
```python
@router.get("", response_model=ProjectListResponse)
async def list_projects(
    auth: AuthContext = Depends(require_auth()),
    page: int = 1,
    limit: int = 20,
):
    client_id = auth.client
    if client_id == "revspot":
        query = {"$or": [{"client_id": "revspot"}, {"client_id": {"$exists": False}}]}
    elif client_id:
        query = {"client_id": client_id}
    else:
        query = {}
```

- [ ] **Step 4: Update create_project**

Replace:
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
With:
```python
@router.post("", response_model=ProjectOut)
async def create_project(
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth()),
    product_name: str = Form(...),
    description: str = Form(default=""),
    ad_format: str = Form(default="1080x1080"),
    product_images: List[UploadFile] = File(default=[]),
    ref_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
):
```

Then inside `create_project`, replace the hardcoded `client_id` reference in the `insert_one` call:
```python
            "client_id": client_id,
```
With:
```python
            "client_id": auth.client,
```

- [ ] **Step 5: Add auth to remaining handlers**

Add `auth: AuthContext = Depends(require_auth())` as the first parameter to each of these handlers (after `self` if any — there is none, just add as first param):

`get_project(project_id: str)` → `get_project(project_id: str, auth: AuthContext = Depends(require_auth()))`

`stop_project(project_id: str)` → `stop_project(project_id: str, auth: AuthContext = Depends(require_auth()))`

`regenerate_project(project_id: str, background_tasks: BackgroundTasks)` → `regenerate_project(project_id: str, background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_auth()))`

`delete_project(project_id: str)` → `delete_project(project_id: str, auth: AuthContext = Depends(require_auth()))`

`download_project(project_id: str, platform: str | None = None)` → `download_project(project_id: str, auth: AuthContext = Depends(require_auth()), platform: str | None = None)`

- [ ] **Step 6: Verify**

```bash
cd backend && python -c "from routers.projects import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/routers/projects.py
git commit -m "feat: migrate projects router to bearer auth"
```

---

### Task 6: Update routers/images.py

**Files:**
- Modify: `backend/routers/images.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update router declaration**

Replace:
```python
router = APIRouter(prefix="/api/images", tags=["images"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/images", tags=["images"])
```

- [ ] **Step 3: Update list_generated_images**

Replace:
```python
@router.get("", response_model=list[ImageOut])
async def list_generated_images(
    client_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
):
    """List generated creatives (used for testing size variants)."""
    query: dict = {"source": CreativeSource.GENERATED}
    if client_id:
        query["client_id"] = client_id
```
With:
```python
@router.get("", response_model=list[ImageOut])
async def list_generated_images(
    auth: AuthContext = Depends(require_auth()),
    page: int = 1,
    limit: int = 50,
):
    """List generated creatives (used for testing size variants)."""
    query: dict = {"source": CreativeSource.GENERATED}
    if auth.client:
        query["client_id"] = auth.client
```

- [ ] **Step 4: Add auth to remaining handlers**

`get_creative(image_id: str)` → `get_creative(image_id: str, auth: AuthContext = Depends(require_auth()))`

`batch_regenerate_images(body: BatchRegenerateRequest, background_tasks: BackgroundTasks)` → add `auth: AuthContext = Depends(require_auth())` as first param before `body`

`download_image(image_id: str)` → `download_image(image_id: str, auth: AuthContext = Depends(require_auth()))`

`request_edit(image_id: str, body: EditImageRequest, background_tasks: BackgroundTasks)` → add `auth: AuthContext = Depends(require_auth())` as first param before `image_id`

`regenerate_image_endpoint(image_id: str, background_tasks: BackgroundTasks)` → add `auth: AuthContext = Depends(require_auth())` as first param

`request_size_variants(image_id: str, body: SizeVariantRequest, background_tasks: BackgroundTasks)` → add `auth: AuthContext = Depends(require_auth())` as first param

- [ ] **Step 5: Verify**

```bash
cd backend && python -c "from routers.images import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add backend/routers/images.py
git commit -m "feat: migrate images router to bearer auth"
```

---

### Task 7: Update routers/creatives.py

**Files:**
- Modify: `backend/routers/creatives.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update router declaration**

Replace:
```python
router = APIRouter(prefix="/api/creatives/upload", tags=["creatives"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/creatives/upload", tags=["creatives"])
```

- [ ] **Step 3: Update upload_creatives — remove client_id form field, use auth.client**

Replace:
```python
@router.post("", response_model=list[CreativeOut])
async def upload_creatives(
    subtype: CreativeSubtype = Form(...),
    name: str = Form(...),
    client_id: str = Form(default="revspot"),
    campaign_tag: str = Form(default=""),
```
With:
```python
@router.post("", response_model=list[CreativeOut])
async def upload_creatives(
    auth: AuthContext = Depends(require_auth()),
    subtype: CreativeSubtype = Form(...),
    name: str = Form(...),
    campaign_tag: str = Form(default=""),
```

Then inside `upload_creatives`, replace:
```python
            "client_id": client_id,
```
With:
```python
            "client_id": auth.client,
```

- [ ] **Step 4: Update list_creatives — remove client_id param, use auth.client**

Replace:
```python
@router.get("", response_model=list[CreativeOut])
async def list_creatives(
    client_id: Optional[str] = None,
    campaign_tag: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    query: dict = {"source": CreativeSource.UPLOADED}
    if client_id:
        query["client_id"] = client_id
```
With:
```python
@router.get("", response_model=list[CreativeOut])
async def list_creatives(
    auth: AuthContext = Depends(require_auth()),
    campaign_tag: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    query: dict = {"source": CreativeSource.UPLOADED}
    if auth.client:
        query["client_id"] = auth.client
```

- [ ] **Step 5: Add auth to remaining handlers**

`get_creative(creative_id: str)` → `get_creative(creative_id: str, auth: AuthContext = Depends(require_auth()))`

`delete_creative(creative_id: str)` → `delete_creative(creative_id: str, auth: AuthContext = Depends(require_auth()))`

- [ ] **Step 6: Verify**

```bash
cd backend && python -c "from routers.creatives import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/routers/creatives.py
git commit -m "feat: migrate creatives router to bearer auth"
```

---

### Task 8: Update routers/generate.py

**Files:**
- Modify: `backend/routers/generate.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update router declaration**

Replace:
```python
router = APIRouter(prefix="/api/image", tags=["image"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/image", tags=["image"])
```

- [ ] **Step 3: Update generate handler — remove client_id form field, use auth.client**

Replace:
```python
@router.post("/generate", response_model=AsyncAccepted, status_code=202)
async def generate(
    background_tasks: BackgroundTasks,
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
```
With:
```python
@router.post("/generate", response_model=AsyncAccepted, status_code=202)
async def generate(
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth()),
    product_name: str = Form(...),
    description: str = Form(default=""),
    ad_format: str = Form(default="1080x1080"),
    subtype: Optional[CreativeSubtype] = Form(default=None),
    count: int = Form(default=4),
    persona_info: str = Form(default=""),
    creative_strategy: str = Form(default=""),
    product_images: List[UploadFile] = File(default=[]),
    ref_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
):
```

Then inside the handler, replace:
```python
        "client_id": client_id,
```
With:
```python
        "client_id": auth.client,
```

- [ ] **Step 4: Verify**

```bash
cd backend && python -c "from routers.generate import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/generate.py
git commit -m "feat: migrate generate router to bearer auth"
```

---

### Task 9: Update routers/fb_form_banner.py

**Files:**
- Modify: `backend/routers/fb_form_banner.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update router declaration**

Replace:
```python
router = APIRouter(prefix="/api/image", tags=["image"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/image", tags=["image"])
```

- [ ] **Step 3: Update generate_fb_form_banner — add auth, replace hardcoded client_id**

Replace:
```python
@router.post("/fb-banner", response_model=AsyncAccepted, status_code=202)
async def generate_fb_form_banner(
    background_tasks: BackgroundTasks,
    product_name: str = Form(...),
```
With:
```python
@router.post("/fb-banner", response_model=AsyncAccepted, status_code=202)
async def generate_fb_form_banner(
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth()),
    product_name: str = Form(...),
```

Then inside the handler, replace:
```python
        "client_id": "revspot",
```
With:
```python
        "client_id": auth.client,
```

- [ ] **Step 4: Verify**

```bash
cd backend && python -c "from routers.fb_form_banner import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/fb_form_banner.py
git commit -m "feat: migrate fb_form_banner router to bearer auth"
```

---

### Task 10: Update routers/logs.py and routers/jobs.py

**Files:**
- Modify: `backend/routers/logs.py`
- Modify: `backend/routers/jobs.py`

- [ ] **Step 1: Update logs.py imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 2: Update logs.py router declaration**

Replace:
```python
router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/logs", tags=["logs"])
```

- [ ] **Step 3: Add auth to all logs.py handlers**

`list_logs()` → `list_logs(auth: AuthContext = Depends(require_auth()))`

`get_log(log_id: str)` → `get_log(log_id: str, auth: AuthContext = Depends(require_auth()))`

`update_eval(log_id: str, body: UpdateEvalRequest)` → `update_eval(log_id: str, body: UpdateEvalRequest, auth: AuthContext = Depends(require_auth()))`

- [ ] **Step 4: Update jobs.py imports**

Replace:
```python
from auth import require_api_key
```
With:
```python
from auth import AuthContext, require_auth
```

- [ ] **Step 5: Update jobs.py router declaration**

Replace:
```python
router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])
```
With:
```python
router = APIRouter(prefix="/api/jobs", tags=["jobs"])
```

- [ ] **Step 6: Add auth to jobs.py handler**

`get_job(job_id: str)` → `get_job(job_id: str, auth: AuthContext = Depends(require_auth()))`

- [ ] **Step 7: Verify both**

```bash
cd backend && python -c "from routers.logs import router; from routers.jobs import router; print('ok')"
```

Expected: `ok`

- [ ] **Step 8: Commit**

```bash
git add backend/routers/logs.py backend/routers/jobs.py
git commit -m "feat: migrate logs and jobs routers to bearer auth"
```

---

### Task 11: Smoke test the full server

**Files:** none — verification only

- [ ] **Step 1: Start the server**

```bash
cd backend && uvicorn main:app --reload --port 8000
```

Expected: server starts with no import errors, logs `MongoDB connected`

- [ ] **Step 2: Verify unauthenticated request is rejected**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/projects
```

Expected: `403` (HTTPBearer returns 403 when header is missing with `auto_error=False` → our code raises 401, FastAPI may vary — acceptable is `401` or `403`)

- [ ] **Step 3: Verify authenticated request works with a valid JWT**

Generate a test token (run once in a Python shell):
```python
import jwt, os
token = jwt.encode({"org_name": "testclient"}, os.getenv("JWT_SECRET"), algorithm="HS256")
print(token)
```

Then:
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <token-from-above>" \
  http://localhost:8000/api/projects
```

Expected: `200`

- [ ] **Step 4: Verify admin without x-client is rejected**

```python
import jwt, os
admin_token = jwt.encode({"org_name": "revspot_admin"}, os.getenv("JWT_SECRET"), algorithm="HS256")
print(admin_token)
```

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <admin-token>" \
  http://localhost:8000/api/projects
```

Expected: `400` (x-client header required)

- [ ] **Step 5: Verify admin with x-client works**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <admin-token>" \
  -H "x-client: testclient" \
  http://localhost:8000/api/projects
```

Expected: `200`

- [ ] **Step 6: Verify OpenAPI security scheme is registered**

Open `http://localhost:8000/docs` in a browser. The Authorize button should show `bearerAuth (http, Bearer)`.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: bearer auth migration complete — JWT + API key fallback on all routes"
```
