# Modular Prompt Strategy Layer

**Date:** 2026-04-29  
**Status:** Approved

## Problem

The prompt layer has organically grown into four files (`prompt_builder.py`, `prompt_builder_v2.py`, `prompt_builder_meta.py`, `prompt_builder_fb.py`) with no clear extensibility model. Testing a different prompting approach — different role persona, copy rules, structural sections, model params — requires editing production code paths. There is no way to run experiments without touching live behavior.

## Goal

A config-driven prompt strategy system where:
- Strategies are YAML files, not code
- The current v2 approach is the default strategy
- Any API request can opt into a named strategy via a `strategy` parameter
- Strategies can override any prompt dimension: role, rules, structural sections, model, temperature, and inline variables
- Strategy ID is stored on each creative document for eval/comparison queries

## Architecture

```
backend/
  strategies/
    default.yaml          # encodes current v2 behavior exactly
    chain-of-thought.yaml # example experimental strategy
  services/
    strategy_registry.py  # loads + caches YAMLs at startup
    strategy_renderer.py  # Jinja2 rendering + variable resolution
```

The existing `prompt_builder*.py` files are **not deleted** — they remain as reference implementations. The pipeline stops calling them directly and routes through the renderer instead.

## YAML Schema

```yaml
name: string              # unique strategy identifier (matches filename)
description: string       # human-readable purpose

defaults:                 # strategy-specific variables (lowest priority)
  max_headline_words: 8
  max_body_words: 10
  cta_list: "Learn More | Sign Up | ..."

stages:
  copy:
    model: gemini-2.5-flash
    temperature: 0.9
    system: |             # Jinja2 template; all variables interpolated inline
      You are {{ role }}.
      {{ taxonomy }}
      {{ persona_block }}
      Copy rules:
      - headline: max {{ max_headline_words }} words
      {{ output_format }}

  image_prompt:
    model: gemini-2.5-flash
    temperature: 0.7
    system: |
      ...

  meta_copy:
    inherit: default      # copy this stage verbatim from the named strategy
    temperature: 0.8      # then apply field-level overrides on top (any of: model, temperature, system)

  image_gen:
    inherit: default
```

**Stages:** `copy`, `image_prompt`, `meta_copy`, `image_gen`

**`inherit`:** A stage can inherit from another strategy's same-named stage, then apply overrides. Inheritance is one level deep only (no chains).

## Variable Resolution

Variables are resolved in priority order, last wins:

| Priority | Source | Notes |
|---|---|---|
| 1 (lowest) | Strategy `defaults` block | Strategy-specific vars with fallback values |
| 2 | Pipeline context (computed) | `taxonomy`, `persona_block`, `strategy_block`, `instructions_block`, `ref_note`, `visual_source`, `logo_source` |
| 3 (highest) | API `extra_vars` field | Caller-supplied; can override defaults and pipeline context |

**Standard pipeline context variables:**

| Variable | Source |
|---|---|
| `taxonomy` | `_image_taxonomy()` based on which image types are present |
| `persona_block` | Formatted `persona_info` from project inputs |
| `strategy_block` | Formatted `creative_strategy` from project inputs |
| `instructions_block` | Formatted `instructions` from project inputs |
| `ref_note` | Reference ad note for image prompt stage |
| `visual_source` | "derived from product images" or "derived from product description" |
| `logo_source` | Logo instruction string based on `has_logo_images` |
| `output_format` | JSON output schema block for the stage — **locked, cannot be overridden by `extra_vars` or `defaults`** |

**Error handling:** Variables referenced in a template but absent from all three layers raise a `StrategyRenderError` at render time with a message naming the missing variable and strategy.

## StrategyRegistry

- Loaded once at app startup (FastAPI lifespan)
- Reads all `*.yaml` files from `backend/strategies/`
- Validates that every YAML has `name`, `description`, and at least one stage
- Exposes `get(strategy_id: str) -> dict` — raises `ValueError` with available IDs if not found
- Exposes `list_ids() -> list[str]` for API validation responses

## StrategyRenderer

- `render(strategy: dict, stage: str, context: dict, extra_vars: dict) -> RenderedStage`
- `RenderedStage`: `system_prompt: str`, `model: str`, `temperature: float`
- Resolves variable layers, then runs Jinja2 with `undefined=StrictUndefined` (fails loudly on missing vars)
- Applies `inherit` resolution before rendering

## API Changes

### `POST /api/projects` — new optional fields

```json
{
  "strategy": "chain-of-thought",
  "extra_vars": { "max_headline_words": 6, "tone": "urgent" }
}
```

- `strategy` defaults to `"default"` if omitted
- Unknown strategy ID → 422 response with `available_strategies: [...]`
- `extra_vars` defaults to `{}`

Both fields stored on the project document and passed through to `PipelineInputs`.

### `GET /api/strategies` (new)

Returns `{ "strategies": ["default", "chain-of-thought", ...] }` — lets the frontend enumerate available strategies.

## Pipeline Changes

`PipelineInputs` gains:

```python
strategy_id: str = "default"
extra_vars: dict = field(default_factory=dict)
```

The pipeline:
1. Loads the strategy from registry at the start of `run_pipeline_core`
2. Calls `StrategyRenderer.render(strategy, stage, context, extra_vars)` for each of the four stages
3. Passes `rendered.model` and `rendered.temperature` to each LLM call (replacing hardcoded values in `llm.py`)

## Creative Document Changes

Each creative document gains a `prompt_strategy` field:

```json
"prompt_strategy": {
  "id": "chain-of-thought",
  "extra_vars": { "max_headline_words": 6 }
}
```

Sits alongside `generated.prompt_used`. Enables MongoDB queries like `db.creatives.find({"prompt_strategy.id": "chain-of-thought"})` for eval comparisons.

## Known Constraint: Output Schema

Strategy templates can change all prompt text. They cannot change the output JSON field names (e.g., `headline`, `body_copy`, `cta`, `variations`) without a matching Pydantic model change in `schemas.py`. Output schema changes are intentionally a code boundary, not a config boundary.

## Default Strategy (`default.yaml`)

`default.yaml` encodes the exact current v2 behavior: same role text, same taxonomy injection, same copy rules, same temperatures (`copy: 0.9`, `image_prompt: 0.7`, `meta_copy: 0.8`), same model (`gemini-2.5-flash`). The pipeline behavior is identical when `strategy` is omitted.

## What Is Not In Scope

- Strategy versioning or history
- A/B test traffic splitting (strategies are explicitly chosen per request)
- UI for strategy selection (API parameter only for now)
- Hot-reload of strategy files without restart
