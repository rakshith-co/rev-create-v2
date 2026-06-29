import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends

from auth import require_auth
from schemas import CreativeOut, CreativeSource, CreativeType, CreativeSubtype, MetaAdCopy
from services.creative_registry import get_size_specs
from services.s3 import upload_bytes, presign_url
import repos.creatives as creatives_repo

router = APIRouter(prefix="/api/creatives", tags=["creatives"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.creatives")

ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/quicktime", "video/webm",
}
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
}


def _to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key", "")
    ad_copy = doc.get("ad_copy")
    if not ad_copy and doc.get("meta_ad_copy"):
        ad_copy = {
            "headline": None,
            "body_copy": None,
            "cta": None,
            "platforms": {"meta": doc.get("meta_ad_copy")},
        }
    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.UPLOADED),
        metadata=doc.get("metadata", {}),
        client_id=doc.get("client_id", "revspot"),
        associations=doc.get("associations", []),
        name=doc.get("name"),
        status=doc.get("status", "done"),
        s3_key=s3_key,
        creative_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        uploaded=doc.get("uploaded"),
        ad_copy=ad_copy,
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
    )


@router.post("/upload", response_model=list[CreativeOut])
async def upload_creatives(
    subtype: CreativeSubtype = Form(...),
    name: str = Form(...),
    client_id: str = Form(default="revspot"),
    campaign_tag: str = Form(default=""),
    associations: Optional[str] = Form(default=None),
    primary_text: Optional[str] = Form(default=None),
    headline: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    call_to_action: Optional[str] = Form(default=None),
    files: List[UploadFile] = File(...),
):
    parsed_associations = []
    if associations:
        try:
            parsed_associations = json.loads(associations)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="associations must be a valid JSON array")

    now = datetime.now(timezone.utc)
    size_specs = get_size_specs(subtype)

    ad_copy = None
    if primary_text or headline or description or call_to_action:
        ad_copy = {
            "headline": None,
            "body_copy": None,
            "cta": None,
            "platforms": {
                "meta": {
                    "primary_text": primary_text or "",
                    "headline": headline or "",
                    "description": description or "",
                    "call_to_action": call_to_action or "",
                }
            },
        }

    created = []
    for upload in files:
        if upload.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{upload.content_type}' for '{upload.filename}'. Allowed: JPEG, PNG, WEBP, MP4, MOV, WEBM.",
            )

        doc_id = str(uuid.uuid4())
        ext = MIME_TO_EXT.get(upload.content_type, "bin")
        s3_key = f"creatives/{doc_id}.{ext}"

        data = await upload.read()
        await upload_bytes(s3_key, data, content_type=upload.content_type)

        creative_type = CreativeType.VIDEO if upload.content_type.startswith("video/") else CreativeType.IMAGE

        doc = {
            "_id": doc_id,
            "source": CreativeSource.UPLOADED,
            "client_id": client_id,
            "associations": parsed_associations,
            "name": name,
            "status": "uploaded",
            "s3_key": s3_key,
            "error_message": None,
            "created_at": now,
            "metadata": {
                "type": creative_type,
                "subtype": subtype,
                "size_specs": size_specs.model_dump(),
            },
            "uploaded": {
                "original_filename": upload.filename,
                "mime_type": upload.content_type,
                "campaign_tag": campaign_tag,
            },
            "ad_copy": ad_copy,
        }
        await creatives_repo.insert(doc)
        created.append(_to_out(doc))
        logger.info("Creative uploaded — id=%s name=%r type=%s", doc_id, name, creative_type)

    return created


@router.get("", response_model=list[CreativeOut])
async def list_all_creatives(
    client_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
):
    docs = await creatives_repo.list_all(
        client_id=client_id,
        skip=(page - 1) * limit,
        limit=limit,
    )
    return [_to_out(d) for d in docs]


@router.get("/{creative_id}", response_model=CreativeOut)
async def get_creative(creative_id: str):
    doc = await creatives_repo.get(creative_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Creative not found")
    return _to_out(doc)


@router.delete("/{creative_id}", status_code=204)
async def delete_creative(creative_id: str):
    deleted = await creatives_repo.delete(creative_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Creative not found")
    logger.info("Creative deleted — id=%s", creative_id)
