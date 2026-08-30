#!/usr/bin/env python3
"""Create hermetic, non-production inputs for the environment packaging gate."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

from cleanup_deployment_test_workspace import (
    validated_deployment_test_workspace,
)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.openssl3_resolver import resolve_openssl3


KEY_ID = "packaging-contract"
PRIVATE_KEY_NAME = "graphql-signing-private.pem"
KEYRING_NAME = "graphql-trusted-public-keys.json"
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def _write_release_attestation(
    workspace: Path,
    *,
    filename: str,
    release_id: str,
    digest_character: str,
) -> None:
    payload = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "payloadSha256": "sha256:" + digest_character * 64,
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
    }
    (workspace / filename).write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def prepare_environment_packaging_contract_inputs(raw_workspace: str) -> None:
    workspace = validated_deployment_test_workspace(raw_workspace)
    if not workspace.is_dir():
        raise ValueError("deployment test workspace must exist before input preparation")

    private_key = workspace / PRIVATE_KEY_NAME
    keyring = workspace / KEYRING_NAME
    for path in (private_key, keyring):
        if path.exists() or path.is_symlink():
            raise ValueError(f"packaging contract input already exists: {path.name}")

    openssl = resolve_openssl3()
    subprocess.run(
        openssl.argv("genpkey", "-algorithm", "ED25519", "-out", str(private_key)),
        check=True,
        capture_output=True,
    )
    os.chmod(private_key, 0o600, follow_symlinks=False)
    public_result = subprocess.run(
        openssl.argv("pkey", "-in", str(private_key), "-pubout", "-outform", "DER"),
        check=True,
        capture_output=True,
    )
    expected_size = len(_ED25519_SPKI_PREFIX) + 32
    if (
        len(public_result.stdout) != expected_size
        or not public_result.stdout.startswith(_ED25519_SPKI_PREFIX)
    ):
        raise ValueError("packaging contract signing key is not Ed25519")
    keyring.write_text(
        json.dumps(
            {KEY_ID: base64.b64encode(public_result.stdout[-32:]).decode("ascii")},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.chmod(keyring, 0o600, follow_symlinks=False)

    _write_release_attestation(
        workspace,
        filename="candidate-release.json",
        release_id="packaging-contract-candidate",
        digest_character="1",
    )
    _write_release_attestation(
        workspace,
        filename="rollback-release.json",
        release_id="packaging-contract-rollback",
        digest_character="2",
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: prepare_environment_packaging_contract_inputs.py WORKSPACE", file=sys.stderr)
        return 2
    try:
        prepare_environment_packaging_contract_inputs(sys.argv[1])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
