# Build Plan & Checklist

Plan for **Approach A** (primary). Each item is a small, shippable deliverable.

## Phases

**Phase 1 — Foundations**
- [ ] Product container: `products` collection + a step that gathers up to 5 tagged reference
      images (upload, or Firecrawl from the URL). *Done = a project produces a product with refs.*
- [x] Format library: **done** — all 40 Marketing Studio previews decoded into worded
      blueprints + 6 RE-native drafts, one `.md` file per format in `backend/formats/`
      (compiled by `build.py`; 3 recipes anchored on leaked verbatim ground truth).

**Phase 2 — Generation**
- [x] Atelier strategy wired: `prompt_strategy=atelier` on the existing generate API
      (`backend/strategies/atelier.py` + format loader + registration). 14 unit tests pass;
      `python -m scripts.atelier_dry_run` prints every assembled prompt with no keys needed.
- [x] Format selector: done — rides the image-prompt LLM call (menu of 32 RE-relevant
      formats, `[format: id]` marker for observability).
- [x] Copy prompts: done — emotion-first headline + friend-voice pipe-separated facts,
      same strict AdCopy/meta JSON contracts the pipeline already parses.
- [ ] **First live generation** — blocked ONLY on `backend/.env` (`OPENAI_API_KEY` for
      gpt-image-2, `GEMINI_API_KEY` for copy/selector, `MONGO_URI`). Everything upstream is ready.

**Phase 3 — Quality & delivery**
- [ ] Input check + quality check: handle thin briefs; reject creatives that wouldn't perform,
      regenerate up to twice. *Done = weak inputs handled, weak outputs filtered.*
- [ ] End to end: Launchpad brief → engine → finished ads.

**Phase 4 — Scale**
- [ ] Grow the template library toward ~60.
- [ ] Feedback store: when an AM rejects a creative, save the correction and apply it next time.

## Fallback trigger

Move to [Approach B (Higgsfield)](approach-b-higgsfield.md) only if, after Phase 2, the quality
from our own `gpt-image-2` path is not good enough and can't be fixed quickly.

## Open inputs needed from PM

- Top 5–10 Meta ad formats to seed the template library.
- 5–10 example "gold" ads (defines the quality bar).
- `gpt-image-2` limits (max reference images, cost per call).
- Confirm the request/response shape Launchpad will call.
