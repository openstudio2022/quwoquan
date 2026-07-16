#!/usr/bin/env python3
"""Strict final closure gate for Zhejiang and Sichuan homepage coverage."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from content.release.canonical.two_province_closure import ATTESTATION_FILES, PROVINCES, expected_entity_refs
from content.release.canonical.two_province_environment_closure import environment_attestation_issues


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _evidence_paths_exist(refs: object) -> bool:
    if not isinstance(refs, list) or not refs:
        return False
    for raw in refs:
        rel = Path(str(raw or ""))
        if rel.is_absolute() or ".." in rel.parts:
            return False
        path = OUTPUT_ROOT / rel
        if not path.is_file() or rel.parts[:3] != ("env", "gamma", "runs"):
            return False
    return True


def _attestation_issues(
    *,
    release_id: str,
    payload_sha256: str,
    kind: str,
    payload: Mapping[str, Any],
    expected: dict[str, set[str]],
    payload_execution_ids: set[str],
) -> list[str]:
    issues: list[str] = []
    try:
        assert_valid(
            dict(payload),
            "release",
            "two_province_release_attestation",
            label=f"two_province_release_attestation:{kind}",
        )
    except (TypeError, ValueError) as exc:
        return [f"GATE_BLOCK attestations/{ATTESTATION_FILES[kind]} invalid: {exc}"]
    if payload.get("kind") != kind:
        issues.append(f"GATE_BLOCK attestations/{ATTESTATION_FILES[kind]} kind mismatch")
    if payload.get("releaseId") != release_id:
        issues.append(f"GATE_BLOCK attestations/{ATTESTATION_FILES[kind]} releaseId mismatch")
    if payload.get("payloadSha256") != payload_sha256:
        issues.append(f"GATE_BLOCK attestations/{ATTESTATION_FILES[kind]} payloadSha256 mismatch")
    all_expected = set().union(*expected.values())
    if kind == "coverage":
        provinces = payload.get("provinces") if isinstance(payload.get("provinces"), Mapping) else {}
        approved = _string_set(payload.get("approvedEntityRefs"))
        if approved != all_expected:
            issues.append("GATE_BLOCK coverage approvedEntityRefs does not exactly equal the two-province master list")
        for province, expected_refs in expected.items():
            row = provinces.get(province) if isinstance(provinces, Mapping) else None
            count = int((row or {}).get("approvedHomepageCount") or 0) if isinstance(row, Mapping) else 0
            if count != len(expected_refs):
                issues.append(
                    f"GATE_BLOCK {province} approved homepage coverage {count} != {len(expected_refs)}"
                )
    elif kind == "source_rights":
        if _string_set(payload.get("qualifiedEntityRefs")) != all_expected:
            issues.append("GATE_BLOCK source-rights qualifiedEntityRefs is incomplete")
        if _string_set(payload.get("rightsEntityRefs")) != all_expected:
            issues.append("GATE_BLOCK source-rights rightsEntityRefs is incomplete")
        if _string_set(payload.get("executionIds")) != payload_execution_ids:
            issues.append("GATE_BLOCK source-rights executionIds does not match immutable payload")
    elif kind == "execution":
        if _string_set(payload.get("approvedEntityRefs")) != all_expected:
            issues.append("GATE_BLOCK execution approvedEntityRefs is incomplete")
        if _string_set(payload.get("executionIds")) != payload_execution_ids:
            issues.append("GATE_BLOCK executionIds does not match immutable payload")
    else:
        if payload.get("environment") != "gamma":
            issues.append(f"GATE_BLOCK {kind} evidence must be from gamma")
        if not _evidence_paths_exist(payload.get("evidenceRefs")):
            issues.append(f"GATE_BLOCK {kind} evidenceRefs do not resolve to Gamma runtime evidence")
    return issues


def two_province_coverage_release_issues(release_id: str) -> list[str]:
    root = RELEASE_ROOT / str(release_id or "").strip()
    if not root.is_dir():
        return [f"GATE_BLOCK release does not exist: {root}"]
    required_payload = ("release.json", "desired_state.json", "index/objects.json", "sample_bundle.json", "media_manifest.json")
    issues = [
        f"GATE_BLOCK release payload missing: payload/{name}"
        for name in required_payload
        if not payload_file(root, name).is_file()
    ]
    if issues:
        return issues
    header = _load_json(payload_file(root, "release.json"))
    if header.get("releaseId") != release_id:
        issues.append("GATE_BLOCK release payload header releaseId mismatch")
    payload_execution_ids = _string_set(header.get("executionIds"))
    if not payload_execution_ids:
        issues.append("GATE_BLOCK release payload has no executionIds")
    try:
        digest = payload_digest(root)
    except (OSError, ValueError) as exc:
        return [*issues, f"GATE_BLOCK release payload digest unavailable: {exc}"]
    expected = expected_entity_refs()
    if any(not refs for refs in expected.values()):
        issues.append("GATE_BLOCK coverage master list cannot derive both province entity sets")
    for kind, filename in ATTESTATION_FILES.items():
        path = attestation_root(root) / filename
        if not path.is_file():
            issues.append(f"GATE_BLOCK missing release attestation: attestations/{filename}")
            continue
        payload = _load_json(path)
        issues.extend(
            _attestation_issues(
                release_id=release_id,
                payload_sha256=digest,
                kind=kind,
                payload=payload,
                expected=expected,
                payload_execution_ids=payload_execution_ids,
            )
        )
        if kind in {"importer_api", "gamma_app_uat", "rollback_replay"}:
            for issue in environment_attestation_issues(release_root=root, kind=kind, payload=payload):
                issues.append(f"GATE_BLOCK {kind} evidence binding invalid: {issue}")
    return issues


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    args = parser.parse_args(argv)
    issues = two_province_coverage_release_issues(args.release)
    if issues:
        print("[verify_two_province_coverage_release] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_two_province_coverage_release] OK")
    return 0
