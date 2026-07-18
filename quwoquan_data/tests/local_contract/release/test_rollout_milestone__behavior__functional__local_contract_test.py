"""Rollout milestones must be derived from immutable Gamma evidence."""
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
from content.release.canonical import rollout_attestation, rollout_milestone  # noqa: E402
from content.release.canonical.rollout_contract import load_rollout_contract  # noqa: E402


CANARY_RELEASE = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-001"
ZHEJIANG = "20260714--travel-homepage-coverage--cn-zhejiang--canary-001"
SICHUAN = "20260714--travel-homepage-coverage--cn-sichuan--canary-001"
M1_ZHEJIANG = "20260714--travel-homepage-coverage--cn-zhejiang--m1-001"


def test_rollout_capacity_is_loaded_from_single_contract() -> None:
    capacity = load_rollout_contract().capacity

    assert capacity.soak_jobs == 30
    assert capacity.minimum_safe_concurrency == 3
    assert capacity.maximum_unrecovered_bridge_failures == 0
    assert capacity.minimum_approved_homepages_per_hour == 18
    assert capacity.maximum_homepage_object_p95_seconds == 720


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_full_sync_receipts(root: Path, release_id: str, refs: list[str]) -> None:
    mapping = {ref: f"homepage-{index}" for index, ref in enumerate(refs, start=1)}
    _write(
        root / "import.json",
        {
            "schema": "quwoquan.content_import_report",
            "status": "active",
            "environment": "gamma",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "mode": "sync",
            "deletePolicy": "tombstone",
            "counts": {"postsLoaded": 0, "entitiesLoaded": len(refs)},
            "auditEvents": [],
        },
    )
    _write(
        root / "homepage-import.json",
        {
            "schema": "quwoquan_service.homepage_import_report",
            "releaseId": release_id,
            "env": "gamma",
            "dryRun": False,
            "mode": "sync",
            "sourceOwner": "qwq_data",
            "projected": len(refs),
            "created": list(mapping.values()),
            "updated": [],
            "offlined": [],
            "skipped": [],
            "entityRefToHomepageId": mapping,
            "issues": [],
            "finishedAt": "2026-07-14T00:00:00Z",
        },
    )


def _closed_canary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    output = tmp_path / "output"
    releases = output / "data/releases"
    release = releases / CANARY_RELEASE
    monkeypatch.setattr(rollout_milestone, "OUTPUT_ROOT", output)
    monkeypatch.setattr(rollout_milestone, "RELEASE_ROOT", releases)
    monkeypatch.setattr(rollout_attestation, "OUTPUT_ROOT", output)
    monkeypatch.setattr(rollout_attestation, "RELEASE_ROOT", releases)
    refs = ["地点/景区/普陀山", "地点/自然景观/东钱湖", "地点/景区/海螺沟"]
    _write(
        payload_file(release, "release.json"),
        {
            "schema": "quwoquan_data.release",
            "releaseId": CANARY_RELEASE,
            "releaseKind": "content",
            "executionIds": [ZHEJIANG, SICHUAN],
            "rolloutMilestone": "canary",
        },
    )
    _write(
        payload_file(release, "desired_state.json"),
        {"releaseId": CANARY_RELEASE, "desiredRefs": {"entities": refs}},
    )
    baseline_id = "20260713--travel-homepage-coverage--cn-zhejiang-sichuan--canary-999"
    evidence_paths = (
        output / "env/gamma/runs/data-release" / CANARY_RELEASE / "import-evidence" / "import.json",
        output / "env/gamma/runs/data-release" / CANARY_RELEASE / "import-evidence" / "homepage-import.json",
        output / "env/gamma/runs/data-release" / CANARY_RELEASE / "import-evidence" / "homepage_verification_cases.json",
        output / "env/gamma/runs/data-release" / CANARY_RELEASE / "api-evidence" / "homepage-api-verification.json",
        output / "env/gamma/runs/patrol-evidence/report.json",
        output / "env/gamma/runs/data-release" / baseline_id / "rollback-evidence" / "rollback_ref.json",
        output / "env/gamma/runs/data-release" / CANARY_RELEASE / "replay-evidence" / "result.json",
    )
    evidence_refs = []
    for path in evidence_paths:
        _write(path, {"ok": True})
        evidence_refs.append(path.relative_to(output).as_posix())
    payload = {
        "schema": "quwoquan_data.rollout_milestone_closure",
        "releaseId": CANARY_RELEASE,
        "payloadSha256": payload_digest(release),
        "rolloutId": "travel-homepage-coverage",
        "milestone": "canary",
        "environment": "gamma",
        "executionIds": [SICHUAN, ZHEJIANG],
        "batchExecutionIds": [SICHUAN, ZHEJIANG],
        "approvedEntityRefs": sorted(refs),
        "approvedEntityRefsByScope": {
            "cn-zhejiang": ["地点/景区/普陀山", "地点/自然景观/东钱湖"],
            "cn-sichuan": ["地点/景区/海螺沟"],
        },
        "batchApprovedEntityRefsByScope": {
            "cn-zhejiang": ["地点/景区/普陀山", "地点/自然景观/东钱湖"],
            "cn-sichuan": ["地点/景区/海螺沟"],
        },
        "evidenceRefs": evidence_refs,
        "rollbackTargetReleaseId": baseline_id,
        "passed": True,
        "recordedAt": "2026-07-14T00:00:00Z",
    }
    _write(attestation_root(release) / rollout_milestone.ATTESTATION_FILE, payload)
    def _fixture_attestation_issues(path: Path, **_kwargs) -> list[str]:
        recorded = json.loads(path.read_text(encoding="utf-8"))
        return (
            []
            if recorded.get("payloadSha256") == payload_digest(path.parent.parent)
            else ["rollout milestone closure is detached from immutable release payload"]
        )
    monkeypatch.setattr(
        rollout_milestone,
        "_milestone_attestation_issues",
        _fixture_attestation_issues,
    )
    return release


def test_m1__requires_gamma_closed_canary__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _closed_canary(monkeypatch, tmp_path)

    assert rollout_milestone.rollout_start_issues(M1_ZHEJIANG) == []


def test_m1__blocks_when_canary_evidence_is_detached__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _closed_canary(monkeypatch, tmp_path)
    payload = json.loads((attestation_root(release) / rollout_milestone.ATTESTATION_FILE).read_text(encoding="utf-8"))
    payload["payloadSha256"] = "sha256:" + "0" * 64
    _write(attestation_root(release) / rollout_milestone.ATTESTATION_FILE, payload)

    issues = rollout_milestone.rollout_start_issues(M1_ZHEJIANG)

    assert len(issues) == 1
    assert "requires an immutable Gamma-closed canary release" in issues[0]


def test_m1__excludes_closed_canary_targets__contract__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _closed_canary(monkeypatch, tmp_path)

    province, limit, mandatory, excluded = rollout_milestone.geo_rollout_parameters(
        execution_id=M1_ZHEJIANG,
    )
    assert province == "浙江省"

    assert limit == 100
    assert mandatory is None
    assert set(excluded) == {"普陀山", "东钱湖"}


def test_canary__locks_fixed_province_targets__local_contract() -> None:
    province, limit, mandatory, excluded = rollout_milestone.geo_rollout_parameters(
        execution_id=ZHEJIANG,
    )
    assert province == "浙江省"

    assert limit == 2
    assert mandatory == "普陀山,东钱湖"
    assert excluded == ()

def test_canary__attestation_binds_execution_and_gamma_evidence__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "output"
    releases = output / "data/releases"
    release = releases / CANARY_RELEASE
    baseline = releases / "20260713--travel-homepage-coverage--cn-zhejiang-sichuan--canary-999"
    monkeypatch.setattr(rollout_milestone, "OUTPUT_ROOT", output)
    monkeypatch.setattr(rollout_milestone, "RELEASE_ROOT", releases)
    monkeypatch.setattr(rollout_attestation, "OUTPUT_ROOT", output)
    monkeypatch.setattr(rollout_attestation, "RELEASE_ROOT", releases)
    roots = {ZHEJIANG: tmp_path / "tasks" / ZHEJIANG, SICHUAN: tmp_path / "tasks" / SICHUAN}
    monkeypatch.setattr(rollout_attestation, "execution_root", lambda execution_id: roots[execution_id])
    monkeypatch.setattr(rollout_attestation, "execution_readiness_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rollout_attestation, "homepage_media_completeness_report", lambda _id: {"passed": True})
    refs = ["地点/景区/普陀山", "地点/自然景观/东钱湖", "地点/景区/海螺沟"]
    _write(payload_file(release, "release.json"), {"schema": "quwoquan_data.release", "releaseId": CANARY_RELEASE, "releaseKind": "content", "executionIds": [ZHEJIANG, SICHUAN], "rolloutMilestone": "canary"})
    _write(payload_file(release, "desired_state.json"), {"releaseId": CANARY_RELEASE, "desiredRefs": {"entities": refs}})
    _write(roots[ZHEJIANG] / "publish_ref.json", {"executionId": ZHEJIANG, "publishedRefs": {"entities": refs[:2]}})
    _write(roots[SICHUAN] / "publish_ref.json", {"executionId": SICHUAN, "publishedRefs": {"entities": refs[2:]}})

    import_root = output / "env/gamma/runs/data-release" / CANARY_RELEASE / "import-001"
    importer_ref = (import_root / "homepage-import.json").relative_to(output).as_posix()
    cases_ref = (import_root / "homepage_verification_cases.json").relative_to(output).as_posix()
    mapping = {ref: f"homepage-{index}" for index, ref in enumerate(refs, start=1)}
    _write(import_root / "run.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "kind": "apply"})
    _write(import_root / "result.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "status": "completed", "homepageVerificationCasesRef": cases_ref})
    _write_full_sync_receipts(import_root, CANARY_RELEASE, refs)
    _write(import_root / "homepage_verification_cases.json", {"schema": "quwoquan_data.homepage_verification_case_manifest", "environment": "gamma", "releaseId": CANARY_RELEASE, "runId": "import-001", "importerReportRef": importer_ref, "generatedAt": "2026-07-14T00:00:00Z", "cases": [{"entityRef": ref, "homepageId": homepage_id, "title": ref.rsplit("/", 1)[-1]} for ref, homepage_id in mapping.items()]})

    api_root = output / "env/gamma/runs/data-release" / CANARY_RELEASE / "api-001"
    api_ref = (api_root / "homepage-api-verification.json").relative_to(output).as_posix()
    _write(api_root / "run.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "kind": "verify"})
    _write(api_root / "result.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "status": "completed", "homepageApiVerificationRef": api_ref})
    _write(api_root / "homepage-api-verification.json", {"schema": "quwoquan_data.homepage_api_verification", "environment": "gamma", "releaseId": CANARY_RELEASE, "runId": "api-001", "sourceCasesRef": cases_ref, "apiBaseUrl": "https://gamma.example.test", "verifiedAt": "2026-07-14T00:00:00Z", "passed": True, "entities": [{"entityRef": ref, "homepageId": homepage_id, "title": ref.rsplit("/", 1)[-1], "detailStatus": 200, "introductionStatus": 200, "coverUrl": f"https://media.example.test/{homepage_id}.jpg", "sectionCount": 1} for ref, homepage_id in mapping.items()], "issues": []})

    app_report = output / "env/gamma/runs/patrol-001/report.json"
    app_payload = {"status": "passed", "runtimeEnv": "gamma", "apiContractEnv": "gamma", "dataSource": "remote", "releaseUatCasesPath": cases_ref, "runs": [{"exitCode": 0}]}
    _write(app_report, app_payload)
    noncanonical_app_report = app_report.with_name("app-uat-report.json")
    _write(noncanonical_app_report, app_payload)
    publish = output / "publish"
    publish.mkdir(parents=True)
    build_empty_baseline_release(
        publish_root=publish,
        release_root=releases,
        release_id=baseline.name,
    )
    rollback_root = output / "env/gamma/runs/data-release" / baseline.name / "rollback-001"
    _write(rollback_root / "run.json", {"environment": "gamma", "releaseId": baseline.name, "kind": "rollback"})
    _write(rollback_root / "result.json", {"environment": "gamma", "releaseId": baseline.name, "status": "completed"})
    _write(rollback_root / "rollback_ref.json", {"rollbackTo": baseline.name, "rollbackFromReleaseId": CANARY_RELEASE})
    _write_full_sync_receipts(rollback_root, baseline.name, [])
    replay_root = output / "env/gamma/runs/data-release" / CANARY_RELEASE / "replay-001"
    _write(replay_root / "run.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "kind": "apply"})
    _write(replay_root / "result.json", {"environment": "gamma", "releaseId": CANARY_RELEASE, "status": "completed"})
    _write_full_sync_receipts(replay_root, CANARY_RELEASE, refs)

    with pytest.raises(
        rollout_attestation.RolloutMilestoneError,
        match="canonical report.json",
    ):
        rollout_attestation.build_rollout_milestone_attestation(
            release_root=release,
            import_run_id="import-001",
            api_run_id="api-001",
            app_uat_report=noncanonical_app_report,
            rollback_target_release_id=baseline.name,
            rollback_run_id="rollback-001",
            replay_run_id="replay-001",
        )

    report = rollout_attestation.build_rollout_milestone_attestation(
        release_root=release,
        import_run_id="import-001",
        api_run_id="api-001",
        app_uat_report=app_report,
        rollback_target_release_id=baseline.name,
        rollback_run_id="rollback-001",
        replay_run_id="replay-001",
    )

    assert report == {"releaseId": CANARY_RELEASE, "milestone": "canary", "attestation": rollout_milestone.ATTESTATION_FILE}
    assert rollout_milestone.rollout_start_issues(M1_ZHEJIANG) == []
