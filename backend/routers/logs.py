import logging

from fastapi import APIRouter, Depends, HTTPException
from auth import require_auth

from schemas import CreativeOut, LogOut, LogSummary, UpdateEvalRequest
from services.creative_registry import CreativeType, CreativeSource, find_subtype_by_dimensions, get_size_specs
import repos.creatives as creatives_repo
import repos.logs as logs_repo

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_auth())])
logger = logging.getLogger("revCreate.logs")


def _img_doc_to_out(doc: dict) -> CreativeOut:
    from services.s3 import presign_url
    s3_key = doc.get("s3_key")

    if "image_s3_key" in doc and not s3_key:
        s3_key = doc["image_s3_key"]

    generated = doc.get("generated")
    if not generated and "variation_index" in doc:
        generated = {
            "prompt_used": doc.get("image_prompt", ""),
            "variation_index": doc.get("variation_index", 1),
            "version": doc.get("version", 1),
            "parent_id": doc.get("parent_id"),
            "edit_instruction": doc.get("edit_instruction"),
        }

    metadata = doc.get("metadata")
    if not metadata:
        dims = doc.get("size_dimensions") or "1080x1080"
        subtype = find_subtype_by_dimensions(dims)
        specs = get_size_specs(subtype)
        metadata = {
            "type": CreativeType.IMAGE,
            "subtype": subtype,
            "size_specs": specs.model_dump(),
        }

    return CreativeOut(
        id=str(doc["_id"]),
        source=doc.get("source", CreativeSource.GENERATED),
        metadata=metadata,
        client_id=doc.get("client_id", "revspot"),
        project_id=doc.get("project_id"),
        name=doc.get("name"),
        status=doc["status"],
        s3_key=s3_key or "",
        creative_url=presign_url(s3_key) if s3_key else None,
        error_message=doc.get("error_message"),
        generated=generated,
        uploaded=doc.get("uploaded"),
        created_at=doc["created_at"],
    )


@router.get("", response_model=list[LogSummary])
async def list_logs():
    docs = await logs_repo.list_all()
    return [
        LogSummary(
            id=str(doc["_id"]),
            project_id=doc["project_id"],
            project_name=doc.get("project_name", ""),
            inputs=doc["inputs"],
            ad_copy=doc["ad_copy"],
            eval=doc.get("eval", {"criteria": [], "overall_notes": ""}),
            image_count=len(doc.get("image_ids", [])),
            created_at=doc["created_at"],
        )
        for doc in docs
    ]


@router.get("/{log_id}", response_model=LogOut)
async def get_log(log_id: str):
    doc = await logs_repo.get(log_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Log not found")

    image_ids = doc.get("image_ids", [])
    img_docs = await creatives_repo.get_many(image_ids)
    img_docs.sort(key=lambda d: d.get("generated", {}).get("variation_index", d.get("variation_index", 0)))

    return LogOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        project_name=doc.get("project_name", ""),
        inputs=doc["inputs"],
        prompts=doc["prompts"],
        ad_copy=doc["ad_copy"],
        image_ids=image_ids,
        images=[_img_doc_to_out(i) for i in img_docs],
        eval=doc.get("eval", {"criteria": [], "overall_notes": ""}),
        created_at=doc["created_at"],
    )


@router.patch("/{log_id}/eval", response_model=LogOut)
async def update_eval(log_id: str, body: UpdateEvalRequest):
    matched = await logs_repo.update_eval(log_id, body.eval.model_dump())
    if matched == 0:
        raise HTTPException(status_code=404, detail="Log not found")
    return await get_log(log_id)
