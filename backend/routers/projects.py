import io
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from auth import require_auth
from fastapi.responses import StreamingResponse

import math
from repos import projects as projects_repo, creatives as creatives_repo

from schemas import BrandInfo, ImageOut, CreativeOut, Association, ProjectListResponse, ProjectOut, ProjectSummary, RegenerateRequest
from services.creative_registry import find_subtype_by_dimensions, get_size_specs, CreativeType, CreativeSource
from core.tasks import run_project_pipeline
from services.s3 import download_bytes, presign_url, upload_bytes
from services.compositor import validate_qr_upload

router = APIRouter(prefix="/api/projects",
                   tags=["projects"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.projects")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _img_doc_to_out(doc: dict) -> CreativeOut:
    s3_key = doc.get("s3_key")

    # Map old field names if they exist (for transition period)
    if "image_s3_key" in doc and not s3_key:
        s3_key = doc["image_s3_key"]

    # Handle both new and old document shapes
    generated = doc.get("generated")
    if not generated and "variation_index" in doc:
        generated = {
            "prompt_used": doc.get("image_prompt", ""),
            "variation_index": doc.get("variation_index", 1),
            "version": doc.get("version", 1),
            "parent_id": doc.get("parent_id"),
            "edit_instruction": doc.get("edit_instruction")
        }

    metadata = doc.get("metadata")
    if not metadata:
        # Synthesize metadata for old docs
        dims = doc.get("size_dimensions") or "1080x1080"
        subtype = find_subtype_by_dimensions(dims)
        specs = get_size_specs(subtype)
        metadata = {
            "type": CreativeType.IMAGE,
            "subtype": subtype,
            "size_specs": specs.model_dump()
        }

    # Backward compat: synthesize associations from legacy project_id field
    associations = doc.get("associations")
    if associations is None:
        project_id = doc.get("project_id")
        associations = [{"type": "project", "id": project_id}] if project_id else []

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        associations=associations,
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key or "",
        creative_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        uploaded=doc.get("uploaded"),
        meta_ad_copy=doc.get("meta_ad_copy"),
        created_at=doc["created_at"],
    )

async def _project_out(project_id: str) -> ProjectOut | None:
    doc = await projects_repo.get(project_id)
    if not doc:
        return None
    imgs = await creatives_repo.list_by_project(project_id)
    # Sort by variation_index and version from generated field
    imgs.sort(key=lambda d: (
        d.get("generated", {}).get("variation_index", d.get("variation_index", 1)),
        d.get("generated", {}).get("version", d.get("version", 1))
    ))
    return ProjectOut(
        id=str(doc["_id"]),
        name=doc.get("name", str(doc["_id"])),
        product_name=doc.get("product_name", ""),
        description=doc.get("description") or "",
        ad_format=doc.get("ad_format", "1080x1080"),
        client_id=doc.get("client_id", "revspot"),
        status=doc.get("status", "pending"),
        headline=doc.get("headline"),
        body_copy=doc.get("body_copy"),
        generated_cta=doc.get("generated_cta"),
        image_prompt=doc.get("image_prompt"),
        error_message=doc.get("error_message"),
        created_at=doc["created_at"],
        images=[_img_doc_to_out(i) for i in imgs],
        brand_info=BrandInfo(**doc["brand_info"]
                             ) if doc.get("brand_info") else None,
    )


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    client_id: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    if client_id == "revspot":
        query = {"$or": [{"client_id": "revspot"}, {"client_id": {"$exists": False}}]}
    elif client_id:
        query = {"client_id": client_id}
    else:
        query = {}

    total = await projects_repo.count(query)
    total_pages = math.ceil(total / limit) if total else 1

    docs = await projects_repo.list_many(
        query,
        {"product_images": 0, "ref_images": 0},
        skip=(page - 1) * limit,
        limit=limit,
    )

    result = []
    for doc in docs:
        pid = str(doc["_id"])
        image_total = await creatives_repo.count_by_project(pid)
        done = await creatives_repo.count_done_by_project(pid)
        result.append(
            ProjectSummary(
                id=pid,
                name=doc.get("name", pid),
                product_name=doc.get("product_name", ""),
                status=doc.get("status", "pending"),
                ad_format=doc.get("ad_format", "1080x1080"),
                client_id=doc.get("client_id", "revspot"),
                created_at=doc.get("created_at", ""),
                image_count=image_total,
                done_count=done,
            )
        )

    return ProjectListResponse(
        items=result,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.post("", response_model=ProjectOut)
async def create_project(
    background_tasks: BackgroundTasks,
    product_name: str = Form(...),
    description: str = Form(default=""),
    ad_format: str = Form(default="1080x1080"),
    client_id: str = Form(default="revspot"),
    product_images: List[UploadFile] = File(default=[]),
    ref_images: List[UploadFile] = File(default=[]),
    logo_images: List[UploadFile] = File(default=[]),
    rera_number: Optional[str] = Form(default=None),
    qr_code: Optional[UploadFile] = File(None),
    provider: Optional[str] = Form(default=None),
):
    project_id = str(uuid.uuid4())

    _MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

    async def _upload_images(uploads: List[UploadFile], prefix: str) -> list[dict]:
        result = []
        for i, upload in enumerate(uploads):
            if upload.filename and upload.content_type in ALLOWED_IMAGE_TYPES:
                data = await upload.read()
                ext = _MIME_EXT.get(upload.content_type, "png")
                key = f"inputs/{project_id}/{prefix}_{i}.{ext}"
                await upload_bytes(key, data, upload.content_type)
                result.append(
                    {"s3_key": key, "mime_type": upload.content_type})
        return result

    product_images_data = await _upload_images(product_images, "product")
    ref_images_data = await _upload_images(ref_images, "ref")
    logo_images_data = await _upload_images(logo_images, "logo")
    
    qr_code_data = None
    qr_code_bytes = await validate_qr_upload(qr_code)
    if qr_code_bytes and qr_code and qr_code.filename:
        ext = _MIME_EXT.get(qr_code.content_type, "png")
        key = f"inputs/{project_id}/qr_code.{ext}"
        await upload_bytes(key, qr_code_bytes, qr_code.content_type)
        qr_code_data = {"s3_key": key, "mime_type": qr_code.content_type}

    now = datetime.now()
    name = f"{product_name} — {datetime.now(timezone.utc).strftime('%b %d, %H:%M')}"

    await projects_repo.insert({
        "_id": project_id,
        "name": name,
        "product_name": product_name,
        "description": description,
        "ad_format": ad_format,
        "client_id": client_id,
        "product_images": product_images_data,
        "ref_images": ref_images_data,
        "logo_images": logo_images_data,
        "qr_code": qr_code_data,
        "rera_number": rera_number or None,
        "status": "pending",
        "headline": None,
        "body_copy": None,
        "generated_cta": None,
        "image_prompt": None,
        "error_message": None,
        "created_at": now,
    })

    logger.info(
        "\n=== API INPUT [create_project] ===\n"
        "  project_id   : %s\n"
        "  client_id    : %s\n"
        "  product_name : %s\n"
        "  ad_format    : %s\n"
        "  images       : product=%d  ref=%d  logo=%d\n"
        "  qr_code      : %s\n"
        "  description  :\n%s\n"
        "==================================",
        project_id, client_id, product_name,
        ad_format,
        len(product_images_data), len(ref_images_data), len(logo_images_data),
        "Yes" if qr_code_data else "No",
        description or "(none)",
    )
    background_tasks.add_task(run_project_pipeline, project_id, provider)
    logger.info("Project created — id=%s product=%r", project_id, product_name)

    out = await _project_out(project_id)
    return out


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    out = await _project_out(project_id)
    if not out:
        raise HTTPException(status_code=404, detail="Project not found")
    return out


@router.post("/{project_id}/stop", response_model=ProjectOut)
async def stop_project(project_id: str):
    doc = await projects_repo.get(project_id, {"_id": 1, "status": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    if doc.get("status") in ("ready", "failed", "stopped"):
        raise HTTPException(
            status_code=400, detail="Project is not in progress")

    await projects_repo.update(project_id, {"status": "stopped", "error_message": "Stopped by user"})
    await creatives_repo.update_many_by_project(
        project_id,
        {"status": "failed", "error_message": "Stopped by user"},
        status_filter=["pending", "generating", "retrying"],
    )
    logger.info("Project stopped — id=%s", project_id)
    out = await _project_out(project_id)
    return out


@router.post("/{project_id}/regenerate", response_model=ProjectOut)
async def regenerate_project(project_id: str, background_tasks: BackgroundTasks):
    doc = await projects_repo.get(project_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    if doc.get("status") in ("pending", "generating_copy", "generating_images"):
        raise HTTPException(
            status_code=400, detail="Project is still generating")

    now = datetime.now(timezone.utc)
    await creatives_repo.update_many_by_project(
        project_id,
        {"status": "pending", "error_message": None, "created_at": now},
    )
    await projects_repo.update(project_id, {
        "status": "pending",
        "headline": None,
        "body_copy": None,
        "generated_cta": None,
        "image_prompt": None,
        "error_message": None,
        "brand_info": None,
    })
    background_tasks.add_task(run_project_pipeline, project_id)
    logger.info("Project regenerating — id=%s", project_id)
    out = await _project_out(project_id)
    return out


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    deleted = await projects_repo.delete(project_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    await creatives_repo.delete_by_project(project_id)
    logger.info("Project deleted — id=%s", project_id)


@router.get("/{project_id}/download")
async def download_project(project_id: str, platform: str | None = None):
    doc = await projects_repo.get(project_id, {"name": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    imgs = await creatives_repo.list_done_by_project(project_id, platform)

    if not imgs:
        raise HTTPException(
            status_code=404, detail="No completed images to download")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        originals = [img for img in imgs if not (img.get("generated", {}).get("parent_id") or img.get("parent_id"))]
        variants = [img for img in imgs if (img.get("generated", {}).get("parent_id") or img.get("parent_id"))]

        # Group originals by variation_index to find the latest version
        latest_originals = {}
        for img in originals:
            vi = img.get("generated", {}).get("variation_index") or img.get("variation_index", 1)
            version = img.get("generated", {}).get("version") or img.get("version", 1)
            
            if vi not in latest_originals or version > (latest_originals[vi].get("generated", {}).get("version") or latest_originals[vi].get("version", 0)):
                latest_originals[vi] = img

        latest_original_ids = {str(img["_id"]) for img in latest_originals.values()}

        for vi, img in latest_originals.items():
            s3_key = img.get("s3_key") or img.get("image_s3_key")
            if not s3_key:
                continue
            img_bytes = await download_bytes(s3_key)
            version = img.get("generated", {}).get("version") or img.get("version", 1)
            fname = f"img{vi}/img{vi}_v{version}.png"
            zf.writestr(fname, img_bytes)

        for img in variants:
            s3_key = img.get("s3_key") or img.get("image_s3_key")
            if not s3_key:
                continue
            
            parent_id = img.get("generated", {}).get("parent_id") or img.get("parent_id")
            if str(parent_id) not in latest_original_ids:
                continue
                
            vi = img.get("generated", {}).get("variation_index") or img.get("variation_index", 1)
            plat = img.get("metadata", {}).get("platform") or img.get("platform", "unknown")
            size_label = img.get("metadata", {}).get("size_label") or img.get("size_label", "variant")
            size_label = size_label.replace(" / ", "-").replace(" ", "_")
            
            img_bytes = await download_bytes(s3_key)
            fname = f"img{vi}/{plat}/{size_label}.png"
            zf.writestr(fname, img_bytes)

    buf.seek(0)
    raw_name = doc.get("name", project_id)
    safe_name = raw_name.encode("ascii", "ignore").decode("ascii").replace(" ", "_").replace("/", "-")
    if not safe_name:
        safe_name = project_id
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
