import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "revCreate")

_client: AsyncMongoClient | None = None
projects: AsyncCollection | None = None
creatives: AsyncCollection | None = None
images: AsyncCollection | None = None
jobs: AsyncCollection | None = None
logs: AsyncCollection | None = None
api_tokens: AsyncCollection | None = None
dlq: AsyncCollection | None = None


async def connect() -> None:
    global _client, projects, creatives, images, jobs, logs, api_tokens, dlq
    _client = AsyncMongoClient(MONGO_URI)
    _db = _client[DB_NAME]
    projects = _db["projects"]
    creatives = _db["creatives"]
    images = _db["images"]  # Keep temporarily for migration
    jobs = _db["jobs"]
    logs = _db["logs"]
    api_tokens = _db["api_tokens"]
    dlq = _db["dlq"]
    # Compound index for association queries:
    # find({"associations": {"$elemMatch": {"type": "campaign", "id": X}}})
    await creatives.create_index(
        [("associations.type", 1), ("associations.id", 1)],
        name="associations_type_id",
    )



async def close() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def _out(doc: dict | None) -> dict | None:
    """Rename _id → id for API responses."""
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc
