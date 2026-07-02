# Build Plan & Checklist

Plan for **Approach A** (primary). Each item is a small, shippable deliverable.

## Phases

**Phase 1 — Foundations**
- [ ] Product container: `products` collection + a step that gathers up to 5 tagged reference
      images (upload, or Firecrawl from the URL). *Done = a project produces a product with refs.*
- [ ] Format library: `formats` collection, seeded from what we already hold — the 3 recipes
      leaked verbatim from Higgsfield job payloads, then vision-decode the 40 saved preview
      images (`~/Downloads/higgsfield-templates/`; contact sheet in `docs/reference/`) into
      worded blueprints and keep the real-estate-relevant ones. *Done = first 3–10 format
      records exist.* (See [architecture.md](architecture.md) for the record schema.)

**Phase 2 — Generation**
- [ ] Atelier path: call `gpt-image-2` with the product refs + a template recipe. *Done = product +
      template → an on-brand static ad.*
- [ ] Template selector: pick the best template for a brief. *Done = brief → template chosen
      automatically.*
- [ ] Copy: personas + hook + USP + CTA (port from the existing persona work). *Done = brief →
      personas + ad copy.*

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
