"""Repository for the logs collection."""
from __future__ import annotations

import db


async def list_all() -> list[dict]:
    return await db.logs.find().sort("created_at", -1).to_list()


async def get(log_id: str) -> dict | None:
    return await db.logs.find_one({"_id": log_id})


async def update_eval(log_id: str, eval_data: dict) -> int:
    result = await db.logs.update_one(
        {"_id": log_id},
        {"$set": {"eval": eval_data}},
    )
    return result.matched_count
