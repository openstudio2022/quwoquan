from __future__ import annotations

import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .output_paths import deployment_work_root


_SECRET_KEYS = ("access_key_id", "access_key_secret", "cdn_sign_key")
_HOST = "gamma-upload.quwoquan-env.test"
_LOCAL_HOST = "gamma-upload.localhost"
_BUCKET = "chat-media"
_REGION = "cn-local-1"


@dataclass(frozen=True)
class LocalGammaObjectStorage:
    environment: dict[str, str]
    host_endpoint: str
    work_root: Path
    secret_path: Path
    ca_path: Path


def prepare_local_gamma_object_storage(*, edge_port: int) -> LocalGammaObjectStorage:
    """Prepare real local S3 credentials and TLS outside repository/output roots."""
    if not isinstance(edge_port, int) or not 0 < edge_port <= 65535:
        raise ValueError("object-storage edge port must be a valid TCP port")
    work_root = deployment_work_root("gamma-local")
    secret_path = work_root / "secrets" / "object-storage.env"
    certificate_root = work_root / "certificates" / "object-storage"
    secret_values = _load_or_create_secrets(secret_path)
    ca_path = _load_or_create_tls(certificate_root)
    endpoint = f"{_HOST}:{edge_port}"
    return LocalGammaObjectStorage(
        environment={
            "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": str(edge_port),
            "LOCAL_GAMMA_OBJECT_STORAGE_BUCKET": _BUCKET,
            "LOCAL_GAMMA_OBJECT_STORAGE_REGION": _REGION,
            "LOCAL_GAMMA_OBJECT_STORAGE_TLS_DIR": str(certificate_root / "minio"),
            "LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE": str(ca_path),
            "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT": endpoint,
            "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID": secret_values["access_key_id"],
            "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET": secret_values["access_key_secret"],
            "LOCAL_GAMMA_OBJECT_STORAGE_CDN_DOMAIN": endpoint,
            "LOCAL_GAMMA_OBJECT_STORAGE_CDN_SIGN_KEY": secret_values["cdn_sign_key"],
        },
        host_endpoint=f"https://{_LOCAL_HOST}:{edge_port}",
        work_root=work_root,
        secret_path=secret_path,
        ca_path=ca_path,
    )


def _load_or_create_secrets(path: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_file():
        _require_mode(path, 0o600, "object-storage secret file")
        values = _read_secret_file(path)
        missing = [key for key in _SECRET_KEYS if not values.get(key)]
        if missing:
            raise RuntimeError("object-storage secret file is incomplete: " + ", ".join(missing))
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


def _load_or_create_tls(root: Path) -> Path:
    ca_path = root / "ca.crt"
    private_key = root / "ca.key"
    server_cert = root / "minio" / "public.crt"
    server_key = root / "minio" / "private.key"
    if all(path.is_file() for path in (ca_path, private_key, server_cert, server_key)):
        _require_mode(root, 0o700, "object-storage certificate directory")
        _require_mode(private_key, 0o600, "object-storage CA key")
        _require_mode(server_key, 0o600, "object-storage server key")
        return ca_path
    if root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(root.parent, 0o700)
    with tempfile.TemporaryDirectory(prefix="object-storage-", dir=root.parent) as temp_dir:
        staged = Path(temp_dir)
        minio_dir = staged / "minio"
        minio_dir.mkdir(mode=0o700)
        extension = staged / "server.ext"
        extension.write_text(
            "subjectAltName=DNS:object-storage,DNS:gamma-upload.quwoquan-env.test,DNS:gamma-upload.localhost\n"
            "extendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n",
            encoding="utf-8",
        )
        _run_openssl([
            "req", "-x509", "-new", "-nodes", "-newkey", "rsa:2048", "-sha256", "-days", "30",
            "-subj", "/CN=QWQ Gamma Local Object Storage CA", "-keyout", str(staged / "ca.key"),
            "-out", str(staged / "ca.crt"),
        ])
        _run_openssl([
            "req", "-new", "-nodes", "-newkey", "rsa:2048", "-subj", f"/CN={_HOST}",
            "-keyout", str(minio_dir / "private.key"), "-out", str(staged / "server.csr"),
        ])
        _run_openssl([
            "x509", "-req", "-sha256", "-days", "30", "-in", str(staged / "server.csr"),
            "-CA", str(staged / "ca.crt"), "-CAkey", str(staged / "ca.key"), "-CAcreateserial",
            "-extfile", str(extension), "-out", str(minio_dir / "public.crt"),
        ])
        for path in (staged / "server.csr", staged / "ca.srl", extension):
            path.unlink(missing_ok=True)
        os.chmod(staged, 0o700)
        os.chmod(minio_dir, 0o700)
        os.chmod(staged / "ca.key", 0o600)
        os.chmod(staged / "ca.crt", 0o644)
        os.chmod(minio_dir / "private.key", 0o600)
        os.chmod(minio_dir / "public.crt", 0o644)
        os.replace(staged, root)
    return ca_path


def _run_openssl(arguments: list[str]) -> None:
    result = subprocess.run(
        ["openssl", *arguments],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("failed to generate local Gamma object-storage TLS material")


def _require_mode(path: Path, expected: int, label: str) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"{label} must use mode {expected:04o}: {path}")
