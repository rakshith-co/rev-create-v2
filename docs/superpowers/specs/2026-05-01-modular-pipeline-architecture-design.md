# Modular Pipeline Architecture Design

**Date:** 2026-05-01
**Branch:** architecture
**Status:** Approved

---

## Problem

The current backend has grown into a structure that is hard to extend and experiment with:

- `pipeline.py` is a 530-line monolith doing brand extraction, copy generation, image prompt generation, image search, image generation, compositing, and S3 upload all in sequence — no clean boundaries
- Parallel implementations exist (`pipeline.py` for Gemini, `pipeline_openai.py` for OpenAI) with duplicated logic
- Four prompt builder files with no shared interface — prompt text embedded in Python string functions
- No API-level control over which model or prompt strategy runs
- No automatic fallback when a provider fails
- No queue — all pipelines triggered simultaneously compete for API rate limits
- No symmetric input/output abstraction layer

---

## Architecture Pattern

**Hexagonal Architecture (Ports & Adapters)**

The `core/` package defines ports — Python `Protocol` interfaces for every swappable concern. All external infrastructure (LLM router, prompt templates, image search, post-processing, storage) is an adapter that implements a port. The pipeline core never imports a concrete class, only protocols.

Secondary patterns:
- **Strategy** — prompt strategies, search strategies
- **Chain of Responsibility** — post-processor list
- **State Machine** — the pipeline executor
- **Router** — LLM model selection and fallback

---

## Module Structure

```
backend/
├── core/
│   ├── protocols.py        # All Protocol interfaces + shared data models
│   ├── pipeline.py         # State machine runner
│   ├── config.py           # PipelineConfig, named presets
│   └── queue.py            # Two-level semaphore queue
│
├── llm/                    # LLM router layer (replaces providers/)
│   ├── base.py             # BaseLLM, LLMRequest, LLMResponse, ImageResponse
│   ├── router.py           # LLMRouter
│   ├── registry.py         # task_type → model_name defaults
│   └── adapters/
│       ├── gemini.py       # GeminiAdapter(BaseLLM)
│       └── openai.py       # OpenAIAdapter(BaseLLM)
│
├── strategies/
│   ├── v2.py               # V2Strategy — selects templates, builds context dict
│   ├── fb.py               # FBStrategy
│   └── templates/
│       ├── v2/
│       │   ├── copy_system.j2
│       │   ├── copy_user.j2
│       │   ├── image_prompt_system.j2
│       │   └── meta_copy_system.j2
│       └── fb/
│           ├── copy_system.j2
│           └── copy_user.j2
│
├── search/
│   ├── web.py              # WebImageSearch
│   └── noop.py             # NoOpSearch (when product images are provided)
│
├── postprocessors/
│   └── compositor.py       # RERACompositor (RERA text + QR overlay)
│
├── serializers/
│   └── mongo_s3.py         # MongoS3Serializer
│
├── deserializers/
│   ├── generate.py         # GenerateDeserializer (multipart + optional S3 keys)
│   ├── regenerate.py       # RegenerateDeserializer (reads existing creative from DB)
│   ├── edit.py             # EditDeserializer (reads creative from DB + instruction)
│   └── size_variant.py     # SizeVariantDeserializer (reads creative from DB + target sizes)
│
└── services/               # Non-swappable utilities — unchanged
    ├── s3.py
    ├── api_keys.py
    ├── creative_registry.py
    └── chat_agent.py
```

---

## LLM Router Layer (`llm/`)

The pipeline never calls a provider directly. All LLM calls go through `LLMRouter`, which selects the right model based on the request's `task_type` and handles fallback transparently.

### Contracts (`llm/base.py`)

```python
@dataclass
class LLMRequest:
    prompt: str
    task_type: str              # "brand_extraction" | "copy_generation" |
                                # "image_prompt_generation" | "image_edit"
    images: ImageBundle | None = None
    max_tokens: int = 512
    temperature: float = 0.7
    metadata: dict | None = None

@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: int
    cost: float
    raw: dict | None = None

@dataclass
class ImageResponse:            # image generation is distinct — no tokens, different cost model
    image_bytes: bytes
    model: str
    latency_ms: int
    cost: float

class BaseLLM:
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    def generate_image(self, request: LLMRequest) -> ImageResponse:
        raise NotImplementedError
```

`task_type` maps to pipeline states:

| Pipeline state | task_type |
|---|---|
| `EXTRACTING_BRAND` | `"brand_extraction"` |
| `GENERATING_COPY` | `"copy_generation"` |
| `GENERATING_IMAGE_PROMPT` | `"image_prompt_generation"` |
| `GENERATING_IMAGES` | `"image_generation"` |
| `EDITING` | `"image_edit"` |

### Router (`llm/router.py`)

```python
class LLMRouter:
    def __init__(self, models: dict[str, BaseLLM], registry: dict[str, str]):
        self.models = models
        self.registry = registry    # task_type → model_name

    def route(self, request: LLMRequest) -> LLMResponse:
        model_name = self.registry[request.task_type]
        try:
            return self._with_retry(lambda: self.models[model_name].generate(request))
        except ProviderTransientError:
            return self.models[self._fallback(model_name)].generate(request)

    def route_image(self, request: LLMRequest) -> ImageResponse:
        model_name = self.registry[request.task_type]
        try:
            return self._with_retry(lambda: self.models[model_name].generate_image(request))
        except ProviderTransientError:
            return self.models[self._fallback(model_name)].generate_image(request)

    def _fallback(self, failed: str) -> str:
        for name in self.models:
            if name != failed:
                return name
        raise RuntimeError("No fallback available")
```

> **Future improvement:** `_fallback` currently iterates over all registered models and returns the first that isn't the failed one — it ignores `task_type`, so it could return an image model as fallback for a text task. The fix is to make the registry express a `fallback` model per task_type alongside the `primary`, and have `_fallback(task_type)` read it directly. Deferred because we only have one model per task category today; becomes important when a second capable model is added for the same task type.

### Model Registry (`llm/registry.py`)

```python
DEFAULT_REGISTRY: dict[str, str] = {
    "brand_extraction":        "gemini-2.5-flash",
    "copy_generation":         "gemini-2.5-flash",
    "image_prompt_generation": "gemini-2.5-flash",
    "image_generation":        "gemini-3.1-flash-image",
    "image_edit":              "gemini-3.1-flash-image",
}
```

`llm/policy.py` is not present — routing is a direct `task_type → model_name` lookup. Scoring and budget-based selection can be introduced later if needed (see Portkey note in "What Is Not In Scope").

### Route Method Disambiguation

The pipeline state determines which router method is called — not `task_type`. `task_type` is metadata used only for model selection within the registry.

| Pipeline state | Router method |
|---|---|
| `EXTRACTING_BRAND`, `GENERATING_COPY`, `GENERATING_IMAGE_PROMPT` | `router.route()` |
| `GENERATING_IMAGES`, `EDITING` | `router.route_image()` |

A model registered for `"image_generation"` must implement `generate_image()`; a model registered for `"copy_generation"` must implement `generate()`. The adapter is responsible for raising `ProviderPermanentError` if the wrong method is called on it.

### Error Taxonomy

Adapters classify all provider exceptions before surfacing them. The router treats error classes differently:

| Error class | Examples | Router behaviour |
|---|---|---|
| `ProviderTransientError` | timeout, 429 rate limit, 503 unavailable | retry same model ≤3 times (exponential backoff), then fallback |
| `ProviderPermanentError` | 400 bad request, 401/403 auth, wrong modality | fail immediately — no retry, no fallback |
| `MalformedResponseError` | response received but unparseable into `LLMResponse`/`ImageResponse` | retry once, then fail |

Retry and fallback are distinct behaviours:
- **Retry** — same model, same request, after a transient failure. Exhausts retry budget before triggering fallback.
- **Fallback** — different model, only after retries are exhausted on the primary.

`PostProcessorError` and `SerializerError` are not router concerns — they propagate directly to the pipeline state machine, which transitions to `FAILED` without retry.

### Adapters (`llm/adapters/`)

Thin wrappers. Each adapter translates `LLMRequest` → provider SDK call → `LLMResponse | ImageResponse`. No business logic beyond translating provider-specific exceptions into the error taxonomy above.

`GeminiAdapter` additionally uses Google Search grounding when `task_type == "brand_extraction"`.

---

## Protocol Interfaces (`core/protocols.py`)

### Shared Data Models

```python
@dataclass
class ImageBundle:
    product_images: list[tuple[bytes, str]]   # (bytes, mime_type)
    ref_images: list[tuple[bytes, str]]
    logo_images: list[tuple[bytes, str]]

class BrandInfo(BaseModel):
    company_name: str | None
    tagline: str | None
    brand_voice: str | None
    target_personas: list[str]
    industry: str | None
    primary_color: str | None               # hex e.g. "#1A2B3C"
    secondary_colors: list[str]
    font_family: str | None
    font_style: str | None                  # "serif" | "sans-serif" | "display"

class AdCopyVariation(BaseModel):
    headline: str
    body_copy: str

class AdCopy(BaseModel):
    headline: str
    body_copy: str
    cta: str
    variations: list[AdCopyVariation]
    platforms: dict                         # keyed by platform name e.g. "meta"

class CreativeContext(BaseModel):
    creative_id: str
    rera_number: str | None
    qr_code_bytes: bytes | None
    ad_format: str
    variation_index: int

@dataclass
class PipelineInputs:
    product_name: str
    description: str
    ad_format: str
    client_id: str
    name: str
    images: ImageBundle
    associations: list[dict]
    persona_info: str = ""
    creative_strategy: str = ""
    instructions: str = ""
    count: int = 4
    rera_number: str | None = None
    qr_code_bytes: bytes | None = None
    product_image_keys: list[dict] = field(default_factory=list)
    ref_image_keys: list[dict] = field(default_factory=list)
    logo_image_keys: list[dict] = field(default_factory=list)
```

### API Request Models

```python
class GenerateRequestParams(BaseModel):
    product_name: str
    description: str
    ad_format: str
    name: str
    client_id: str = "revspot"
    persona_info: str = ""
    creative_strategy: str = ""
    instructions: str = ""
    count: int = 4
    rera_number: str | None = None
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    brand: dict = Field(default_factory=dict)   # caller-provided brand overrides
    # S3 keys for re-generation (no file upload needed)
    product_image_keys: list[dict] = Field(default_factory=list)
    ref_image_keys: list[dict] = Field(default_factory=list)
    logo_image_keys: list[dict] = Field(default_factory=list)

class RegenerateRequestParams(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

class EditRequestParams(BaseModel):
    instruction: str
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

class SizeVariantRequestParams(BaseModel):
    platform: str
    sizes: list[str] = Field(default_factory=list)  # empty = all sizes for platform
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
```

> **Implementation note:** All mutable defaults (`list`, `dict`, nested Pydantic models) use `Field(default_factory=...)`. Bare `= []` / `= {}` / `= PipelineConfig()` in Pydantic model definitions share the same object across instances — a silent footgun that causes cross-request state pollution.

### PromptStrategy

```python
class PromptStrategy(Protocol):
    def build_copy_system_prompt(self, context: dict) -> str: ...
    def build_copy_user_brief(self, context: dict) -> str: ...
    def build_image_prompt_system(self, context: dict) -> str: ...
    def build_meta_copy_system(self, context: dict) -> str: ...
    def build_image_prompt_brief(self, context: dict) -> str: ...
    def variation_hints(self) -> list[str]: ...     # per-variation style directives
```

Each method renders a Jinja template with the provided context dict. `variation_hints()` returns the strategy's list of per-variation style directives (previously `_VARIATION_HINTS` in `pipeline.py`).

### ImageSearchStrategy

```python
class ImageSearchStrategy(Protocol):
    async def find(
        self,
        product_name: str,
        description: str,
        ad_copy_text: str,
        persona_info: str,
        creative_strategy: str,
    ) -> tuple[bytes, str] | None: ...
```

### PostProcessor

```python
class PostProcessor(Protocol):
    async def process(self, image_bytes: bytes, context: CreativeContext) -> bytes: ...
```

Post-processors run as an ordered chain. Each receives the output of the previous.

### OutputSerializer

```python
class OutputSerializer(Protocol):
    async def write_creative(
        self,
        creative_id: str,
        inputs: PipelineInputs,
        ad_copy: AdCopy,
        prompt_used: str,
        variation_index: int,
        subtype: CreativeSubtype,       # from services/creative_registry.py
    ) -> None: ...

    async def upload_image(self, creative_id: str, image_bytes: bytes) -> str: ...
    async def mark_done(self, creative_id: str) -> None: ...
    async def mark_failed(self, creative_id: str, error: str) -> None: ...
```

### InputDeserializer

```python
class InputDeserializer(Protocol):
    async def parse(self, ...) -> tuple[PipelineInputs, PipelineConfig]: ...
```

Four concrete implementations — each takes different inputs matching its endpoint:

| Deserializer | Inputs | S3 fetch? |
|---|---|---|
| `GenerateDeserializer` | `GenerateRequestParams` + `UploadFile`s | Only for re-gen keys |
| `RegenerateDeserializer` | `creative_id` + `RegenerateRequestParams` | Yes — fetches source images |
| `EditDeserializer` | `creative_id` + `EditRequestParams` | Yes — fetches parent image |
| `SizeVariantDeserializer` | `creative_id` + `SizeVariantRequestParams` | Yes — fetches source images |

Each deserializer's `parse()` is responsible for two config steps before returning:
1. Resolve base `PipelineConfig` from `MODE_DEFAULTS[mode]`
2. Run the `POST_PROCESSOR_GUARDS` pruning pass against the parsed `PipelineInputs`

The returned `PipelineConfig.post_processors` is final — the pipeline runner uses it as-is.

---

## PipelineConfig (`core/config.py`)

```python
class PipelineConfig(BaseModel):
    mode: PipelineMode = PipelineMode.GENERATE
    prompt_strategy: str = "v2"
    image_search: str = "web"           # "web" | "none"
    post_processors: list[str] = Field(default_factory=list)  # populated from MODE_DEFAULTS, then pruned by guards
```

`brand` is a top-level API field separate from `pipeline`. The deserializer merges it as `overrides` before brand extraction runs, so the router only looks up what is missing.

Routing (model selection, fallback) is handled entirely by `LLMRouter` — not expressed in `PipelineConfig`. Named presets (e.g. `"default"`, `"fb"`) are defined in `config.py` and expand to a full `PipelineConfig`.

**Fallback trigger:** only `ProviderTransientError` (after retries exhausted) triggers fallback. `ProviderPermanentError` and `MalformedResponseError` propagate immediately without fallback. The pipeline state machine does not handle fallback — that responsibility belongs entirely to `LLMRouter`. See Error Taxonomy in the LLM Router section.

### Mode-Aware Post-Processor Defaults

`PipelineConfig` itself carries no default post-processors. Instead, `config.py` defines mode-level starting lists:

```python
MODE_DEFAULTS: dict[PipelineMode, PipelineConfig] = {
    PipelineMode.GENERATE:     PipelineConfig(post_processors=["compositor"]),
    PipelineMode.REGENERATE:   PipelineConfig(post_processors=[]),
    PipelineMode.EDIT:         PipelineConfig(post_processors=[]),
    PipelineMode.SIZE_VARIANT: PipelineConfig(post_processors=[]),
}
```

Deserializers resolve the appropriate `MODE_DEFAULTS` entry as their base config before applying any caller-provided overrides.

### Post-Processor Activation Guards

Each post-processor name maps to a predicate over `PipelineInputs`. After inputs are parsed, every deserializer runs a pruning pass:

```python
POST_PROCESSOR_GUARDS: dict[str, Callable[[PipelineInputs], bool]] = {
    "compositor": lambda inputs: bool(inputs.rera_number or inputs.qr_code_bytes),
}

# run in every deserializer after parse():
config.post_processors = [
    p for p in config.post_processors
    if POST_PROCESSOR_GUARDS.get(p, lambda _: True)(inputs)
]
```

Guards live in `config.py` only — deserializers run the pruning loop without knowing the conditions. A post-processor absent from `POST_PROCESSOR_GUARDS` is always included. This eliminates unnecessary post-processor runs and their API latency cost when the required inputs are not present in the request.

---

## State Machine (`core/pipeline.py`)

### Pipeline Modes

```python
class PipelineMode(str, Enum):
    GENERATE     = "generate"       # full pipeline — all states
    REGENERATE   = "regenerate"     # QUEUED → GENERATING_IMAGES → ...
    EDIT         = "edit"           # QUEUED → EDITING → ...
    SIZE_VARIANT = "size_variant"   # QUEUED → GENERATING_IMAGES → ... (different ad_format)
```

### States

```python
class PipelineState(str, Enum):
    QUEUED                  = "queued"
    EXTRACTING_BRAND        = "extracting_brand"
    GENERATING_COPY         = "generating_copy"
    GENERATING_IMAGE_PROMPT = "generating_image_prompt"
    SEARCHING_IMAGES        = "searching_images"
    GENERATING_IMAGES       = "generating_images"
    EDITING                 = "editing"
    POST_PROCESSING         = "post_processing"
    SERIALIZING             = "serializing"
    DONE                    = "done"
    FAILED                  = "failed"
```

### PipelineContext

```python
@dataclass
class PipelineContext:
    state: PipelineState
    inputs: PipelineInputs
    config: PipelineConfig
    router: LLMRouter
    strategy: PromptStrategy
    search: ImageSearchStrategy
    post_processors: list[PostProcessor]
    serializer: OutputSerializer
    # accumulated results
    brand_info: BrandInfo | None = None
    ad_copy: AdCopy | None = None
    image_prompt: str | None = None
    effective_product_images: list[tuple[bytes, str]] = field(default_factory=list)
    creative_ids: list[str] = field(default_factory=list)
```

### Transition Flows by Mode

**GENERATE** (full pipeline):
```
QUEUED → EXTRACTING_BRAND → GENERATING_COPY → GENERATING_IMAGE_PROMPT
       → SEARCHING_IMAGES → GENERATING_IMAGES → POST_PROCESSING → SERIALIZING → DONE
```

**REGENERATE / SIZE_VARIANT**:
```
QUEUED → GENERATING_IMAGES → POST_PROCESSING → SERIALIZING → DONE
```

**EDIT**:
```
QUEUED → EDITING → POST_PROCESSING → SERIALIZING → DONE
```

The runner resolves the state sequence from `config.mode` at start — no branching logic inside individual state handlers.

### Key State Handlers

**`GENERATING_IMAGES`** — `asyncio.gather` over N variations. Each variation acquires `image_semaphore` then calls `router.route_image(LLMRequest(task_type="image_generation", ...))`.

**`EDITING`** — calls `router.route_image(LLMRequest(task_type="image_edit", ...))` with the parent image bytes in `images.product_images[0]` and the instruction in `metadata`.

**`GENERATING_IMAGE_PROMPT`** — after the router returns, RERA scrubbing is applied inline (strips hallucinated RERA text when no RERA number was provided). This is a pipeline-level correctness invariant, not a strategy or adapter concern.

State is written to MongoDB on every transition. Resume mechanism: on app startup a background task queries MongoDB for creatives stuck in non-terminal states and re-queues their parent pipelines from the last safe checkpoint. `DONE` and `FAILED` are terminal.

### Observability Fields

Each state transition record written to MongoDB must include:

| Field | Description |
|---|---|
| `state` | The state entered |
| `entered_at` | UTC timestamp of transition |
| `model_selected` | Model name chosen by the router for this state (where applicable) |
| `fallback_chain` | List of models attempted before success, if fallback triggered |
| `prompt_strategy` | Strategy name used (e.g. `"v2"`) |
| `post_processors` | Final pruned post-processor list for this run |
| `error` | Error class + message on `FAILED` transition |

These fields are the minimum needed to debug routing regressions, quality issues, and stalled pipelines without re-running.

---

## Two-Level Queue (`core/queue.py`)

```python
pipeline_semaphore = asyncio.Semaphore(int(os.getenv("PIPELINE_CONCURRENCY", "5")))
image_semaphore    = asyncio.Semaphore(int(os.getenv("IMAGE_GEN_CONCURRENCY", "8")))
```

- **Pipeline semaphore** — acquired at `QUEUED → first active state`. Controls total concurrent pipeline runs.
- **Image semaphore** — acquired per variation inside `GENERATING_IMAGES` and `EDITING`. Controls total concurrent image API calls across all pipelines. Variations from different pipelines interleave as slots free up.

---

## Prompt Strategy + Jinja Templates

Prompt text lives in `.j2` files. The Python strategy class does two things only:
1. Select the right template file
2. Build the context dict

```python
class V2Strategy:
    _env = Environment(loader=PackageLoader("strategies", "templates/v2"))

    def build_copy_system_prompt(self, context: dict) -> str:
        return self._env.get_template("copy_system.j2").render(context)

    def variation_hints(self) -> list[str]:
        return [
            "",
            " Alternate layout: budget left-aligned, bold headline right, strong negative space.",
            " High-contrast dramatic lighting, deep shadows with sharp product highlight.",
            " Aspirational lifestyle context, warm ambient environment, human presence implied.",
        ]
```

---

## Brand Info

`BrandInfo` is the central brand kit flowing through the pipeline into every strategy call.

**Sources (merged, provided wins over extracted):**
1. **Caller-provided** — top-level `brand` field in the API request
2. **Extracted** — router calls `BaseLLM.generate(LLMRequest(task_type="brand_extraction", ...))`

`GeminiAdapter` uses Google Search grounding for brand extraction. `OpenAIAdapter` uses plain inference. Both return responses parseable into `BrandInfo`.

---

## Observability (Datadog)

Consistent with other revspot repos. `ddtrace` is the single integration point — it auto-instruments FastAPI, Motor (MongoDB), and outbound HTTP calls with zero manual wiring.

### APM + Tracing

`ddtrace-run` wraps the uvicorn process. Each inbound request gets a root span automatically. The pipeline adds child spans manually at two points:

**State transitions** — one span per state entered, tagged with the observability fields defined in the State Machine section:

```python
from ddtrace import tracer

with tracer.trace("pipeline.state", resource=state.value) as span:
    span.set_tag("pipeline.model_selected", model_name)
    span.set_tag("pipeline.prompt_strategy", config.prompt_strategy)
    span.set_tag("pipeline.creative_id", creative_id)
```

**LLM router calls** — one span per `route()` / `route_image()` call, tagged with model, task_type, fallback chain, and latency:

```python
with tracer.trace("llm.route", resource=request.task_type) as span:
    span.set_tag("llm.model", model_name)
    span.set_tag("llm.fallback", fallback_triggered)
```

### Custom Metrics

Emitted via `datadog.statsd` (DogStatsD):

| Metric | Type | Tags |
|---|---|---|
| `pipeline.duration` | histogram | `mode`, `status` (done/failed) |
| `llm.latency` | histogram | `task_type`, `model` |
| `llm.fallback` | count | `task_type`, `failed_model` |
| `llm.retry` | count | `task_type`, `model`, `attempt` |
| `postprocessor.duration` | histogram | `processor` |

### Log Correlation

`ddtrace` injects `dd.trace_id` and `dd.span_id` into every log record automatically when using standard Python `logging`. No manual changes to logging calls.

### New Environment Variables

```env
DD_API_KEY=<datadog-api-key>
DD_ENV=production          # or staging / dev
DD_SERVICE=rev-create
DD_VERSION=<git-sha>
DD_AGENT_HOST=localhost    # or Datadog Agent address in Docker
```

---

## Covered API Endpoints

| Endpoint | Mode | Router |
|---|---|---|
| `POST /generate` | `GENERATE` | `generate.py` (consolidates `generate.py`, `generate_openai.py`, `openai_v2.py`, `fb_form_banner.py`) |
| `POST /{id}/regenerate` | `REGENERATE` | `images.py` |
| `POST /batch-regenerate` | `REGENERATE` × N | `images.py` |
| `POST /{id}/edit` | `EDIT` | `images.py` |
| `POST /{id}/size-variants` | `SIZE_VARIANT` | `images.py` |

`generate_openai.py`, `openai_v2.py`, and `fb_form_banner.py` are deleted — they become named presets on the unified `/generate` endpoint. `compositor_test.py` is deleted.

---

## Authentication Migration

Current auth is key-based: `X-API-Key` header, SHA-256 hashed and looked up in MongoDB `api_tokens` collection via the `require_api_key` FastAPI dependency in `auth.py`.

**Target:** Auth0 JWT + API key dual strategy, consistent with other revspot repos.

### Strategy

Auth is **not a hard cutover**. The dependency tries JWT first; if that fails it falls back to API key. Both methods coexist during and after migration.

```
Authorization: Bearer <jwt>   →  Auth0 JWT validation (primary)
X-API-Key: rc_<token>         →  MongoDB hash lookup (fallback)
```

### AuthContext

`auth.py` exposes a single FastAPI dependency `require_auth` that returns an `AuthContext`:

```python
@dataclass
class AuthContext:
    user: dict          # Auth0 user info or {"org_name": <name>} for API key path
    is_admin: bool      # True when org_name == "revspot_admin"
    client: str | None  # org the request is scoped to (see Client Scoping below)
```

All routers replace `Depends(require_api_key)` with `Depends(require_auth())`. The return value changes from a raw token document to `AuthContext`.

### JWT Path

1. Extract `Bearer` token from `Authorization` header.
2. Validate via Auth0 JWKS (`RS256`, check `aud` == `AUTH0_AUDIENCE`).
3. Read `org_name` from JWT payload. If absent (Launchpad tokens), resolve via Auth0 Management API `get_user_orgs(sub)` — cache result in Redis at key `auth0-user-orgs:{sub}` (TTL 648000s).
4. `is_admin = org_name == "revspot_admin"`.
5. Fetch full user record — cache in Redis at `auth0-users:{sub}` (TTL 648000s).

### API Key Fallback

If JWT validation throws, fall back to MongoDB hash lookup (existing `require_api_key` logic). Admin identity on this path: `company_name == "revspot"`.

### Client Scoping

`require_auth` accepts a `require_client` flag (default `True`). When the function being protected accepts a `client` parameter:

| Caller | `require_client=True` | `require_client=False` |
|---|---|---|
| Regular user | `client = org_name` (always) | `client = org_name` (always) |
| Admin | must send `x-client` header | `client = None` (all-org access) |

In FastAPI this is handled by inspecting `Request` rather than `inspect.signature` (the Flask approach). Routers that need client scoping declare `client: str | None` in their path function and receive it from the dependency.

### Redis Dependency

User org resolution and user info lookups are cached in Redis. revCreate does not currently have Redis — options:

- **In-memory LRU cache** (`functools.lru_cache`) — acceptable for single-process; lost on restart. Simplest migration path.
- **Add Redis** — consistent with other repos, required if multiple workers run.

Defer Redis until multi-worker deployment. Use in-memory cache initially.

### Files Deleted

| File | Reason |
|---|---|
| `services/api_keys.py` | Token generation/hashing replaced by Auth0 |
| `routers/tokens.py` | Token lifecycle managed in Auth0 dashboard |

### New Environment Variables

```env
AUTH0_DOMAIN=<tenant>.auth0.com
AUTH0_AUDIENCE=<api-identifier>
AUTH0_CLIENT_ID=<m2m-client-id>        # for Management API (org resolution)
AUTH0_CLIENT_SECRET=<m2m-client-secret>
```

`ADMIN_SECRET` (used by `routers/tokens.py`) is removed.

---

## File Migration Map

| Before | After | Action |
|---|---|---|
| `services/pipeline.py` | `core/pipeline.py` | Rewritten as state machine |
| `services/pipeline_openai.py` | — | Deleted |
| `services/llm.py` | `llm/adapters/gemini.py` | Thin adapter |
| `services/image_model.py` | `llm/adapters/gemini.py` | Merged into adapter |
| `services/image_model_openai.py` | `llm/adapters/openai.py` | Thin adapter |
| `services/brand.py` | `llm/adapters/gemini.py` + `llm/adapters/openai.py` | Split into adapters |
| `services/prompt_builder*.py` | `strategies/` + `strategies/templates/` | Logic/content split |
| `services/image_search.py` | `search/web.py` | Moved |
| `services/compositor.py` | `postprocessors/compositor.py` | Moved |
| `routers/generate_openai.py` | — | Deleted (preset) |
| `routers/openai_v2.py` | — | Deleted (preset) |
| `routers/fb_form_banner.py` | — | Deleted (preset) |
| `routers/compositor_test.py` | — | Deleted |
| `auth.py` | `auth.py` | Rewritten — Auth0 JWT validation replaces key-based lookup |
| `services/api_keys.py` | — | Deleted (Auth0 migration) |
| `routers/tokens.py` | — | Deleted (Auth0 migration) |
| `services/s3.py` | `services/s3.py` | Unchanged |
| `services/creative_registry.py` | `services/creative_registry.py` | Unchanged |
| `services/chat_agent.py` | `services/chat_agent.py` | Unchanged |

---

## What Is Not In Scope

- Celery / Redis job queue (deferred — semaphore approach is the migration foundation)
- Video creative pipeline
- Stock image search (Unsplash / Getty)
- Multi-tenant brand profiles in DB (brand passed per-request for now)
- Cascade routing (cheap model draft → expensive model review) — foundation is in place
- Feedback loop / routing weight updates from user signals
- **Portkey gateway (optional future swap)** — Portkey's conditional routing and automatic fallback directly map to `LLMRouter`. If the custom routing layer grows complex, `llm/registry.py` and the two provider adapters can be replaced by a single `PortkeyAdapter` with routing config moved to Portkey. Custom implementation is used now to keep external dependencies minimal; the hexagonal architecture makes this swap localised to `llm/`.
