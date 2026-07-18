"""Create the non-environment attestations for the Zhejiang/Sichuan final release.

The writer intentionally has no partial or canary mode.  A two-province closure
is meaningful only when the immutable payload contains every static coverage
identity and every contributing execution is fully review-ready.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from governance.coverage.master_list import iter_master_leaves, load_master_list_file, master_list_files
from core.io import read_json, write_json
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from content.execution.workspace import execution_root
from verify.verify_execution_readiness import execution_readiness_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report


PROVINCES = ("浙江省", "四川省")
ATTESTATION_FILES = {
    "coverage": "coverage_closure.json",
    "source_rights": "source_rights_closure.json",
    "execution": "execution_closure.json",
    "importer_api": "importer_api_closure.json",
    "gamma_app_uat": "gamma_app_uat_closure.json",
    "rollback_replay": "rollback_replay_closure.json",
}


class TwoProvinceClosureError(ValueError):
    """The immutable release does not yet satisfy the final two-province contract."""


def expected_entity_refs() -> dict[str, set[str]]:
    rows: dict[str, set[str]] = {province: set() for province in PROVINCES}
    for path in master_list_files():
        document = load_master_list_file(path)
        province = str(document.get("province") or "")
        if province not in rows:
            continue
        for _district, leaf in iter_master_leaves(document):
            name = str(leaf.get("canonicalName") or leaf.get("name") or "").strip()
            entity_type = str(leaf.get("entityType") or "").strip()
            if name and entity_type:
                rows[province].add(f"{entity_type}/{name}")
    return rows


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise TwoProvinceClosureError(f"{label} unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TwoProvinceClosureError(f"{label} must be an object: {path}")
    return payload


def _release_payload(release_root: Path) -> tuple[str, tuple[str, ...], set[str], str]:
    header = _read_object(payload_file(release_root, "release.json"), label="release header")
    desired = _read_object(payload_file(release_root, "desired_state.json"), label="release desired state")
    release_id = str(header.get("releaseId") or "").strip()
    if not release_id or release_id != release_root.name:
        raise TwoProvinceClosureError("release header releaseId does not match immutable release directory")
    execution_ids = tuple(sorted({str(item).strip() for item in (header.get("executionIds") or []) if str(item).strip()}))
    if not execution_ids:
        raise TwoProvinceClosureError("release payload has no executionIds")
    desired_refs = desired.get("desiredRefs") if isinstance(desired.get("desiredRefs"), Mapping) else {}
    entity_refs = {str(item).strip() for item in (desired_refs.get("entities") or []) if str(item).strip()}
    if not entity_refs:
        raise TwoProvinceClosureError("release payload has no entity desiredRefs")
    return release_id, execution_ids, entity_refs, payload_digest(release_root)


def _target_refs_for_execution(execution_id: str) -> set[str]:
    root = execution_root(execution_id)
    qualification_path = root / "sources" / "qualification" / "result.json"
    qualification = _read_object(qualification_path, label="source qualification")
    try:
        assert_valid(
            qualification,
            "execution",
            "source_qualification_result",
            label=f"source_qualification_result:{execution_id}",
        )
    except (TypeError, ValueError) as exc:
        raise TwoProvinceClosureError(str(exc)) from exc
    if qualification.get("executionId") != execution_id or qualification.get("passed") is not True:
        raise TwoProvinceClosureError(f"{execution_id}: source qualification is not passed")

    spec_path = root / "0.plan" / "execution_spec.yaml"
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise TwoProvinceClosureError(f"{execution_id}: execution spec unreadable: {exc}") from exc
    scope = spec.get("scope") if isinstance(spec, Mapping) and isinstance(spec.get("scope"), Mapping) else {}
    targets = scope.get("coverageTargets") if isinstance(scope, Mapping) else []
    by_name: dict[str, str] = {}
    for target in targets if isinstance(targets, list) else []:
        if not isinstance(target, Mapping):
            raise TwoProvinceClosureError(f"{execution_id}: coverage target is not an object")
        name = str(target.get("name") or "").strip()
        entity_type = str(target.get("entityType") or "").strip()
        if not name or not entity_type or name in by_name:
            raise TwoProvinceClosureError(f"{execution_id}: coverage target identity is invalid")
        by_name[name] = f"{entity_type}/{name}"
    if not by_name:
        raise TwoProvinceClosureError(f"{execution_id}: execution spec has no coverage targets")

    confirmed: set[str] = set()
    rows = qualification.get("targets") if isinstance(qualification.get("targets"), list) else []
    if len(rows) != len(by_name):
        raise TwoProvinceClosureError(f"{execution_id}: qualification target count drift")
    for row in rows:
        if not isinstance(row, Mapping):
            raise TwoProvinceClosureError(f"{execution_id}: qualification target is not an object")
        name = str(row.get("name") or "").strip()
        ref = by_name.get(name)
        primary = row.get("primarySource") if isinstance(row.get("primarySource"), Mapping) else {}
        if not ref or str(row.get("status") or "") != "confirmed":
            raise TwoProvinceClosureError(f"{execution_id}: target qualification is not confirmed: {name or '<missing>'}")
        if not all(str(primary.get(key) or "").strip() for key in ("canonicalUrl", "snapshotHash", "evidenceRef")):
            raise TwoProvinceClosureError(f"{execution_id}: confirmed target lacks source evidence: {name}")
        confirmed.add(ref)
    if confirmed != set(by_name.values()):
        raise TwoProvinceClosureError(f"{execution_id}: qualification targets do not close execution targets")
    return confirmed


def write_two_province_attestation(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        assert_valid(
            dict(payload),
            "release",
            "two_province_release_attestation",
            label=path.as_posix(),
        )
    except (TypeError, ValueError) as exc:
        raise TwoProvinceClosureError(str(exc)) from exc
    if path.exists():
        existing = _read_object(path, label="existing two-province attestation")
        # `recordedAt` describes the first successful write.  Re-running the
        # command against the same frozen payload must be safe, but must never
        # replace the original attestation or permit evidence drift.
        expected = dict(payload)
        comparable_existing = dict(existing)
        comparable_expected = dict(expected)
        comparable_existing.pop("recordedAt", None)
        comparable_expected.pop("recordedAt", None)
        if comparable_existing != comparable_expected:
            raise TwoProvinceClosureError(f"attestation is immutable and conflicts: {path}")
        return
    write_json(path, dict(payload))


def build_pre_environment_attestations(release_root: Path) -> dict[str, Any]:
    """Write coverage/source-rights/execution attestations after full static closure.

    Gamma importer/API/UAT and rollback proofs intentionally remain absent here:
    they must be produced by the corresponding environment operations, not by a
    local release assembler.
    """
    release_id, execution_ids, desired_refs, digest = _release_payload(release_root)
    expected_by_province = expected_entity_refs()
    expected_refs = set().union(*expected_by_province.values())
    if not all(expected_by_province.values()):
        raise TwoProvinceClosureError("two-province coverage master list is incomplete")
    if desired_refs != expected_refs:
        raise TwoProvinceClosureError(
            f"release coverage is incomplete: expected={len(expected_refs)} actual={len(desired_refs)}"
        )

    confirmed_refs: set[str] = set()
    for execution_id in execution_ids:
        readiness_issues = execution_readiness_issues(execution_id, require_reviewed=True)
        if readiness_issues:
            raise TwoProvinceClosureError(
                f"{execution_id}: execution readiness failed: {readiness_issues[0]}"
            )
        media = homepage_media_completeness_report(execution_id)
        if not bool(media.get("passed")):
            raise TwoProvinceClosureError(f"{execution_id}: homepage media completeness failed")
        refs = _target_refs_for_execution(execution_id)
        if not refs <= desired_refs:
            unexpected = sorted(refs - desired_refs)
            raise TwoProvinceClosureError(
                f"{execution_id}: qualified target absent from immutable release: {unexpected[:3]}"
            )
        confirmed_refs.update(refs)
    if confirmed_refs != desired_refs:
        missing = sorted(desired_refs - confirmed_refs)
        raise TwoProvinceClosureError(
            f"release execution/source closure is incomplete: missing={missing[:3]} count={len(missing)}"
        )

    recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    common = {
        "schema": "quwoquan_data.two_province_release_attestation",
        "releaseId": release_id,
        "payloadSha256": digest,
        "passed": True,
        "recordedAt": recorded_at,
    }
    attestations = attestation_root(release_root)
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["coverage"],
        {
            **common,
            "kind": "coverage",
            "provinces": {
                province: {"approvedHomepageCount": len(refs)}
                for province, refs in expected_by_province.items()
            },
            "approvedEntityRefs": sorted(desired_refs),
        },
    )
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["source_rights"],
        {
            **common,
            "kind": "source_rights",
            "executionIds": list(execution_ids),
            "qualifiedEntityRefs": sorted(confirmed_refs),
            "rightsEntityRefs": sorted(confirmed_refs),
        },
    )
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["execution"],
        {
            **common,
            "kind": "execution",
            "executionIds": list(execution_ids),
            "approvedEntityRefs": sorted(confirmed_refs),
        },
    )
    return {
        "releaseId": release_id,
        "payloadSha256": digest,
        "executionIds": list(execution_ids),
        "entityCount": len(confirmed_refs),
        "attestations": [
            ATTESTATION_FILES["coverage"],
            ATTESTATION_FILES["source_rights"],
            ATTESTATION_FILES["execution"],
        ],
    }


__all__ = [
    "ATTESTATION_FILES",
    "PROVINCES",
    "TwoProvinceClosureError",
    "build_pre_environment_attestations",
    "expected_entity_refs",
    "write_two_province_attestation",
]
