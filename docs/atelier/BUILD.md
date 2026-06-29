# Atelier (RevCreate V2) — Build Packet

**One-line:** Launchpad sends a campaign spec → this engine returns Meta-performant ad creatives.
We **build our own Marketing-Studio-equivalent** on top of RevCreate (which already wraps
`gpt-image-2`) — a **Product container** + a **Meta ad-template library** + GPT-image as the
multi-reference base. We do **not** wrap Higgsfield.

> Locked decisions: extend RevCreate · bounded pipeline (no agent runtime) · **own the generation
> stack on `gpt-image-2`** · Higgsfield/MCP **deprioritized** (wrapper-of-a-wrapper = logistically
> hard; kept only as a future alt backend) · Product Catalog + Templates in Mongo.

---

## Plan change log
- **v1 (2026-06-25):** extend RevCreate; reach Higgsfield Marketing Studio via an MCP sidecar.
- **v2 (2026-06-25, PIVOT — current):** **drop the Higgsfield wrapper.** A wrapper-of-a-wrapper is
  logistically fragile and "very unorganized for our product." Instead **replicate what Marketing
  Studio does, and own it**: Product container + Meta template library + `gpt-image-2`. This is the
  "top-of-infrastructure with lots of Meta skills." Higgsfield drops to lowest priority.

---

## What Marketing Studio actually does (reverse-understood) — and our version

| MS pillar | What it does | Our version |
|---|---|---|
| **Product container** | User adds ~5 images (logo + hero + interior + angles). The 5-cap is intentional — limits deviation. References are pulled from these. | `products` collection holding ≤5 role-tagged reference images. |
| **Base model** | GPT-image (multi-image reference → genuinely *different* angles). Nano-Banana/Gemini repeats the same image even when asked to vary; GPT-image varies. | **`gpt-image-2`** — already wired in rev-create (`openai/gpt-image-2-2026-04-21`). |
| **~60 ad templates** | Static **ADS** (perform on Meta) — before/after, etc. — not just static *creatives* (pretty/awareness). Picks the best template for context. | **Meta ad-template library** = the "skills." A selector maps brief+context → best template. |

> **Static creative vs static ad:** a *creative* looks good on paper (awareness). An *ad* performs
> on Meta. We build **ads**. The template library is what makes the difference.

---

## Architecture

```
 Product container (≤5 refs: logo · hero · interior · angle)
            +
 Meta ad-template library  ──►  template selector (best fit for brief/context)
            ↓
 gpt-image-2  (multi-reference, varied angles)   ← already in RevCreate
            ↓
 static AD (Meta-performant)
```

Everything organized, owned, and flexible — no MCP call in the hot path.

---

## The "skills" = Meta ad templates (your PM's metric, finally grounded)

Each **skill = one Meta ad format**, independently shippable:
```jsonc
// collection: templates
{
  "_id": "before_after_v1",
  "name": "Before / After",
  "meta_format": "single_image",
  "ref_slots": ["hero"],                 // which container images it needs
  "layout_spec": "split frame, label strips, ...",
  "prompt_recipe": "<gpt-image-2 instruction template with {slots}>",
  "perf_notes": "strong for transformation/renovation angles"
}
```
Start with the top **5–10** (before/after, price-drop, location-advantage, amenity-highlight,
limited-offer…), prove the loop, then grow toward the ~60. One skill at a time = clean PM units.

---

## Pipeline (extend `core/pipeline.py`, `prompt_strategy=atelier`)

```
QUEUED
 → ASSESS_INPUT       ① is the brief/site rich enough? what to amplify?
 → ENSURE_PRODUCT     ② gather ≤5 role-tagged reference images → product record
 → SELECT_TEMPLATE    ③ pick best Meta template for the brief/context
 → SYNTHESIZE_COPY    ④ personas + hook + USP + CTA  (port from Niya persona-engine)
 → GENERATE           gpt-image-2 with {product refs + template recipe + copy}
 → CRITIQUE           ⑤ "would this PERFORM as a Meta ad?" → else regenerate (max 2)
 → SERIALIZE → DONE
```

Each ①–⑤ is one structured LLM call / selection. No agent loop.

---

## Skill / decision contracts

- **`assess_input`** — `{name, description, scraped_text}` → `{richness, gaps[], amplify_plan[], usable}`
- **`ensure_product`** — `{project_id, url?, uploaded_images?}` → product with ≤5 role-tagged refs
  (`logo|hero|interior|angle`). Source: manual upload, or Firecrawl pull from URL (100k credits).
- **`select_template`** — `{brief, context, product}` → `{template_id, why}`
- **`synthesize_copy`** — `{assess, product, persona}` → `{hook, usp, pain_point, cta, ad_copy}`
- **`critique_creative`** — `{image_url, template, brief}` → `{pass, issues[], fix_hint?}` ·
  pass bar = **Meta-performant**, not "pretty." Max 2 regenerations.

> **Learning (build explicitly, later):** AM rejects a creative → write `{template_id, pattern, correction}`
> to a `corrections` collection; `select_template` + `critique` inject applicable ones next time.

---

## Data model (Mongo)

```jsonc
// products  (one per project, referenced by product_id everywhere)
{ "_id","project_name","ref_images":[{ "role":"logo|hero|interior|angle","url" }],  // ≤5
  "personas":[...], "style_id":"...", "source_url":"..." }

// templates  (the skill library) — schema above
// corrections (the feedback store) — later
```
Generation references `product_id` + `template_id` only. The grounding (refs + template) is the moat.

---

## Build sequence (PM checklist — each line shippable)

- [ ] **1. Product container** — `products` collection + `ensure_product` (≤5 role-tagged refs;
      upload + Firecrawl). *Deliverable: a project → a product with references.*
- [ ] **2. Template library** — `templates` collection + **3 seed templates** (before/after,
      price-drop, location-advantage). *Deliverable: 3 real Meta ad templates.*
- [ ] **3. Atelier strategy** — `gpt-image-2` call with product refs + template recipe. *Deliverable:
      product + template → on-brand static **ad**.*
- [ ] **4. `select_template`** — brief/context → best template. *Deliverable: auto template pick.*
- [ ] **5. `synthesize_copy`** — port Niya persona-engine. *Deliverable: brief → personas + copy.*
- [ ] **6. `assess_input` + `critique_creative`** — judgment + capped retry. *Deliverable: thin
      input handled; non-performant statics rejected.*
- [ ] **7. End-to-end** — Launchpad spec → `/api/image/generate` (atelier) → job_id → poll → ads.
- [ ] **8. Grow the library** toward ~60 templates · `corrections` feedback store.
- [ ] **9. (Deprioritized) Higgsfield** as an *alternative* backend only — revisit if our
      gpt-image path underdelivers or they grant a clean REST token.

---

## Inputs still needed from PM
- The list of Meta ad formats to seed (your ~60 — start with the top 5–10).
- 5–10 "gold" reference **ads** (defines `critique_creative`'s Meta-performance bar — the moat).
- `gpt-image-2` limits: max reference images per call, cost/call.
- Firecrawl fields needed for `ensure_product` image extraction.
