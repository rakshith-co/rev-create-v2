# RevCreate V2 — Creative Engine for Launchpad

The execution engine behind **Launchpad**. Give it a campaign brief and it returns
**Meta-ready ad creatives** — images and ad copy. Launchpad calls it as a service; other surfaces
can too.

```
Campaign brief  →  RevCreate V2 engine  →  ad creatives  →  Meta
```

---

## What we're building

Our own version of what Higgsfield's Marketing Studio does — and we own it end to end. Three parts:

1. **Product container** — up to 5 reference images per project (logo, hero, interior, angles).
2. **Meta ad-template library** — proven Meta ad formats (before/after, price-drop, etc.). These
   are our "skills," added one at a time. They're what make a static *perform* as an ad, not just
   look good.
3. **`gpt-image-2`** — the image model that takes those references and produces genuinely
   different angles. (The existing RevCreate code already generates with it.)

> **Static creative vs static ad:** a creative looks good (awareness). An ad performs on Meta.
> We build **ads**.

---

## Two approaches (one chosen, one kept as backup)

| | **A — Build our own** *(primary)* | **B — Higgsfield** *(fallback)* |
|---|---|---|
| Idea | Product container + Meta templates on `gpt-image-2` | Wrap Higgsfield Marketing Studio behind a small service |
| Why | Full control, organised, no external dependency in the main path | Reuses Higgsfield's mature rendering |
| Trade-off | We build the template library | A wrapper on a wrapper; depends on Higgsfield |
| Status | **In progress** | Standby — only if A underdelivers |

Full detail in [`docs/`](docs/README.md): [Approach A](docs/approach-a-build-our-own.md) ·
[Approach B](docs/approach-b-higgsfield.md) · [Build plan](docs/build-plan.md).

---

## Status — 2026-06-25

- Architecture decided: **extend this codebase** (it already has the job API, MongoDB, S3, and
  `gpt-image-2`).
- Building **Approach A**. **Approach B** kept as a documented fallback.

---

## How it's built

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.12) + Uvicorn |
| Database | MongoDB |
| Storage | S3 (presigned URLs) |
| Image generation | `gpt-image-2` |
| Frontend | React + TypeScript + Vite + Tailwind |
| Deploy | Docker |

The engine is a **service with a bounded pipeline** — fixed steps, an LLM only at specific
decision points. It is *not* an open-ended agent.

---

## Run it locally

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# create backend/.env with: MONGO_URI, DB_NAME, S3 + model keys
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

> Secrets live in `.env` files (gitignored) — never commit keys.

---

## Documentation

- [Product plan & approaches](docs/README.md)
- [Approach A — Build our own](docs/approach-a-build-our-own.md) *(primary)*
- [Approach B — Higgsfield](docs/approach-b-higgsfield.md) *(fallback)*
- [Build plan & checklist](docs/build-plan.md)
