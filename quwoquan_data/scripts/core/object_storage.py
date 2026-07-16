"""统一对象存储抽象：source bundle / media CAS / entity assets / release 共用。

环境只通过 QWQ_OBJECT_STORAGE_* 注入 backend；业务层只处理 object key/manifest，
不得出现 MinIO/AWS/OSS/R2 分支。S3 backend 使用 path-style，兼容本地 MinIO 与多云 S3。
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from core import paths
from core.schema import assert_valid


ARTIFACT_KINDS = frozenset({"source_bundle", "media_cas", "entity_asset", "release"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class ObjectStorage(Protocol):
    backend: str

    def put_file(self, source: Path, key: str, *, sha256: str) -> str: ...

    def head(self, key: str) -> dict[str, Any] | None: ...

    def get_bytes(self, key: str) -> bytes: ...


@dataclass
class FilesystemObjectStorage:
    root: Path
    backend: str = "filesystem"

    def put_file(self, source: Path, key: str, *, sha256: str) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and _sha256_file(target) == sha256:
            return target.as_uri()
        tmp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
        shutil.copyfile(source, tmp)
        if _sha256_file(tmp) != sha256:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"object storage checksum mismatch before publish: {key}")
        os.replace(tmp, target)
        return target.as_uri()

    def head(self, key: str) -> dict[str, Any] | None:
        path = self.root / key
        if not path.is_file():
            return None
        return {"bytes": path.stat().st_size, "sha256": _sha256_file(path)}

    def get_bytes(self, key: str) -> bytes:
        path = self.root / key
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()


class S3ObjectStorage:
    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint: str = "",
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
        ca_bundle: str = "",
    ) -> None:
        if not bucket:
            raise ValueError("QWQ_OBJECT_STORAGE_BUCKET required for s3 backend")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("s3 backend requires boto3") from exc
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": region,
            "config": Config(s3={"addressing_style": "path"}),
        }
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if access_key:
            kwargs["aws_access_key_id"] = access_key
        if secret_key:
            kwargs["aws_secret_access_key"] = secret_key
        if ca_bundle:
            kwargs["verify"] = ca_bundle
        self.bucket = bucket
        self.client = boto3.client(**kwargs)

    def put_file(self, source: Path, key: str, *, sha256: str) -> str:
        existing = self.head(key)
        if existing and existing.get("sha256") == sha256:
            return f"s3://{self.bucket}/{key}"
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        self.client.upload_file(
            str(source),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {"sha256": sha256.removeprefix("sha256:")},
            },
        )
        confirmed = self.head(key)
        if not confirmed or confirmed.get("sha256") != sha256:
            raise ValueError(f"s3 object checksum metadata mismatch after upload: {key}")
        return f"s3://{self.bucket}/{key}"

    def head(self, key: str) -> dict[str, Any] | None:
        try:
            row = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # botocore ClientError is optional at import time
            response = getattr(exc, "response", {})
            status = int(((response or {}).get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
            if status == 404:
                return None
            raise
        digest = str((row.get("Metadata") or {}).get("sha256") or "")
        return {
            "bytes": int(row.get("ContentLength") or 0),
            "sha256": f"sha256:{digest}" if digest else "",
            "etag": str(row.get("ETag") or ""),
        }

    def get_bytes(self, key: str) -> bytes:
        row = self.client.get_object(Bucket=self.bucket, Key=key)
        return row["Body"].read()


def storage_from_env() -> ObjectStorage:
    backend = str(os.environ.get("QWQ_OBJECT_STORAGE_BACKEND") or "filesystem").strip()
    if backend == "filesystem":
        root = Path(
            os.environ.get("QWQ_OBJECT_STORAGE_ROOT")
            or paths.OUTPUT_ROOT / "data" / "objects"
        )
        root.mkdir(parents=True, exist_ok=True)
        return FilesystemObjectStorage(root=root.resolve())
    if backend == "s3":
        return S3ObjectStorage(
            bucket=str(os.environ.get("QWQ_OBJECT_STORAGE_BUCKET") or ""),
            endpoint=str(os.environ.get("QWQ_OBJECT_STORAGE_ENDPOINT") or ""),
            region=str(os.environ.get("QWQ_OBJECT_STORAGE_REGION") or "us-east-1"),
            access_key=str(
                os.environ.get("QWQ_OBJECT_STORAGE_ACCESS_KEY")
                or os.environ.get("AWS_ACCESS_KEY_ID")
                or ""
            ),
            secret_key=str(
                os.environ.get("QWQ_OBJECT_STORAGE_SECRET_KEY")
                or os.environ.get("AWS_SECRET_ACCESS_KEY")
                or ""
            ),
            ca_bundle=str(
                os.environ.get("QWQ_OBJECT_STORAGE_CA_BUNDLE")
                or os.environ.get("AWS_CA_BUNDLE")
                or ""
            ),
        )
    raise ValueError(f"unsupported QWQ_OBJECT_STORAGE_BACKEND: {backend}")


def artifact_object_key(kind: str, source: Path, sha256: str, *, prefix: str = "") -> str:
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"unsupported object storage artifact kind: {kind}")
    digest = sha256.removeprefix("sha256:")
    parts = [str(prefix).strip("/"), kind, "sha256", digest[:2], digest, source.name]
    return "/".join(part for part in parts if part)


def store_artifact(
    source: str | Path,
    *,
    kind: str,
    logical_ref: str,
    storage: ObjectStorage | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if not logical_ref:
        raise ValueError("logical_ref required")
    storage = storage or storage_from_env()
    sha256 = _sha256_file(path)
    key = artifact_object_key(kind, path, sha256, prefix=prefix)
    uri = storage.put_file(path, key, sha256=sha256)
    head = storage.head(key)
    stored_bytes = int(head["bytes"]) if head and "bytes" in head else -1
    if not head or head.get("sha256") != sha256 or stored_bytes != path.stat().st_size:
        raise ValueError(f"missing/corrupt object after publish: {key}")
    manifest = {
        "schemaVersion": "quwoquan_data.object_storage_manifest/1",
        "backend": storage.backend,
        "kind": kind,
        "logicalRef": logical_ref,
        "objectKey": key,
        "objectUri": uri,
        "sha256": sha256,
        "bytes": path.stat().st_size,
        "storedAt": _now_iso(),
    }
    assert_valid(manifest, "release", "object_storage_manifest", label="object_storage_manifest")
    return manifest


def sync_artifact_tree(
    source_root: str | Path,
    *,
    kind: str,
    storage: ObjectStorage | None = None,
    prefix: str = "",
    exclude_paths: set[Path] | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    storage = storage or storage_from_env()
    objects: list[dict[str, Any]] = []
    excluded = {path.resolve() for path in (exclude_paths or set())}
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and item.resolve() not in excluded
    ):
        logical_ref = path.relative_to(root).as_posix()
        objects.append(
            store_artifact(
                path,
                kind=kind,
                logical_ref=logical_ref,
                storage=storage,
                prefix=prefix,
            )
        )
    return {
        "schemaVersion": "quwoquan_data.object_storage_sync_report/1",
        "backend": storage.backend,
        "kind": kind,
        "sourceRoot": str(root),
        "objectCount": len(objects),
        "missingObjectCount": 0,
        "duplicatePublishCount": 0,
        "objects": objects,
        "completedAt": _now_iso(),
    }


__all__ = [
    "ARTIFACT_KINDS",
    "FilesystemObjectStorage",
    "ObjectStorage",
    "S3ObjectStorage",
    "artifact_object_key",
    "storage_from_env",
    "store_artifact",
    "sync_artifact_tree",
]
