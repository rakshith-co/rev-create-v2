# Engine Architecture

How the V2 engine works internally. Based on a full decode of how Higgsfield's Marketing Studio
actually operates (observed from its job payloads) — we replicate the mechanism and improve on it.

## What the decode showed

Marketing Studio is **not** a template system with slots and components. It is five simple pieces:

1. A fixed **system prompt** ("award-winning creative director").
2. ~40 **format recipes** — each "template" UUID is just a *worded layout description*, 2–4
   sentences (e.g. *"top 50% lifestyle photo, brand logo centered, bottom 50% dark gradient, big
   uppercase statistic headline…"*).
3. The **user prompt** (headline / subline / price / CTA / footer copy).
4. The **product images** passed as visual conditioning.
5. One **text-to-image pass** that draws the whole ad as flat pixels — layout, typography, text,
   everything. Nothing is assembled from parts; elements never move between templates. If an
   output looks like a mix, it's because the prompt asked for those elements together.

Their quality = **conditioning (real product images) + a good recipe + negatives** ("no starbursts,
no DTC clutter, editorial…"). All three are replicable. None of it is secret sauce in the model.

## Our engine — same mechanism, owned

```
brief + product
   │
   ├─ ① SELECT FORMAT     LLM picks the best format record for the brief (by use_when tags,
   │                      not by eyeballing previews)
   ├─ ② WRITE COPY        LLM fills the copy slots: hook / headline / subline / price / CTA / footer
   │
   ├─ ③ ASSEMBLE PROMPT   pure code: system prompt + format blueprint + copy + negatives
   │
   ├─ ④ GENERATE          gpt-image-2 · one pass · prompt + up to 5 product reference images
   │
   ├─ ⑤ POST-PROCESS      pure code: composite the REAL logo (generated logos garble),
   │                      RERA/fine-print strip (compositing already exists in this codebase),
   │                      safe-zone check
   │
   └─ ⑥ CRITIQUE          vision LLM: "would this perform as a Meta ad?" → regenerate with a
                          fix hint, max 2 retries
```

Steps ①, ②, ⑥ are single bounded LLM calls. ③ and ⑤ are plain code. No agent loop.

## The format record (one per Meta ad format — these are the "skills")

On disk, each format is **one `.md` file** in `backend/formats/` (frontmatter + worded blueprint —
see the README there), compiled into the record below. This mirrors how Higgsfield stores its own
recipes (numbered snake_case prompt artifacts like `37_hero_promo_burst`).

```jsonc
// collection: formats
{
  "_id": "stat_callout_lifestyle_v1",
  "name": "Lifestyle with Numbers",
  "blueprint": "top 50% lifestyle photo, brand logo centered, bottom 50% dark gradient, big uppercase statistic headline, supporting subline, CTA button bottom center",
  "negatives": "no starbursts, no discount badges, no DTC clutter, editorial, premium",
  "copy_slots": ["headline", "subline", "price", "cta", "footer"],
  "ref_slots":  ["hero", "logo"],
  "use_when":   ["stat-led", "premium", "location-advantage"],   // what the selector matches on
  "perf_notes": ""
}
```

## What lives where — format vs brand vs compositing

A deliberate split. Formats stay minimal **on purpose** (Higgsfield's own recipes are 2–4
sentences — if fat spec files made better ads, theirs would be fat):

| Concern | Lives in | Why |
|---|---|---|
| Layout grammar: zones, % splits, type *weight/hierarchy* ("massive condensed uppercase", "type = ⅓ of canvas") | **Format file** | This is the language the image model actually obeys |
| Exact colors, palette, logo, type vibe | **Brand kit on the product record** | Brand-specific, injected at prompt assembly — a format hardcoding a color breaks on the next builder |
| Pixel-exact elements: logo, RERA fine print, (optionally) CTA / price pill | **Compositing in code (step ⑤)** | The model can never be trusted with these; composite the real pixels |
| Fonts, hex-precise type | **Not in prompts** | Text-to-image ignores px/font-name precision; if type fidelity becomes critical for a format, flip that format to scene-only generation + code-composited text (per-format flag, future) |

### How color is actually decided (the precedence chain)

Observed from Marketing Studio: coloring is **automatic** — most users provide no brand kit and
mediocre product images, and outputs still look coherent. The mechanism, in precedence order:

1. **Recipe → tonal structure.** Blueprints hardcode the skeleton ("dark bg", "warm solid canvas",
   "white panel"), never the hue.
2. **Conditioning image → anchor hues.** No palette-extraction code exists; the image model itself
   reads dominant colors off the product refs and harmonizes around them.
3. **The model's aesthetic prior → everything else.** Trained on millions of professional ads,
   it defaults to good color harmony when inputs give no signal. This is what makes bad inputs
   still produce decent ads.

**Our default path is the same: no brand kit required — let the model auto-harmonize.**
The brand kit is an *optional override* for clients with strict guidelines:

```jsonc
"brand_kit": {                   // OPTIONAL — absent = auto-harmonize (the MS default)
  "palette": [{ "name": "deep forest green", "hex": "#1D3B2A", "role": "primary" }],
  "logo_url": "...",             // the composited one — never generated
  "type_vibe": "elegant serif, editorial"
}
```

Where brand color must be *exact* (developer's logo red, a CTA chip), prompt steering is hope —
**compositing is enforcement** (step ⑤).

> Calibration test (first thing after the OpenAI key lands): same format, minimal blueprint vs
> hex/font-stuffed prompt — measure what the model actually obeys instead of arguing about it.

## Seeding the format library

We already hold the raw material:

- **Three recipes leaked verbatim** in Higgsfield job payloads (hero-promo-burst,
  stat-callout-lifestyle, curiosity-scroll-stop) → first three records, near-verbatim.
- **All 40 preview images saved locally** (`~/Downloads/higgsfield-templates/`, contact sheet in
  `docs/reference/`) → run each through a vision model to draft its worded blueprint → human-curate
  → keep the ones that fit real estate.
- **Add RE-native formats they don't have** (RERA-compliant footer, price-pill launch,
  location/connectivity map callout…). This is where we beat them — their 40 are D2C-biased.

## Where we're better than Marketing Studio

| Their weakness | Our fix |
|---|---|
| Generated logos garble | Always composite the real logo in code (⑤) |
| Fine print / RERA garbles | Composite as pixels — already built in this codebase |
| D2C-biased formats | RE-native format library |
| No feedback loop | `corrections` store keyed by format_id, injected into ① and ⑥ |
| Shared-account token pain, no control | Our stack, our keys |

## Components already in this codebase

- Job API (`POST /api/image/generate` → job_id → poll) · pipeline state machine · `LLMRouter`
  with fallback · S3 + presigned URLs · Mongo · `gpt-image-2` wiring · RERA compositing ·
  the V2 prompt strategy's image-role taxonomy (product / reference / logo).

New work = the `formats` + `products` collections, the four bounded steps, and the prompt assembler.
