"""S3 / Cloudflare R2 storage utilities for the FastAPI application.

Usage:
    from utils.s3 import upload_file, generate_presigned_url
"""

from __future__ import annotations

from typing import Optional

import boto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from config import settings

logger = structlog.get_logger(__name__)


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name="auto",
    )


def _is_configured() -> bool:
    return bool(settings.s3_endpoint and settings.s3_access_key and settings.s3_secret_key)


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
    """Upload bytes to S3/R2. Returns key on success, None on failure or if not configured."""
    if not _is_configured():
        return None
    try:
        _client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("s3.uploaded", key=key, size=len(data))
        return key
    except (BotoCoreError, ClientError) as exc:
        logger.warning("s3.upload_failed", key=key, error=str(exc))
        return None


def generate_presigned_url(key: str, expires: int = 3600) -> Optional[str]:
    """Return a pre-signed download URL. Returns None if not configured."""
    if not _is_configured():
        return None
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("s3.presign_failed", key=key, error=str(exc))
        return None


def download_file(key: str) -> Optional[bytes]:
    """Download bytes from S3/R2. Returns None if not configured or key missing."""
    if not _is_configured():
        return None
    try:
        resp = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return resp["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.warning("s3.download_failed", key=key, error=str(exc))
        return None
