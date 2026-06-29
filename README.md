# revCreate

AI-powered ad creative generator for real estate and product advertising. Tell us about the project, upload product images and an optional reference ad, and revCreate generates performance-optimized Meta/Instagram ad creatives — headline, body copy, CTA, and 4 image variations.

## Features

- Provide the project name and mention all its details in the description
- Upload product images and optional reference ad images (used as structural/style template)
- AI-generated copy: headline, body copy with pipe-separated details (config | price | location), and CTA
- 4 image variation outputs per project using Gemini image generation
- In-app image editing via natural language instructions
- Project management with status tracking and ZIP download
- Pipeline audit logs with eval support

## Tech Stack

| Layer            | Technology                                 |
| ---------------- | ------------------------------------------ |
| Frontend         | React 18 + TypeScript + Vite + TailwindCSS |
| Backend          | FastAPI (Python 3.12) + Uvicorn            |
| Database         | MongoDB (via Motor async driver)           |
| Copy generation  | Gemini 2.0 Flash (multimodal)              |
| Image generation | Gemini 3.1 Flash Image Preview (`gemini-3.1-flash-image-preview`) |
| Deployment       | Docker (nginx frontend + uvicorn backend)  |

## Project Structure

```
revCreate/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── db.py                 # MongoDB connection
│   ├── schemas.py            # Pydantic models
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── routers/
│   │   ├── projects.py       # Project CRUD + ZIP download
│   │   ├── images.py         # Image retrieval + editing
│   │   └── logs.py           # Pipeline audit logs
│   └── services/
│       ├── pipeline.py       # Main generation workflow
│       ├── llm.py            # Copy generation (Gemini)
│       ├── image_model.py    # Image generation + editing (Gemini)
│       └── prompt_builder.py # Prompt construction
└── frontend/
    ├── src/
    │   ├── App.tsx            # Root component + state
    │   ├── api.ts             # API client (Axios)
    │   ├── types.ts           # TypeScript interfaces
    │   └── components/        # UI components
    ├── Dockerfile
    ├── nginx.conf             # SPA routing + /api proxy
    └── vite.config.ts
```

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- MongoDB (local or Atlas)
- Google Gemini API key

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GEMINI_API_KEY=your_key_here
MONGO_URI=mongodb://localhost:27017
DB_NAME=revCreate
```

```bash
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api` requests to `http://localhost:8000`.

## Docker Deployment

Build and run both containers on a shared network:

```bash
docker network create revcreate-net

docker build -t revcreate-backend ./backend
docker run -d --name backend --network revcreate-net \
  --env-file backend/.env \
  revcreate-backend

docker build -t revcreate-frontend ./frontend
docker run -d --name frontend --network revcreate-net \
  -p 80:80 \
  revcreate-frontend
```

The frontend nginx proxies all `/api` requests to the backend container on the internal network.

## Environment Variables

| Variable         | Where          | Description                                               |
| ---------------- | -------------- | --------------------------------------------------------- |
| `GEMINI_API_KEY` | backend        | Google Gemini API key                                     |
| `MONGO_URI`      | backend        | MongoDB connection string                                 |
| `DB_NAME`        | backend        | Database name (default: `revCreate`)                      |
| `VITE_API_URL`   | frontend build | API base URL injected at build time (empty = same origin) |

## Model Notes

### Image Generation: `gemini-3.1-flash-image-preview` vs `gemini-3-pro-image-preview`

When generating ad statics with reference ads and product images as inputs, `gemini-3.1-flash-image-preview` produces better results than `gemini-3-pro-image-preview`. The flash model more accurately follows the dual-image taxonomy (Type A product images as visual source, Type B reference ads as layout-only wireframe) and generates cleaner ad compositions with correct branding when both input types are provided.

## Marketplace Deployment

This project follows the [marketplace.revspot.ai](https://marketplace.revspot.ai) deployment spec:

- API calls use `import.meta.env.VITE_API_URL` (injected at build time)
- Vite base path is hardcoded to `/`
- Frontend nginx proxies `/api` to the backend container on the internal Docker network
- No hardcoded domains or slugs in application code

To package for upload:

```bash
zip -r rev_create.zip . -x "**/node_modules/*" -x ".git/*" -x "**/__pycache__/*" -x "**/venv/*" -x "assets/*" -x "outputs/*" -x ".vscode/*"
```
