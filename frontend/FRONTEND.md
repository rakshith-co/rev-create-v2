# revCreate Frontend

React + TypeScript + Vite single-page application for the revCreate AI ad generation pipeline.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | React 18.3.1 |
| Language | TypeScript 5.5.3 |
| Build tool | Vite 5.3.4 |
| Styling | Tailwind CSS 3.4.7 |
| HTTP client | Axios |
| ZIP downloads | JSZip |
| Production server | Nginx (Docker) |

---

## Directory Structure

```
frontend/
├── index.html                    # HTML shell, mounts #root
├── package.json
├── tsconfig.json
├── vite.config.ts                # Base path + dev proxy
├── tailwind.config.js            # Brand colour tokens
├── postcss.config.js
├── Dockerfile                    # Multi-stage build → nginx
├── nginx.conf                    # Proxies /api to backend:8000
├── .env                          # VITE_API_URL, VITE_API_KEY
└── src/
    ├── main.tsx                  # React root mount
    ├── App.tsx                   # All top-level state + view routing
    ├── api.ts                    # Axios wrappers for every endpoint
    ├── types.ts                  # Shared TypeScript interfaces
    ├── index.css                 # Tailwind directives + component layer
    ├── vite-env.d.ts             # ImportMetaEnv type declarations
    └── components/
        ├── CreateProjectForm.tsx # Upload form (product, ref, logo images)
        ├── ProjectDetail.tsx     # 2×2 variation grid + actions
        ├── ImageCard.tsx         # Single variation card
        ├── ImageDetailPanel.tsx  # Full edit/variant/download panel
        ├── SizeVariantModal.tsx  # Platform size picker modal
        ├── StatusBadge.tsx       # Coloured status pill
        ├── LogsList.tsx          # Pipeline run list with scores
        └── LogDetail.tsx         # Full log viewer + eval editor
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | No | Backend base URL. Empty = same origin (dev proxy handles it). Set to `https://your-backend.com` in production. |
| `VITE_API_KEY` | Yes | API token for `X-API-Key` header. Create via `POST /api/admin/tokens`. |

`.env` example:
```
VITE_API_URL=
VITE_API_KEY=rc_...
```

> In Docker builds inject `VITE_API_KEY` as a build arg since Vite bakes env vars at build time.

---

## Local Development

```bash
npm install
npm run dev          # http://localhost:5173
```

The Vite dev server proxies all `/api` requests to `http://localhost:8000` (see `vite.config.ts`).

```bash
npm run build        # TypeScript check + production bundle → dist/
npm run preview      # Serve dist/ locally
```

---

## Vite Configuration

```ts
// vite.config.ts
base: "/p/rev-create/"          // Subpath — change this for your deployment
server.proxy["/api"] → "http://localhost:8000"
```

**If deploying at root (`/`)** change `base` to `"/"`.

---

## Authentication

Every Axios request automatically includes:

```
X-API-Key: <VITE_API_KEY>
```

Set once at module load in `api.ts`:

```ts
axios.defaults.headers.common["X-API-Key"] = import.meta.env.VITE_API_KEY || "";
```

Any new `axios` call you add inherits this automatically.

---

## API Client (`src/api.ts`)

All backend calls are centralised here. Base URL = `${VITE_API_URL}/api`.

### Projects

| Function | Method | Endpoint |
|---|---|---|
| `createProject(form)` | POST | `/projects` — multipart FormData |
| `listProjects()` | GET | `/projects` |
| `getProject(id)` | GET | `/projects/:id` |
| `stopProject(id)` | POST | `/projects/:id/stop` |
| `regenerateProject(id)` | POST | `/projects/:id/regenerate` |
| `deleteProject(id)` | DELETE | `/projects/:id` |
| `projectDownloadUrl(id)` | — | Returns URL string for `/projects/:id/download` |

> `projectDownloadUrl` returns a bare URL string (used as `<a href>`), **not** an axios call. It does **not** send `X-API-Key`. If you add auth to the download endpoint, switch it to an axios call.

### Images

| Function | Method | Endpoint |
|---|---|---|
| `requestImageEdit(imageId, instruction)` | POST | `/images/:id/edit` |
| `requestSizeVariants(imageId, platform)` | POST | `/images/:id/size-variants` |

### Logs

| Function | Method | Endpoint |
|---|---|---|
| `listLogs()` | GET | `/logs` |
| `getLog(id)` | GET | `/logs/:id` |
| `updateLogEval(id, evalData)` | PATCH | `/logs/:id/eval` |

---

## State Architecture

All state lives in `App.tsx`. Components are presentational — they receive data and callbacks via props.

### Top-level state

```ts
view: "create" | "project" | "logs"   // which main view is shown
form: GenerateFormData                 // controlled form state
activeProject: ProjectOut | null       // currently open project
projectList: ProjectSummary[]          // sidebar list
isCreating: boolean                    // POST /projects in-flight
createError: string                    // creation error message
selectedVariation: number | null       // open image detail panel (1-4)
isLoadingProject: boolean              // loading spinner
isPolling: boolean                     // polling indicator
logList: LogSummary[]
activeLog: LogOut | null
```

### Polling

A `setInterval` at 2.5s polls `getProject(id)` while a project is active. Polling stops when:

```ts
status === "ready" || status === "failed" || status === "stopped"
  AND no image has status "pending" | "generating" | "retrying"
```

The interval ref is stored in `useRef` and cleared on view change or unmount.

---

## Views

### Create view
`CreateProjectForm` — three upload sections (product images, reference ads, brand logo). Submits via `createProject()`, then switches to project view and starts polling.

### Project view
`ProjectDetail` — shows the 4 variation `ImageCard`s in a 2×2 grid. Actions: **Stop**, **Regenerate**, **Download All** (ZIP via JSZip). Clicking a done image opens `ImageDetailPanel`.

### Logs view
`LogsList` — all pipeline runs. Clicking a row opens `LogDetail` as a full-height overlay panel. Log detail includes prompts, generated copy, images, and editable evaluation scores.

---

## Components

### `CreateProjectForm`

Props: `value: GenerateFormData`, `onChange`, `onSubmit`, `isLoading`, `error`

Contains a reusable `ImageUploadZone` (drag-and-drop + click, accepts jpg/png/webp, shows thumbnails with delete).

---

### `ProjectDetail`

Props: `project`, `onStop`, `onRegenerate`, `onDownloadAll`, `onSelectVariation`

Uses `latestPerVariation(images)` to always show the highest-version image per slot:

```ts
function latestPerVariation(images: ImageOut[]): Record<number, ImageOut>
```

---

### `ImageDetailPanel`

Props: `project`, `variationIndex`, `onClose`, `onEdit`, `onSizeVariants`

The most complex component. Manages:
- **Version history** — thumbnails of all versions for the selected variation, sorted by `version`
- **Size variants** — separated from versions using `is_size_variant` flag, grouped by platform
- **Edit input** — free-text instruction → `requestImageEdit()`
- **ZIP download** — organises images into `meta/` and `google/` folders via JSZip
- **SizeVariantModal** — platform + size picker

Size variant ZIP structure:
```
variation-1/
  meta/
    Feed Square (1080x1080).png
    Story - Reels (1080x1920).png
  google/
    Horizontal (1200x628).png
```

---

### `ImageCard`

Props: `image: ImageOut | undefined`, `variationIndex`, `onClick`

States: `done` (clickable + image), `generating/retrying/pending` (spinner), `failed` (error text).

---

### `StatusBadge`

Props: `status: string`

Statuses with spinning indicator: `pending`, `generating_copy`, `generating_images`, `generating`, `retrying`.

---

### `SizeVariantModal`

Props: `onGenerate(platform)`, `onClose`, `isLoading`

Platforms: `meta` (Feed Square, Feed Landscape, Story/Reels), `google` (Horizontal, Square, Logo Square, Logo Rectangular). Shows proportional size preview boxes.

---

### `LogsList`

Props: `logs`, `onSelect`

Computes average eval score across scored criteria. Score colour thresholds: green ≥ 8, yellow ≥ 5, red < 5.

---

### `LogDetail`

Props: `log`, `onClose`, `onSave(id, eval)`

Two-column layout (left: inputs/copy/prompts, right: images/eval). Eval scores are editable in 0.5 increments (1–10). Prompts section is collapsed by default.

---

## Type Definitions (`src/types.ts`)

Key interfaces for migration:

```ts
GenerateFormData        // form input
ProjectStatus           // "pending" | "generating_copy" | "generating_images" | "ready" | "failed" | "stopped"
ImageStatus             // "pending" | "generating" | "retrying" | "done" | "failed"
ImageOut                // image record with version, variation_index, is_size_variant, platform, size_label
ProjectOut              // project with images[], headline, body_copy, generated_cta, image_prompt
ProjectSummary          // lightweight list item
LogSummary / LogOut     // pipeline run record with eval criteria
```

---

## Styling

Tailwind dark theme. Base: `bg-gray-950 text-gray-100`.

Custom component classes in `index.css`:

| Class | Usage |
|---|---|
| `.input` | All form inputs — gray-800 bg, violet focus ring |
| `.label` | Form field labels — gray-400, xs |
| `.section-card` | Card container — gray-900 bg, gray-800 border, rounded-xl |
| `.section-title` | Section headings — gray-300, uppercase, tracking-wider |

Brand colour tokens (in `tailwind.config.js`):

```
brand-50   #f5f3ff
brand-500  #6d28d9
brand-600  #5b21b6
brand-700  #4c1d95
```

---

## Docker / Production

### Build

```bash
docker build \
  --build-arg VITE_API_KEY=rc_... \
  --build-arg VITE_API_URL=https://api.yourdomain.com \
  -t revcreate-frontend .
```

> Vite bakes env vars at build time. Pass them as `--build-arg` and expose them in the Dockerfile via `ARG` + `ENV` before `npm run build`.

The current Dockerfile does not declare these ARGs — add them if needed:

```dockerfile
ARG VITE_API_URL=""
ARG VITE_API_KEY=""
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_KEY=$VITE_API_KEY
```

### Nginx

`nginx.conf` proxies `/api` to `http://backend:8000` (the Docker Compose service name). Update `proxy_pass` if your backend hostname differs.

- Upload limit: `client_max_body_size 50M`
- API timeout: `proxy_read_timeout 120s`
- SPA fallback: `try_files $uri $uri/ /index.html`

---

## Migration Checklist

- [ ] Copy `src/`, `public/` (if any), `index.html`
- [ ] Copy `package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`, `postcss.config.js`
- [ ] Copy `Dockerfile`, `nginx.conf`
- [ ] Create `.env` with `VITE_API_URL` and `VITE_API_KEY`
- [ ] Update `base` in `vite.config.ts` if deploying at a different path
- [ ] Update `proxy_pass` in `nginx.conf` if backend hostname changes
- [ ] Add `ARG`/`ENV` lines to `Dockerfile` if injecting env vars at build time
- [ ] Update `vite-env.d.ts` if you add new `VITE_*` variables
- [ ] Run `npm install && npm run build` to verify no TS errors
