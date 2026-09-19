"""Strict incremental App readiness facts.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib import app_readiness_facts as subject
from quwoquan_ops.cli.lib.app_launch_attempt import (
    SCHEMA as APP_LAUNCH_ATTEMPT_SCHEMA,
)

D = "sha256:" + "a" * 64
TREE = "sha1:" + "b" * 40
SHA = "c" * 40
ATTEMPT = "launch-attempt-1"
JOURNEYS = (
    "login_otp", "anonymous_isolation", "feed_loaded", "content_image_decode",
    "author_avatar_decode", "video_terminal", "detail_terminal", "persona_isolation",
    "release_isolation", "cache_isolation", "grant_isolation",
)


def _write(root: Path, name: str, value: object) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return {"ref": name, "digest": subject.exact_byte_digest(path)}


def _launch(root: Path, *, non_promotable: bool, content_source: str = "remote",
            lease: str = D, required_transport: bool = True, stopped: bool = False,
            damage: str = "") -> Path:
    terminal = {
        "schema": "quwoquan_app.startup_safe_terminal.v1", "launchAttemptId": ATTEMPT,
        "startupAttemptId": "startup-1", "platform": "android", "deviceId": "pixel-1",
        "applicationId": "com.quwoquan", "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": "external_runtime_package", "effectiveLaunchManifestDigest": D,
        "artifactDigest": D, "configurationState": "complete", "surface": "router_shell",
        "canonicalTerminal": "routerShell", "hotRestart": False, "observedMarkerDigest": D,
    }
    terminal_ref = _write(root, "startup-terminal.json", terminal)
    attempt = {
        "schema": APP_LAUNCH_ATTEMPT_SCHEMA, "attemptId": ATTEMPT, "status": "launched",
        "artifactDigest": D, "runtimeConfigPackageDigest": D, "runtimeConfigTrustEnvelopeDigest": D,
        "launchDigest": D, "platform": "android", "deviceId": "pixel-1", "nonPromotable": non_promotable,
    }
    attempt.update(environment="alpha", target="alpha-local")
    if stopped:
        from quwoquan_ops.cli.lib.app_launch_attempt import create_app_launch_attempt, FORWARD_STATES
        attempt = create_app_launch_attempt(root / "producer-attempt.json", environment="alpha", target="alpha-local",
            platform="android", build_profile="nonprod", build_mode="debug", run_mode="content-live",
            launch_provenance="canonical_launcher", runtime_config_supply_mode="external_runtime_package",
            runtime_config_trust_envelope_digest=D, runtime_config_package_digest=D, application_id="com.quwoquan",
            flutter_version="3.47.0", command_resolution_digest=D, device_id="pixel-1", artifact_digest=D,
            launch_digest=D, attempt_id=ATTEMPT, non_promotable=non_promotable)
        attempt.update(status="stopped", configurationState="complete", runtimeHealthStatus="healthy",
            startupTerminalAttemptId="startup-1", startupTerminalEvidenceDigest=terminal_ref["digest"],
            startupTerminalEvidenceRef=str(root / "startup-terminal.json"),
            transitions=[{"status": state, "at": attempt["updatedAt"]} for state in (*FORWARD_STATES, "stopped")])
        if damage == "missing":
            del attempt["transitions"][2]
        elif damage == "failed":
            attempt["transitions"].insert(-1, {"status": "failed", "at": attempt["updatedAt"]})
        elif damage == "terminal":
            attempt["startupTerminalEvidenceDigest"] = "sha256:" + "f" * 64
        elif damage == "blocker":
            attempt["firstBlocker"] = "APP.LAUNCH.compile_failed"
    attempt_ref = _write(root, "attempt.json", attempt)
    launch_digest = "sha256:" + __import__("hashlib").sha256(json.dumps(attempt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report = {
        "schema": "quwoquan_app.test_live_launch", "launchAttemptId": ATTEMPT,
        "launchAttemptRef": str(root / "attempt.json"), "launchAttemptDigest": launch_digest,
        "startupTerminalEvidenceRef": str(root / "startup-terminal.json"),
        "startupTerminalEvidenceDigest": terminal_ref["digest"], "sourceGitSha": SHA,
        "sourceTreeDigest": TREE, "artifactDigest": D, "runtimeConfigPackageDigest": D,
        "runtimeConfigTrustEnvelopeDigest": D, "effectiveLaunchManifestDigest": D,
        "platform": "android", "deviceId": "pixel-1", "nonPromotable": non_promotable,
        "compileStatus": "compiled", "installStatus": "installed", "launchStatus": "launched",
        "runtimeStatus": "healthy", "consumerLeaseId": D,
        "transport": {"required": True, "reverseExpectedPorts": "19000,19010",
                      "reverseActualPorts": "19000,19010", "reverseReceiptDigest": D},
        "installedConfigReadback": {"configurationState": "complete", "runtimeConfigPackageDigest": D,
            "runtimeConfigTrustEnvelopeDigest": D, "effectiveLaunchManifestDigest": D},
    }
    report.update(contentSource=content_source, consumerLeaseId=lease)
    if not required_transport:
        report["transport"] = {"required": False, "reverseExpectedPorts": "", "reverseActualPorts": "", "reverseReceiptDigest": ""}
    _write(root, "report.json", report)
    return subject.create_launch_ready_fact_from_report(report_path=root / "report.json")


def _content(root: Path, launch: Path, *, non_promotable: bool) -> Path:
    journeys = []
    for journey in JOURNEYS:
        exact = _write(root, f"journeys/{journey}.json", {
            "journeyId": journey, "status": "passed", "producer": "app",
            "layer": "user_acceptance", "attemptId": ATTEMPT,
        })
        journeys.append({"journeyId": journey, **exact, "status": "passed", "producer": "app", "layer": "user_acceptance"})
    return subject.write_app_readiness_fact(subject.build_content_ready_fact(
        attempt_id=ATTEMPT, predecessor=subject.exact_ref(launch, attempt_dir=root),
        journeys=journeys, non_promotable=non_promotable,
    ), attempt_dir=root)


def _release(root: Path, content: Path) -> Path:
    composition = "sha256:" + "d" * 64
    candidate = _write(root, "candidate.json", {"releaseCompositionId": composition,
        "artifactDigest": D, "sourceGitSha": SHA, "sourceTreeDigest": TREE, "status": "artifact-complete"})
    candidate.update({"releaseCompositionId": composition, "artifactDigest": D,
                      "sourceGitSha": SHA, "sourceTreeDigest": TREE, "status": "artifact-complete"})
    qualification = {}
    for name in ("eaf", "androidPhysical", "iosPhysical", "provider", "migration", "rollback", "performance", "reliability", "cleanup"):
        value = {"status": "passed", "releaseCompositionId": composition}
        if name == "androidPhysical": value.update(platform="android", deviceClass="physical", registered=True)
        if name == "iosPhysical": value.update(platform="ios", deviceClass="physical", registered=True)
        if name == "provider": value["providerClass"] = "real"
        qualification[name] = _write(root, f"qualification/{name}.json", value)
    return subject.write_app_readiness_fact(subject.build_release_ready_fact(
        attempt_id=ATTEMPT, predecessor=subject.exact_ref(content, attempt_dir=root),
        release_candidate=candidate, qualification=qualification,
    ), attempt_dir=root)


@pytest.mark.parametrize("source,required,promotable,accepted", [
    ("bundled_snapshot", False, False, True), ("remote", False, False, False),
    ("bundled_snapshot", True, False, False), ("bundled_snapshot", False, True, False),
    ("unknown", False, False, False),
])
def test_empty_lease_is_only_offline_without_runtime_transport(tmp_path, source, required, promotable, accepted):
    if accepted:
        path = _launch(tmp_path, non_promotable=not promotable, content_source=source, lease="", required_transport=required)
        assert subject.load_app_readiness_fact(path)["consumerLeaseId"] == ""
    else:
        with pytest.raises(subject.AppReadinessFactError):
            _launch(tmp_path, non_promotable=not promotable, content_source=source, lease="", required_transport=required)


@pytest.mark.parametrize("damage", ["", "missing", "failed", "terminal", "blocker"])
def test_stopped_requires_complete_success_and_bound_safe_terminal(tmp_path, damage):
    if damage:
        with pytest.raises(subject.AppReadinessFactError):
            _launch(tmp_path, non_promotable=True, stopped=True, damage=damage)
    else:
        assert subject.load_app_readiness_fact(_launch(tmp_path, non_promotable=True, stopped=True))["launchAttempt"]["status"] == "stopped"


def test_three_stage_positive_chain(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    launch = _launch(root, non_promotable=False)
    content = _content(root, launch, non_promotable=False)
    release = _release(root, content)
    assert subject.load_app_readiness_fact(launch)["factType"] == subject.LAUNCH
    assert subject.load_app_readiness_fact(content)["factType"] == subject.CONTENT
    assert subject.load_app_readiness_fact(release)["factType"] == subject.RELEASE


def test_development_launch_is_non_promotable_and_release_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    launch = _launch(root, non_promotable=True)
    content = _content(root, launch, non_promotable=True)
    with pytest.raises(subject.AppReadinessFactError, match="APP.READINESS.non_promotable"):
        _release(root, content)


def test_content_requires_direct_complete_journey_set(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    launch = _launch(root, non_promotable=False)
    fact = subject.build_content_ready_fact(attempt_id=ATTEMPT,
        predecessor=subject.exact_ref(launch, attempt_dir=root), journeys=[], non_promotable=False)
    with pytest.raises(subject.AppReadinessFactError, match="raw UAT journeys are required"):
        subject.write_app_readiness_fact(fact, attempt_dir=root)


def test_wrong_or_skipped_predecessor_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    launch = _launch(root, non_promotable=False)
    fact = subject.build_release_ready_fact(attempt_id=ATTEMPT,
        predecessor=subject.exact_ref(launch, attempt_dir=root), release_candidate={}, qualification={})
    with pytest.raises(subject.AppReadinessFactError, match="requires ContentReadyFact"):
        subject.write_app_readiness_fact(fact, attempt_dir=root)


def test_fact_and_evidence_digest_tampering_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    launch = _launch(root, non_promotable=False)
    value = json.loads(launch.read_text(encoding="utf-8"))
    value["deviceId"] = "other-device"
    launch.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(subject.AppReadinessFactError, match="digest_drift"):
        subject.load_app_readiness_fact(launch)


def test_create_once_and_stale_attempt_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    _launch(root, non_promotable=False)
    with pytest.raises(subject.AppReadinessFactError, match="create_once_conflict"):
        subject.create_launch_ready_fact_from_report(report_path=root / "report.json")
    with pytest.raises(subject.AppReadinessFactError, match="stale_attempt"):
        subject.write_app_readiness_fact({}, attempt_dir=root, create_attempt=True)


def test_symlink_evidence_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / ATTEMPT
    root.mkdir()
    _launch(root, non_promotable=False)
    report = root / "report.json"
    report.unlink()
    report.symlink_to(root / "attempt.json")
    with pytest.raises(subject.AppReadinessFactError, match="path_blocked"):
        subject.create_launch_ready_fact_from_report(report_path=report)
