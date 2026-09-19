"""immutable release attestation 绑定与 ContractGraph 摘要。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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


def _workspace_root_digest() -> str:
    return "sha256:" + hashlib.sha256(str(_pkg.ROOT.resolve()).encode("utf-8")).hexdigest()


def _local_candidate_binding(candidate_evidence: str) -> dict[str, Any]:
    from quwoquan_ops.cli.lib.candidate_evidence import (
        candidate_identity,
        validate_candidate_ref,
    )

    raw_ref = str(candidate_evidence or "").strip()
    if not raw_ref:
        raise ValueError("alpha-local package requires current candidate evidence")
    ref, raw, payload, fingerprint = validate_candidate_ref(
        raw_ref, repo_root=_pkg.ROOT
    )
    identity = candidate_identity(ref, raw, payload, fingerprint)
    return {
        "authority": "local-candidate-evidence",
        "environmentScope": "alpha-local",
        "nonPromotable": True,
        "workspaceRootDigest": _workspace_root_digest(),
        "candidateEvidence": {
            "ref": identity["ref"],
            "canonicalBytesSha256": identity["canonical_bytes_sha256"],
            "changedPathsDigest": identity["changed_paths_digest"],
            "impactPlanRef": identity["impact_plan_ref"],
            "impactPlanDigest": identity["impact_plan_digest"],
            "workspaceDigests": identity["workspace_digests"],
        },
    }


def resolve_package_release_binding(
    env_name: str,
    target_name: str,
    *,
    release_attestation: str,
    rollback_release_attestation: str,
    candidate_evidence: str = "",
) -> dict[str, Any]:
    if env_name == "alpha" and target_name == "alpha-local":
        has_release = bool(str(release_attestation or "").strip())
        has_rollback = bool(str(rollback_release_attestation or "").strip())
        has_candidate = bool(str(candidate_evidence or "").strip())
        if has_release or has_rollback:
            if has_candidate:
                raise ValueError(
                    "alpha-local package must choose formal release attestations or local candidate evidence"
                )
            return validate_release_attestations(
                release_attestation, rollback_release_attestation
            )
        return _local_candidate_binding(candidate_evidence)
    if str(candidate_evidence or "").strip():
        raise ValueError(
            "local candidate evidence is restricted to alpha-local packaging"
        )
    return validate_release_attestations(
        release_attestation, rollback_release_attestation
    )


def validate_release_attestations(
    release_attestation: str,
    rollback_release_attestation: str,
) -> dict[str, dict[str, str]]:
    """Fail before package/build work when immutable release inputs are absent."""

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
