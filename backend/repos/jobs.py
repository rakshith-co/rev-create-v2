"""Repository for the jobs collection."""
from __future__ import annotations

import db


async def get(job_id: str) -> dict | None:
    return await db.jobs.find_one({"_id": job_id})


async def insert(doc: dict) -> None:
    await db.jobs.insert_one(doc)


async def update(job_id: str, fields: dict) -> None:
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})
