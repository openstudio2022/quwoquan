"""Materialize local non-production assistant Skill package trust keys.

assistant-service refuses to start without
``ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON``. Local Alpha/Beta/Gamma
material is issued under the target-scoped deploy work root and never committed.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .local_integration_service_mtls import _openssl_bin
from .output_paths import deployment_target_path


ROLE = "assistant-skill-package"
KEY_ID = "local-managed-ed25519"


@dataclass(frozen=True)
class LocalAssistantSkillPackageKeys:
    environment: dict[str, str]
    public_keys_json: str
    private_key_path: Path


def prepare_local_assistant_skill_package_keys(
    environment: str,
    target_name: str,
) -> LocalAssistantSkillPackageKeys:
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "assistant Skill package key bootstrap is limited to Alpha/Beta/Gamma"
        )
    if target_name != f"{environment}-local":
        raise ValueError(
            "assistant Skill package key target/environment mismatch: "
            f"environment={environment} target={target_name}"
        )
    openssl = _openssl_bin()
    key_dir = deployment_target_path(target_name, "secrets", ROLE)
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    private_pem = key_dir / "signing.pem"
    public_keys_path = key_dir / "trusted_public_keys.json"
    if not _material_is_ready(openssl, private_pem, public_keys_path):
        _issue_keypair(
            openssl=openssl,
            key_dir=key_dir,
            private_pem=private_pem,
            public_keys_path=public_keys_path,
        )
    if not _material_is_ready(openssl, private_pem, public_keys_path):
        raise RuntimeError(
            "GATE_BLOCK: assistant Skill package trust keys are empty or invalid "
            f"for {target_name}"
        )
    public_keys_json = public_keys_path.read_text(encoding="utf-8").strip()
    return LocalAssistantSkillPackageKeys(
        environment={
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON": public_keys_json,
        },
        public_keys_json=public_keys_json,
        private_key_path=private_pem,
    )


def _material_is_ready(
    openssl: str,
    private_pem: Path,
    public_keys_path: Path,
) -> bool:
    if not private_pem.is_file() or not public_keys_path.is_file():
        return False
    if private_pem.is_symlink() or public_keys_path.is_symlink():
        return False
    if private_pem.stat().st_mode & 0o077:
        return False
    if private_pem.stat().st_size == 0 or public_keys_path.stat().st_size == 0:
        return False
    try:
        payload = json.loads(public_keys_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or KEY_ID not in payload:
        return False
    check = subprocess.run(
        [openssl, "pkey", "-in", str(private_pem), "-noout"],
        capture_output=True,
        check=False,
    )
    return check.returncode == 0


def _issue_keypair(
    *,
    openssl: str,
    key_dir: Path,
    private_pem: Path,
    public_keys_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(dir=key_dir) as temporary:
        temp = Path(temporary)
        next_private = temp / "signing.pem"
        next_public_der = temp / "public.der"
        commands = (
            [
                openssl,
                "genpkey",
                "-algorithm",
                "ED25519",
                "-out",
                str(next_private),
            ],
            [
                openssl,
                "pkey",
                "-in",
                str(next_private),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(next_public_der),
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
                    "GATE_BLOCK: assistant Skill package key issuance failed: "
                    + (result.stderr or result.stdout).strip()
                )
        der = next_public_der.read_bytes()
        # Ed25519 SubjectPublicKeyInfo ends with the 32-byte raw public key.
        if len(der) < 32:
            raise RuntimeError(
                "GATE_BLOCK: assistant Skill package public key DER is invalid"
            )
        raw_public = der[-32:]
        payload = {KEY_ID: base64.b64encode(raw_public).decode("ascii")}
        next_json = temp / "trusted_public_keys.json"
        next_json.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(next_private, 0o600)
        os.chmod(next_json, 0o600)
        next_private.replace(private_pem)
        next_json.replace(public_keys_path)
        os.chmod(private_pem, 0o600)
        os.chmod(public_keys_path, 0o600)
