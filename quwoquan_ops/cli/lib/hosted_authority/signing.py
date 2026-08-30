"""Detached Ed25519 verification for hosted authority exact response bytes."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

try:
    from lib.openssl3_resolver import resolve_openssl3
except ImportError:  # repository package import path
    from quwoquan_ops.cli.lib.openssl3_resolver import resolve_openssl3

from .client import HostedAuthorityError, SignatureEnvelope

_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def decode_public_keyring(raw: bytes) -> dict[str, bytes]:
    """Decode a rotation-capable key-id -> raw Ed25519 public-key mapping."""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "keyring is unreadable") from error
    if not isinstance(value, dict) or not value:
        raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "keyring must be a non-empty object")
    decoded: dict[str, bytes] = {}
    for key_id, encoded in value.items():
        if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None or not isinstance(encoded, str):
            raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "keyring entry is invalid")
        try:
            public_key = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "public key is not strict base64") from error
        if len(public_key) != 32:
            raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "public key is not Ed25519")
        if base64.b64encode(public_key).decode("ascii") != encoded:
            raise HostedAuthorityError("HOSTED_AUTHORITY.KEYRING_INVALID", "public key is not canonical base64")
        decoded[key_id] = public_key
    return decoded


def signature_message(exact_body: bytes, _envelope: SignatureEnvelope) -> bytes:
    """Backend signer contract: Ed25519 signs the exact canonical receipt bytes only."""
    return exact_body


def verify_ed25519(
    exact_body: bytes, envelope: SignatureEnvelope, trusted_public_keys: Mapping[str, bytes],
) -> None:
    public_key = trusted_public_keys.get(envelope.key_id)
    if public_key is None or len(public_key) != 32:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "signature key id is untrusted")
    encoded = envelope.signature_b64
    if "=" in encoded:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "signature is not canonical raw base64")
    try:
        signature = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
    except ValueError as error:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "signature is not strict raw base64") from error
    if base64.b64encode(signature).decode("ascii").rstrip("=") != encoded:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "signature is not canonical raw base64")
    if len(signature) != 64:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "signature is not Ed25519")
    openssl = resolve_openssl3()
    with tempfile.TemporaryDirectory(prefix="qwq-hosted-authority-verify-") as temporary:
        root = Path(temporary)
        public_path = root / "public.der"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        public_path.write_bytes(_ED25519_SPKI_PREFIX + public_key)
        payload_path.write_bytes(signature_message(exact_body, envelope))
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [
                str(openssl.executable), "pkeyutl", "-verify", "-rawin", "-pubin",
                "-keyform", "DER", "-inkey", str(public_path), "-in", str(payload_path),
                "-sigfile", str(signature_path),
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
    if result.returncode != 0:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SIGNATURE_INVALID", "Ed25519 verification failed")
