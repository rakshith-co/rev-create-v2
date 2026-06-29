"""Repository for the creatives collection."""
from __future__ import annotations

import db


async def get(creative_id: str, projection: dict | None = None) -> dict | None:
    return await db.creatives.find_one({"_id": creative_id}, projection)


async def get_many(ids: list[str], projection: dict | None = None) -> list[dict]:
    return await db.creatives.find({"_id": {"$in": ids}}, projection).to_list(length=len(ids))


async def list_generated(
    client_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    query: dict = {"source": "generated"}
    if client_id:
        query["client_id"] = client_id
    return await db.creatives.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)


async def list_uploaded(
    client_id: str | None = None,
    campaign_tag: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[dict]:
    query: dict = {"source": "uploaded"}
    if client_id:
        query["client_id"] = client_id
    if campaign_tag:
        query["uploaded.campaign_tag"] = campaign_tag
    return await db.creatives.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)


async def list_all(
    client_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    query: dict = {}
    if client_id:
        query["client_id"] = client_id
    return await db.creatives.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)


async def list_by_project(project_id: str) -> list[dict]:
    return await db.creatives.find(
        {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
    ).to_list()


async def list_done_by_project(project_id: str, platform: str | None = None) -> list[dict]:
    query: dict = {
        "associations": {"$elemMatch": {"type": "project", "id": project_id}},
        "status": "done",
    }
    if platform:
        query["metadata.platform"] = platform
    return await db.creatives.find(query).to_list()


async def count_by_project(project_id: str) -> int:
    return await db.creatives.count_documents(
        {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
    )


async def count_done_by_project(project_id: str) -> int:
    return await db.creatives.count_documents(
        {"associations": {"$elemMatch": {"type": "project", "id": project_id}}, "status": "done"}
    )


async def find_latest_child(parent_id: str) -> dict | None:
    return await db.creatives.find_one(
        {"generated.parent_id": str(parent_id), "status": "done"},
        sort=[("created_at", -1)],
    )


async def find_size_variant(parent_id: str, platform: str, width: int, height: int) -> dict | None:
    return await db.creatives.find_one({
        "generated.parent_id": parent_id,
        "metadata.platform": platform,
        "metadata.size_specs.width": width,
        "metadata.size_specs.height": height,
    })


async def insert(doc: dict) -> None:
    await db.creatives.insert_one(doc)


async def update(creative_id: str, fields: dict) -> None:
    await db.creatives.update_one({"_id": creative_id}, {"$set": fields})


async def update_many_by_ids(ids: list[str], fields: dict) -> None:
    await db.creatives.update_many({"_id": {"$in": ids}}, {"$set": fields})


async def update_many_by_project(
    project_id: str,
    fields: dict,
    status_filter: list[str] | None = None,
) -> None:
    query: dict = {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
    if status_filter:
        query["status"] = {"$in": status_filter}
    await db.creatives.update_many(query, {"$set": fields})


async def upsert(creative_id: str, update_op: dict) -> None:
    await db.creatives.update_one({"_id": creative_id}, update_op, upsert=True)


async def delete(creative_id: str) -> int:
    result = await db.creatives.delete_one({"_id": creative_id})
    return result.deleted_count


async def delete_by_project(project_id: str) -> None:
    await db.creatives.delete_many(
        {"associations": {"$elemMatch": {"type": "project", "id": project_id}}}
    )
