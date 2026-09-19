"""Prepare the shared nonprod App runtime signing authority outside the repo."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .app_runtime_config_signing import SigningMaterial, validate_signing_material
from .openssl3_resolver import OpenSSL3Executable, resolve_openssl3
from .output_paths import deployment_target_path

ROLE = "app-runtime-config"
LOCAL_AUTHORITY_PROFILE = "nonprod"
LOCAL_AUTHORITY_TARGET = "app-build-products"
DEFAULT_KEY_ID = "local-managed-app-runtime-nonprod-ed25519"
PROD_SIM_REHEARSAL_ENVIRONMENT = "prod"
PROD_SIM_REHEARSAL_TARGET = "prod-sim"
PROD_SIM_REHEARSAL_PROFILE = "prod-local-rehearsal"
PROD_SIM_REHEARSAL_KEY_ID = "local-prod-sim-rehearsal-ed25519"


def prepare_local_app_runtime_config_signing(repo_root: Path) -> SigningMaterial:
    """Return the create-once Alpha/Beta/Gamma signing authority.

    Prod has no local issuance path through this API. The only local prod exception
    is the separately scoped prod-sim rehearsal authority below.
    """

    return _prepare_local_signing(
        repo_root,
        authority_target=LOCAL_AUTHORITY_TARGET,
        profile=LOCAL_AUTHORITY_PROFILE,
        key_id=DEFAULT_KEY_ID,
        partial_label="App runtime local nonprod signing authority",
    )


def prepare_local_prod_sim_rehearsal_runtime_config_signing(
    repo_root: Path,
    *,
    environment: str,
    target: str,
) -> SigningMaterial:
    """Issue only target-scoped, non-promotable prod-sim rehearsal material.

    This is deliberately not the nonprod authority and never accepts prod-hosted.
    Its key material remains under the prod-sim deployment target and must only be
    used with the prod-sim local rehearsal runtime-config materializer.
    """

    if (environment, target) != (
        PROD_SIM_REHEARSAL_ENVIRONMENT,
        PROD_SIM_REHEARSAL_TARGET,
    ):
        raise ValueError(
            "local prod-sim rehearsal signing requires environment=prod "
            "and target=prod-sim"
        )
    return _prepare_local_signing(
        repo_root,
        authority_target=PROD_SIM_REHEARSAL_TARGET,
        profile=PROD_SIM_REHEARSAL_PROFILE,
        key_id=PROD_SIM_REHEARSAL_KEY_ID,
        partial_label="App runtime local prod-sim rehearsal signing authority",
    )


def _prepare_local_signing(
    repo_root: Path,
    *,
    authority_target: str,
    profile: str,
    key_id: str,
    partial_label: str,
) -> SigningMaterial:
    openssl = resolve_openssl3()
    key_dir = deployment_target_path(authority_target, "secrets", ROLE, profile)
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    private_path = key_dir / "signing.pem"
    keyring_path = key_dir / "trusted_public_keys.json"
    exists = (private_path.exists(), keyring_path.exists())
    if exists == (False, False):
        _issue_keypair(
            key_dir,
            private_path,
            keyring_path,
            key_id=key_id,
            openssl=openssl,
        )
        exists = (private_path.exists(), keyring_path.exists())
    if exists != (True, True):
        raise ValueError(f"{partial_label} is partial")
    if private_path.is_symlink() or keyring_path.is_symlink():
        raise ValueError("App runtime local signing material must not use symlinks")
    try:
        keyring = json.loads(keyring_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"App runtime local trusted keyring is unreadable: {exc}"
        ) from exc
    if not isinstance(keyring, dict) or set(keyring) != {key_id}:
        raise ValueError("App runtime local trusted keyring must contain one expected key")
    signing = SigningMaterial(key_id, private_path, keyring_path)
    validate_signing_material(repo_root, signing, openssl=openssl)
    return signing


def _issue_keypair(
    key_dir: Path,
    private_path: Path,
    keyring_path: Path,
    *,
    key_id: str = DEFAULT_KEY_ID,
    openssl: OpenSSL3Executable | None = None,
) -> None:
    selected = openssl or resolve_openssl3()
    with tempfile.TemporaryDirectory(dir=key_dir) as temporary:
        staging = Path(temporary)
        next_private = staging / "signing.pem"
        public_der = staging / "public.der"
        commands = (
            ("genpkey", "-algorithm", "ED25519", "-out", str(next_private)),
            (
                "pkey",
                "-in",
                str(next_private),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(public_der),
            ),
        )
        for arguments in commands:
            result = subprocess.run(
                selected.argv(*arguments),
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "GATE_BLOCK: App runtime local key issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        encoded = public_der.read_bytes()
        if len(encoded) < 32:
            raise RuntimeError(
                "GATE_BLOCK: App runtime local public key DER is invalid"
            )
        next_keyring = staging / "trusted_public_keys.json"
        next_keyring.write_text(
            json.dumps(
                {key_id: base64.b64encode(encoded[-32:]).decode("ascii")},
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(next_private, 0o600)
        os.chmod(next_keyring, 0o600)
        try:
            with private_path.open("xb") as destination:
                destination.write(next_private.read_bytes())
            os.chmod(private_path, 0o600)
        except FileExistsError:
            pass
        try:
            with keyring_path.open("xb") as destination:
                destination.write(next_keyring.read_bytes())
            os.chmod(keyring_path, 0o600)
        except FileExistsError:
            pass
