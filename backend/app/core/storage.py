import uuid

import boto3
from botocore.client import Config

from app.core.config import settings

_client = boto3.client(
    "s3",
    endpoint_url=settings.minio_endpoint,
    aws_access_key_id=settings.minio_root_user,
    aws_secret_access_key=settings.minio_root_password,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

# Presigned URLs are consumed by the browser on the host, not by another
# container on the Docker network — they need the public-facing endpoint
# (localhost:9000) baked into the signature, not the internal `minio:9000`
# hostname the backend itself uses for put_object/list_buckets. The
# signature covers the Host header, so this has to be a second client, not
# a string replace on the URL after the fact.
_public_client = boto3.client(
    "s3",
    endpoint_url=settings.minio_public_endpoint,
    aws_access_key_id=settings.minio_root_user,
    aws_secret_access_key=settings.minio_root_password,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


def ensure_bucket() -> None:
    existing = [b["Name"] for b in _client.list_buckets().get("Buckets", [])]
    if settings.minio_bucket not in existing:
        _client.create_bucket(Bucket=settings.minio_bucket)


# Receipts and similar evidence: what a phone camera or a bank's PDF gives.
# Checked by the file's first bytes, not its name or the browser's claim.
EVIDENCE_TYPES = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
MAX_EVIDENCE_FILES = 5


def evidence_type(file_bytes: bytes) -> str | None:
    """The real type of an evidence file, or None if it isn't one we accept."""
    for content_type, signatures in EVIDENCE_TYPES.items():
        if any(file_bytes.startswith(sig) for sig in signatures):
            if content_type == "image/webp" and file_bytes[8:12] != b"WEBP":
                continue
            return content_type
    return None


def upload_file(file_bytes: bytes, content_type: str, key_prefix: str) -> str:
    key = f"{key_prefix}/{uuid.uuid4()}"
    _client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def download_file(storage_key: str) -> bytes:
    return _client.get_object(Bucket=settings.minio_bucket, Key=storage_key)["Body"].read()


def presigned_url(storage_key: str, expires_in: int = 3600) -> str:
    return _public_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )
