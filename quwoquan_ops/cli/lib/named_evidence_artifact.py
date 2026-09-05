"""Fail-closed named-evidence artifact descriptor and report validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agent_governance_contract import declared_object, validate_declared_fields
from .descriptor_safe_io import read_repo_relative_regular_single_link
from .evidence_fingerprint import normalize_repo_relative_path


class NamedEvidenceArtifactError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _descriptor(path: Path, evidence_id: str) -> dict[str, Any]:
    try:
        raw = read_repo_relative_regular_single_link(path.parent, path.name)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact descriptor 非 single-link regular JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact descriptor 必须为 object"
        )
    try:
        validate_declared_fields(
            value, "named_evidence_receipt", "evidence_artifact_fields"
        )
    except ValueError as exc:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact 字段漂移: {exc}"
        ) from exc
    return value


def _assert_identity(
    descriptor: dict[str, Any],
    expected: dict[str, Any],
    evidence_id: str,
) -> None:
    drift = [field for field, value in expected.items() if descriptor.get(field) != value]
    if drift:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact identity 漂移: {', '.join(drift)}"
        )


def _report(
    descriptor: dict[str, Any], *, repo_root: Path, evidence_id: str
) -> dict[str, Any]:
    ref = normalize_repo_relative_path(str(descriptor["ref"]), repo_root)
    try:
        raw = read_repo_relative_regular_single_link(repo_root, ref)
    except (OSError, ValueError) as exc:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact report 非 single-link regular file: {exc}"
        ) from exc
    if _sha256(raw) != descriptor["canonical_bytes_sha256"]:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact report bytes digest 漂移"
        )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact report JSON 非法"
        ) from exc
    if not isinstance(value, dict):
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact report 必须为 object"
        )
    return value


def _assert_report_summary(
    report: dict[str, Any], descriptor: dict[str, Any], evidence_id: str
) -> None:
    expected = {
        "schema": descriptor["schema"],
        "terminal": descriptor["terminal"],
        "baseSha": descriptor["base_sha"],
        "headSha": descriptor["head_sha"],
        "changedPathsDigest": descriptor["changed_paths_digest"],
        "summary": descriptor["summary"],
        "findings": descriptor["findings"],
    }
    if any(report.get(field) != value for field, value in expected.items()):
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact report summary 漂移"
        )
    fingerprint = report.get("evidenceFingerprint")
    if not isinstance(fingerprint, dict) or (
        fingerprint.get("ref") != descriptor["evidence_fingerprint_ref"]
        or fingerprint.get("digest") != descriptor["evidence_fingerprint_digest"]
    ):
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact fingerprint 漂移"
        )


def read_result_artifact(
    *, kind: str | None, descriptor_path: Path, evidence_id: str,
    plan: dict[str, Any], plan_ref: str, plan_sha256: str,
    source: dict[str, Any], repo_root: Path,
) -> dict[str, Any] | None:
    if kind is None:
        if descriptor_path.exists() or descriptor_path.is_symlink():
            raise NamedEvidenceArtifactError(
                f"evidence={evidence_id} 未声明 result_artifact 却写入 descriptor"
            )
        return None
    descriptor = _descriptor(descriptor_path, evidence_id)
    if descriptor["kind"] != kind:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact kind 漂移"
        )
    if descriptor["terminal"] not in {"PASS", "PR_WARN", "GATE_BLOCK"}:
        raise NamedEvidenceArtifactError(
            f"evidence={evidence_id} result artifact terminal 非法"
        )
    candidate = plan["candidate_evidence_identity"]
    _assert_identity(descriptor, {
        "plan_ref": plan_ref, "plan_sha256": plan_sha256,
        "candidate_evidence_ref": candidate["ref"],
        "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
        "head_sha": source["head_sha"], "base_sha": source["merge_base_sha"],
        "changed_paths_digest": candidate["changed_paths_digest"],
        "impact_plan_ref": candidate["impact_plan_ref"],
        "impact_plan_digest": candidate["impact_plan_digest"],
    }, evidence_id)
    report = _report(descriptor, repo_root=repo_root, evidence_id=evidence_id)
    _assert_report_summary(report, descriptor, evidence_id)
    return declared_object(
        descriptor, "named_evidence_receipt", "evidence_artifact_fields"
    )
