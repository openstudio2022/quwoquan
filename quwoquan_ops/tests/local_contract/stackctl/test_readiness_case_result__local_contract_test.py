"""Canonical Python ReadinessCaseResult validator and create-once storage.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    build_readiness_result_bundle,
    canonical_json_bytes,
    validate_readiness_case_result,
    write_create_once_json,
)


def _result() -> dict[str, object]:
    return {
        "objectId": "entity.homepage",
        "specRef": "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001",
        "caseId": "homepage_release_consumer_render_app_uat",
        "producer": "app",
        "layer": "user_acceptance",
        "status": "blocked",
        "target": {"kind": "page", "id": "entity.detail"},
        "commitSha": "a" * 40,
        "contractGraphSourceHash": "b" * 64,
        "deploymentTarget": "gamma-local",
        "baselineId": "c" * 64,
        "packageDigest": "sha256:" + "d" * 64,
        "configurationDigest": "sha256:" + "e" * 64,
        "candidateManifestSha256": "f" * 64,
        "candidateDigest": "sha256:" + "1" * 64,
        "releaseDigest": "sha256:" + "2" * 64,
        "releaseId": "release-a",
        "targetUatBindingDigest": "sha256:" + "3" * 64,
        "entrySurface": "direct_or_object_route",
        "carrier": "homepage",
        "environment": "gamma",
        "platform": "android",
        "deviceClass": "simulator",
        "provider": "first-party-https",
        "startedAt": "2026-08-29T07:00:00Z",
        "completedAt": "2026-08-29T07:01:00Z",
        "runnerIdentity": "gamma-patrol-release-homepage",
        "artifactSha256": "4" * 64,
        "artifactPath": "env/gamma/runs/blocker.json",
        "deviceIdentity": "emulator-5554",
        "uatProfile": "rehearsal",
        "nonPromotable": True,
        "artifactClass": "production_behavior",
        "physicalDevice": False,
        "reasonCode": "APP.GAMMA_UAT.blocked",
    }


def test_validator_uses_canonical_schema_and_rejects_retired_fields() -> None:
    result = _result()
    assert validate_readiness_case_result(
        result, generated_at="2026-08-29T07:01:00Z"
    ) == result
    for mutation in (
        {"status": "gate_block"},
        {"specRefs": [result["specRef"]]},
        {"schema": "quwoquan.test.case-result"},
    ):
        drifted = dict(result)
        drifted.update(mutation)
        with pytest.raises(ReadinessCaseResultError):
            validate_readiness_case_result(
                drifted, generated_at="2026-08-29T07:01:00Z"
            )


def test_bundle_has_results_only_and_no_second_verdict() -> None:
    bundle = build_readiness_result_bundle(
        [_result()], generated_at="2026-08-29T07:01:00Z"
    )
    assert set(bundle) == {"generatedAt", "results"}
    assert not {"status", "verdict", "promotionAuthority"}.intersection(bundle)


def test_create_once_conflict_never_overwrites_old_result(tmp_path: Path) -> None:
    path = write_create_once_json(tmp_path / "result.json", _result())
    original = path.read_bytes()
    assert write_create_once_json(path, _result()) == path
    failed = dict(_result(), status="failed")
    with pytest.raises(ReadinessCaseResultError, match="different bytes"):
        write_create_once_json(path, failed)
    assert path.read_bytes() == original == canonical_json_bytes(_result())
