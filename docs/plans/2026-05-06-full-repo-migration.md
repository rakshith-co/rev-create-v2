# Full Repository Migration Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate all direct `db` calls outside of `backend/repos/` by migrating to a repository-based architecture.

**Architecture:** 
- Centralize all MongoDB interactions within `backend/repos/`.
- Ensure routers and services only interact with repositories.

**Tech Stack:** Python, Motor (MongoDB), FastAPI

---

### Task 1: Tokens Repository and Auth Refactor

**Files:**
- Create: `backend/repos/tokens.py`
- Modify: `backend/auth.py`

**Step 1: Create `backend/repos/tokens.py`**

```python
from datetime import datetime
import db

async def get_by_hash(token_hash: str) -> dict | None:
    return await db.api_tokens.find_one({"token_hash": token_hash, "is_active": True})

async def update_last_used(token_id: str, last_used: datetime) -> None:
    await db.api_tokens.update_one({"_id": token_id}, {"$set": {"last_used_at": last_used}})
```

**Step 2: Update `backend/auth.py`**
- Import `repos.tokens as tokens_repo`
- Replace `db.api_tokens.find_one` with `tokens_repo.get_by_hash`
- Replace `db.api_tokens.update_one` with `tokens_repo.update_last_used`

---

### Task 2: Enhance Repositories for Images Router

**Files:**
- Modify: `backend/repos/creatives.py`
- Modify: `backend/repos/jobs.py`

**Step 1: Add `find_latest_done_child` and `find_specific_size_variant` to `creatives_repo` if missing or incomplete.**
(Check existing methods: `find_latest_child` and `find_size_variant` already exist but check logic).

**Step 2: Add `insert` to `creatives_repo` if missing.** (Already exists).

---

### Task 3: Refactor `backend/routers/images.py`

**Files:**
- Modify: `backend/routers/images.py`

**Step 1: Replace direct `db` calls in `regenerate_image_endpoint`**
- Use `creatives_repo.get(image_id)`
- Use `creatives_repo.insert(new_doc)`

**Step 2: Replace direct `db` calls in `request_size_variants`**
- Use `creatives_repo.get(target_id)`
- Use `creatives_repo.find_size_variant(...)`
- Use `creatives_repo.update(...)`
- Use `creatives_repo.insert(...)`
- Use `jobs_repo.insert(...)`

---

### Task 4: Refactor Deserializers

**Files:**
- Modify: `backend/deserializers/edit.py`
- Modify: `backend/deserializers/regenerate.py`
- Modify: `backend/deserializers/size_variant.py`

**Step 1: Replace `db.creatives.find_one` and `db.projects.find_one` with repo calls.**

---

### Task 5: Refactor Core Tasks and Pipeline

**Files:**
- Modify: `backend/core/tasks.py`
- Modify: `backend/core/pipeline.py`
- Modify: `backend/services/chat_agent.py`

**Step 1: Replace all `db.creatives.update_one`, `db.jobs.update_one`, etc. with repo calls.**

---

### Task 6: Cleanup

**Step 1: Verify no `db.` remains outside of `repos/` and `db.py` and `main.py` (lifespan).**
Run: `grep -r "db\." backend/ | grep -v "repos/" | grep -v "venv/" | grep -v "db.py" | grep -v "main.py"`
Expected: No output.

---
