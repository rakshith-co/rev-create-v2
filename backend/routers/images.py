import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from auth import require_auth
from fastapi.responses import Response

from repos import projects as projects_repo, creatives as creatives_repo, jobs as jobs_repo
from schemas import EditImageRequest, CreativeOut, ImageOut, SizeVariantRequest, BatchRegenerateRequest, RegenerateRequest, AsyncAccepted
from services.creative_registry import CreativeType, CreativeSource, find_subtype_by_dimensions, get_size_specs
from services.s3 import download_bytes, presign_url
from core.tasks import run_edit, run_regeneration, run_size_variants

router = APIRouter(prefix="/api/images", tags=["images"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.images")

# (size_label, dimensions, explicit_aspect_ratio)
# Aspect ratios are pinned explicitly — never auto-computed — to ensure
# the model generates the correct canvas shape for each placement.
PLATFORM_SIZES: dict[str, list[tuple[str, str, str]]] = {
    "meta": [
        ("Feed Square", "1080x1080", "1:1"),
        ("Feed Portrait", "1080x1350", "4:5"),
        ("Feed Landscape", "1200x628", "1.91:1"),
        ("Story / Reels", "1080x1920", "9:16"),
    ],
    "google": [
        ("Horizontal", "1200x628", "1.91:1"),
        ("Square", "600x600", "1:1"),
        ("Logo Square", "1200x1200", "1:1"),
        # 4:1 not supported; still we are able to generate a good variant by asking for 1200x300 and forcing 4:1 aspect ratio.
        ("Logo Rectangular", "1200x300", "4:1"),
    ],
}

PLATFORM_LABELS = {
    "meta":   "Meta (Facebook & Instagram)",
    "google": "Google Display Network",
}


def _to_out(doc: dict) -> CreativeOut:
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

    ad_copy = doc.get("ad_copy")
    if not ad_copy and doc.get("meta_ad_copy"):
        ad_copy = {
            "headline": None,
            "body_copy": None,
            "cta": None,
            "platforms": {
                "meta": doc.get("meta_ad_copy")
            }
        }

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        associations=associations,
        name=doc.get("name"),
        status=doc.get("status", "processing"),
        s3_key=s3_key or "",
        creative_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        uploaded=doc.get("uploaded"),
        ad_copy=ad_copy,
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
    )


@router.get("", response_model=list[ImageOut])
async def list_generated_images(
    client_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
):
    """List generated creatives (used for testing size variants)."""
    query: dict = {"source": CreativeSource.GENERATED}
    if client_id:
        query["client_id"] = client_id

    skip = (page - 1) * limit
    docs = await creatives_repo.list_generated(client_id=client_id, skip=skip, limit=limit)

    return [_to_out(d) for d in docs]


@router.get("/{image_id}", response_model=CreativeOut)
async def get_creative(image_id: str):
    """Get a single creative by ID."""
    doc = await creatives_repo.get(image_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Creative not found")
    return _to_out(doc)


@router.post("/batch-regenerate", response_model=AsyncAccepted, status_code=202)
async def batch_regenerate_images(
    body: BatchRegenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    Regenerate multiple creatives by their UUIDs.
    Creates new versions of the same variations, reusing the original prompts and source images.
    """
    new_creative_ids = []
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    for image_id in body.image_ids:
        original = await creatives_repo.get(image_id)
        if not original:
            raise HTTPException(status_code=404, detail=f"Creative {image_id} not found")

        new_id = str(uuid.uuid4())

        gen = original.get("generated") or {}
        version = gen.get("version", original.get("version", 1)) + 1
        variation_index = gen.get("variation_index", original.get("variation_index", 1))
        prompt = gen.get("prompt_used", "")
        metadata = original.get("metadata")
        generation_inputs = original.get("generation_inputs") or {}

        await creatives_repo.insert({
            "_id": new_id,
            "source": CreativeSource.GENERATED,
            "client_id": original.get("client_id", "revspot"),
            "associations": original.get("associations", []),
            "input_sources": original.get("input_sources"),
            "generation_inputs": generation_inputs,
            "name": f"{original.get('name', 'Creative')} (v{version})",
            "status": "pending",
            "s3_key": f"creatives/{new_id}.png",
            "error_message": None,
            "created_at": now,
            "metadata": metadata,
            "generated": {
                "prompt_used": prompt,
                "variation_index": variation_index,
                "version": version,
                "parent_id": image_id,
                "edit_instruction": None,
            },
            "ad_copy": original.get("ad_copy"),
        })
        new_creative_ids.append(new_id)

        background_tasks.add_task(run_regeneration, job_id, new_id, image_id, body.provider)

    await jobs_repo.insert({
        "_id": job_id,
        "type": "batch_regenerate",
        "creative_ids": new_creative_ids,
        "created_at": now,
    })

    return AsyncAccepted(job_id=job_id)


@router.post("/{image_id}/replace", response_model=CreativeOut)
async def replace_creative_image(
    image_id: str,
    file: UploadFile,
):
    """Replace a creative's image by uploading a new file. Overwrites S3 in-place, sets status=uploaded."""
    doc = await db.creatives.find_one({"_id": image_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Creative not found")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported type '{file.content_type}'. Use JPEG, PNG, or WEBP.")

    data = await file.read()
    s3_key = doc.get("s3_key") or doc.get("image_s3_key") or f"creatives/{image_id}.png"
    await upload_bytes(s3_key, data, content_type=file.content_type)

    updated = await db.creatives.find_one({"_id": image_id})
    return _to_out(updated)


@router.get("/{image_id}/download")
async def download_image(image_id: str):
    doc = await creatives_repo.get(image_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")

    s3_key = doc.get("s3_key") or doc.get("image_s3_key")
    if not s3_key:
        raise HTTPException(status_code=404, detail="Image S3 key not found")
        
    if doc["status"] != "done":
        raise HTTPException(status_code=400, detail="Image not ready")
    img_bytes = await download_bytes(s3_key)
    return Response(content=img_bytes, media_type="image/png")


def _format_meta_copy(meta_copy: dict | None) -> str:
    if not meta_copy:
        return ""
    lines = ["Meta Ad Copy:"]
    if "headline" in meta_copy:
        h = meta_copy["headline"]
        h_str = h[0] if isinstance(h, list) and h else h
        lines.append(f"  Headline: {h_str}")
    if "primary_text" in meta_copy:
        p = meta_copy["primary_text"]
        p_str = p[0] if isinstance(p, list) and p else p
        lines.append(f"  Primary Text: {p_str}")
    return "\n".join(lines)


async def _resolve_latest_creative(creative_id: str) -> dict | None:
    """Walk the edit chain forward and return the most recent done descendant."""
    doc = await creatives_repo.get(creative_id)
    if not doc:
        return None
    while True:
        child = await creatives_repo.find_latest_child(doc["_id"])
        if not child:
            break
        doc = child
    return doc


@router.post("/{image_id}/edit", response_model=AsyncAccepted, status_code=202)
async def request_edit(
    image_id: str,
    background_tasks: BackgroundTasks,
    instruction: str = Form(...),
    provider: Optional[str] = Form(None),
    ref_images: list[UploadFile] = File(default=[]),
):
    parent = await creatives_repo.get(image_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Image not found")

    new_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    parent_gen = parent.get("generated") or {}
    version = parent_gen.get("version", parent.get("version", 1)) + 1
    variation_index = parent_gen.get("variation_index", parent.get("variation_index", 1))
    generation_inputs = parent.get("generation_inputs") or {}
    ad_copy = parent.get("ad_copy") or {}

    await creatives_repo.insert({
        "_id": new_id,
        "source": CreativeSource.GENERATED,
        "client_id": parent.get("client_id", "revspot"),
        "associations": parent.get("associations", []),
        "input_sources": parent.get("input_sources"),
        "generation_inputs": generation_inputs,
        "name": f"{parent.get('name', 'Creative')} (Edit)",
        "status": "pending",
        "s3_key": f"creatives/{new_id}.png",
        "error_message": None,
        "created_at": now,
        "metadata": parent.get("metadata"),
        "generated": {
            "prompt_used": parent_gen.get("prompt_used", ""),
            "variation_index": variation_index,
            "version": version,
            "parent_id": image_id,
            "edit_instruction": instruction,
        },
        "ad_copy": ad_copy,
    })

    await jobs_repo.insert({
        "_id": job_id,
        "type": "edit",
        "creative_ids": [new_id],
        "edit_instruction": instruction,
        "created_at": now,
    })

    ref_images_data: list[tuple[bytes, str]] = [
        (await f.read(), f.content_type or "image/png") for f in ref_images
    ]

    background_tasks.add_task(run_edit, job_id, new_id, image_id, instruction, provider, ref_images_data)
    return AsyncAccepted(job_id=job_id)




@router.post("/{image_id}/regenerate", response_model=CreativeOut, status_code=202)
async def regenerate_image_endpoint(
    image_id: str,
    background_tasks: BackgroundTasks,
    body: RegenerateRequest = None,
):
    """
    Regenerate a specific creative by UUID.
    Creates a new version of the same variation, reusing the original prompt and source images.
    """
    original = await creatives_repo.get(image_id)
    if not original:
        raise HTTPException(status_code=404, detail="Creative not found")

    new_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4()) # Add job_id for single regenerate too
    now = datetime.now(timezone.utc)

    gen = original.get("generated") or {}
    version = gen.get("version", original.get("version", 1)) + 1
    variation_index = gen.get("variation_index", original.get("variation_index", 1))
    prompt = gen.get("prompt_used", "")
    metadata = original.get("metadata")
    generation_inputs = original.get("generation_inputs") or {}

    new_doc = {
        "_id": new_id,
        "source": CreativeSource.GENERATED,
        "client_id": original.get("client_id", "revspot"),
        "associations": original.get("associations", []),
        "input_sources": original.get("input_sources"),
        "generation_inputs": generation_inputs,
        "name": f"{original.get('name', 'Creative')} (v{version})",
        "status": "pending",
        "s3_key": f"creatives/{new_id}.png",
        "error_message": None,
        "created_at": now,
        "metadata": metadata,
        "generated": {
            "prompt_used": prompt,
            "variation_index": variation_index,
            "version": version,
            "parent_id": image_id,
            "edit_instruction": None,
        },
        "ad_copy": original.get("ad_copy"),
    }
    await creatives_repo.insert(new_doc)
    
    # Needs a job doc since run_regeneration updates it
    await jobs_repo.insert({
        "_id": job_id,
        "type": "regenerate",
        "creative_ids": [new_id],
        "created_at": now,
    })

    background_tasks.add_task(run_regeneration, job_id, new_id, image_id, body.provider if body else None)
    return _to_out(new_doc)




@router.post("/{image_id}/size-variants", response_model=AsyncAccepted, status_code=202)
async def request_size_variants(
    image_id: str,
    body: SizeVariantRequest,
    background_tasks: BackgroundTasks,
):
    target_id = body.creative_id or image_id
    if body.use_latest:
        parent = await _resolve_latest_creative(target_id)
    else:
        parent = await creatives_repo.get(target_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Creative not found")

    platform = body.platform.lower()
    if platform not in PLATFORM_SIZES:
        raise HTTPException(
            status_code=400, detail=f"Unknown platform '{platform}'. Choose from: {list(PLATFORM_SIZES)}")

    sizes = PLATFORM_SIZES[platform]
    if body.sizes:
        # Filter the sizes based on the provided list of dimensions
        sizes = [s for s in sizes if s[1] in body.sizes]
        if not sizes:
            raise HTTPException(
                status_code=400,
                detail=f"None of the provided sizes {body.sizes} are valid for platform '{platform}'",
            )

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # (image_id, size_label, dimensions, aspect_ratio)
    new_entries: list[tuple[str, str, str, str]] = []
    new_creative_ids = []

    parent_gen = parent.get("generated") or {}
    variation_index = parent_gen.get("variation_index", parent.get("variation_index", 1))
    version = parent_gen.get("version", parent.get("version", 1))
    parent_s3_key = parent.get("s3_key") or parent.get("image_s3_key")

    generation_inputs = parent.get("generation_inputs") or {}

    for size_label, dimensions, aspect_ratio in sizes:
        width = int(dimensions.split('x')[0])
        height = int(dimensions.split('x')[1])
        subtype = find_subtype_by_dimensions(dimensions)
        size_specs = get_size_specs(subtype)

        # Reuse the existing doc if it is still in-flight (avoids race condition where
        # delete_many would remove a doc that a concurrent background task is still updating).
        existing = await creatives_repo.find_size_variant(target_id, platform, width, height)

        if existing and existing["status"] in ("pending", "generating", "retrying"):
            new_id = str(existing["_id"])
            await creatives_repo.update(
                new_id,
                {"status": "pending", "error_message": None, "created_at": now},
            )
        else:
            if existing:
                new_id = str(existing["_id"])
                await creatives_repo.update(
                    new_id,
                    {"status": "pending", "error_message": None, "created_at": now},
                )
            else:
                new_id = str(uuid.uuid4())
                await creatives_repo.insert({
                    "_id": new_id,
                    "source": CreativeSource.GENERATED,
                    "client_id": parent.get("client_id", "revspot"),
                    "associations": parent.get("associations", []),
                    "input_sources": parent.get("input_sources"),
                    "generation_inputs": generation_inputs,
                    "name": f"{parent.get('name', 'Creative')} ({size_label})",
                    "status": "pending",
                    "s3_key": f"creatives/{new_id}.png",
                    "error_message": None,
                    "created_at": now,
                    "metadata": {
                        "type": CreativeType.IMAGE,
                        "subtype": subtype,
                        "size_specs": size_specs.model_dump(),
                        "platform": platform,
                        "size_label": size_label,
                    },
                    "generated": {
                        "prompt_used": parent_gen.get("prompt_used", ""),
                        "variation_index": variation_index,
                        "version": version,
                        "parent_id": target_id,
                        "edit_instruction": None,
                    },
                })

        new_entries.append((new_id, size_label, dimensions, aspect_ratio))
        new_creative_ids.append(new_id)

    await jobs_repo.insert({
        "_id": job_id,
        "type": "size_variants",
        "creative_ids": new_creative_ids,
        "created_at": now,
    })

    project_assoc = next(
        (a for a in parent.get("associations", []) if a.get("type") == "project"),
        None,
    )
    project_id = project_assoc["id"] if project_assoc else "unknown"

    # Read RERA number and QR key stored in generation_inputs at creation time
    rera_number: str | None = generation_inputs.get("rera_number") or None
    qr_s3_key: str | None = generation_inputs.get("qr_s3_key") or None

    if new_entries:
        background_tasks.add_task(run_size_variants, job_id, new_entries, target_id, platform, body.provider)

    return AsyncAccepted(job_id=job_id)


