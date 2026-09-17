"""immutable release attestation 绑定与 ContractGraph 摘要。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from .constants import RELEASE_ATTESTATION_SCHEMA_PATH


def _release_binding(path_value: str, *, label: str) -> dict[str, str]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        raise ValueError(f"{label} release attestation is required")
    path = path.resolve()
    try:
        encoded = path.read_bytes()
        value = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} release attestation is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} release attestation must be an object")
    # Data authoring schema 是唯一闭集；旧类别和未知字段不能被投影掉后通过。
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise ValueError("release attestation schema validator is unavailable") from exc

    schema = json.loads(RELEASE_ATTESTATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(validator.iter_errors(value), None)
    if error is not None:
        raise ValueError(f"{label} release attestation schema mismatch: {error.message}")
    return {
        "releaseId": value["releaseId"],
        "releaseDigest": value["payloadSha256"],
        "attestationRef": str(path),
        "attestationDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def canonical_contract_graph_digest() -> str:
    """Digest the exact canonical ContractGraph bytes used by this package."""

    path = _pkg.CONTRACT_GRAPH_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("canonical ContractGraph is missing or unsafe")
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"canonical ContractGraph is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("canonical ContractGraph must be a JSON object")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_release_attestations(
    release_attestation: str,
    rollback_release_attestation: str,
    *,
    environment: str = "",
    target: str = "",
) -> dict[str, dict[str, str]]:
    """Fail before package/build work when immutable release inputs are absent.
    
    Alpha local offline is exempt per environment-topology-and-packaging spec REQ-002:
    "dev-session does not create or activate immutable candidate, also not require
    Data release attestation" and "Alpha offline does not request Remote".
    """
    
    # Alpha local offline exemption: dev-session path does not require attestation
    is_alpha_local = environment == "alpha" and target == "alpha-local"
    if is_alpha_local and not release_attestation.strip() and not rollback_release_attestation.strip():
        # Return empty binding for alpha-local offline scenario
        return {
            "candidate": {
                "releaseId": "",
                "releaseDigest": "",
                "attestationRef": "",
                "attestationDigest": "",
            },
            "rollback": {
                "releaseId": "",
                "releaseDigest": "",
                "attestationRef": "",
                "attestationDigest": "",
            },
        }

    candidate = _release_binding(release_attestation, label="candidate")
    rollback = _release_binding(
        rollback_release_attestation,
        label="rollback",
    )
    if (
        candidate["releaseId"] == rollback["releaseId"]
        or candidate["releaseDigest"] == rollback["releaseDigest"]
    ):
        raise ValueError(
            "candidate and rollback release attestations must have distinct "
            "releaseId and releaseDigest"
        )
    return {
        "candidate": candidate,
        "rollback": rollback,
    }
