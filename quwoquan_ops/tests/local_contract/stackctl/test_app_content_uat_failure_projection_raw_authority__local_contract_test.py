"""App content UAT raw authority failure projection contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands.app_preflight_uat_receipt import (
    build_app_content_uat_receipt,
    project_app_content_uat_raw_authority,
)
from quwoquan_ops.cli.lib.readiness_case_result import canonical_json_bytes


def _raw_authority_result(*, status: str) -> dict[str, object]:
    value: dict[str, object] = {
        "objectId": "article-a",
        "specRef": "specs/feature-tree/content/spec.md#gwt-001",
        "caseId": "article_feed_uat",
        "producer": "app",
        "layer": "user_acceptance",
        "status": status,
        "target": {"kind": "page", "id": "article-a"},
        "commitSha": "a" * 40,
        "contractGraphSourceHash": "b" * 64,
        "deploymentTarget": "alpha-local",
        "baselineId": "c" * 64,
        "packageDigest": "sha256:" + "d" * 64,
        "configurationDigest": "sha256:" + "e" * 64,
        "candidateManifestSha256": "f" * 64,
        "candidateDigest": "sha256:" + "1" * 64,
        "releaseDigest": "sha256:" + "2" * 64,
        "releaseId": "release-a",
        "targetUatBindingDigest": "sha256:" + "3" * 64,
        "entrySurface": "feed",
        "carrier": "article",
        "environment": "alpha",
        "platform": "android",
        "deviceClass": "emulator",
        "deviceRegistered": False,
        "provider": "first-party-https",
        "startedAt": "2026-08-29T07:00:00Z",
        "completedAt": "2026-08-29T07:01:00Z",
        "runnerIdentity": "qwq_app.content_uat.feed.article.v1",
        "artifactSha256": "4" * 64,
        "artifactPath": "case/article-feed.json",
        "deviceIdentity": "emulator-5554",
        "uatProfile": "rehearsal",
        "nonPromotable": True,
        "artifactClass": "production_behavior",
        "physicalDevice": False,
    }
    if status != "passed":
        value["reasonCode"] = "APP.UAT.PATROL_FAILED"
    return value

def _projection_receipt(
    *,
    status: str,
    raw_authority_projection: dict[str, object],
    issues: list[str],
    dry_run: bool = False,
) -> dict[str, object]:
    return build_app_content_uat_receipt(
        status=status,
        targets=["alpha-local"],
        platform="android",
        device_id="emulator-5554",
        uat_profile={
            "profile": "rehearsal",
            "deviceClass": "emulator",
            "deviceRegistered": False,
            "nonPromotable": True,
        },
        runtime_bindings=[],
        launch_bindings={},
        target_uat_binding_refs={},
        raw_authority_projection=raw_authority_projection,
        preflights=[],
        runs=[],
        experience_screenshot_digests={},
        issues=issues,
        dry_run=dry_run,
        canonical_checksum=lambda _value: "sha256:" + "0" * 64,
    )


def test_parent_projection_has_no_raw_outcome_verdict_or_passed_text(
    tmp_path: Path,
) -> None:
    raw_ref = "raw/result.json"
    raw_path = tmp_path / raw_ref
    raw_path.parent.mkdir(parents=True)
    raw_bytes = canonical_json_bytes(_raw_authority_result(status="passed"))
    raw_path.write_bytes(raw_bytes)
    digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    projection, issues = project_app_content_uat_raw_authority(
        evidence_root=tmp_path,
        targets=["alpha-local"],
        raw_results={
            "alpha-local": [
                {"slotId": "sha256:" + "1" * 64, "ref": raw_ref, "digest": digest}
            ]
        },
        expected_raw_coverage={"alpha-local": 1},
        dry_run=False,
    )

    assert issues == []
    parent = _projection_receipt(
        status="complete", raw_authority_projection=projection, issues=[]
    )
    assert parent["status"] == "complete"
    assert parent["rawResultRefs"]["alpha-local"] == [
        {"slotId": "sha256:" + "1" * 64, "ref": raw_ref}
    ]
    assert parent["rawResultDigests"]["alpha-local"] == [
        {"slotId": "sha256:" + "1" * 64, "digest": digest}
    ]
    encoded = json.dumps(parent, ensure_ascii=False).lower()
    assert '"status": "passed"' not in encoded
    assert "all suites passed" not in encoded
    assert parent["details"] == ["raw authority projection complete"]


def test_noncanonical_passed_shape_cannot_become_parent_authority(
    tmp_path: Path,
) -> None:
    raw_ref = "raw/not-authority.json"
    raw_path = tmp_path / raw_ref
    raw_path.parent.mkdir(parents=True)
    raw_bytes = b'{"status":"passed"}'
    raw_path.write_bytes(raw_bytes)

    projection, issues = project_app_content_uat_raw_authority(
        evidence_root=tmp_path,
        targets=["alpha-local"],
        raw_results={
            "alpha-local": [
                {
                    "slotId": "sha256:" + "9" * 64,
                    "ref": raw_ref,
                    "digest": "sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
                }
            ]
        },
        expected_raw_coverage={"alpha-local": 1},
        dry_run=False,
    )

    assert issues and "not a canonical ReadinessCaseResult" in issues[0]
    assert projection["rawResultRefs"] == {"alpha-local": []}
    assert projection["rawCoverage"]["alpha-local"] == {
        "expected": 1,
        "present": 0,
        "missing": 1,
    }


def test_raw_failed_cannot_promote_parent_projection_to_complete(
    tmp_path: Path,
) -> None:
    raw_ref = "raw/failed.json"
    raw_path = tmp_path / raw_ref
    raw_path.parent.mkdir(parents=True)
    raw_bytes = canonical_json_bytes(_raw_authority_result(status="failed"))
    raw_path.write_bytes(raw_bytes)
    projection, issues = project_app_content_uat_raw_authority(
        evidence_root=tmp_path,
        targets=["alpha-local"],
        raw_results={
            "alpha-local": [
                {
                    "slotId": "sha256:" + "2" * 64,
                    "ref": raw_ref,
                    "digest": "sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
                }
            ]
        },
        expected_raw_coverage={"alpha-local": 1},
        dry_run=False,
    )

    assert issues and "not green" in issues[0]
    assert projection["rawResultRefs"]["alpha-local"]
    parent = _projection_receipt(
        status="gate_block",
        raw_authority_projection=projection,
        issues=issues,
    )
    assert parent["status"] == "gate_block"
    assert parent["rawGaps"]["alpha-local"]
    assert "failed" not in json.dumps(parent["rawGaps"]).lower()


def test_dry_run_projects_planned_expected_coverage_without_raw_refs(
    tmp_path: Path,
) -> None:
    projection, issues = project_app_content_uat_raw_authority(
        evidence_root=tmp_path,
        targets=["alpha-local"],
        raw_results={},
        expected_raw_coverage={"alpha-local": 16},
        dry_run=True,
    )

    assert issues == []
    assert projection["rawResultRefs"] == {"alpha-local": []}
    assert projection["rawResultDigests"] == {"alpha-local": []}
    assert projection["rawCoverage"]["alpha-local"] == {
        "expected": 16,
        "present": 0,
        "missing": 16,
    }
    parent = _projection_receipt(
        status="planned",
        raw_authority_projection=projection,
        issues=[],
        dry_run=True,
    )
    assert parent["status"] == "planned"
    assert parent["details"] == [
        "dry-run planned expected raw authority coverage; no raw result was written"
    ]


def test_parent_status_rejects_retired_passed_alias() -> None:
    projection = {
        "rawResultRefs": {"alpha-local": []},
        "rawResultDigests": {"alpha-local": []},
        "rawCoverage": {
            "alpha-local": {"expected": 1, "present": 0, "missing": 1}
        },
        "rawGaps": {"alpha-local": ["missing"]},
    }
    with pytest.raises(ValueError, match="projection status is invalid"):
        _projection_receipt(
            status="passed", raw_authority_projection=projection, issues=[]
        )


