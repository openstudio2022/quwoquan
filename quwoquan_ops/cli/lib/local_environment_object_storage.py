from __future__ import annotations

import fcntl
import os
import secrets
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .environment_topology import get_target, load_environment_topology
from .output_paths import deployment_target_path, deployment_work_root, remove_deployment_tree
from .public_domain_tls import certificate_paths, root_certificate_path


_SECRET_KEYS = ("access_key_id", "access_key_secret", "cdn_sign_key")


@dataclass(frozen=True)
class LocalEnvironmentObjectStorage:
    """Target-isolated real S3 credentials and TLS material for local stacks."""

    environment: dict[str, str]
    host_endpoint: str
    work_root: Path
    secret_path: Path
    certificate_path: Path
    private_key_path: Path
    root_certificate_path: Path


def prepare_local_environment_object_storage(
    *,
    environment: str,
    target_name: str,
    edge_port: int,
    environment_prefix: str,
    bucket: str = "chat-media",
    region: str = "cn-local-1",
) -> LocalEnvironmentObjectStorage:
    """Prepare MinIO credentials and the target's canonical TLS material."""
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(f"unsupported local object-storage environment: {environment}")
    if not target_name.endswith("-local"):
        raise ValueError(f"local object-storage target must end with -local: {target_name}")
    if not isinstance(edge_port, int) or not 0 < edge_port <= 65535:
        raise ValueError("object-storage edge port must be a valid TCP port")
    if not environment_prefix:
        raise ValueError("object-storage environment prefix is required")
    public_bases = get_target(load_environment_topology(), target_name)["publicBases"]
    public_upload_base = str(public_bases["mediaUpload"])
    public_host = urlparse(public_upload_base).hostname or ""
    if not public_host:
        raise ValueError(f"{target_name} mediaUpload role has no public host")

    work_root = deployment_work_root(target_name)
    secret_path = deployment_target_path(
        target_name,
        "secrets",
        "object-storage.env",
    )
    certificate_root = deployment_target_path(
        target_name,
        "certificates",
        "object-storage",
    )
    secret_values = _load_or_create_secrets(secret_path)
    source_certificate, source_private_key = certificate_paths(target_name)
    source_root_certificate = root_certificate_path(target_name)
    certificate_path, private_key_path = _materialize_public_tls(
        certificate_root,
        target_name=target_name,
        source_certificate=source_certificate,
        source_private_key=source_private_key,
    )
    prefix = environment_prefix.rstrip("_")
    endpoint = f"{public_host}:{edge_port}"
    return LocalEnvironmentObjectStorage(
        environment={
            f"{prefix}_OBJECT_STORAGE_EDGE_PORT": str(edge_port),
            f"{prefix}_OBJECT_STORAGE_BUCKET": bucket,
            f"{prefix}_OBJECT_STORAGE_REGION": region,
            f"{prefix}_OBJECT_STORAGE_TLS_DIR": str(certificate_root / "minio"),
            f"{prefix}_OBJECT_STORAGE_CA_FILE": str(source_root_certificate),
            f"{prefix}_OBJECT_STORAGE_ENDPOINT": endpoint,
            f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": secret_values["access_key_id"],
            f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": secret_values[
                "access_key_secret"
            ],
            f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": secret_values["cdn_sign_key"],
        },
        host_endpoint=f"https://{public_host}:{edge_port}",
        work_root=work_root,
        secret_path=secret_path,
        certificate_path=certificate_path,
        private_key_path=private_key_path,
        root_certificate_path=source_root_certificate,
    )


def _load_or_create_secrets(path: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with _exclusive_lock(path.parent / ".object-storage-secrets.lock"):
        if path.is_file():
            _require_mode(path, 0o600, "object-storage secret file")
            values = _read_secret_file(path)
            missing = [key for key in _SECRET_KEYS if not values.get(key)]
            if missing:
                raise RuntimeError(
                    "object-storage secret file is incomplete: " + ", ".join(missing)
                )
            return values
        if path.exists():
            raise RuntimeError(f"object-storage secret path is not a file: {path}")
        values = {
            "access_key_id": "qwq" + secrets.token_hex(10),
            "access_key_secret": secrets.token_urlsafe(36),
            "cdn_sign_key": secrets.token_hex(32),
        }
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key in _SECRET_KEYS:
                    handle.write(f"{key}={values[key]}\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return values


def _read_secret_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or not value:
            raise RuntimeError(f"invalid object-storage secret file: {path}")
        values[key] = value
    return values


def _materialize_public_tls(
    root: Path,
    *,
    target_name: str,
    source_certificate: Path,
    source_private_key: Path,
) -> tuple[Path, Path]:
    server_cert = root / "minio" / "public.crt"
    server_key = root / "minio" / "private.key"
    root.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(root.parent, 0o700)
    with _exclusive_lock(root.parent / ".object-storage-tls.lock"):
        if (
            server_cert.is_file()
            and server_key.is_file()
            and server_cert.read_bytes() == source_certificate.read_bytes()
            and server_key.read_bytes() == source_private_key.read_bytes()
        ):
            _require_mode(root, 0o700, "object-storage certificate directory")
            _require_mode(server_key, 0o600, "object-storage server key")
            return server_cert, server_key
        if root.exists():
            remove_deployment_tree(
                target_name,
                "certificates",
                "object-storage",
            )
        with tempfile.TemporaryDirectory(prefix="object-storage-", dir=root.parent) as temp_dir:
            staged = Path(temp_dir)
            minio_dir = staged / "minio"
            minio_dir.mkdir(mode=0o700)
            shutil.copyfile(source_certificate, minio_dir / "public.crt")
            shutil.copyfile(source_private_key, minio_dir / "private.key")
            os.chmod(staged, 0o700)
            os.chmod(minio_dir, 0o700)
            os.chmod(minio_dir / "private.key", 0o600)
            os.chmod(minio_dir / "public.crt", 0o644)
            os.replace(staged, root)
        return server_cert, server_key


@contextmanager
def _exclusive_lock(path: Path):
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _require_mode(path: Path, expected: int, label: str) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"{label} must use mode {expected:04o}: {path}")
