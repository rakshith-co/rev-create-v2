import logging

from fastapi import APIRouter, Depends, HTTPException
from auth import require_auth

from schemas import JobOut, CreativeOut
from routers.images import _to_out
import repos.jobs as jobs_repo
import repos.creatives as creatives_repo
from core.queue import request_cancellation

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.jobs")


def _derive_job_status(creatives: list[CreativeOut], has_creative_ids: bool = False) -> str:
    if not creatives:
        return "processing" if has_creative_ids else "pending"
    
    statuses = [c.status for c in creatives]
    if all(s == "done" for s in statuses):
        return "done"
    if all(s == "failed" for s in statuses):
        return "failed"
    
    # Any other state is considered "processing"
    return "processing"


_TERMINAL_STATES = {"done", "failed", "cancelled"}

_CANCELLABLE_STATES = {
    "pending", "queued", "extracting_brand", "generating_copy", "generating_meta_copy",
    "generating_image_prompt", "searching_images", "generating_images",
    "post_processing", "serializing", "processing", "cancelling",
}


@router.post("/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str):
    job_doc = await jobs_repo.get(job_id)
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    current_status = job_doc.get("status", "")
    if current_status in _TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Job already {current_status}")

    # Signal the running pipeline (no-op if it already finished)
    was_running = request_cancellation(job_id)

    if was_running:
        # Pipeline will handle DB updates itself when it detects the flag
        await jobs_repo.update(job_id, {"status": "cancelling"})
        return {"job_id": job_id, "status": "cancelling"}
    else:
        # Pipeline not running (queued but not started, or already exited)
        creative_ids = job_doc.get("creative_ids", [])
        if creative_ids:
            await creatives_repo.update_many_by_ids(creative_ids, {"status": "cancelled"})
        await jobs_repo.update(job_id, {"status": "cancelled"})
        return {"job_id": job_id, "status": "cancelled"}


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str):
    job_doc = await jobs_repo.get(job_id)
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    creative_ids = job_doc.get("creative_ids", [])
    creative_docs = await creatives_repo.get_many(creative_ids) if creative_ids else []

    doc_map = {str(d["_id"]): d for d in creative_docs}
    creatives = [_to_out(doc_map[cid]) for cid in creative_ids if cid in doc_map]

    explicit_status = job_doc.get("status")
    
    # Granular pipeline states that should be returned as-is
    granular_states = (
        "queued", "extracting_brand", "generating_copy", "generating_meta_copy",
        "generating_image_prompt", "searching_images",
        "generating_images", "post_processing", "serializing",
        "cancelling", "cancelled", "failed", "done"
    )
    
    if explicit_status in granular_states:
        status = explicit_status
    else:
        status = _derive_job_status(creatives, has_creative_ids=bool(creative_ids))

    return JobOut(
        id=str(job_doc["_id"]),
        type=job_doc["type"],
        status=status,
        creative_ids=creative_ids,
        creatives=creatives,
        headline=job_doc.get("headline"),
        body_copy=job_doc.get("body_copy"),
        generated_cta=job_doc.get("generated_cta"),
        image_prompt=job_doc.get("image_prompt"),
        ad_copy=job_doc.get("ad_copy"),
        edit_history=job_doc.get("edit_history"),
        edit_instruction=job_doc.get("edit_instruction"),
        created_at=job_doc["created_at"],
    )
