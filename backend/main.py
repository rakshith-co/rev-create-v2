import os

from dotenv import load_dotenv
load_dotenv()

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.errors import AppError

import db
from routers.projects import router as projects_router
from routers.images import router as images_router
from routers.logs import router as logs_router
from routers.generate import router as generate_router
from routers.creatives import router as creatives_router
from routers.jobs import router as jobs_router
from routers.chat import router as chat_router


logging.basicConfig(

    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("revCreate")

logger.info("ENV — GEMINI_API_KEY=%s MONGO_URI=%s S3_BUCKET=%s OPENAI_API_KEY=%s",                                                                                                   
      "set" if os.getenv("GEMINI_API_KEY") else "MISSING",                                                                                                           
      os.getenv("MONGO_URI", "MISSING"),                                                                                                                             
      os.getenv("S3_BUCKET_NAME", "MISSING"),      
      os.getenv("OPENAI_API_KEY", "MISING")                                                                                                                  
    ) 

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    logger.info("MongoDB connected")
    yield
    await db.close()
    logger.info("MongoDB disconnected")


app = FastAPI(title="revCreate API", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s %d (%.0fms)", request.method, request.url.path, response.status_code, ms)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(images_router)
app.include_router(logs_router)
app.include_router(generate_router)
app.include_router(creatives_router)
app.include_router(jobs_router)
app.include_router(chat_router)


@app.get("/health")
def health():
    return {"status": "ok"}
