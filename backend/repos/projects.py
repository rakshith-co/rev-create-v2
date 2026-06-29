"""Repository for the projects collection."""
from __future__ import annotations

import db


async def get(project_id: str, projection: dict | None = None) -> dict | None:
    return await db.projects.find_one({"_id": project_id}, projection)


async def list_many(
    query: dict,
    projection: dict | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[dict]:
    return await db.projects.find(query, projection).sort("created_at", -1).skip(skip).limit(limit).to_list()


async def count(query: dict) -> int:
    return await db.projects.count_documents(query)


async def insert(doc: dict) -> None:
    await db.projects.insert_one(doc)


async def update(project_id: str, fields: dict) -> None:
    await db.projects.update_one({"_id": project_id}, {"$set": fields})


async def delete(project_id: str) -> int:
    result = await db.projects.delete_one({"_id": project_id})
    return result.deleted_count
