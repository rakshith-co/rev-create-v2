"""Repository for the api_tokens collection."""
from __future__ import annotations

from datetime import datetime
import db

async def get_by_hash(token_hash: str) -> dict | None:
    return await db.api_tokens.find_one({"token_hash": token_hash, "is_active": True})

async def update_last_used(token_id: str, last_used: datetime) -> None:
    await db.api_tokens.update_one({"_id": token_id}, {"$set": {"last_used_at": last_used}})
