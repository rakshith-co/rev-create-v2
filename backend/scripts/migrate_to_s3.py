"""
One-time migration: move all base64 image data from MongoDB to S3.

Migrates:
  - images collection: image_base64 → S3 key images/{id}.png
  - projects collection: product_images/ref_images [{data, mime_type}] → [{s3_key, mime_type}]

Usage:
  cd backend
  pip install boto3 pymongo python-dotenv
  python scripts/migrate_to_s3.py

Requires env vars (or .env file in backend/):
  MONGO_URI, DB_NAME, S3_BUCKET_NAME, AWS_REGION
"""
import base64
import logging
import os
import sys

# Load .env from backend/ directory (one level up from scripts/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import boto3
from botocore.config import Config
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("migrate_to_s3")

MONGO_URI = os.environ["MONGO_URI"]
DB_NAME = os.getenv("DB_NAME", "revCreate")
BUCKET = os.getenv("S3_BUCKET_NAME", "rev-create-images")
REGION = os.getenv("AWS_REGION", "ap-south-1")

MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))


def upload(key: str, data: bytes, content_type: str = "image/png") -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)


def migrate_images(db) -> None:
    logger.info("=== STEP 1: Migrating images collection ===")
    collection = db["images"]
    docs = list(collection.find({"image_base64": {"$exists": True, "$ne": None}}))
    logger.info("Found %d image doc(s) with base64 data to migrate", len(docs))

    ok = fail = skip = 0

    for doc in docs:
        img_id = str(doc["_id"])

        try:
            img_bytes = base64.b64decode(doc["image_base64"])
        except Exception as e:
            logger.warning("SKIP  image %s — base64 decode error: %s", img_id, e)
            skip += 1
            continue

        key = f"images/{img_id}.png"
        try:
            upload(key, img_bytes, "image/png")
            logger.info("UPLOAD  image %s → s3://%s/%s (%.1f KB)",
                        img_id, BUCKET, key, len(img_bytes) / 1024)
        except Exception as e:
            logger.error("FAIL  image %s — S3 upload error: %s", img_id, e)
            fail += 1
            continue

        collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"image_s3_key": key}, "$unset": {"image_base64": ""}},
        )
        logger.info("OK    image %s — MongoDB updated, base64 removed", img_id)
        ok += 1

    logger.info("Images migration complete — ok=%d  fail=%d  skip=%d\n", ok, fail, skip)


def migrate_projects(db) -> None:
    logger.info("=== STEP 2: Migrating projects collection ===")
    collection = db["projects"]

    docs = list(collection.find(
        {"product_images": {"$elemMatch": {"data": {"$exists": True}}}}
    ))
    logger.info("Found %d project(s) with base64 product/ref images to migrate", len(docs))

    ok = fail = 0

    for doc in docs:
        project_id = str(doc["_id"])
        logger.info("Processing project %s", project_id)

        new_product = []
        for i, img in enumerate(doc.get("product_images", [])):
            if "data" not in img:
                new_product.append(img)
                continue
            ext = MIME_EXT.get(img["mime_type"], "png")
            key = f"projects/{project_id}/product_{i}.{ext}"
            try:
                img_bytes = base64.b64decode(img["data"])
                upload(key, img_bytes, img["mime_type"])
                new_product.append({"s3_key": key, "mime_type": img["mime_type"]})
                logger.info("UPLOAD  project %s product_%d → s3://%s/%s (%.1f KB)",
                            project_id, i, BUCKET, key, len(img_bytes) / 1024)
                ok += 1
            except Exception as e:
                logger.error("FAIL  project %s product_%d — %s", project_id, i, e)
                new_product.append(img)
                fail += 1

        new_ref = []
        for i, img in enumerate(doc.get("ref_images", [])):
            if "data" not in img:
                new_ref.append(img)
                continue
            ext = MIME_EXT.get(img["mime_type"], "png")
            key = f"projects/{project_id}/ref_{i}.{ext}"
            try:
                img_bytes = base64.b64decode(img["data"])
                upload(key, img_bytes, img["mime_type"])
                new_ref.append({"s3_key": key, "mime_type": img["mime_type"]})
                logger.info("UPLOAD  project %s ref_%d → s3://%s/%s (%.1f KB)",
                            project_id, i, BUCKET, key, len(img_bytes) / 1024)
                ok += 1
            except Exception as e:
                logger.error("FAIL  project %s ref_%d — %s", project_id, i, e)
                new_ref.append(img)
                fail += 1

        collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"product_images": new_product, "ref_images": new_ref}},
        )
        logger.info("OK    project %s — MongoDB updated", project_id)

    logger.info("Projects migration complete — ok=%d  fail=%d\n", ok, fail)


def main() -> None:
    logger.info("Starting S3 migration — bucket=%s  region=%s  db=%s", BUCKET, REGION, DB_NAME)
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    try:
        migrate_images(db)
        migrate_projects(db)
        logger.info("=== Migration finished ===")
    finally:
        client.close()


if __name__ == "__main__":
    main()
