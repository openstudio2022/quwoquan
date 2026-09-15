"""离线页面验收不借用在线权威。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
"""

import argparse
import copy
import json
import base64
import plistlib
import hashlib
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch
from quwoquan_ops.cli.commands import app_preflight_uat_offline as offline
from quwoquan_ops.cli.commands import app_preflight_uat_offline_pages as pages
from quwoquan_ops.cli.lib.target_uat_binding import read_target_uat_binding

ROOT = Path(__file__).resolve().parents[4]
DIGEST = "sha256:" + "a" * 64
SCREENSHOT = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9o0AAAAASUVORK5CYII=")
SCREENSHOT_DIGEST = "sha256:" + hashlib.sha256(SCREENSHOT).hexdigest()


@pytest.mark.parametrize("platform", ["android", "ios"])
def test_rehearsal_required_cases_keep_unimplemented_evidence_blocked(platform: str) -> None:
    plans = {plan["caseId"]: plan for plan in _plans(_launch_identity(platform))}
    assert not {"login-unavailable", "private-unavailable", "write-unavailable"} & plans.keys()
    for case in ("login-success", "login-error", "private-continuation", "local-write",
                 "otp-expiry", "identity-restart", "network-refusal", "otp-refusal",
                 "push-refusal", "remote-refusal", "outbox-refusal"):
        plan = plans[case]
        assert plan["specRef"].endswith("#gwt-008")
        assert plan["executionBlocker"].startswith("APP.UAT.")
        with pytest.raises(ValueError, match="APP.UAT."):
            pages.require_executable_page_plan(plan)
    cancel = plans["login-cancel"]
    assert cancel["executionBlocker"] == ""
    assert cancel["specRef"].endswith("#gwt-008")
    pages.require_executable_page_plan(cancel)


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("mode", ["correct", "incorrect"])
def test_native_ui_otp_input_contract_is_value_free_and_redacted(platform: str, mode: str) -> None:
    step = {"operation": "input-otp", "selector": "otp-field", "sourceSelector": "rehearsal-hint", "mode": mode}
    pages._validate_page_step(step)
    pages._validate_step_observation(step, {"operation": "input-otp", "selector": "otp-field", "observed": "input-redacted"})
    with pytest.raises(ValueError):
        pages._validate_step_observation(step, {"operation": "input-otp", "selector": "otp-field", "observed": "000000"})
    # 同一 plan validator 负责两端；未授予演练空间的 case 不得借输入 API 变成可执行。
    plan = next(plan for plan in _plans(_launch_identity(platform)) if plan["caseId"] == "login-error")
    plan["executionBlocker"] = ""
    plan["planDigest"] = pages.document_digest({key: value for key, value in plan.items() if key != "planDigest"})
    with pytest.raises(ValueError):
        pages.validate_page_plan(plan)


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("change", [
    {"value": "000000"}, {"mode": "arbitrary"}, {"sourceSelector": ""},
    {"selector": "text-prefix:otp"}, {"sourceSelector": "text-prefix:hint"}, {"shell": "input"},
])
def test_native_input_rejects_undeclared_parameters(platform: str, change: dict) -> None:
    plan = next(plan for plan in _plans(_launch_identity(platform)) if plan["caseId"] == "login-cancel")
    plan["steps"].insert(0, {"operation": "input-otp", "selector": "otp-field", "sourceSelector": "hint", "mode": "correct", **change})
    plan["planDigest"] = pages.document_digest({key: value for key, value in plan.items() if key != "planDigest"})
    with pytest.raises(ValueError):
        pages.validate_page_plan(plan)


def test_both_native_hosts_block_input_until_redacted_execution_is_available() -> None:
    android = (ROOT / "quwoquan_app/test_host/patrol/android/app/src/androidTest/java/com/quwoquan/testhost/patrol/ProductionHomepageExternalAutTest.java").read_text()
    ios = (ROOT / "quwoquan_app/test_host/patrol/ios/RunnerUITests/RunnerUITests.m").read_text()
    for source in (android, ios):
        assert "redacted native input execution is unavailable" in source
        assert "sourceSelector" in source and "incorrect" in source
        assert "input-redacted" in source
    assert "field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT" not in android
    assert "[field typeText:" not in ios
    assert "fields.size()" in android and "field.isEditable() && field.isEnabled()" in android
    assert "fields.count" in ios and "field.enabled && field.hittable" in ios


def test_input_plan_cannot_reach_native_command_through_low_level_executor(tmp_path: Path) -> None:
    binding = _launch_identity()
    plan = next(plan for plan in _plans(binding) if plan["caseId"] == "login-success")
    with pytest.raises(ValueError, match="authorized rehearsal identity"):
        pages._execute_native_page(plan=plan, launch=binding, context={}, case_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.fixture
def private_offline_projection(tmp_path):
    """仅私有source capsule，无签名材料、真实构建或设备。"""
    from quwoquan_ops.cli.lib.package_reuse.input_capsule import _digest_record, _baseline_id, _capsule_identity_payload
    capsule, root = tmp_path / "capsule", tmp_path / "projection"
    raw = b'{"privateSnapshot":true}\n'
    pin = "sha256:" + hashlib.sha256(raw).hexdigest()
    files = {"quwoquan_app/assets/content/alpha/manifest.json": raw,
             "quwoquan_app/assets/content/alpha/bundle_identity.json": json.dumps({"manifestDigest": pin}).encode()}
    entries = []
    for relative, content in files.items():
        for base, mode in ((capsule / "repo", 0o444), (root, 0o644)):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(mode)
        entries.append({"logicalPath": relative, "capsulePath": "repo/" + relative, "kind": "file",
                        "digest": "sha256:" + hashlib.sha256(content).hexdigest(), "size": len(content), "mode": 0o444})
    source_digest, count = _digest_record([(path, "file", content) for path, content in files.items()])
    roots = ["quwoquan_app/assets"]
    manifest = {"schema": "stackctl-package-input-capsule.v1", "sourceRevision": "b" * 40,
                "baselineId": _baseline_id(_capsule_identity_payload(roots=roots, input_digest=source_digest, input_count=count)),
                "workspaceStatusDigest": DIGEST, "deploymentInputDigest": source_digest,
                "deploymentInputFileCount": count, "deploymentInputRoots": roots, "entries": entries}
    (capsule / "manifest.json").write_text(json.dumps(manifest))
    pd, pc = launch._projection_cas(manifest=manifest, capsule_root=capsule, projection_root=root, reject_unmanifested=True)
    evidence = {"schema": "quwoquan_ops.app_content_uat_source_projection.v1", "contentSource": "bundled_snapshot",
                "candidateDigest": DIGEST, "sourceRevision": "b" * 40, "sourceCapsuleDigest": source_digest,
                "sourceCapsuleWorkspaceStatusDigest": DIGEST, "sourceCapsuleManifestDigest": pages.document_digest(manifest),
                "sourceCapsuleManifestRef": str(capsule / "manifest.json"), "sourceProjectionRoot": str(root),
                "sourceProjectionDigest": pd, "sourceProjectionFileCount": pc}
    ref = tmp_path / "projection.json"
    ref.write_text(json.dumps(evidence))
    projection = {**evidence, "sourceProjectionEvidenceRef": str(ref), "sourceProjectionEvidenceDigest": pages.document_digest(evidence)}
    runtime = {**evidence, "environment": "alpha", "target": "alpha-local"}
    return runtime, projection, pin


@pytest.mark.parametrize("platform", ["android", "ios-simulator"])
@pytest.mark.parametrize("isolated", [False, True])
def test_offline_launch_forwards_private_selection_without_signing_or_device(tmp_path, monkeypatch, private_offline_projection, platform, isolated):
    from quwoquan_ops.cli import stackctl
    runtime, projection, pin = private_offline_projection
    args = argparse.Namespace(platform=platform, device_id="private-device", isolated_rehearsal=isolated,
                              rehearsal_instance_id="private-test-space" if isolated else "")
    # 保留真实control writer和handoff校验，仅在系统执行边界终止。
    def no_launch(*args, **kwargs):
        raise RuntimeError("test-stop-before-system-execution")
    monkeypatch.setattr(stackctl, "run", no_launch)
    with pytest.raises(RuntimeError, match="test-stop-before-system"):
        offline._launch(args, runtime, projection, tmp_path / "run", tmp_path)
    control = json.loads((tmp_path / "run/attempt-1/control.json").read_text())
    assert control["deviceId"] == args.device_id and control["candidateDigest"] == DIGEST
    if isolated:
        assert control["rehearsalSpaceSelection"] == {"mode": "isolated", "instanceId": "private-test-space", "snapshotDigest": pin}
    else:
        assert "rehearsalSpaceSelection" not in control
    assert not (tmp_path / "run/attempt-1/attempt.json").exists()


@pytest.mark.parametrize("change", [
    {"isolated_rehearsal": True, "rehearsal_instance_id": ""},
    {"isolated_rehearsal": False, "rehearsal_instance_id": "private-test-space"},
    {"isolated_rehearsal": True, "rehearsal_instance_id": "default"},
    {"isolated_rehearsal": True, "rehearsal_instance_id": "../space"},
])
def test_explicit_selection_cannot_fall_back_to_default(tmp_path, private_offline_projection, change):
    runtime, projection, _ = private_offline_projection
    args = argparse.Namespace(platform="android", device_id="private-device", **change)
    with pytest.raises(ValueError):
        offline._launch(args, runtime, projection, tmp_path / "run", tmp_path)
    assert not (tmp_path / "run/attempt-1/control.json").exists()


@pytest.mark.parametrize("field,value", [
    ("deviceId", "another-device"), ("candidateDigest", "sha256:" + "d" * 64),
    ("launchAttemptRef", "another-attempt"), ("sourceCapsuleDigest", "sha256:" + "d" * 64),
    ("contentSource", "remote"), ("selection", None), ("snapshot", "sha256:" + "f" * 64),
])
def test_isolated_forwarding_drift_is_rejected_before_system_execution(tmp_path, monkeypatch, private_offline_projection, field, value):
    from quwoquan_ops.cli import stackctl
    runtime, projection, _ = private_offline_projection
    original = launch.write_app_content_launch_control
    def corrupt(**kwargs):
        control = original(**kwargs)
        path = Path(control["controlRef"])
        payload = json.loads(path.read_text())
        if field == "selection":
            payload.pop("rehearsalSpaceSelection")
        elif field == "snapshot":
            payload["rehearsalSpaceSelection"]["snapshotDigest"] = value
        else:
            payload[field] = value
        path.write_text(json.dumps(payload))
        return {**payload, "controlRef": str(path), "controlDigest": pages.document_digest(payload)}
    monkeypatch.setattr(launch, "write_app_content_launch_control", corrupt)
    def forbidden(*args, **kwargs):
        pytest.fail("must not execute build, signer or device")
    monkeypatch.setattr(stackctl, "run", forbidden)
    args = argparse.Namespace(platform="android", device_id="private-device", isolated_rehearsal=True, rehearsal_instance_id="private-test-space")
    with pytest.raises(ValueError):
        offline._launch(args, runtime, projection, tmp_path / "run", tmp_path)


@pytest.mark.parametrize("damage", ["candidate", "snapshot", "source", "missing-pin"])
def test_isolated_request_rejects_projection_drift_before_control(tmp_path, private_offline_projection, damage):
    runtime, projection, _ = private_offline_projection
    if damage == "candidate":
        runtime["candidateDigest"] = "sha256:" + "e" * 64
    elif damage == "source":
        runtime["contentSource"] = "remote"
    else:
        manifest = Path(projection["sourceProjectionRoot"]) / "quwoquan_app/assets/content/alpha/manifest.json"
        if damage == "snapshot":
            manifest.write_text("changed")
        else:
            manifest.unlink()
    args = argparse.Namespace(platform="android", device_id="private-device", isolated_rehearsal=True, rehearsal_instance_id="private-test-space")
    with pytest.raises((ValueError, OSError)):
        offline._launch(args, runtime, projection, tmp_path / "run", tmp_path)
    assert not (tmp_path / "run/attempt-1/control.json").exists()


@pytest.mark.parametrize("arguments", [
    ["--targets", "beta-local", "--isolated-rehearsal", "--rehearsal-instance-id", "private-space"],
    ["--targets", "alpha-local,beta-local", "--isolated-rehearsal", "--rehearsal-instance-id", "private-space"],
    ["--targets", "alpha-local", "--isolated-rehearsal"],
    ["--targets", "alpha-local", "--rehearsal-instance-id", "private-space"],
])
def test_isolated_cli_rejects_partial_or_cross_target_before_dispatch(monkeypatch, arguments):
    from quwoquan_ops.cli import stackctl
    from quwoquan_ops.cli.commands.app_preflight_uat_lock import command_app_content_uat
    args = stackctl.build_parser().parse_args(["app-content-uat", "--device-id", "private-device", *arguments])
    monkeypatch.setattr(stackctl, "_command_app_content_uat", lambda *a, **k: pytest.fail("must reject before UAT dispatch"))
    result = command_app_content_uat(args)
    assert result["exitCode"] == 2 and result["firstBlocker"] == "APP.LAUNCH.receipt_invalid"


def test_isolated_selection_does_not_authorize_native_pages_without_aut_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(offline, "_candidate", lambda *args: {})
    monkeypatch.setattr(offline, "_prepare_launch", lambda *args: ({}, {}))
    monkeypatch.setattr(offline, "_launch", lambda *args: {})
    monkeypatch.setattr(pages, "execute_offline_page_cases", lambda **kwargs: pytest.fail("missing AUT observation must block native pages"))
    result = offline.run_offline_app_content_uat(
        args=argparse.Namespace(dry_run=False, platform="android", device_id="private-device", isolated_rehearsal=True),
        report_dir=tmp_path, output_root=tmp_path, issues=[],
    )
    assert result["exitCode"] == 2
    assert "three-storage" in result["details"][0]
    assert result["rawResultRefs"] == {}


def test_home_video_and_tab_roundtrip_are_required_real_journeys() -> None:
    plans = {plan["caseId"]: plan for plan in _plans(_launch_identity())}
    video = plans["homepage-video-playback"]
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    recommended = next(row["orderedPostIds"] for row in snapshot["channels"] if row["channelId"] == "recommend")
    post = next(row["detail"] for row in snapshot["posts"]
                if row["projection"]["postId"] in recommended and row["detail"]["contentType"] == "video")
    assert post["postId"] in video["route"]
    assert video["steps"][-3] == {"operation": "tap", "selector": post["title"]}
    assert [step["operation"] for step in video["steps"]][-3:] == ["tap", "visible", "playback"]
    assert any(step["operation"] == "reveal" for step in video["steps"])
    tabs = plans["homepage-tab-roundtrip"]
    assert tabs["steps"][-1]["operation"] == "tab-roundtrip"
    for plan in (video, tabs):
        pages.validate_page_plan(plan)
        assert plan["caseId"] in offline.OFFLINE_REQUIRED_CASES


@pytest.mark.parametrize("geometry", [
    {"initial": [80, 10], "middle": [80], "further": [80], "restored": [80, 10]},
    {"initial": [80, 10], "middle": [10], "further": [40], "restored": [80, 10]},
    {"initial": [80, 10], "middle": [10], "further": [10], "restored": [10, -70]},
])
def test_tab_roundtrip_rejects_unpinned_or_unrestored_geometry(geometry: dict) -> None:
    step = {"operation": "tab-roundtrip", "selector": "推荐|关注"}
    with pytest.raises(ValueError, match="geometry"):
        pages._validate_step_observation(step, {**step, "observed": "推荐|关注 geometry=" + json.dumps(geometry)})


def test_home_video_cannot_replace_click_with_route_or_first_frame() -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == "homepage-video-playback")
    plan["steps"] = [step for step in plan["steps"] if step["operation"] != "reveal"]
    plan["planDigest"] = pages.document_digest({key: value for key, value in plan.items() if key != "planDigest"})
    with pytest.raises(ValueError):
        pages.validate_page_plan(plan)


def test_source_selection_comes_from_canonical_policy() -> None:
    assert offline.content_source_for_target("alpha-local") == "bundled_snapshot"
    assert offline.content_source_for_target("beta-local") == "remote"
    assert offline.content_source_for_target("gamma-local") == "remote"
    with pytest.raises(ValueError):
        offline.content_source_for_target("alpha-unknown")


def test_offline_dry_run_needs_no_backend_or_candidate(tmp_path: Path) -> None:
    result = offline.run_offline_app_content_uat(
        args=argparse.Namespace(dry_run=True, platform="android", device_id="emulator-test"),
        report_dir=tmp_path, output_root=tmp_path, issues=[],
    )
    assert result["status"] == "gate_block"
    assert result["blockedCases"]
    assert result["exitCode"] == 2
    assert result["nonPromotable"] is True
    assert result["rawResultRefs"] == {}
    assert result["preconditions"] == ["exact_candidate", "signed_bundled_snapshot", "managed_device"]
    assert len(result["requiredCases"]) >= 10


def test_offline_live_missing_candidate_is_blocked_before_device_access(tmp_path: Path) -> None:
    result = offline.run_offline_app_content_uat(
        args=argparse.Namespace(dry_run=False, platform="android", device_id="emulator-test"),
        report_dir=tmp_path, output_root=tmp_path, issues=[],
    )
    assert result["status"] == "gate_block"
    assert result["rawResultRefs"] == {}
    assert "candidate" in result["details"][0]


def _control(tmp_path: Path, runtime: dict[str, object]) -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    projection = {
        "sourceCapsuleManifestDigest": digest,
        "sourceCapsuleManifestRef": str(tmp_path / "capsule/manifest.json"),
        "sourceProjectionRoot": str(tmp_path / "projection"),
        "sourceProjectionEvidenceDigest": digest,
        "sourceProjectionEvidenceRef": str(tmp_path / "projection.json"),
    }
    return launch.write_app_content_launch_control(
        runtime_binding=runtime, projection=projection, output_root=tmp_path,
        control_path=tmp_path / "control.json", attempt_path=tmp_path / "attempt.json",
        report_path=tmp_path / "report.json", terminal_receipt_path=tmp_path / "terminal.json",
        platform="android", device_id="emulator-test",
        build_projection_policy_id=launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        build_projection_seal_path=tmp_path / "seal.json", expected_build_projection_digest=None,
    )


def test_offline_control_omits_remote_package_authority(tmp_path: Path) -> None:
    value = _control(tmp_path, {"environment": "alpha", "target": "alpha-local", "contentSource": "bundled_snapshot"})
    assert "packageDigest" not in value
    assert value["contentSource"] == "bundled_snapshot"
    assert json.loads(Path(value["controlRef"]).read_text())["contentSource"] == "bundled_snapshot"


@pytest.mark.parametrize("change", [
    {"environment": "beta"}, {"target": "beta-local"}, {"contentSource": "remote"}, {"packageDigest": ""},
])
def test_offline_control_rejects_mixed_authority(tmp_path: Path, change: dict[str, object]) -> None:
    value = {"environment": "alpha", "target": "alpha-local", "contentSource": "bundled_snapshot", **change}
    with pytest.raises(ValueError, match="authority mismatch"):
        _control(tmp_path, value)


def _native_marker(plan: dict[str, object], binding: dict[str, object]) -> str:
    observations = []
    for step in plan["steps"]:
        observed = step["selector"].removeprefix("text-prefix:")
        if step["operation"] == "playback":
            observed += " 2:07 / 2:07"
        elif step["operation"] == "seek":
            observed += " 0:30 / 2:07"
        elif step["operation"] == "tab-roundtrip":
            observed += ' geometry={"initial":[80,10],"middle":[10],"further":[10],"restored":[80,10]}'
        observations.append({**step, "observed": observed})
    return "QWQ_OFFLINE_PAGE " + json.dumps({
        **{key: binding[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
        "screenshotDigest": SCREENSHOT_DIGEST, "screenshotByteLength": len(SCREENSHOT),
        "schema": "quwoquan_ops.offline_native_page_result.v1", "caseId": plan["caseId"],
        "planDigest": plan["planDigest"], "platform": binding["platform"],
        "applicationId": binding["applicationId"], "status": "passed",
        "processIdBefore": binding["canonicalProcessId"], "processIdAfter": binding["canonicalProcessId"],
        "observations": observations,
    }, ensure_ascii=False)


def _launch_identity(platform: str = "android") -> dict[str, object]:
    return {"platform": platform, "applicationId": "com.quwoquan.app", "canonicalProcessId": 8123,
        "candidateDigest": DIGEST, "artifactDigest": DIGEST, "deviceId": "emulator-test" if platform == "android" else "SIM-EXACT",
        "launchAttemptId": "offline-attempt", "environment": "alpha", "target": "alpha-local",
        "sourceGitSha": "a" * 40, "contentSource": "bundled_snapshot", "runtimeConfigPackageDigest": DIGEST,
        "runtimeConfigTrustEnvelopeDigest": DIGEST, "contractGraphDigest": DIGEST}


def _plans(binding: dict[str, object]) -> list[dict[str, object]]:
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    return pages.build_offline_page_plans(snapshot=snapshot, app_root=ROOT / "quwoquan_app", launch=binding)


def test_plans_derive_all_cases_from_current_snapshot_and_typed_routes() -> None:
    plans = _plans(_launch_identity())
    assert tuple(plan["caseId"] for plan in plans) == offline.OFFLINE_REQUIRED_CASES
    for plan in plans:
        pages.validate_page_plan(plan)
        if plan["executionBlocker"]:
            with pytest.raises(ValueError, match="APP.UAT."):
                pages.validate_native_page_result(_native_marker(plan, _launch_identity()), plan=plan, launch=_launch_identity())
        else:
            pages.validate_native_page_result(_native_marker(plan, _launch_identity()), plan=plan, launch=_launch_identity())
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    for row in snapshot["posts"]:
        if row["detail"]["contentType"] == "article":
            row["detail"]["title"] = "由真实快照字段决定的标题"
    changed = pages.build_offline_page_plans(snapshot=snapshot, app_root=ROOT / "quwoquan_app", launch=_launch_identity())
    assert any(step["selector"] == "由真实快照字段决定的标题" for plan in changed for step in plan["steps"])


@pytest.mark.parametrize("operation", ["shell", "launch", "text", "delete", "unknown"])
def test_native_plan_rejects_unknown_or_unsafe_operations_before_running(operation: str) -> None:
    plan = copy.deepcopy(_plans(_launch_identity())[0])
    plan["steps"].insert(0, {"operation": operation, "selector": "unsafe"})
    plan["planDigest"] = pages.document_digest({k: v for k, v in plan.items() if k != "planDigest"})
    with pytest.raises(ValueError, match="unknown or unsafe"):
        pages.validate_native_page_result(_native_marker(plan, _launch_identity()), plan=plan, launch=_launch_identity())


@pytest.mark.parametrize("drift", ["pid", "no-observations", "unobserved", "plan", "duplicate", "application",
                                   "candidateDigest", "artifactDigest", "deviceId", "launchAttemptId", "screenshotDigest"])

def test_native_result_rejects_unobserved_or_drifted_fact(drift: str) -> None:
    binding = _launch_identity()
    plan = _plans(binding)[0]
    output = _native_marker(plan, binding)
    result = json.loads(output.split("QWQ_OFFLINE_PAGE ")[1])
    if drift == "pid":
        result["processIdAfter"] += 1
    elif drift == "no-observations":
        result["observations"] = []
    elif drift == "unobserved":
        result["observations"][0]["observed"] = "null null"
    elif drift == "plan":
        result["planDigest"] = "sha256:" + "b" * 64
    elif drift == "application":
        result["applicationId"] = "com.quwoquan.testhost.patrol"
    elif drift in {"candidateDigest", "artifactDigest", "deviceId", "launchAttemptId", "screenshotDigest"}:
        result[drift] = "drifted"
    output = "QWQ_OFFLINE_PAGE " + json.dumps(result)
    if drift == "duplicate":
        output += "\n" + output
    with pytest.raises(ValueError):
        pages.validate_native_page_result(output, plan=plan, launch=binding)


def _live_boundaries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str = "android", *, fail_case: str = ""):
    binding = _launch_identity(platform)
    attempt = tmp_path / "attempt.json"
    pages.write_create_once_json(attempt, {"attemptId": "offline-attempt"})
    binding.update(launchAttemptRef=str(attempt), launchAttemptDigest=pages.document_digest(json.loads(attempt.read_bytes())))
    candidate = {"candidateId": DIGEST, "commit": "a" * 40, "tree": "b" * 40}
    projection = {"sourceProjectionRoot": str(ROOT), "candidateDigest": DIGEST, "sourceRevision": candidate["commit"]}
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    monkeypatch.setattr(pages, "read_artifact_snapshot", lambda **_: snapshot)
    monkeypatch.setattr(pages, "_verify_page_projection", lambda _: None)
    monkeypatch.setattr(pages, "_acquire_page_device_lock", lambda *_: nullcontext())
    monkeypatch.setattr(pages, "_device", lambda args: {"id": args.device_id, "targetPlatform": platform, "emulator": True})
    context = {"host": ROOT / "quwoquan_app/test_host/patrol", "environment": {}, "adb": "/sealed/adb",
        "device": {"id": binding["deviceId"], "targetPlatform": platform, "emulator": True}, "binding": {"native": "driver-boundary"}}
    monkeypatch.setattr(pages, "_prepare_native_driver", lambda **_: context)
    monkeypatch.setattr(pages, "_read_driver_binding", lambda _: context["binding"])
    monkeypatch.setattr(pages, "_verify_driver_dependencies", lambda _: None)
    monkeypatch.setattr(pages, "_read_aut_binding", lambda **_: {"platform": platform, "deviceId": binding["deviceId"], "digest": DIGEST})
    if platform == "ios":
        source = tmp_path / "Runner_iphonesimulator.xctestrun"
        source.write_bytes(plistlib.dumps({"RunnerUITests": {
            "TestHostBundleIdentifier": pages.driver.PATROL_IOS_XCTRUNNER_BUNDLE_ID,
            "EnvironmentVariables": {}, "TestBundlePath": "__TESTROOT__/RunnerUITests.xctest",
        }}))
        context["binding"] = {"evidence": {"xctestrunPath": str(source), "xctestrunDigest": pages._file_digest(source)}}
    commands = []
    def native(command, *, cwd, env, timeout_seconds, log_path):
        commands.append(command)
        if platform == "android":
            plan = json.loads(base64.b64decode(command[command.index("qwqOfflinePagePlan") + 1]))
            assert command[:3] == ["/sealed/adb", "-s", binding["deviceId"]]
            assert command[command.index("class") + 1].endswith("#" + pages.ANDROID_PAGE_METHOD)
        else:
            assert command[:2] == ["xcodebuild", "test-without-building"]
            assert command[command.index("-destination") + 1] == "platform=iOS Simulator,id=" + binding["deviceId"]
            assert command[command.index("-only-testing") + 1].endswith("/" + pages.IOS_PAGE_METHOD)
            assert command[command.index("-parallel-testing-enabled") + 1] == "NO"
            payload = plistlib.loads(Path(command[command.index("-xctestrun") + 1]).read_bytes())
            environment = payload["RunnerUITests"]["EnvironmentVariables"]
            assert environment["QWQ_IOS_TARGET_BUNDLE_ID"] == binding["applicationId"]
            plan = json.loads(base64.b64decode(environment["QWQ_OFFLINE_PAGE_PLAN"]))
        output = ("QWQ_OFFLINE_SCREENSHOT " + plan["planDigest"] + " 0 " + base64.b64encode(SCREENSHOT).decode()
                  + "\n" + _native_marker(plan, binding))
        if platform == "android":
            output += "\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n"
        if plan["caseId"] == fail_case:
            output = "APP.LAUNCH.runtime_config_trust_missing: actual command failed"
        log_path.write_text(output)
        return {"exitCode": 1 if plan["caseId"] == fail_case else 0, "outputSummary": output, "command": command}
    monkeypatch.setattr(pages, "run_command", native)
    return binding, candidate, projection, commands


@pytest.mark.parametrize("platform", ["android", "ios"])
def test_live_dispatch_calls_real_executor_and_produces_full_acceptance_refs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str) -> None:
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path, platform)
    monkeypatch.setattr(offline, "_candidate", lambda *_: candidate)
    monkeypatch.setattr(offline, "_prepare_launch", lambda *_: ({}, projection))
    monkeypatch.setattr(offline, "_launch", lambda *_: binding)
    monkeypatch.setattr(offline, "_verify_source", lambda *_: None)
    receipt = offline.run_offline_app_content_uat(args=argparse.Namespace(dry_run=False, platform="android" if platform == "android" else "ios-simulator", device_id=binding["deviceId"]),
        report_dir=tmp_path / "uat", output_root=tmp_path, issues=[])
    assert receipt["status"] == "gate_block", receipt
    assert receipt["firstBlocker"] == "APP.UAT.page_artifact_binding_missing"
    supported = sum(not offline.offline_case_blocker(case) for case in offline.OFFLINE_REQUIRED_CASES)
    assert len(commands) == supported
    assert len(receipt["rawResultRefs"]["alpha-local"]) == supported
    assert len(receipt["rawResultDigests"]["alpha-local"]) == supported
    assert len(receipt["pageResultRefs"]) == supported
    assert receipt["blockedCases"]
    results = [json.loads((tmp_path / ref["ref"]).read_bytes()) for ref in receipt["rawResultRefs"]["alpha-local"]]
    target = receipt["targetUatBindingRefs"]["alpha-local"]
    typed_binding = read_target_uat_binding(tmp_path / target["ref"])
    with pytest.raises(ValueError, match="incomplete"):
        pages.validate_offline_page_coverage(results=results, bindings=[typed_binding], candidate=candidate, platforms=[platform])
    if platform == "ios":
        assert not list(tmp_path.glob("*.external-aut.*.xctestrun"))
    with pytest.raises(ValueError, match="incomplete"):
        pages.validate_offline_page_coverage(results=results, bindings=[typed_binding], candidate=candidate)
    for ref, digest in zip(receipt["rawResultRefs"]["alpha-local"], receipt["rawResultDigests"]["alpha-local"], strict=True):
        assert pages._file_digest(tmp_path / ref["ref"]) == digest["digest"]
    for row in receipt["pageResultRefs"]:
        evidence = json.loads((tmp_path / row["evidence"]["ref"]).read_bytes())
        for field in ("plan", "nativeResult", "nativeDriverBinding", "launchBinding", "targetUatBinding", "screenshot", "log"):
            assert pages._file_digest(tmp_path / evidence[field]["ref"]) == evidence[field]["digest"]


def test_live_failure_keeps_first_typed_blocker_and_completed_raw_refs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path, fail_case="article-detail")
    receipt = pages.execute_offline_page_cases(args=argparse.Namespace(platform="android", device_id=binding["deviceId"]),
        candidate=candidate, launch=binding, projection=projection, report_dir=tmp_path / "uat", output_root=tmp_path)
    assert receipt["status"] == "gate_block"
    assert receipt["firstBlocker"] == "APP.LAUNCH.runtime_config_trust_missing"
    assert len(commands) == 4
    assert len(receipt["rawResultRefs"]["alpha-local"]) == 3
    assert receipt["rawCoverage"]["alpha-local"] == {"expected": len(offline.OFFLINE_REQUIRED_CASES), "present": 3, "missing": len(offline.OFFLINE_REQUIRED_CASES) - 3}


@pytest.mark.parametrize("field", ["candidateDigest", "sourceGitSha", "deviceId", "platform"])
def test_live_identity_drift_blocks_before_driver_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str) -> None:
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path)
    binding[field] = "wrong"
    receipt = pages.execute_offline_page_cases(args=argparse.Namespace(platform="android", device_id="emulator-test"),
        candidate=candidate, launch=binding, projection=projection, report_dir=tmp_path / "uat", output_root=tmp_path)
    assert receipt["exitCode"] == 2
    assert not commands
    assert receipt["rawResultRefs"] == {"alpha-local": []}


@pytest.mark.parametrize("path,accepted", [
    ("quwoquan_app/lib/new_adapter.dart", False),
    ("quwoquan_ops/cli/new_runner.py", False),
    ("quwoquan_app/assets/new_content.png", False),
    ("quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/new_source.dart", False),
    ("quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/new_masterImage.png", False),
    ("quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/app_page_error_state_dark_masterImage.png", True),
])
def test_candidate_freeze_rejects_untracked_source_but_not_known_diagnostics(monkeypatch: pytest.MonkeyPatch, path: str, accepted: bool) -> None:
    def check_output(command, **_):
        if command[1:] == ["rev-parse", "HEAD"]:
            return "a" * 40
        if command[1:] == ["rev-parse", "HEAD^{tree}"]:
            return "b" * 40
        assert command[1:] == ["ls-files", "--others", "--exclude-standard", "-z"]
        return path + "\0"
    monkeypatch.setattr(offline.subprocess, "check_output", check_output)
    monkeypatch.setattr(offline.subprocess, "run", lambda *_, **__: subprocess.CompletedProcess([], 0))
    if accepted:
        offline._verify_source({"commit": "a" * 40, "tree": "b" * 40}, ROOT)
    else:
        with pytest.raises(ValueError, match="untracked source"):
            offline._verify_source({"commit": "a" * 40, "tree": "b" * 40}, ROOT)


def test_first_typed_launch_error_is_not_replaced(tmp_path: Path) -> None:
    receipt = offline.run_offline_app_content_uat(args=argparse.Namespace(dry_run=False, platform="android", device_id="emulator-test"),
        report_dir=tmp_path, output_root=tmp_path, issues=["APP.DEPENDENCY.bundle_stale: field=source"])
    assert receipt["firstBlocker"] == "APP.DEPENDENCY.bundle_stale"


@pytest.mark.parametrize("drift", ["aut", "driver", "screenshot", "projection"])
def test_live_actual_observation_failure_never_emits_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, drift: str) -> None:
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path)
    calls = 0
    def readback(**_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("APP.LAUNCH.receipt_invalid: AUT artifact drifted after observation")
        return {"digest": DIGEST}
    if drift == "aut":
        monkeypatch.setattr(pages, "_read_aut_binding", readback)
    elif drift == "driver":
        monkeypatch.setattr(pages, "_read_driver_binding", lambda _: {"drifted": True})
    elif drift == "screenshot":
        monkeypatch.setattr(pages, "native_page_screenshot", lambda *_: b"corrupt")
    else:
        def projection_readback(_):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise ValueError("APP.LAUNCH.receipt_invalid: source projection drifted")
        monkeypatch.setattr(pages, "_verify_page_projection", projection_readback)
    receipt = pages.execute_offline_page_cases(args=argparse.Namespace(platform="android", device_id=binding["deviceId"]),
        candidate=candidate, launch=binding, projection=projection, report_dir=tmp_path / "uat", output_root=tmp_path)
    assert receipt["exitCode"] == 2
    assert len(commands) == 1
    assert receipt["rawResultRefs"] == {"alpha-local": []}


def test_android_zero_shell_exit_without_junit_terminal_is_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binding = _launch_identity()
    plan = _plans(binding)[0]
    def native(command, *, cwd, env, timeout_seconds, log_path):
        log_path.write_text(_native_marker(plan, binding))
        return {"exitCode": 0, "command": command}
    monkeypatch.setattr(pages, "run_command", native)
    with pytest.raises(ValueError, match="Instrumentation did not finish"):
        pages._execute_native_page(plan=plan, launch=binding,
            context={"host": tmp_path, "environment": {}, "adb": "/sealed/adb"}, case_dir=tmp_path)


def test_native_sources_prevalidate_all_steps_and_check_canonical_pid() -> None:
    android = (ROOT / "quwoquan_app/test_host/patrol/android/app/src/androidTest/java/com/quwoquan/testhost/patrol/ProductionHomepageExternalAutTest.java").read_text()
    ios = (ROOT / "quwoquan_app/test_host/patrol/ios/RunnerUITests/RunnerUITests.m").read_text()
    assert android.count("private static String observedNode(") == 1
    assert android.index('matches("visible|tap|scroll|seek|playback|back|reveal|tab-roundtrip|input-otp")') < android.index("int before = requireSingleRunningPid(automation, target);")
    assert 'plan.getInt("canonicalProcessId"), before' in android
    assert 'Assume.assumeTrue(explicitlySelected || arguments.containsKey("qwqOfflinePagePlan"))' in android
    assert 'XCTAssertEqualObjects(before, plan[@"canonicalProcessId"])' in ios
    assert ios.index("[operations containsObject:step[@\"operation\"]]") < ios.index("[app activate];")


@pytest.mark.parametrize("damage", ["missing", "digest", "order", "duplicate", "bytes", "length", "encoding", "truncated"])
def test_native_screenshot_requires_current_ordered_exact_bytes(damage: str) -> None:
    binding = _launch_identity()
    plan = _plans(binding)[0]
    native = json.loads(_native_marker(plan, binding).split("QWQ_OFFLINE_PAGE ")[1])
    encoded = base64.b64encode(SCREENSHOT).decode()
    output = f"QWQ_OFFLINE_SCREENSHOT {plan['planDigest']} 0 {encoded}\n"
    assert pages.native_page_screenshot(output, native) == SCREENSHOT
    if damage == "missing":
        output = ""
    elif damage == "digest":
        output = output.replace(plan["planDigest"], "sha256:" + "b" * 64)
    elif damage == "order":
        output = output.replace(" 0 ", " 1 ")
    elif damage == "duplicate":
        output += output
    elif damage == "bytes":
        output = output.replace(encoded, base64.b64encode(b"not a screenshot").decode())
    elif damage == "encoding":
        output = output.replace(encoded, "%%invalid-base64%%")
    elif damage == "truncated":
        output = output.replace(encoded, encoded[:-4])
    else:
        native["screenshotByteLength"] += 1
    with pytest.raises(ValueError, match="screenshot"):
        pages.native_page_screenshot(output, native)


def test_native_screenshot_reassembles_ordered_chunks_with_native_log_prefixes() -> None:
    binding = _launch_identity()
    plan = _plans(binding)[0]
    native = json.loads(_native_marker(plan, binding).split("QWQ_OFFLINE_PAGE ")[1])
    encoded = base64.b64encode(SCREENSHOT).decode()
    chunks = [encoded[index:index + 20] for index in range(0, len(encoded), 20)]
    output = "\n".join(f"native stdout: QWQ_OFFLINE_SCREENSHOT {plan['planDigest']} {index} {chunk}"
                       for index, chunk in enumerate(chunks))
    assert pages.native_page_screenshot(output, native) == SCREENSHOT


@pytest.mark.parametrize("kind", ["existing", "symlink", "dangling-symlink"])
def test_native_screenshot_slot_is_fresh_before_any_driver_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    binding = _launch_identity()
    plan = _plans(binding)[0]
    screenshot = tmp_path / "screenshot.png"
    target = tmp_path / "owned-elsewhere.png"
    if kind == "existing":
        screenshot.write_bytes(b"prior evidence")
    else:
        if kind == "symlink":
            target.write_bytes(b"other owner bytes")
        screenshot.symlink_to(target)
    commands = []
    monkeypatch.setattr(pages, "run_command", lambda *args, **kwargs: commands.append(args))
    with pytest.raises(ValueError, match="screenshot path must be fresh"):
        pages._execute_native_page(plan=plan, launch=binding,
            context={"host": tmp_path, "environment": {}, "adb": "/sealed/adb"}, case_dir=tmp_path)
    assert not commands
    if kind == "existing":
        assert screenshot.read_bytes() == b"prior evidence"
    elif kind == "symlink":
        assert target.read_bytes() == b"other owner bytes"
    else:
        assert not target.exists()


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("damage", ["missing", "foreign-plan", "corrupt", "duplicate"])
def test_native_screenshot_closure_failure_never_emits_raw_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, damage: str) -> None:
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path, platform)
    native_command = pages.run_command
    def damaged(*args, **kwargs):
        result = native_command(*args, **kwargs)
        path = kwargs["log_path"]
        output = path.read_text()
        first, remainder = output.split("\n", 1)
        if damage == "missing":
            output = remainder
        elif damage == "foreign-plan":
            fields = first.split(" ")
            fields[1] = "sha256:" + "b" * 64
            output = " ".join(fields) + "\n" + remainder
        elif damage == "corrupt":
            output = first.rsplit(" ", 1)[0] + " %%invalid%%\n" + remainder
        else:
            output = first + "\n" + output
        path.write_text(output)
        return result
    monkeypatch.setattr(pages, "run_command", damaged)
    receipt = pages.execute_offline_page_cases(args=argparse.Namespace(
        platform="android" if platform == "android" else "ios-simulator", device_id=binding["deviceId"]),
        candidate=candidate, launch=binding, projection=projection, report_dir=tmp_path / "uat", output_root=tmp_path)
    assert receipt["firstBlocker"] == "APP.UAT.page_artifact_binding_missing"
    assert receipt["status"] == "gate_block" and receipt["rawResultRefs"] == {"alpha-local": []}
    assert len(commands) == 1
    assert not (tmp_path / "uat/pages/default-entry/screenshot.png").exists()
    if platform == "ios":
        assert not list(tmp_path.glob("*.external-aut.*.xctestrun"))


def test_native_tap_selectors_are_exact_and_body_prefix_is_observation_only() -> None:
    binding = _launch_identity()
    plans = _plans(binding)
    for plan in plans:
        assert all(not step["selector"].startswith("text-prefix:") for step in plan["steps"] if step["operation"] == "tap")
    plan = copy.deepcopy(plans[0])
    plan["steps"].append({"operation": "tap", "selector": "text-prefix:wrong card"})
    plan["planDigest"] = pages.document_digest({k: v for k, v in plan.items() if k != "planDigest"})
    with pytest.raises(ValueError, match="prefix"):
        pages.validate_page_plan(plan)
    android = (ROOT / "quwoquan_app/test_host/patrol/android/app/src/androidTest/java/com/quwoquan/testhost/patrol/ProductionHomepageExternalAutTest.java").read_text()
    ios = (ROOT / "quwoquan_app/test_host/patrol/ios/RunnerUITests/RunnerUITests.m").read_text()
    assert "toString().contains(selector)" not in android
    assert "label CONTAINS" not in ios
    assert "automation.takeScreenshot()" in android and "app.screenshot.PNGRepresentation" in ios


@pytest.mark.parametrize("case_id", offline.OFFLINE_REQUIRED_CASES[1:])
def test_nondefault_case_cannot_be_relabelled_first_frame(case_id: str) -> None:
    plan = _plans(_launch_identity())[0]
    plan["caseId"] = case_id
    plan["planDigest"] = pages.document_digest({k: v for k, v in plan.items() if k != "planDigest"})
    with pytest.raises(ValueError, match="page_plan_invalid"):
        pages.validate_page_plan(plan)


@pytest.mark.parametrize("case_id", ["article-detail", "video-seek", "empty-state"])
def test_video_restores_home_through_canonical_top_back_before_next_case(case_id: str) -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == case_id)
    assert plan["steps"][:2] == [
        {"operation": "tap", "selector": "works-top-back"},
        {"operation": "visible", "selector": "qwq.surface.home"},
    ]


def test_local_write_requires_readback_not_legacy_capability_refusal() -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == "local-write")
    assert "query/readback" in plan["executionBlocker"]
    with pytest.raises(ValueError, match="query/readback"):
        pages.require_executable_page_plan(plan)


def test_creator_avatar_binds_feed_tap_and_decoded_profile_to_same_identity() -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == "creator-avatar")
    persona = plan["route"].removeprefix("/user/")
    assert plan["steps"][-3:] == [
        {"operation": "reveal", "selector": "creator-avatar:" + persona},
        {"operation": "tap", "selector": "creator-avatar:" + persona},
        {"operation": "visible", "selector": "creator-profile-avatar:" + persona},
    ]


def test_login_cancel_observes_login_control_and_guest_return() -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == "login-cancel")
    assert plan["route"] == "/"
    assert plan["steps"][-1]["selector"] == plan["steps"][-5]["selector"]
    assert plan["steps"][-4]["selector"] == plan["steps"][-3]["selector"]
    assert not any("capability-unavailable" in step["selector"] for step in plan["steps"])


@pytest.mark.parametrize("case_id", ["creator-avatar", "login-cancel"])
@pytest.mark.parametrize("replacement", ["内容暂不可用", "app-image-load-success", "qwq.surface.home"])
def test_identity_journey_rejects_generic_text_or_first_frame_terminal(case_id: str, replacement: str) -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == case_id)
    plan["steps"][-1]["selector"] = replacement
    plan["planDigest"] = pages.document_digest({k: v for k, v in plan.items() if k != "planDigest"})
    with pytest.raises(ValueError, match="page_plan_invalid"):
        pages.validate_native_page_result(_native_marker(plan, _launch_identity()), plan=plan, launch=_launch_identity())


@pytest.mark.parametrize("case_id,route", [("login-cancel", "/chat"), ("login-cancel", "/create")])
def test_refusal_cannot_record_unentered_route(case_id: str, route: str) -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == case_id)
    plan["route"] = route
    plan["planDigest"] = pages.document_digest({k: v for k, v in plan.items() if k != "planDigest"})
    with pytest.raises(ValueError, match="page_plan_invalid"):
        pages.validate_page_plan(plan)


def test_android_snapshot_reads_actual_apk_and_rejects_corrupted_media(tmp_path: Path) -> None:
    import zipfile
    import hashlib
    app = tmp_path / "app"
    source = app / "assets/content/alpha"
    source.mkdir(parents=True)
    body = b"actual-media-object"
    relative = "assets/content/alpha/media/asset.png"
    manifest = {"media": [{"assetId": "asset", "assetPath": relative, "byteLength": len(body),
                            "sha256": "sha256:" + hashlib.sha256(body).hexdigest()}]}
    manifest["bundleId"] = "alpha-" + pages.document_digest(manifest).removeprefix("sha256:")
    pages.write_create_once_json(source / "manifest.json", manifest)
    identity = {"bundleId": manifest["bundleId"], "manifestDigest": pages._file_digest(source / "manifest.json")}
    pages.write_create_once_json(source / "bundle_identity.json", identity)
    def package(path: Path, media: bytes):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("assets/flutter_assets/assets/content/alpha/manifest.json", (source / "manifest.json").read_bytes())
            archive.writestr("assets/flutter_assets/assets/content/alpha/bundle_identity.json", (source / "bundle_identity.json").read_bytes())
            archive.writestr("assets/flutter_assets/" + relative, media)
    apk = tmp_path / "correct.apk"
    package(apk, body)
    assert pages.read_artifact_snapshot(artifact=apk, platform="android", expected_artifact_digest=pages._file_digest(apk), app_root=app) == manifest
    corrupt = tmp_path / "corrupt.apk"
    package(corrupt, b"corrupt")
    with pytest.raises(ValueError, match="corrupted"):
        pages.read_artifact_snapshot(artifact=corrupt, platform="android", expected_artifact_digest=pages._file_digest(corrupt), app_root=app)
    with pytest.raises(ValueError, match="artifact digest drifted"):
        pages.read_artifact_snapshot(artifact=apk, platform="android", expected_artifact_digest=DIGEST, app_root=app)
