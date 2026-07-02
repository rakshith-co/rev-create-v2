# RevCreate V2 — Creative Engine

The execution engine for **Launchpad**. It takes a campaign brief and returns Meta-ready ad
creatives (images + ad copy). Launchpad calls it as a service; other surfaces can too.

```
Campaign brief  →  RevCreate V2 engine  →  ad creatives  →  Meta
```

## Two approaches (one chosen, one kept as backup)

We are building **Approach A**. **Approach B** is fully documented and kept as a fallback — not deleted.

| | **Approach A — Build our own** *(primary)* | **Approach B — Higgsfield** *(fallback)* |
|---|---|---|
| Idea | Our own marketing-studio: a product container + a Meta ad-template library, generated with `gpt-image-2` | Wrap Higgsfield's Marketing Studio behind a small service |
| Upside | Full control, organised, flexible, no external dependency in the main path | Reuses Higgsfield's mature rendering |
| Downside | We build the template library ourselves | A wrapper on top of a wrapper; depends on Higgsfield; extra auth overhead |
| Status | **In progress** | Standby — revisit only if A underdelivers |

## Documents

- [Approach A — Build our own](approach-a-build-our-own.md) *(primary)*
- [Engine architecture](architecture.md) — how it works internally, based on a full decode of
  Higgsfield's Marketing Studio mechanism
- [Approach B — Higgsfield](approach-b-higgsfield.md) *(fallback)*
- [Build plan & checklist](build-plan.md)

## Status — 2026-06-25

- Architecture decided: extend the existing RevCreate codebase (FastAPI + MongoDB + S3; already
  generates with `gpt-image-2`).
- Building Approach A.
- Approach B preserved as a documented fallback.
