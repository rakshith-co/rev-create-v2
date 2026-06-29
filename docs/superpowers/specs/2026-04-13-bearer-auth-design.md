# Design: Bearer Auth with JWT + API Key Fallback

**Date:** 2026-04-13  
**Scope:** Backend only — `auth.py`, `db.py`, all routers

---

## Overview

Replace the current `X-API-Key` hashed-token system with a unified `Authorization: Bearer` auth that mirrors the pattern used in other revspot services. Auth tries JWT first (validated with `JWT_SECRET`), falls back to an API key lookup in the `revv` MongoDB database. Every route handler receives an `AuthContext` object containing the resolved `client` (org name), `is_admin` flag, and user info.

---

## Core Auth Logic (`backend/auth.py`)

Full replacement of the current file.

### JWT validation

```python
jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
```

Extracts `org_name` from the decoded payload. If `org_name` is missing or empty → 401.

### API key fallback

On `PyJWTError`, look up the raw token in `revv_db["clients"]` by `api_key` field. If no document found → 401. Extract `company_name` from the document; if missing → 401.

### Admin detection

- JWT path: `is_admin = org_name == "revspot_admin"`
- API key path: `is_admin = company_name == "revspot"`

### Role enforcement

`require_auth(roles=["admin"])` → if not `is_admin` → 403. Applied after both auth paths.

### `AuthContext` dataclass

```python
@dataclass
class AuthContext:
    client: str | None    # resolved org name; None only when admin + require_client=False + no x-client
    company_name: str     # raw org from JWT/API key before client resolution
    is_admin: bool
    user: dict            # JWT payload or {'org_name': company_name} for API key path
```

### `require_auth(roles=None, require_client=True)` dependency factory

Returns an async FastAPI dependency function with signature:

```python
async def _dependency(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(HTTPBearer()),
) -> AuthContext:
```

**Client resolution logic (same as Flask reference):**

- Non-admin: `client = company_name`
- Admin + `x-client` header present: `client = request.headers.get("x-client")`
- Admin + no `x-client` + `require_client=True` (default) → 400 `"x-client header is required for admin access"`
- Admin + no `x-client` + `require_client=False` → `client = None`

The resolved `AuthContext` is also stored on `request.state.auth` for middleware/logging access.

---

## Database Changes (`backend/db.py`)

Add a `revv` database connection on the same `MONGO_URI`:

```python
REVV_DB_NAME = os.getenv("REVV_DB_NAME", "revv")
revv_clients: AsyncCollection | None = None
```

Wired in `connect()`:
```python
_revv_db = _client[REVV_DB_NAME]
revv_clients = _revv_db["clients"]
```

And released in `close()`.

The existing `api_tokens` collection reference is removed. `revv_clients` is the only auth-related collection.

---

## Router Changes (all 7 routers)

Remove `dependencies=[Depends(require_api_key)]` from every `APIRouter(...)` declaration.

Add `auth: AuthContext = Depends(require_auth())` to **every route handler** individually. Handlers access `auth.client` for org-scoped queries.

Affected routers:
- `routers/projects.py`
- `routers/images.py`
- `routers/creatives.py`
- `routers/generate.py`
- `routers/fb_form_banner.py`
- `routers/jobs.py`
- `routers/logs.py`

`routers/tokens.py` — **deleted entirely** (old hashed-token management endpoints no longer needed).

---

## Files Removed

- `backend/routers/tokens.py`
- `backend/services/api_keys.py`

---

## Dependencies

Add to `backend/requirements.txt`:
```
PyJWT
```

---

## Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `JWT_SECRET` | Yes | — | HS256 signing secret |
| `REVV_DB_NAME` | No | `revv` | revv database name |

Add `JWT_SECRET=` to `.env.example`.

---

## OpenAPI

`Security(HTTPBearer())` in the dependency signature causes FastAPI to automatically register a `bearerAuth` security scheme in the OpenAPI spec. No additional setup in `main.py` required.

---

## What Does NOT Change

- All route paths and response schemas remain identical
- MongoDB `revCreate` database and its collections are untouched
- `main.py` lifespan, middleware, and router registration are untouched (except removing the tokens router)
- Frontend `api.ts` — only needs the `X-API-Key` header swapped to `Authorization: Bearer <token>` on the sending side (out of scope for this spec)
