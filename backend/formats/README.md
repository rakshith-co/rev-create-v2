# Format Library — one file per ad format

Each `.md` file here is **one Meta ad format** (a "skill"). The file *is* the format:
a structured header + the worded layout blueprint the image model is prompted with.

This mirrors how Higgsfield stores its recipes internally (numbered snake_case prompt
artifacts like `37_hero_promo_burst`) — small named text files, versioned, reviewable.

## File anatomy

```markdown
---
id: hero_statement_v1          # stable id the engine references
name: Hero Statement
status: active | draft         # draft = blueprint not yet production-ready
source: higgsfield-decode | re-native-draft
re_relevance: 8                # 0-10 fit for premium real estate
copy_slots: ["headline", "subline", "cta"]
ref_slots: ["hero", "logo"]    # which product-container images it needs
use_when: ["launch", "premium"]  # what the select_format step matches on
---

# Hero Statement

## Blueprint
<the worded layout recipe — zones, % splits, type treatment.
 This text goes into the generation prompt.>

## Negatives
<what to forbid so it stays premium/editorial>

## Real-estate adaptation
<how the D2C layout maps to property creative>
```

## Rules

- **Edit the `.md` files, never `seeds/formats.json`** — that file is compiled.
- After any change: `python3 backend/formats/build.py` (validates + recompiles).
- New format = new file. Keep ids `snake_case_v1`; bump `_v2` for a redesign, don't
  mutate a version that has performance history against it.
- `status: draft` formats are excluded from selection until their blueprint is finished
  and flipped to `active`.
