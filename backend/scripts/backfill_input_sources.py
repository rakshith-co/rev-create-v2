"""
Backfill input_sources on creative documents that are missing it or have all-empty lists.

Resolution order per creative:
  1. Walk up the parent chain (via generated.parent_id) to find an ancestor
     that already has non-empty input_sources.
  2. Fall back to the project association on the creative (or any ancestor).

Usage:
  cd backend
  python scripts/backfill_input_sources.py [--dry-run]

Requires env vars (or .env file in backend/):
  MONGO_URI, DB_NAME
"""
import logging
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "revCreate")
DRY_RUN = "--dry-run" in sys.argv

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill")


def _has_input_sources(doc: dict) -> bool:
    src = doc.get("input_sources")
    if not src:
        return False
    return bool(src.get("product_images") or src.get("ref_images") or src.get("logo_images"))


def _resolve_input_sources(creative: dict, creatives_col, projects_col) -> dict | None:
    """
    1. Walk up parent chain for an ancestor with non-empty input_sources.
    2. Fall back to the project association.
    Returns the input_sources dict or None if unresolvable.
    """
    visited = set()
    current = creative
    while True:
        cid = str(current["_id"])
        if cid in visited:
            break
        visited.add(cid)

        if _has_input_sources(current):
            return current["input_sources"]

        parent_id = (current.get("generated") or {}).get("parent_id")
        if not parent_id:
            break
        parent = creatives_col.find_one({"_id": parent_id})
        if not parent:
            break
        current = parent

    # Fall back to project association
    for assoc in creative.get("associations", []):
        if assoc.get("type") == "project":
            project = projects_col.find_one({"_id": assoc["id"]})
            if project:
                return {
                    "product_images": project.get("product_images", []),
                    "ref_images": project.get("ref_images", []),
                    "logo_images": project.get("logo_images", []),
                }

    return None


def main() -> None:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    creatives = db["creatives"]
    projects = db["projects"]

    candidates = list(creatives.find({
        "$or": [
            {"input_sources": {"$exists": False}},
            {"input_sources": None},
            {
                "input_sources.product_images": {"$size": 0},
                "input_sources.ref_images": {"$size": 0},
                "input_sources.logo_images": {"$size": 0},
            },
        ]
    }))

    logger.info("Found %d creatives to backfill", len(candidates))

    updated = 0
    unresolvable = 0

    for doc in candidates:
        cid = str(doc["_id"])
        resolved = _resolve_input_sources(doc, creatives, projects)

        if not resolved:
            logger.warning("UNRESOLVABLE %s (no parent chain or project)", cid)
            unresolvable += 1
            continue

        counts = (
            len(resolved.get("product_images", [])),
            len(resolved.get("ref_images", [])),
            len(resolved.get("logo_images", [])),
        )
        logger.info(
            "%s %s → product=%d ref=%d logo=%d",
            "DRY-RUN" if DRY_RUN else "UPDATE",
            cid,
            *counts,
        )

        if not DRY_RUN:
            creatives.update_one(
                {"_id": doc["_id"]},
                {"$set": {"input_sources": resolved}},
            )
        updated += 1

    logger.info(
        "Done — %s %d, unresolvable %d",
        "would update" if DRY_RUN else "updated",
        updated,
        unresolvable,
    )
    client.close()


if __name__ == "__main__":
    main()
