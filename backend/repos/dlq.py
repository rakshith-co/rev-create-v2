"""Repository for the dlq collection."""
from __future__ import annotations

import db


async def insert(doc: dict) -> None:
    await db.dlq.insert_one(doc)


async def get_all(skip: int = 0, limit: int = 50) -> list[dict]:
    return await db.dlq.find().sort("failed_at", -1).skip(skip).limit(limit).to_list(length=limit)
