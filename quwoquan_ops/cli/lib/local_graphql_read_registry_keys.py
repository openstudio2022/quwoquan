"""Prepare target-scoped GraphQL registry signing keys for local non-production."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .graphql_read_registry_signing import (
    SigningMaterial,
    validate_signing_material,
)
from .local_integration_service_mtls import _openssl_bin
from .output_paths import deployment_target_path


ROLE = "graphql-read-registry"
DEFAULT_KEY_ID = "local-managed-ed25519"


def prepare_local_graphql_read_registry_signing(
    repo_root: Path,
    environment: str,
    target: str,
) -> SigningMaterial:
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "GraphQL registry local signing bootstrap is limited to Alpha/Beta/Gamma"
        )
    if target != f"{environment}-local":
        raise ValueError(
            "GraphQL registry local signing target/environment mismatch: "
            f"environment={environment} target={target}"
        )
    key_dir = deployment_target_path(target, "secrets", ROLE)
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    private_path = key_dir / "signing.pem"
    keyring_path = key_dir / "trusted_public_keys.json"
    exists = (private_path.exists(), keyring_path.exists())
    if exists == (False, False):
        _issue_keypair(key_dir, private_path, keyring_path)
    elif exists != (True, True):
        raise ValueError(
            f"GraphQL registry local signing material is partial for {target}"
        )
    if private_path.is_symlink() or keyring_path.is_symlink():
        raise ValueError("GraphQL registry local signing material must not use symlinks")
    try:
        keyring = json.loads(keyring_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"GraphQL registry local trusted keyring is unreadable: {exc}"
        ) from exc
    if not isinstance(keyring, dict) or len(keyring) != 1:
        raise ValueError("GraphQL registry local trusted keyring must contain one key")
    key_id = next(iter(keyring))
    signing = SigningMaterial(key_id, private_path, keyring_path)
    validate_signing_material(repo_root, signing)
    return signing


def _issue_keypair(
    key_dir: Path,
    private_path: Path,
    keyring_path: Path,
) -> None:
    openssl = _openssl_bin()
    with tempfile.TemporaryDirectory(dir=key_dir) as temporary:
        staging = Path(temporary)
        next_private = staging / "signing.pem"
        public_der = staging / "public.der"
        commands = (
            [openssl, "genpkey", "-algorithm", "ED25519", "-out", str(next_private)],
            [
                openssl,
                "pkey",
                "-in",
                str(next_private),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(public_der),
            ],
        )
        for command in commands:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "GATE_BLOCK: GraphQL registry local key issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        encoded = public_der.read_bytes()
        if len(encoded) < 32:
            raise RuntimeError(
                "GATE_BLOCK: GraphQL registry local public key DER is invalid"
            )
        next_keyring = staging / "trusted_public_keys.json"
        next_keyring.write_text(
            json.dumps(
                {DEFAULT_KEY_ID: base64.b64encode(encoded[-32:]).decode("ascii")},
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(next_private, 0o600)
        os.chmod(next_keyring, 0o600)
        next_private.replace(private_path)
        next_keyring.replace(keyring_path)
        os.chmod(private_path, 0o600)
        os.chmod(keyring_path, 0o600)
