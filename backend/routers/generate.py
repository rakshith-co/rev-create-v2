import json
import logging
import uuid
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends, BackgroundTasks

from auth import require_auth
from repos import jobs as jobs_repo
from schemas import AsyncAccepted
from services.creative_registry import CreativeSubtype
from deserializers.generate import GenerateRequestParams
from core.tasks import run_generate

router = APIRouter(prefix="/api/image", tags=["image"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.generate")


@router.post("/generate", response_model=AsyncAccepted, status_code=202)
async def generate(
    background_tasks: BackgroundTasks,
    product_name: str = Form(...),
    description: str = Form(default=""),
    ad_format: str = Form(default="1080x1080"),
    count: int = Form(default=4),
    client_id: str = Form(default="revspot"),
    persona_info: str = Form(default=""),
    creative_strategy: str = Form(default=""),
    instructions: str = Form(default=""),
    prompt_strategy: str = Form(default="v2"),
    image_search: str = Form(default="web"),
    provider: Optional[str] = Form(default=None),
    product_images: List[UploadFile] = File(default=[]),
    ref_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
    rera_number: Optional[str] = Form(default=None),
    associations: Optional[str] = Form(default=None),
    qr_code: Optional[UploadFile] = File(None),
):
    if count not in (1, 4):
        raise HTTPException(status_code=400, detail="count must be 1 or 4")

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    name = f"{product_name} — {now.strftime('%b %d, %H:%M')}"

    await jobs_repo.insert({
        "_id": job_id,
        "type": "generate",
        "creative_ids": [],
        "status": "pending",
        "created_at": now,
    })

    qr_code_bytes = None
    if qr_code:
        qr_code_bytes = await qr_code.read()

    from core.config import PipelineConfig
    parsed_associations = []
    if associations:
        try:
            parsed_associations = json.loads(associations)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="associations must be a valid JSON array")

    params = GenerateRequestParams(
        product_name=product_name,
        description=description,
        ad_format=ad_format,
        name=name,
        client_id=client_id,
        persona_info=persona_info,
        creative_strategy=creative_strategy,
        instructions=instructions,
        count=count,
        rera_number=rera_number or None,
        associations=parsed_associations,
        pipeline=PipelineConfig(
            prompt_strategy=prompt_strategy,
            image_search=image_search,
            provider=provider,
        )
    )

    background_tasks.add_task(run_generate, job_id, params, product_images, ref_images, logo_images, qr_code_bytes)

    return AsyncAccepted(job_id=job_id)
