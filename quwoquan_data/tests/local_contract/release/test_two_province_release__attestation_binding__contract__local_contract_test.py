"""Final two-province release gate binds every attestation to one payload."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import attestation_root, payload_digest, payload_file  # noqa: E402
from content.release.canonical.baseline_release import build_empty_baseline_release  # noqa: E402
from content.release.canonical import two_province_environment_closure as environment_closure  # noqa: E402
from verify import verify_two_province_coverage_release as gate  # noqa: E402


RELEASE_ID = "20260713--travel-homepage-coverage--cn-zhejiang-sichuan--m3-901"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    output = tmp_path / "output"
    release = output / "data/releases" / RELEASE_ID
    monkeypatch.setattr(gate, "RELEASE_ROOT", output / "data/releases")
    monkeypatch.setattr(gate, "OUTPUT_ROOT", output)
    monkeypatch.setattr(environment_closure, "OUTPUT_ROOT", output)
    monkeypatch.setattr(environment_closure, "RELEASE_ROOT", output / "data/releases")
    refs_by_province = {
        "浙江省": {"地点/景区/普陀山"},
        "四川省": {"地点/景区/海螺沟"},
    }
    monkeypatch.setattr(gate, "expected_entity_refs", lambda: refs_by_province)
    monkeypatch.setattr(environment_closure, "expected_entity_refs", lambda: refs_by_province)
    refs = set().union(*refs_by_province.values())
    execution_id = "20260713--travel-homepage-coverage--cn-zhejiang-sichuan--m3-901"
    _write(
        payload_file(release, "release.json"),
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "releaseKind": "content",
            "executionIds": [execution_id],
        },
    )
    _write(payload_file(release, "desired_state.json"), {"releaseId": RELEASE_ID, "desiredRefs": {"entities": sorted(refs)}})
    _write(payload_file(release, "index/objects.json"), {"entities": sorted(refs)})
    _write(payload_file(release, "sample_bundle.json"), {"entities": sorted(refs)})
    _write(payload_file(release, "media_manifest.json"), {"assets": []})
    digest = payload_digest(release)
    baseline_release_id = "20260712--travel-homepage-coverage--cn-zhejiang-sichuan--canary-001"
    publish = output / "publish"
    publish.mkdir(parents=True)
    build_empty_baseline_release(
        publish_root=publish,
        release_root=output / "data/releases",
        release_id=baseline_release_id,
    )
    import_run_id = "import-001"
    import_root = output / "env/gamma/runs/data-release" / RELEASE_ID / import_run_id
    importer_ref = (import_root / "homepage-import.json").relative_to(output).as_posix()
    cases_ref = (import_root / "homepage_verification_cases.json").relative_to(output).as_posix()
    mapping = {"地点/景区/普陀山": "homepage-putuo", "地点/景区/海螺沟": "homepage-hailuogou"}
    _write(import_root / "run.json", {"environment": "gamma", "releaseId": RELEASE_ID, "kind": "apply"})
    _write(import_root / "result.json", {"environment": "gamma", "releaseId": RELEASE_ID, "status": "completed", "homepageVerificationCasesRef": cases_ref})
    _write(
        import_root / "homepage-import.json",
        {
            "schema": "quwoquan_service.homepage_import_report",
            "releaseId": RELEASE_ID,
            "env": "gamma",
            "dryRun": False,
            "mode": "upsert",
            "sourceOwner": "qwq_data",
            "projected": len(mapping),
            "created": list(mapping.values()),
            "updated": [],
            "offlined": [],
            "skipped": [],
            "entityRefToHomepageId": mapping,
            "issues": [],
            "finishedAt": "2026-07-13T00:00:00Z",
        },
    )
    _write(
        import_root / "homepage_verification_cases.json",
        {
            "schema": "quwoquan_data.homepage_verification_case_manifest",
            "environment": "gamma",
            "releaseId": RELEASE_ID,
            "runId": import_run_id,
            "importerReportRef": importer_ref,
            "generatedAt": "2026-07-13T00:00:00Z",
            "cases": [
                {"entityRef": entity_ref, "homepageId": homepage_id, "title": entity_ref.rsplit("/", 1)[-1]}
                for entity_ref, homepage_id in sorted(mapping.items())
            ],
        },
    )
    api_run_id = "api-001"
    api_root = output / "env/gamma/runs/data-release" / RELEASE_ID / api_run_id
    api_ref = (api_root / "homepage-api-verification.json").relative_to(output).as_posix()
    _write(api_root / "run.json", {"environment": "gamma", "releaseId": RELEASE_ID, "kind": "verify"})
    _write(api_root / "result.json", {"environment": "gamma", "releaseId": RELEASE_ID, "status": "completed", "homepageApiVerificationRef": api_ref})
    _write(
        api_root / "homepage-api-verification.json",
        {
            "schema": "quwoquan_data.homepage_api_verification",
            "environment": "gamma",
            "releaseId": RELEASE_ID,
            "runId": api_run_id,
            "sourceCasesRef": cases_ref,
            "apiBaseUrl": "https://gamma.example.test",
            "verifiedAt": "2026-07-13T00:00:00Z",
            "passed": True,
            "entities": [
                {"entityRef": entity_ref, "homepageId": homepage_id, "title": entity_ref.rsplit("/", 1)[-1], "detailStatus": 200, "introductionStatus": 200, "coverUrl": f"https://media.example.test/{homepage_id}.jpg", "sectionCount": 1}
                for entity_ref, homepage_id in sorted(mapping.items())
            ],
            "issues": [],
        },
    )
    app_report = output / "env/gamma/runs/two-province-patrol-001/report.json"
    _write(
        app_report,
        {
            "status": "passed",
            "runtimeEnv": "gamma",
            "apiContractEnv": "gamma",
            "dataSource": "remote",
            "target": "test/user_acceptance/patrol/entity/two_province_homepage__rollout_render__functional__user_acceptance_test.dart",
            "releaseUatCasesPath": cases_ref,
            "runs": [{"exitCode": 0}],
        },
    )
    rollback_run_id = "rollback-001"
    rollback_root = output / "env/gamma/runs/data-release" / baseline_release_id / rollback_run_id
    rollback_ref = (rollback_root / "rollback_ref.json").relative_to(output).as_posix()
    _write(rollback_root / "run.json", {"environment": "gamma", "releaseId": baseline_release_id, "kind": "rollback"})
    _write(rollback_root / "result.json", {"environment": "gamma", "releaseId": baseline_release_id, "status": "completed"})
    _write(rollback_root / "rollback_ref.json", {"rollbackTo": baseline_release_id, "rollbackFromReleaseId": RELEASE_ID})
    replay_run_id = "replay-001"
    replay_root = output / "env/gamma/runs/data-release" / RELEASE_ID / replay_run_id
    replay_ref = (replay_root / "result.json").relative_to(output).as_posix()
    _write(replay_root / "run.json", {"environment": "gamma", "releaseId": RELEASE_ID, "kind": "apply"})
    _write(replay_root / "result.json", {"environment": "gamma", "releaseId": RELEASE_ID, "status": "completed"})
    common = {
        "schema": "quwoquan_data.two_province_release_attestation",
        "releaseId": RELEASE_ID,
        "payloadSha256": digest,
        "passed": True,
        "recordedAt": "2026-07-13T00:00:00Z",
    }
    _write(
        attestation_root(release) / "coverage_closure.json",
        {
            **common,
            "kind": "coverage",
            "provinces": {
                province: {"approvedHomepageCount": len(rows)}
                for province, rows in refs_by_province.items()
            },
            "approvedEntityRefs": sorted(refs),
        },
    )
    _write(
        attestation_root(release) / "source_rights_closure.json",
        {
            **common,
            "kind": "source_rights",
            "executionIds": [execution_id],
            "qualifiedEntityRefs": sorted(refs),
            "rightsEntityRefs": sorted(refs),
        },
    )
    _write(
        attestation_root(release) / "execution_closure.json",
        {
            **common,
            "kind": "execution",
            "executionIds": [execution_id],
            "approvedEntityRefs": sorted(refs),
        },
    )
    _write(
        attestation_root(release) / "importer_api_closure.json",
        {**common, "kind": "importer_api", "environment": "gamma", "evidenceRefs": [importer_ref, cases_ref, api_ref]},
    )
    _write(
        attestation_root(release) / "gamma_app_uat_closure.json",
        {**common, "kind": "gamma_app_uat", "environment": "gamma", "evidenceRefs": [app_report.relative_to(output).as_posix()]},
    )
    _write(
        attestation_root(release) / "rollback_replay_closure.json",
        {**common, "kind": "rollback_replay", "environment": "gamma", "rollbackTargetReleaseId": baseline_release_id, "evidenceRefs": [rollback_ref, replay_ref]},
    )
    return release


def test_two_province_release__attestation_binding__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixture(monkeypatch, tmp_path)

    assert gate.two_province_coverage_release_issues(RELEASE_ID) == []


def test_two_province_release__payload_mutation__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _fixture(monkeypatch, tmp_path)
    _write(payload_file(release, "sample_bundle.json"), {"entities": []})

    issues = gate.two_province_coverage_release_issues(RELEASE_ID)

    assert any("payloadSha256 mismatch" in issue for issue in issues)


def test_two_province_release__detached_runtime_report__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _fixture(monkeypatch, tmp_path)
    payload_path = attestation_root(release) / "importer_api_closure.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["evidenceRefs"] = [payload["evidenceRefs"][0]]
    _write(payload_path, payload)

    issues = gate.two_province_coverage_release_issues(RELEASE_ID)

    assert any("importer_api evidence binding invalid" in issue for issue in issues)


def test_two_province_release__environment_attestation_replay__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _fixture(monkeypatch, tmp_path)

    result = environment_closure.build_environment_attestations(
        release_root=release,
        import_run_id="import-001",
        api_run_id="api-001",
        app_uat_report=tmp_path / "output/env/gamma/runs/two-province-patrol-001/report.json",
        rollback_target_release_id="20260712--travel-homepage-coverage--cn-zhejiang-sichuan--canary-001",
        rollback_run_id="rollback-001",
        replay_run_id="replay-001",
    )

    assert result["entityCount"] == 2
    assert gate.two_province_coverage_release_issues(RELEASE_ID) == []
