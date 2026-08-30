"""External Ed25519 authority for signed GraphQL registry packages."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3

SIGNING_KEY_ID_ENV = "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_KEY_ID"
SIGNING_PRIVATE_KEY_FILE_ENV = "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_PRIVATE_KEY_FILE"
TRUSTED_PUBLIC_KEYS_FILE_ENV = "QWQ_GRAPHQL_READ_REGISTRY_TRUSTED_PUBLIC_KEYS_FILE"
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RAW_ED25519_PUBLIC_KEY_SIZE = 32
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
        raise ValueError(
            f"GraphQL trusted public keyring is unreadable: {exc}"
        ) from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("GraphQL trusted public keyring must be a non-empty object")
    normalized: dict[str, str] = {}
    for key_id, public_value in value.items():
        if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None:
            raise ValueError("GraphQL trusted public keyring has an invalid keyId")
        if not isinstance(public_value, str):
            raise ValueError("GraphQL trusted public key must be base64 text")
        try:
            raw = base64.b64decode(public_value, validate=True)
        except ValueError as exc:
            raise ValueError("GraphQL trusted public key is not strict base64") from exc
        if len(raw) != _RAW_ED25519_PUBLIC_KEY_SIZE:
            raise ValueError("GraphQL trusted public key must be Ed25519")
        normalized[key_id] = base64.b64encode(raw).decode("ascii")
    if value != normalized:
        raise ValueError("GraphQL trusted public keyring is not canonical")
    return normalized


def _derive_public_key(
    private_key: bytes,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> bytes:
    selected = openssl or resolve_openssl3()
    result = subprocess.run(
        selected.argv("pkey", "-pubout", "-outform", "DER"),
        input=private_key,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("GraphQL signing private key is not a valid Ed25519 PEM")
    if not result.stdout.startswith(_ED25519_SPKI_PREFIX) or len(result.stdout) != (
        len(_ED25519_SPKI_PREFIX) + _RAW_ED25519_PUBLIC_KEY_SIZE
    ):
        raise ValueError("GraphQL signing private key is not Ed25519")
    return result.stdout[-_RAW_ED25519_PUBLIC_KEY_SIZE:]


def resolve_signing_material(
    repo_root: Path,
    getenv: Callable[[str], str | None] = os.getenv,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> SigningMaterial:
    """Resolve one explicit external authority without serializing secret refs."""

    key_id = str(getenv(SIGNING_KEY_ID_ENV) or "").strip()
    private_value = str(getenv(SIGNING_PRIVATE_KEY_FILE_ENV) or "").strip()
    keyring_value = str(getenv(TRUSTED_PUBLIC_KEYS_FILE_ENV) or "").strip()
    if not key_id or not private_value or not keyring_value:
        raise ValueError(
            "GraphQL registry signing keyId, private-key ref, and trusted keyring "
            "are required"
        )
    if _KEY_ID.fullmatch(key_id) is None:
        raise ValueError("GraphQL registry signing keyId is invalid")
    private_path = _outside_repository(
        repo_root,
        Path(private_value).expanduser(),
        label="GraphQL registry signing private key",
    )
    keyring_path = _outside_repository(
        repo_root,
        Path(keyring_value).expanduser(),
        label="GraphQL registry trusted public keyring",
    )
    private_info = _regular_file(
        private_path, label="GraphQL registry signing private key"
    )
    keyring_info = _regular_file(
        keyring_path, label="GraphQL registry trusted public keyring"
    )
    if private_info.st_mode & 0o077:
        raise ValueError(
            "GraphQL registry signing private key permissions must be 0600"
        )
    if keyring_info.st_mode & 0o022:
        raise ValueError(
            "GraphQL registry trusted public keyring permissions are unsafe"
        )
    private_bytes = private_path.read_bytes()
    keyring = decode_keyring(keyring_path.read_bytes())
    if key_id not in keyring:
        raise ValueError(
            "GraphQL registry signing keyId is absent from trusted keyring"
        )
    expected_public = base64.b64decode(keyring[key_id], validate=True)
    selected = openssl or resolve_openssl3()
    if _derive_public_key(private_bytes, openssl=selected) != expected_public:
        raise ValueError("GraphQL registry signing private key does not match keyring")
    return SigningMaterial(key_id, private_path, keyring_path)


def validate_signing_material(
    repo_root: Path,
    signing: SigningMaterial,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> tuple[bytes, bytes, dict[str, str]]:
    resolved = resolve_signing_material(
        repo_root,
        {
            SIGNING_KEY_ID_ENV: signing.key_id,
            SIGNING_PRIVATE_KEY_FILE_ENV: str(signing.private_key_path),
            TRUSTED_PUBLIC_KEYS_FILE_ENV: str(signing.trusted_public_keys_path),
        }.get,
        openssl=openssl,
    )
    private_bytes = resolved.private_key_path.read_bytes()
    keyring_bytes = resolved.trusted_public_keys_path.read_bytes()
    return private_bytes, keyring_bytes, decode_keyring(keyring_bytes)


def sign_payload(
    private_key: bytes,
    payload: bytes,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> bytes:
    selected = openssl or resolve_openssl3()
    with tempfile.TemporaryDirectory(prefix="qwq-graphql-sign-") as temporary:
        payload_path = Path(temporary) / "payload.json"
        signature_path = Path(temporary) / "signature.bin"
        payload_path.write_bytes(payload)
        result = subprocess.run(
            selected.argv(
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                "/dev/stdin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ),
            input=private_key,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError("GraphQL registry signing failed")
        signature = signature_path.read_bytes()
    if len(signature) != 64:
        raise ValueError("GraphQL registry signature is not Ed25519")
    return signature


def verify_signature(
    public_key: bytes,
    payload: bytes,
    signature: bytes,
    *,
    openssl: OpenSSL3Executable | None = None,
) -> None:
    if len(public_key) != 32 or len(signature) != 64:
        raise ValueError("GraphQL registry signature material is invalid")
    selected = openssl or resolve_openssl3()
    with tempfile.TemporaryDirectory(prefix="qwq-graphql-verify-") as temporary:
        root = Path(temporary)
        public_path = root / "public.der"
        payload_path = root / "payload.json"
        signature_path = root / "signature.bin"
        public_path.write_bytes(_ED25519_SPKI_PREFIX + public_key)
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            selected.argv(
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
            ),
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise ValueError("GraphQL registry signature verification failed")
