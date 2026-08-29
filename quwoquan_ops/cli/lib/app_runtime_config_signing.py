"""External Ed25519 authority for signed App runtime configuration packages."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Callable, Mapping


SIGNING_KEY_ID_ENV = "QWQ_APP_RUNTIME_CONFIG_SIGNING_KEY_ID"
SIGNING_PRIVATE_KEY_FILE_ENV = "QWQ_APP_RUNTIME_CONFIG_SIGNING_PRIVATE_KEY_FILE"
TRUSTED_PUBLIC_KEYS_FILE_ENV = "QWQ_APP_RUNTIME_CONFIG_TRUSTED_PUBLIC_KEYS_FILE"
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RAW_ED25519_PUBLIC_KEY_SIZE = 32
_ED25519_SIGNATURE_SIZE = 64
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


@dataclass(frozen=True)
class SigningMaterial:
    key_id: str
    private_key_path: Path
    trusted_public_keys_path: Path


def _regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    return info


def _outside_repository(repo_root: Path, path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute external path")
    absolute = Path(os.path.abspath(path))
    _regular_file(absolute, label=label)
    resolved = absolute.resolve()
    roots = (repo_root.resolve(), (repo_root / ".qwq_output").resolve())
    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise ValueError(f"{label} must stay outside repository and output roots")
    return absolute


def decode_keyring(encoded: bytes) -> dict[str, str]:
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"App runtime trusted public keyring is unreadable: {exc}") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("App runtime trusted public keyring must be a non-empty object")
    normalized: dict[str, str] = {}
    for key_id, public_value in value.items():
        if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None:
            raise ValueError("App runtime trusted public keyring has an invalid keyId")
        if not isinstance(public_value, str):
            raise ValueError("App runtime trusted public key must be base64 text")
        try:
            raw = base64.b64decode(public_value, validate=True)
        except ValueError as exc:
            raise ValueError("App runtime trusted public key is not strict base64") from exc
        if len(raw) != _RAW_ED25519_PUBLIC_KEY_SIZE:
            raise ValueError("App runtime trusted public key must be Ed25519")
        normalized[key_id] = base64.b64encode(raw).decode("ascii")
    if value != normalized:
        raise ValueError("App runtime trusted public keyring is not canonical")
    return normalized


def _openssl_identity() -> str:
    """PATH 上解析到的 openssl 自述，用于把工具链问题指名道姓。"""

    probe = subprocess.run(
        ["openssl", "version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return "openssl version 不可执行"
    return (probe.stdout or b"").decode("utf-8", "replace").strip() or "未知实现"


def _derive_public_key(private_key: bytes) -> bytes:
    result = subprocess.run(
        ["openssl", "pkey", "-pubout", "-outform", "DER"],
        input=private_key,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        # macOS 自带 /usr/bin/openssl 是 LibreSSL，不实现 Ed25519：它对一把
        # 完全合法的密钥同样退非零。把这种情况报成「密钥非法」会把排查引向
        # 密钥材料，而真正要换的是 PATH 上解析到的 openssl。
        stderr = (result.stderr or b"").decode("utf-8", "replace")
        if "unsupported" in stderr.lower():
            raise ValueError(
                "PATH 上的 openssl 不支持 Ed25519（macOS 自带的是 LibreSSL），"
                f"无法派生 App runtime signing 公钥；实现: {_openssl_identity()}"
            )
        raise ValueError("App runtime signing private key is not a valid Ed25519 PEM")
    if not result.stdout.startswith(_ED25519_SPKI_PREFIX) or len(result.stdout) != (
        len(_ED25519_SPKI_PREFIX) + _RAW_ED25519_PUBLIC_KEY_SIZE
    ):
        raise ValueError("App runtime signing private key is not Ed25519")
    return result.stdout[-_RAW_ED25519_PUBLIC_KEY_SIZE:]


def resolve_signing_material(
    repo_root: Path,
    getenv: Callable[[str], str | None] = os.getenv,
) -> SigningMaterial:
    """Resolve one explicit external authority without serializing secret refs."""

    key_id = str(getenv(SIGNING_KEY_ID_ENV) or "").strip()
    private_value = str(getenv(SIGNING_PRIVATE_KEY_FILE_ENV) or "").strip()
    keyring_value = str(getenv(TRUSTED_PUBLIC_KEYS_FILE_ENV) or "").strip()
    if not key_id or not private_value or not keyring_value:
        raise ValueError(
            "App runtime signing keyId, private-key ref, and trusted keyring are required"
        )
    if _KEY_ID.fullmatch(key_id) is None:
        raise ValueError("App runtime signing keyId is invalid")
    private_path = _outside_repository(
        repo_root,
        Path(private_value).expanduser(),
        label="App runtime signing private key",
    )
    keyring_path = _outside_repository(
        repo_root,
        Path(keyring_value).expanduser(),
        label="App runtime trusted public keyring",
    )
    private_info = _regular_file(private_path, label="App runtime signing private key")
    keyring_info = _regular_file(
        keyring_path, label="App runtime trusted public keyring"
    )
    if private_info.st_mode & 0o077:
        raise ValueError("App runtime signing private key permissions must be 0600")
    if keyring_info.st_mode & 0o022:
        raise ValueError("App runtime trusted public keyring permissions are unsafe")
    private_bytes = private_path.read_bytes()
    keyring = decode_keyring(keyring_path.read_bytes())
    if key_id not in keyring:
        raise ValueError("App runtime signing keyId is absent from trusted keyring")
    expected_public = base64.b64decode(keyring[key_id], validate=True)
    if _derive_public_key(private_bytes) != expected_public:
        raise ValueError("App runtime signing private key does not match keyring")
    return SigningMaterial(key_id, private_path, keyring_path)


def validate_signing_material(
    repo_root: Path,
    signing: SigningMaterial,
) -> tuple[bytes, bytes, dict[str, str]]:
    resolved = resolve_signing_material(
        repo_root,
        {
            SIGNING_KEY_ID_ENV: signing.key_id,
            SIGNING_PRIVATE_KEY_FILE_ENV: str(signing.private_key_path),
            TRUSTED_PUBLIC_KEYS_FILE_ENV: str(signing.trusted_public_keys_path),
        }.get,
    )
    private_bytes = resolved.private_key_path.read_bytes()
    keyring_bytes = resolved.trusted_public_keys_path.read_bytes()
    return private_bytes, keyring_bytes, decode_keyring(keyring_bytes)


def canonical_signed_payload(package: Mapping[str, Any]) -> bytes:
    """Encode the signed package payload, excluding only the signature field."""

    payload = {str(key): value for key, value in package.items() if key != "signature"}
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sign_payload(private_key: bytes, payload: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="qwq-app-runtime-sign-") as temporary:
        payload_path = Path(temporary) / "payload.json"
        signature_path = Path(temporary) / "signature.bin"
        payload_path.write_bytes(payload)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                "/dev/stdin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            input=private_key,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError("App runtime configuration signing failed")
        signature = signature_path.read_bytes()
    if len(signature) != _ED25519_SIGNATURE_SIZE:
        raise ValueError("App runtime configuration signature is not Ed25519")
    return signature


def verify_signature(public_key: bytes, payload: bytes, signature: bytes) -> None:
    if (
        len(public_key) != _RAW_ED25519_PUBLIC_KEY_SIZE
        or len(signature) != _ED25519_SIGNATURE_SIZE
    ):
        raise ValueError("App runtime configuration signature material is invalid")
    with tempfile.TemporaryDirectory(prefix="qwq-app-runtime-verify-") as temporary:
        root = Path(temporary)
        public_path = root / "public.der"
        payload_path = root / "payload.json"
        signature_path = root / "signature.bin"
        public_path.write_bytes(_ED25519_SPKI_PREFIX + public_key)
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-rawin",
                "-pubin",
                "-keyform",
                "DER",
                "-inkey",
                str(public_path),
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise ValueError("App runtime configuration signature verification failed")
