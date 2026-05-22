"""
Artifact store: upload/download model artifacts to S3-compatible object storage.
Supports MinIO, Aliyun OSS, Cloudflare R2, AWS S3.
"""
import os
import hashlib
from pathlib import Path
from typing import Optional

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    boto3 = None
    BotoConfig = None

DEFAULT_BUCKET = os.environ.get("MODEL_ARTIFACT_BUCKET", "quwoquan-models")
DEFAULT_ENDPOINT = os.environ.get("MODEL_ARTIFACT_ENDPOINT", "")
DEFAULT_REGION = os.environ.get("MODEL_ARTIFACT_REGION", "us-east-1")
CACHE_DIR = Path(os.environ.get("MODEL_CACHE_DIR", "/app/cache"))


def _get_client():
    if boto3 is None:
        raise ImportError("pip install boto3")

    kwargs = {
        "service_name": "s3",
        "region_name": DEFAULT_REGION,
        "aws_access_key_id": os.environ.get("MODEL_ARTIFACT_ACCESS_KEY", os.environ.get("AWS_ACCESS_KEY_ID", "")),
        "aws_secret_access_key": os.environ.get("MODEL_ARTIFACT_SECRET_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY", "")),
    }
    endpoint = DEFAULT_ENDPOINT
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["config"] = BotoConfig(s3={"addressing_style": "path"})
    return boto3.client(**kwargs)


def artifact_key(scenario: str, version: str, filename: str) -> str:
    return f"models/{scenario}/{version}/{filename}"


def upload(local_path: str, scenario: str, version: str, bucket: Optional[str] = None) -> str:
    """Upload a model artifact and return its S3 URI."""
    bucket = bucket or DEFAULT_BUCKET
    filename = Path(local_path).name
    key = artifact_key(scenario, version, filename)

    client = _get_client()
    client.upload_file(local_path, bucket, key)
    uri = f"s3://{bucket}/{key}"
    print(f"[artifact_store] Uploaded {local_path} → {uri}")
    return uri


def download(uri: str, cache_dir: Optional[Path] = None) -> str:
    """Download an artifact from S3 URI to local cache. Returns local path."""
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not uri.startswith("s3://"):
        if os.path.exists(uri):
            return uri
        raise FileNotFoundError(f"Not an S3 URI and local path not found: {uri}")

    cache_key = hashlib.sha256(uri.encode()).hexdigest()[:16]
    parts = uri.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    filename = Path(key).name
    local_path = cache_dir / f"{cache_key}_{filename}"

    if local_path.exists():
        return str(local_path)

    client = _get_client()
    client.download_file(bucket, key, str(local_path))
    print(f"[artifact_store] Downloaded {uri} → {local_path}")
    return str(local_path)


def exists(uri: str) -> bool:
    """Check if an artifact exists (local path or S3)."""
    if not uri.startswith("s3://"):
        return os.path.exists(uri)
    parts = uri.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    try:
        client = _get_client()
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False
