import asyncio
import os

import boto3
from botocore.config import Config

BUCKET = os.getenv("S3_BUCKET_NAME", "rev-create-images")
REGION = os.getenv("AWS_REGION", "ap-south-1")
PRESIGN_EXPIRY = 3600  # 1 hour

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
    return _s3


async def upload_bytes(key: str, data: bytes, content_type: str = "image/png") -> str:
    """Upload raw bytes to S3 and return the key."""
    await asyncio.to_thread(
        _client().put_object, Bucket=BUCKET, Key=key, Body=data, ContentType=content_type
    )
    return key


async def delete_object(key: str) -> None:
    """Delete a single S3 object, ignoring NoSuchKey."""
    try:
        await asyncio.to_thread(_client().delete_object, Bucket=BUCKET, Key=key)
    except Exception:
        pass


async def download_bytes(key: str) -> bytes:
    """Download object from S3 and return raw bytes."""
    resp = await asyncio.to_thread(_client().get_object, Bucket=BUCKET, Key=key)
    return resp["Body"].read()


def presign_url(key: str) -> str:
    """Generate a pre-signed GET URL valid for PRESIGN_EXPIRY seconds."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=PRESIGN_EXPIRY,
    )
