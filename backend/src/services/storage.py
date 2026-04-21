import uuid
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import UploadFile

from src.core.config import get_settings
from src.core.logger import logger

settings = get_settings()


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.MINIO_USE_SSL else ''}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket_exists() -> None:
    """Create the default bucket if it doesn't exist."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=settings.MINIO_BUCKET)
        logger.info(f"Bucket '{settings.MINIO_BUCKET}' already exists.")
    except ClientError:
        client.create_bucket(Bucket=settings.MINIO_BUCKET)
        logger.info(f"Bucket '{settings.MINIO_BUCKET}' created.")


async def upload_file(file: UploadFile, folder: str = "uploads") -> dict:
    """
    Upload a file to Minio and return its storage key and public URL path.
    """
    client = _get_client()
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    object_key = f"{folder}/{uuid.uuid4()}.{file_ext}"

    contents = await file.read()
    await file.seek(0)

    try:
        client.put_object(
            Bucket=settings.MINIO_BUCKET,
            Key=object_key,
            Body=contents,
            ContentType=file.content_type or "application/octet-stream",
        )
        logger.info(f"Uploaded '{file.filename}' â†’ s3://{settings.MINIO_BUCKET}/{object_key}")
        return {
            "object_key": object_key,
            "bucket": settings.MINIO_BUCKET,
            "filename": file.filename,
            "size": len(contents),
        }
    except ClientError as e:
        logger.error(f"Minio upload failed: {e}")
        raise


def get_presigned_url(object_key: str, expiry: int = 3600) -> str:
    """Generate a pre-signed URL for downloading a file."""
    client = _get_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.MINIO_BUCKET, "Key": object_key},
        ExpiresIn=expiry,
    )
    return url


def delete_file(object_key: str) -> None:
    """Delete a file from Minio."""
    client = _get_client()
    client.delete_object(Bucket=settings.MINIO_BUCKET, Key=object_key)
    logger.info(f"Deleted s3://{settings.MINIO_BUCKET}/{object_key}")


def download_file_bytes(object_key: str) -> bytes:
    """Download raw file bytes from Minio."""
    client = _get_client()
    response = client.get_object(Bucket=settings.MINIO_BUCKET, Key=object_key)
    return response["Body"].read()


def upload_bytes(
    contents: bytes, object_key: str, content_type: str = "application/octet-stream"
) -> dict:
    """Upload raw bytes to Minio under a specific object key."""
    client = _get_client()
    try:
        client.put_object(
            Bucket=settings.MINIO_BUCKET,
            Key=object_key,
            Body=contents,
            ContentType=content_type,
        )
        logger.info(f"Uploaded bytes → s3://{settings.MINIO_BUCKET}/{object_key}")
        return {
            "object_key": object_key,
            "bucket": settings.MINIO_BUCKET,
            "size": len(contents),
        }
    except ClientError as e:
        logger.error(f"Minio byte upload failed: {e}")
        raise
