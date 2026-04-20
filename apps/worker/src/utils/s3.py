"""S3 / Cloudflare R2 storage utilities for the Celery worker.

Usage:
    from utils.s3 import upload_file, generate_presigned_url

All functions return gracefully when S3 is not configured (settings.s3_configured
is False) — callers should treat a None return as "not stored".
"""

from __future__ import annotations

import os
from typing import Optional

import boto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from config import settings

logger = structlog.get_logger(__name__)


def _client():
    """Return a boto3 S3 client configured for R2 or AWS S3."""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name="auto",  # R2 uses "auto"; AWS ignores this when endpoint_url is absent
    )


def upload_file(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> Optional[str]:
    """Upload bytes to S3/R2.

    Returns the S3 key on success, None if S3 is not configured or upload fails.
    """
    if not settings.s3_configured:
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


def upload_file_from_path(
    key: str,
    file_path: str,
    content_type: str = "application/octet-stream",
) -> Optional[str]:
    """Upload a local file to S3/R2 by path.

    Returns the S3 key on success, None otherwise.
    """
    if not settings.s3_configured:
        return None
    if not os.path.exists(file_path):
        logger.warning("s3.upload_file_not_found", path=file_path)
        return None
    try:
        with open(file_path, "rb") as fh:
            return upload_file(key, fh.read(), content_type)
    except OSError as exc:
        logger.warning("s3.read_failed", path=file_path, error=str(exc))
        return None


def generate_presigned_url(key: str, expires: int = 3600) -> Optional[str]:
    """Return a pre-signed download URL for the given S3 key.

    Returns None if S3 is not configured or the key does not exist.
    """
    if not settings.s3_configured:
        return None
    try:
        url = _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )
        return url
    except (BotoCoreError, ClientError) as exc:
        logger.warning("s3.presign_failed", key=key, error=str(exc))
        return None


def download_file(key: str) -> Optional[bytes]:
    """Download a file from S3/R2 and return its bytes.

    Returns None if S3 is not configured or the key does not exist.
    """
    if not settings.s3_configured:
        return None
    try:
        resp = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return resp["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.warning("s3.download_failed", key=key, error=str(exc))
        return None
