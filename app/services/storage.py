from __future__ import annotations

import uuid
from typing import BinaryIO, Literal

import boto3
from botocore.client import Config

from config.settings import settings

FileRoleStr = Literal[
    "original_catalogs",
    "correction_templates",
    "corrections_uploaded",
    "reports_before",
    "reports_after",
    "corrected_catalogs",
    "cwr_exports",
    "logs",
]

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


def ensure_bucket() -> None:
    client = _get_client()
    bucket = settings.minio_bucket
    existing = client.list_buckets().get("Buckets", [])
    if not any(b["Name"] == bucket for b in existing):
        client.create_bucket(Bucket=bucket)


def build_key(role: FileRoleStr, job_id: uuid.UUID | str, filename: str) -> str:
    return f"{role}/{job_id}/{filename}"


def put_object(role: FileRoleStr, job_id: uuid.UUID | str, filename: str, body: bytes | BinaryIO,
               content_type: str = "application/octet-stream") -> str:
    key = build_key(role, job_id, filename)
    _get_client().put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return key


def get_object(s3_key: str) -> bytes:
    resp = _get_client().get_object(Bucket=settings.minio_bucket, Key=s3_key)
    return resp["Body"].read()


def presigned_url(s3_key: str, ttl_seconds: int | None = None) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": s3_key},
        ExpiresIn=ttl_seconds or settings.presigned_url_ttl_seconds,
    )
