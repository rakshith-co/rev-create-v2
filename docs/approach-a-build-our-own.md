# Approach A — Build Our Own Engine (Primary)

## Summary

Build our own version of what Higgsfield's Marketing Studio does, and own it end to end.
Three parts: a **product container**, a **Meta ad-template library**, and **`gpt-image-2`** as
the image model. The existing RevCreate codebase already generates with `gpt-image-2`, so this
extends it rather than starting over.

## What Marketing Studio does, and our version

| Their part | What it does | Our version |
|---|---|---|
| Product container | User adds up to 5 images (logo, hero, interior, angles). The 5-image cap keeps outputs consistent. | A `products` record holding up to 5 tagged reference images. |
| Image model | GPT-image — handles several reference images and produces genuinely different angles. | `gpt-image-2`, already wired in RevCreate. |
| ~60 ad templates | Proven Meta ad formats (before/after, etc.). Picks the best one for the context. | Our **Meta ad-template library**. A selector picks the best template per brief. |

**Static creative vs static ad:** a creative looks good (awareness). An ad performs on Meta.
We build ads — the template library is what makes the difference.

## Flow

```
brief → assess input → build product (≤5 refs) → pick template → write copy
      → generate (gpt-image-2 + refs + template) → check quality → deliver
```

Each step is a single, bounded call. No open-ended agent loop.

## The template library = our "skills"

Each template is one Meta ad format, added one at a time:

```
id            before_after_v1
name          Before / After
meta_format   single_image
ref_slots     [hero]
prompt_recipe gpt-image-2 instruction with {slots}
notes         strong for renovation / transformation angles
```

Start with the top 5–10 formats (before/after, price-drop, location-advantage, amenity,
limited-offer), then grow toward ~60.

## Data (MongoDB)

```
products    one per project — up to 5 tagged refs (logo|hero|interior|angle), personas, style
templates   the ad-format library (schema above)
```

Generation references `product_id` + `template_id`. The grounding (refs + template) is the quality moat.

## What we still need from the PM

- The list of Meta ad formats to seed (start with the top 5–10).
- 5–10 example "gold" ads that define the quality bar.
- `gpt-image-2` limits: max reference images per call, cost per call.
