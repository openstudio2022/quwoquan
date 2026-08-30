"""Build one environment-bound official Assistant Skill package release."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_assistant_skill_package_keys import (
    KEY_ID,
    prepare_local_assistant_skill_package_keys,
)
from .openssl3_resolver import resolve_openssl3
from .local_assistant_skill_package_publication import (
    _private_key_base64,
    _source_digest,
    derive_official_skill_package_release_identity,
    materialize_packaged_official_skill_release,
)


@dataclass(frozen=True)
class SigningMaterial:
    key_id: str
    private_key_base64: str
    public_keys_json: str


def _signing_material(
    environment: str,
    target: str,
    package_environment: dict[str, str],
) -> SigningMaterial:
    if environment == "prod" or target == "prod-hosted":
        key_id = str(
            package_environment.get("ASSISTANT_SKILL_PACKAGE_SIGNING_KEY_ID") or ""
        ).strip()
        private_key_base64 = str(
            package_environment.get(
                "ASSISTANT_SKILL_PACKAGE_SIGNING_PRIVATE_KEY_BASE64"
            )
            or ""
        ).strip()
        public_keys_json = str(
            package_environment.get(
                "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"
            )
            or ""
        ).strip()
        try:
            private_key = base64.b64decode(private_key_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise RuntimeError(
                "prod official Skill package signing private key is invalid"
            ) from exc
        if len(private_key) != 64 or not key_id or not public_keys_json:
            raise RuntimeError(
                "prod official Skill package release requires externally managed signing material"
            )
        return SigningMaterial(
            key_id=key_id,
            private_key_base64=private_key_base64,
            public_keys_json=public_keys_json,
        )
    openssl = resolve_openssl3()
    keys = prepare_local_assistant_skill_package_keys(
        environment, target, openssl=openssl
    )
    return SigningMaterial(
        key_id=KEY_ID,
        private_key_base64=_private_key_base64(
            keys.private_key_path,
            keys.public_keys_json,
            openssl=openssl,
        ),
        public_keys_json=keys.public_keys_json,
    )


def build_official_skill_package_publication(
    environment: str,
    target: str,
    *,
    package_source_root: Path,
    package_environment: dict[str, str],
    output_root: Path,
) -> dict[str, Any]:
    signing = _signing_material(environment, target, package_environment)
    source_root = (
        package_source_root
        / "quwoquan_service/services/assistant-service/resources/skill_packages/official"
    )
    source_digest = _source_digest(source_root)
    source_revision = str(
        package_environment.get("QWQ_PACKAGE_SOURCE_REVISION") or ""
    ).strip()
    identity = derive_official_skill_package_release_identity(
        environment=environment,
        target=target,
        source_digest=source_digest,
        source_revision=source_revision,
        public_keys_json=signing.public_keys_json,
        signing_key_id=signing.key_id,
    )
    if output_root.exists():
        shutil.rmtree(output_root)
    command = [
        "go",
        "run",
        "./services/assistant-service/cmd/skill-package-build",
        "--source-root",
        "services/assistant-service/resources/skill_packages/official",
        "--output-root",
        str(output_root),
        "--package-version",
        "1.0.0",
        "--build-id",
        identity["buildId"],
        "--source-repository",
        "quwoquan",
        "--source-revision",
        source_revision,
        "--built-at",
        "2026-01-01T00:00:00Z",
        "--key-id",
        signing.key_id,
        "--command-id",
        identity["commandId"],
        "--expected-revision",
        "0",
        "--activated-by",
        (
            f"service:release-bootstrap:{target}"
            if environment == "prod"
            else f"service:local-managed-bootstrap:{target}"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=str(package_source_root / "quwoquan_service"),
        env={
            **os.environ,
            **package_environment,
            "ASSISTANT_SKILL_PACKAGE_SIGNING_PRIVATE_KEY_BASE64": (
                signing.private_key_base64
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        try:
            build_report = json.loads(result.stdout)
            release = materialize_packaged_official_skill_release(
                output_root=output_root,
                environment=environment,
                target=target,
                source_digest=source_digest,
                source_revision=source_revision,
                public_keys_json=signing.public_keys_json,
                build_report=build_report,
                signing_key_id=signing.key_id,
            )
            result.stdout = json.dumps(
                {**build_report, "packagedRelease": release},
                ensure_ascii=True,
                separators=(",", ":"),
            ) + "\n"
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            result = subprocess.CompletedProcess(
                command,
                1,
                stdout=result.stdout,
                stderr=str(exc),
            )
    return {
        "name": "assistant-skill-package-publication",
        "argv": command,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
