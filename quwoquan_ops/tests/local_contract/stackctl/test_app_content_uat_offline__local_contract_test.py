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
def test_gwt008_cases_are_executable_with_launcher_owned_relay(platform: str) -> None:
    plans = {plan["caseId"]: plan for plan in _plans(_launch_identity(platform))}
    for case in {"login-success", "login-error", "private-continuation", "local-write", "otp-expiry",
                 "identity-restart", "network-refusal", "otp-refusal", "push-refusal", "remote-refusal",
                 "outbox-refusal"}:
        assert plans[case]["executionBlocker"] == ""
        pages.require_executable_page_plan(plans[case])
        assert plans[case]["nativeContract"]["caseId"] == case

@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("mode", ["correct", "incorrect"])
def test_native_ui_otp_input_contract_is_value_free_and_redacted(platform: str, mode: str) -> None:
    step = {"operation": "input-otp", "selector": "otp-field", "sourceSelector": "rehearsal-hint", "mode": mode}
    pages._validate_page_step(step)
    pages._validate_step_observation(step, {"operation": "input-otp", "selector": "otp-field", "observed": "input-redacted"})
    with pytest.raises(ValueError):
        pages._validate_step_observation(step, {"operation": "input-otp", "selector": "otp-field", "observed": "000000"})
    plan = next(plan for plan in _plans(_launch_identity(platform)) if plan["caseId"] == "login-error")
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


def test_both_native_hosts_emit_only_non_authorizing_terminal_result() -> None:
    android = (ROOT / "quwoquan_app/test_host/patrol/android/app/src/androidTest/java/com/quwoquan/testhost/patrol/ProductionHomepageExternalAutTest.java").read_text()
    ios = (ROOT / "quwoquan_app/test_host/patrol/ios/RunnerUITests/RunnerUITests.m").read_text()
    for source in (android, ios):
        assert "actualObservation" not in source
        assert "external-uat-terminal-result" in source and "terminalRef" in source
        assert "capability" not in source.lower() and "verifier" not in source.lower()


def test_input_plan_rejects_cross_attempt_before_native_command(tmp_path: Path) -> None:
    binding = _launch_identity()
    plan = next(plan for plan in _plans(binding) if plan["caseId"] == "login-success")
    plan["launchAttemptId"] = "foreign-attempt"
    plan["planDigest"] = pages.document_digest({key: value for key, value in plan.items() if key != "planDigest"})
    with pytest.raises(ValueError, match="cross AUT/attempt"):
        pages._execute_native_page(plan=plan, launch=binding, context={}, case_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.fixture
def private_offline_projection(tmp_path):
    """仅私有source capsule，无签名材料、真实构建或设备。"""
    from quwoquan_ops.cli.lib.package_reuse.input_capsule import _digest_record, _baseline_id, _capsule_identity_payload, PACKAGE_INPUT_CAPSULE_SCHEMA
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
    manifest = {"schema": PACKAGE_INPUT_CAPSULE_SCHEMA, "sourceRevision": "b" * 40,
                "baselineId": _baseline_id(_capsule_identity_payload(roots=roots, input_digest=source_digest, input_count=count)),
                "workspaceStatusDigest": DIGEST, "deploymentInputDigest": source_digest,
                "deploymentInputFileCount": count, "deploymentInputRoots": roots, "entries": entries,
                "dependencyPlatforms": ["android", "ios"]}
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
    control_path, = (tmp_path / "run/case-launches/login-success/generation-1").glob("*/attempt-1/control.json")
    control = json.loads(control_path.read_text())
    assert control["deviceId"] == args.device_id and control["candidateDigest"] == DIGEST
    if isolated:
        selection = control["rehearsalSpaceSelection"]
        assert selection["mode"] == "isolated" and selection["snapshotDigest"] == pin
        assert selection["caseId"] == "login-success" and selection["lifecycleGeneration"] == "1"
        assert selection["instanceId"] == "private-test-space-login-success-1"
        assert selection["observationBinding"].startswith("sha256:")
    else:
        assert "rehearsalSpaceSelection" not in control
    assert not (tmp_path / "run/attempt-1/attempt.json").exists()


@pytest.mark.parametrize("isolated", [False, True])
def test_every_case_generation_and_repeated_login_gets_fresh_control(tmp_path, monkeypatch, private_offline_projection, isolated):
    from quwoquan_ops.cli import stackctl
    runtime, projection, _ = private_offline_projection
    args = argparse.Namespace(platform="ios-simulator", device_id="private-device", isolated_rehearsal=isolated,
        rehearsal_instance_id="private-test-space" if isolated else "")
    def stop(*_, **__):
        raise RuntimeError("stop-before-device")
    monkeypatch.setattr(stackctl, "run", stop)
    controls = []
    for case, generation in (("login-success", 1), ("login-error", 1), ("login-success", 1), ("identity-restart", 2)):
        with pytest.raises(RuntimeError, match="stop-before-device"):
            offline._launch(args, runtime, projection, tmp_path / "run", tmp_path, case_id=case, generation=generation)
        current = set((tmp_path / "run").rglob("control.json"))
        fresh, = current - {path for path, _ in controls}
        controls.append((fresh, fresh.read_bytes()))
    assert len(controls) == 4
    assert len({json.loads(raw)["launchAttemptRef"] for _, raw in controls}) == 4
    assert all(path.read_bytes() == raw for path, raw in controls)


def test_restart_generations_preserve_space_but_not_observation(tmp_path, private_offline_projection):
    runtime, projection, _ = private_offline_projection
    args = argparse.Namespace(platform="ios-simulator", device_id="private-device", isolated_rehearsal=True,
        rehearsal_instance_id="private-test-space")
    one = offline._isolated_selection(args, runtime, projection, case_id="identity-restart", generation=1,
        attempt_ref=str(tmp_path / "one"))
    two = offline._isolated_selection(args, runtime, projection, case_id="identity-restart", generation=2,
        attempt_ref=str(tmp_path / "two"))
    assert one["instanceId"] == two["instanceId"]
    assert one["snapshotDigest"] == two["snapshotDigest"]
    assert one["observationBinding"] != two["observationBinding"]
    assert one["lifecycleGeneration"] != two["lifecycleGeneration"]


@pytest.mark.parametrize("platform", ["ios", "android"])
def test_native_driver_acquires_only_selected_platform_before_build(tmp_path, monkeypatch, platform):
    from quwoquan_ops.cli.lib import patrol_execution_lock
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"baselineId": DIGEST}))
    observed = []
    def lock(**kwargs):
        observed.append(kwargs)
        raise RuntimeError("stop-before-build")
    monkeypatch.setattr(patrol_execution_lock, "acquire_patrol_execution_lock", lock)
    projection = {"sourceCapsuleManifestRef": str(manifest), "candidateDigest": DIGEST,
        "sourceRevision": "a" * 40, "sourceCapsuleDigest": DIGEST, "sourceCapsuleWorkspaceStatusDigest": DIGEST}
    with pytest.raises(RuntimeError, match="stop-before-build"):
        pages._prepare_native_driver(args=argparse.Namespace(), projection=projection, launch={},
            artifact=tmp_path / "artifact", report_dir=tmp_path / "run", output_root=tmp_path,
            device={"targetPlatform": platform})
    assert observed == [{"env_name": "alpha", "target": "offline-native-pages", "platforms": (platform,)}]


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


def test_isolated_selection_enters_native_pages_only_with_case_bound_launch(monkeypatch, tmp_path):
    binding = {"launchAttemptId": "attempt-1", "canonicalProcessId": 7}
    monkeypatch.setattr(offline, "_candidate", lambda *args: {})
    monkeypatch.setattr(offline, "_prepare_launch", lambda *args: ({}, {}))
    monkeypatch.setattr(offline, "_launch", lambda *args, **kwargs: binding)
    observed = {}
    monkeypatch.setattr(pages, "execute_offline_page_cases", lambda **kwargs: observed.update(kwargs) or {"status": "gate_block", "exitCode": 2, "firstBlocker": "APP.UAT.page_artifact_binding_missing"})
    offline.run_offline_app_content_uat(args=argparse.Namespace(dry_run=False, platform="android", device_id="private-device", isolated_rehearsal=True), report_dir=tmp_path, output_root=tmp_path, issues=[])
    assert observed["launch"] == binding


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
    assert result["status"] == "planned"
    assert result["blockedCases"] == []
    assert result["exitCode"] == 0
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


def _actual_observation(plan: dict[str, object], binding: dict[str, object]) -> dict[str, object]:
    contract = plan["nativeContract"]
    restart = plan["caseId"] == "identity-restart"
    details = {
        "ui-control": "unique-editable-control",
        "rehearsal-session-readback": "session-established",
        "rehearsal-auth-error-readback": "recoverable-error-observed",
        "continuation-query-readback": "continued-once-readback",
        "local-command-query-readback": "command-query-readback",
        "monotonic-clock": "elapsed-300s-challenge-expired",
        "native-process": "cold-restart-new-process",
        "rehearsal-challenge-readback": "challenge-expired",
        "native-network-attempt": "refused-at-side-effect-boundary",
        "native-otp-delivery-attempt": "refused-at-side-effect-boundary",
        "native-push-registration-attempt": "refused-at-side-effect-boundary",
        "native-remote-transport-attempt": "refused-at-side-effect-boundary",
        "native-connected-outbox-attempt": "refused-at-side-effect-boundary",
    }
    return {"schema": "quwoquan_ops.alpha_gwt008_native_observation.v1", "caseId": plan["caseId"],
        "contractDigest": contract["contractDigest"], "applicationId": binding["applicationId"], "deviceId": binding["deviceId"],
        "candidateDigest": binding["candidateDigest"], "artifactDigest": binding["artifactDigest"],
        "launchAttemptBefore": binding["launchAttemptId"], "processIdBefore": binding["canonicalProcessId"],
        "launchAttemptAfter": "restart-attempt" if restart else binding["launchAttemptId"],
        "processIdAfter": binding["canonicalProcessId"] + 1 if restart else binding["canonicalProcessId"],
        "observations": [{"source": source, "status": "observed", "detail": details[source]} for source in contract["observationSources"]],
        "logSummary": "input-redacted"}

def _native_marker(plan: dict[str, object], binding: dict[str, object]) -> str:
    if "nativeContract" in plan:
        body = {"schema": "external-uat-terminal-result", "planDigest": plan["planDigest"],
            "caseId": plan["caseId"], "launchAttemptId": binding["launchAttemptId"],
            "generation": plan["nativeContract"]["generation"], "processId": binding["canonicalProcessId"],
            "deviceId": binding["deviceId"], "sessionId": plan["nativeContract"]["sessionId"],
            "status": "passed", "screenshotDigest": SCREENSHOT_DIGEST}
        terminal = {**body, "terminalDigest": pages.document_digest(body),
                    "terminalRef": "runner-terminal:" + str(plan["planDigest"])}
        return "QWQ_EXTERNAL_UAT_TERMINAL " + json.dumps(terminal, ensure_ascii=False)
    observations = []
    for step in plan["steps"]:
        observed = step["selector"].removeprefix("text-prefix:")
        if step["operation"] == "playback": observed += " 2:07 / 2:07"
        elif step["operation"] == "seek": observed += " 0:30 / 2:07"
        elif step["operation"] == "tab-roundtrip": observed += ' geometry={"initial":[80,10],"middle":[10],"further":[10],"restored":[80,10]}'
        observations.append({**step, "observed": observed})
    return "QWQ_OFFLINE_PAGE " + json.dumps({
        **{key: binding[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
        "screenshotDigest": SCREENSHOT_DIGEST, "screenshotByteLength": len(SCREENSHOT),
        "schema": "quwoquan_ops.offline_native_page_result.v1", "caseId": plan["caseId"],
        "planDigest": plan["planDigest"], "platform": binding["platform"],
        "applicationId": binding["applicationId"], "status": "passed",
        "processIdBefore": binding["canonicalProcessId"], "processIdAfter": binding["canonicalProcessId"],
        "observations": observations}, ensure_ascii=False)


def _launch_identity(platform: str = "android") -> dict[str, object]:
    return {"platform": platform, "applicationId": "com.quwoquan.app", "canonicalProcessId": 8123,
        "candidateDigest": DIGEST, "artifactDigest": DIGEST, "deviceId": "emulator-test" if platform == "android" else "SIM-EXACT",
        "launchAttemptId": "offline-attempt", "environment": "alpha", "target": "alpha-local",
        "sourceGitSha": "a" * 40, "contentSource": "bundled_snapshot", "runtimeConfigPackageDigest": DIGEST,
        "runtimeConfigTrustEnvelopeDigest": DIGEST, "contractGraphDigest": DIGEST}


def _plans(binding: dict[str, object]) -> list[dict[str, object]]:
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    return pages.build_offline_page_plans(snapshot=snapshot, app_root=ROOT / "quwoquan_app", launch=binding)


@pytest.mark.parametrize("fail_launch", [False, True])
def test_page_lock_handoff_uses_real_exclusive_flock(tmp_path, monkeypatch, fail_launch):
    from contextlib import ExitStack
    from quwoquan_ops.cli.lib import host_locks
    monkeypatch.setenv(host_locks.HOST_LOCK_ROOT_ENV, str(tmp_path / "locks"))
    def acquire(*_):
        return host_locks.acquire_device_lock(device="device", app="app", worktree_path=ROOT)
    monkeypatch.setattr(pages, "_acquire_page_device_lock", acquire)
    owned = ExitStack()
    owned.enter_context(acquire())
    def launch_case(case, generation):
        with acquire():
            with pytest.raises(host_locks.HostLockBusyError):
                acquire()
            if fail_launch:
                raise ValueError("APP.LAUNCH.compile_failed")
        return {"deviceId": "device", "applicationId": "app"}
    try:
        if fail_launch:
            with pytest.raises(ValueError, match="compile_failed"):
                pages._launch_between_page_locks(owned=owned, device_id="device", application_id="app",
                    launch_case=launch_case, case_id="default-entry", generation=1)
        else:
            pages._launch_between_page_locks(owned=owned, device_id="device", application_id="app",
                launch_case=launch_case, case_id="default-entry", generation=1)
            with pytest.raises(host_locks.HostLockBusyError):
                acquire()
    finally:
        owned.close()
    with acquire():
        pass


def test_page_lock_handoff_does_not_release_intervening_owner(tmp_path, monkeypatch):
    from contextlib import ExitStack
    from quwoquan_ops.cli.lib import host_locks
    monkeypatch.setenv(host_locks.HOST_LOCK_ROOT_ENV, str(tmp_path / "locks"))
    def acquire(*_):
        return host_locks.acquire_device_lock(device="device", app="app", worktree_path=ROOT)
    monkeypatch.setattr(pages, "_acquire_page_device_lock", acquire)
    owned = ExitStack()
    owned.enter_context(acquire())
    intervening = []
    def launch_case(*_):
        intervening.append(acquire())
        return {"deviceId": "device", "applicationId": "app"}
    try:
        with pytest.raises(host_locks.HostLockBusyError):
            pages._launch_between_page_locks(owned=owned, device_id="device", application_id="app",
                launch_case=launch_case, case_id="default-entry", generation=1)
        owned.close()
        with pytest.raises(host_locks.HostLockBusyError):
            acquire()
    finally:
        for lock in intervening:
            lock.close()
        owned.close()


def test_bounded_case_parser_and_diagnostic_never_becomes_full_acceptance(tmp_path, monkeypatch):
    from quwoquan_ops.cli import stackctl
    from quwoquan_ops.cli.lib.integration_app_launch import _validate_offline_receipt_status
    parser = stackctl.build_parser()
    args = parser.parse_args(['app-content-uat', '--device-id', 'SIM-EXACT', '--case', 'default-entry', '--dry-run'])
    assert offline.selected_offline_cases(args) == ('default-entry',)
    with pytest.raises(SystemExit):
        parser.parse_args(['app-content-uat', '--device-id', 'SIM-EXACT', '--case', 'unknown'])
    binding, candidate, projection, commands = _live_boundaries(monkeypatch, tmp_path)
    result = pages.execute_offline_page_cases(args=argparse.Namespace(platform='android', device_id=binding['deviceId'],
        offline_cases=['default-entry']), candidate=candidate, launch=binding, projection=projection,
        report_dir=tmp_path / 'selected', output_root=tmp_path)
    assert result['status'] == 'diagnostic_passed', result
    assert len(commands) == 1 and result['rawCoverage']['alpha-local']['missing'] == len(offline.OFFLINE_REQUIRED_CASES) - 1
    with pytest.raises(ValueError):
        _validate_offline_receipt_status({**result, 'schema': 'quwoquan_ops.app_content_uat_receipt',
            'contentSource': 'bundled_snapshot', 'targets': ['alpha-local'], 'nonPromotable': True,
            'status': 'passed', 'profile': 'rehearsal'})


def test_fresh_page_attempt_does_not_restore_previous_process_navigation():
    snapshot = json.loads((ROOT / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
    plans = pages.build_offline_page_plans(snapshot=snapshot, app_root=ROOT / "quwoquan_app",
        launch=_launch_identity(), fresh_launch=True)
    article = next(plan for plan in plans if plan["caseId"] == "article-detail")
    assert {"operation": "tap", "selector": "works-top-back"} not in article["steps"]
    pages.validate_page_plan(article)


def test_native_restart_plan_preserves_successor_relay_identity():
    from quwoquan_ops.cli.commands import app_preflight_uat_offline_native_contract as native
    launch = {**_launch_identity("ios"), "generation": 2, "sessionId": "fresh-session",
              "observationBinding": DIGEST, "launchAttemptId": "fresh-attempt", "canonicalProcessId": 9000}
    plan = next(plan for plan in _plans(launch) if plan["caseId"] == "identity-restart")
    contract = plan["nativeContract"]
    assert (contract["generation"], contract["sessionId"], contract["observationBinding"]) == (2, "fresh-session", DIGEST)
    assert [step["operation"] for step in plan["steps"]] == ["visible"]
    session = native.admit_launch(contract, launch, signing_digest=DIGEST, lifecycle_digest=DIGEST)
    assert session.admission["platform"] == "ios-simulator"
    session.revoke()


def test_identity_restart_generation_two_is_restore_only():
    first = next(plan for plan in _plans(_launch_identity("ios")) if plan["caseId"] == "identity-restart")
    assert {step["operation"] for step in first["steps"]} >= {"restart", "input-otp"}
    successor = {**_launch_identity("ios"), "generation": 2, "sessionId": "fresh-session",
                 "observationBinding": DIGEST, "launchAttemptId": "fresh-attempt"}
    second = next(plan for plan in _plans(successor) if plan["caseId"] == "identity-restart")
    assert [step["operation"] for step in second["steps"]] == ["visible"]
    assert not any(step.get("operation") in {"restart", "input-otp"} for step in second["steps"])


def test_supervised_restart_page_does_not_consume_relay(tmp_path, monkeypatch):
    launch = {**_launch_identity("android"), "generation": 1, "sessionId": "s", "observationBinding": DIGEST}
    plan = next(plan for plan in _plans(launch) if plan["caseId"] == "identity-restart")
    calls = []
    monkeypatch.setattr(pages, "_relay_runtime", lambda **_: calls.append("relay"))
    def native(command, *, cwd, env, timeout_seconds, log_path):
        log_path.write_text("OK (1 test)\nINSTRUMENTATION_CODE: -1\n" + _native_marker(plan, launch))
        return {"exitCode": 0, "command": command}
    monkeypatch.setattr(pages, "run_command", native)
    monkeypatch.setattr(pages, "native_page_screenshot", lambda *_: SCREENSHOT)
    evidence, result = pages._execute_native_page(
        plan=plan, launch=launch, context={"host": tmp_path, "environment": {}, "adb": "/sealed/adb"},
        case_dir=tmp_path, consume_relay=False)
    assert calls == []
    assert "launcherComparison" not in result
    assert evidence["caseId"] == "identity-restart"


def test_death_probes_are_distinct_and_readback_error_is_not_death():
    from quwoquan_ops.cli.commands.app_preflight_uat_process import (
        confirm_canonical_app_process_absent,
        confirm_host_process_table_absent,
        observe_canonical_app_process_id,
    )
    launch = {**_launch_identity("ios"), "canonicalProcessId": 4312}

    def empty(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "   8  -  other.service\n", "")

    with pytest.raises(ValueError, match="is not running"):
        observe_canonical_app_process_id(
            platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"], runner=empty)
    assert confirm_canonical_app_process_absent(
        platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"],
        expected_pid=4312, runner=empty) is True

    def two(command, **_kwargs):
        line = "  {pid}      -  UIKitApplication:" + launch["applicationId"] + "[cafe][rb-legacy]\n"
        return subprocess.CompletedProcess(command, 0, line.format(pid=4312) + line.format(pid=4313), "")

    with pytest.raises(ValueError, match="one launchd process"):
        observe_canonical_app_process_id(
            platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"], runner=two)
    with pytest.raises(ValueError, match="teardown_pid_alive"):
        confirm_canonical_app_process_absent(
            platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"],
            expected_pid=4312, runner=two)

    def unreadable(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "denied")

    with pytest.raises(ValueError, match="unreadable"):
        observe_canonical_app_process_id(
            platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"], runner=unreadable)
    with pytest.raises(ValueError, match="teardown_pid_alive"):
        confirm_canonical_app_process_absent(
            platform="ios", device_id=launch["deviceId"], application_id=launch["applicationId"],
            expected_pid=4312, runner=unreadable)

    def ps_unreadable(command, **_kwargs):
        return subprocess.CompletedProcess(command, 2, "", "ps: failed")

    with pytest.raises(ValueError, match="unreadable"):
        confirm_host_process_table_absent(process_id=4312, runner=ps_unreadable)
    assert confirm_host_process_table_absent(
        process_id=4312, runner=lambda command, **_: subprocess.CompletedProcess(command, 1, "", "")) is True
    assert confirm_host_process_table_absent(
        process_id=4312, runner=lambda command, **_: subprocess.CompletedProcess(command, 0, "4312\n", "")) is False

    class BrokenBroker:
        def peer_absent(self):
            raise ConnectionError("container unreadable")

    with pytest.raises(ValueError, match="broker readback failed"):
        pages._broker_peer_absent(transport=BrokenBroker())
    with pytest.raises(ValueError, match="broker death probe is unavailable"):
        pages._broker_peer_absent(transport=object())
    assert pages._broker_peer_absent(transport=type("Gone", (), {"peer_absent": lambda self: True})()) is True


def test_relay_runtime_rejects_missing_producer_session_before_admission():
    launch = _launch_identity("ios")
    plan = next(plan for plan in _plans(launch) if plan["caseId"] == "login-success")
    with pytest.raises(ValueError, match="APP.UAT.relay_scope_mismatch"):
        pages._relay_runtime(plan=plan, launch=launch, context={"relayFactory": lambda **_: None}, terminal={})


@pytest.mark.parametrize("second_status", ["passed", "failed"])
def test_restart_supervision_cannot_promote_failed_successor(monkeypatch, second_status):
    from types import SimpleNamespace
    from quwoquan_ops.cli.commands import app_preflight_uat_offline_native_contract as native
    launch = {**_launch_identity("ios"), "generation": 1}
    first_plan = next(plan for plan in _plans(launch) if plan["caseId"] == "identity-restart")
    first = native.admit_launch(first_plan["nativeContract"], launch, signing_digest=DIGEST, lifecycle_digest=DIGEST)
    successor = {**launch, "generation": 2, "caseId": "identity-restart", "launchAttemptId": "second-attempt",
                 "canonicalProcessId": 9001, "continuityDigest": DIGEST}
    second_plan = next(plan for plan in _plans(successor) if plan["caseId"] == "identity-restart")
    second = native.admit_launch(second_plan["nativeContract"], successor, signing_digest=DIGEST, lifecycle_digest=DIGEST)
    def relay(**kwargs):
        session = kwargs["session"]
        session.consumed = True
        session.terminal_digest = DIGEST
        session.revoke()
        return {"status": "passed" if session is first else second_status, "comparisonDigest": DIGEST}
    monkeypatch.setattr(native, "execute_launcher_relay", relay)
    arguments = dict(attempt1_session=first, attempt1_plan=first_plan, attempt1_terminal=native.TerminalReference({}),
        attempt1_transport=SimpleNamespace(disconnected=True), expected_attempt1={}, terminate_aut=lambda _: None,
        death_readbacks=[lambda: True] * 3, launch_next=lambda *_: successor,
        prepare_attempt2=lambda _: (second_plan, second, native.TerminalReference({}), SimpleNamespace()),
        expected_attempt2={}, continuity_digest=DIGEST)
    if second_status == "passed":
        result = native.supervise_identity_restart(**arguments)
        assert result["attempt2"]["status"] == "passed" and result["teardown"]["state"] == "terminated"
    else:
        with pytest.raises(ValueError, match="APP.UAT.restart_identity_mismatch"):
            native.supervise_identity_restart(**arguments)


def test_relaunched_case_emits_its_own_exact_attempt_binding(tmp_path, monkeypatch):
    launch, candidate, projection, _ = _live_boundaries(monkeypatch, tmp_path)
    collected = []
    def relaunch(case, generation):
        value = {**launch, "launchAttemptId": case + "-attempt", "canonicalProcessId": 9000 + len(collected)}
        path = tmp_path / (case + "-attempt.json")
        payload = {"attemptId": value["launchAttemptId"]}
        pages.write_create_once_json(path, payload)
        value.update(launchAttemptRef=str(path), launchAttemptDigest=pages.document_digest(payload))
        return value
    def collect(**kwargs):
        if len(collected) == 2:
            raise ValueError("APP.UAT.relay_peer_rejected: stop at boundary")
        refs = kwargs["receipt"]
        bound = json.loads((tmp_path / refs["launchBindingRef"]["ref"]).read_bytes())
        target = read_target_uat_binding(tmp_path / refs["targetUatBindingRefs"]["alpha-local"]["ref"])
        attempt = json.loads((tmp_path / target["launchAttempt"]["ref"]).read_bytes())
        assert bound["launchAttemptId"] == kwargs["plan"]["launchAttemptId"] == attempt["attemptId"]
        collected.append(refs["targetUatBindingRefs"]["alpha-local"])
        return {"ref": "contract-evidence.json", "digest": DIGEST}, "2026-09-16T00:00:00+00:00"
    monkeypatch.setattr(pages, "_collect_offline_page_evidence", collect)
    receipt = pages.execute_offline_page_cases(args=argparse.Namespace(platform="android", device_id=launch["deviceId"]),
        candidate=candidate, launch=launch, projection=projection, report_dir=tmp_path / "pages-run",
        output_root=tmp_path, launch_case=relaunch)
    assert receipt["firstBlocker"] == "APP.UAT.relay_peer_rejected", receipt
    assert len(collected) == 2 and collected[0] != collected[1]
    for row, binding in zip(receipt["pageResultRefs"], collected):
        raw = json.loads((tmp_path / row["result"]["ref"]).read_bytes())
        assert raw["targetUatBindingDigest"] == binding["digest"]


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
    monkeypatch.setattr(offline, "_launch", lambda *_, **__: binding)
    monkeypatch.setattr(offline, "_verify_source", lambda *_: None)
    receipt = offline.run_offline_app_content_uat(args=argparse.Namespace(dry_run=False, platform="android" if platform == "android" else "ios-simulator", device_id=binding["deviceId"]),
        report_dir=tmp_path / "uat", output_root=tmp_path, issues=[])
    assert receipt["status"] == "gate_block", receipt
    assert receipt["firstBlocker"] == "APP.UAT.relay_peer_rejected"
    # fake native command不注入runtime_verified platform adapter，必须在首个GWT-008 case fail closed。
    supported = sum("nativeContract" not in plan and not plan["executionBlocker"] for plan in _plans(binding))
    assert len(commands) == supported  # 缺 relay admission 必须在首个 GWT-008 UI 命令之前阻断。
    assert len(receipt["rawResultRefs"]["alpha-local"]) == supported
    assert len(receipt["rawResultDigests"]["alpha-local"]) == supported
    assert len(receipt["pageResultRefs"]) == supported
    assert receipt.get("blockedCases") in ({}, [], None) or not receipt["blockedCases"]
    results = [json.loads((tmp_path / ref["ref"]).read_bytes()) for ref in receipt["rawResultRefs"]["alpha-local"]]
    typed_bindings = []
    for row in receipt["pageResultRefs"]:
        evidence = json.loads((tmp_path / row["evidence"]["ref"]).read_bytes())
        typed_bindings.append(read_target_uat_binding(tmp_path / evidence["targetUatBinding"]["ref"]))
    with pytest.raises(ValueError, match="incomplete"):
        pages.validate_offline_page_coverage(results=results, bindings=typed_bindings, candidate=candidate, platforms=[platform])
    if platform == "ios":
        assert not list(tmp_path.glob("*.external-aut.*.xctestrun"))
    with pytest.raises(ValueError, match="incomplete"):
        pages.validate_offline_page_coverage(results=results, bindings=typed_bindings, candidate=candidate)
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


def test_candidate_source_allows_live_worktree_dirt_when_git_objects_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def check_output(command, **_):
        commands.append(list(command))
        if command[1:3] == ["rev-parse", "--verify"]:
            return "b" * 40
        raise AssertionError(command)

    def run(*_, **__):
        raise AssertionError("live worktree must not be inspected")

    monkeypatch.setattr(offline.subprocess, "check_output", check_output)
    monkeypatch.setattr(offline.subprocess, "run", run)
    offline._verify_source({"commit": "a" * 40, "tree": "b" * 40}, ROOT)
    assert commands == [["git", "rev-parse", "--verify", "a" * 40 + "^{tree}"]]


def test_candidate_source_rejects_tree_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        offline.subprocess,
        "check_output",
        lambda command, **_: "c" * 40,
    )
    with pytest.raises(ValueError, match="candidate tree mismatch"):
        offline._verify_source({"commit": "a" * 40, "tree": "b" * 40}, ROOT)


def test_candidate_export_copies_commit_bytes_not_live_dirt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owned.txt").write_text("committed\n")
    subprocess.run(["git", "init", "-b", "dev1.0"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "add", "owned.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "owned.txt").write_text("live-dirty\n")
    (repo / "foreign.txt").write_text("untracked\n")
    checkout = tmp_path / "checkout"
    offline._export_candidate_tree(
        commit=commit, repository=repo, destination=checkout, roots=("owned.txt",)
    )
    assert (checkout / "owned.txt").read_text() == "committed\n"
    assert not (checkout / "foreign.txt").exists()


def test_first_typed_launch_error_is_not_replaced(tmp_path: Path) -> None:
    receipt = offline.run_offline_app_content_uat(args=argparse.Namespace(dry_run=False, platform="android", device_id="emulator-test"),
        report_dir=tmp_path, output_root=tmp_path, issues=["APP.DEPENDENCY.bundle_stale: field=source"])
    assert receipt["firstBlocker"] == "APP.DEPENDENCY.bundle_stale"


def test_projection_seal_log_is_not_masked_as_receipt_invalid() -> None:
    log = (
        "ValueError: App build projection derived output rejected by policy: "
        "quwoquan_app/test_host/patrol/.dart_tool\n"
        "APP.LAUNCH.receipt_invalid: partial build projection seal identity\n"
    )
    assert offline.first_typed_blocker(log) == "APP.LAUNCH.projection_seal_rejected"
    escaped = "App build projection symlink escapes build root: quwoquan_app/.dart_tool/qwq_ios_cocoapods_dependency/production/user-home/.config/swiftpm/configuration"
    assert offline.first_typed_blocker(escaped) == "APP.LAUNCH.projection_seal_rejected"


def test_diagnostic_compile_launch_uses_selected_case_not_login_success(monkeypatch, tmp_path):
    launches: list[str] = []

    def capture_launch(*args, **kwargs):
        launches.append(str(kwargs.get("case_id") or "missing"))
        return {"launchAttemptId": "attempt-1"}

    monkeypatch.setattr(offline, "_candidate", lambda *args: {
        "candidateId": "sha256:" + "a" * 64, "commit": "c" * 40, "tree": "d" * 40,
    })
    monkeypatch.setattr(offline, "_prepare_launch", lambda *args: ({}, {}))
    monkeypatch.setattr(offline, "_launch", capture_launch)
    monkeypatch.setattr(offline, "_verify_source", lambda *args: None)
    monkeypatch.setattr(
        "quwoquan_ops.cli.commands.app_preflight_uat_offline_pages.execute_offline_page_cases",
        lambda **kwargs: {"status": "diagnostic_passed", "exitCode": 0},
    )
    args = argparse.Namespace(
        dry_run=False, platform="ios-simulator", device_id="E0C937A3-F805-4E04-A469-B7706AB79F0A",
        offline_cases=["default-entry"], isolated_rehearsal=False, rehearsal_instance_id="",
    )
    offline.run_offline_app_content_uat(args=args, report_dir=tmp_path, output_root=tmp_path, issues=[])
    assert launches == ["default-entry"]


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
    assert android.index('matches("visible|tap|scroll|seek|playback|back|reveal|tab-roundtrip|input-otp|wait|restart|observe")') < android.index("int before = requireSingleRunningPid(automation, target);")
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


def test_local_write_requires_action_and_same_run_readback() -> None:
    plan = next(plan for plan in _plans(_launch_identity()) if plan["caseId"] == "local-write")
    assert [step["operation"] for step in plan["steps"]][-2:] == ["tap", "visible"]
    assert plan["steps"][-2]["selector"] == plan["steps"][-1]["selector"]
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

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
def test_gwt008_native_contract_rejects_cross_aut_attempt_parameter_drift_and_sensitive_logs() -> None:
    from quwoquan_ops.cli.commands import app_preflight_uat_offline_native_contract as native
    launch = {**_launch_identity(), "snapshotDigest": DIGEST}
    contract = native.build_native_case_contract("login-success", launch)
    for field, value in (("applicationId", "foreign.aut"), ("launchAttemptId", "foreign-attempt")):
        changed = {**contract, field: value}
        changed["contractDigest"] = native._digest({k: v for k, v in changed.items() if k != "contractDigest"})
        with pytest.raises(ValueError, match="cross AUT/attempt"):
            native.validate_native_case_contract(changed, launch=launch)
    changed = {**contract, "runnerTimeoutSeconds": 121}
    with pytest.raises(ValueError, match="drifted"):
        native.validate_native_case_contract(changed, launch=launch)
    actual = {
        "schema": "quwoquan_ops.alpha_gwt008_native_observation.v1", "caseId": "login-success",
        "contractDigest": contract["contractDigest"], "applicationId": launch["applicationId"], "deviceId": launch["deviceId"],
        "candidateDigest": DIGEST, "artifactDigest": DIGEST, "launchAttemptBefore": launch["launchAttemptId"],
        "processIdBefore": launch["canonicalProcessId"], "launchAttemptAfter": launch["launchAttemptId"],
        "processIdAfter": launch["canonicalProcessId"],
        "observations": [{"source": "ui-control", "status": "observed", "detail": "unique-editable-control"},
                         {"source": "rehearsal-session-readback", "status": "observed", "detail": "session-established"}],
        "logSummary": "input-redacted",
    }
    native.validate_actual_observation(actual, contract=contract)
    actual["logSummary"] = "otp=123456"
    with pytest.raises(ValueError, match="not redacted"):
        native.validate_actual_observation(actual, contract=contract)


def test_gwt008_expiry_and_restart_contracts_preserve_real_boundaries() -> None:
    from quwoquan_ops.cli.commands import app_preflight_uat_offline_native_contract as native
    launch = {**_launch_identity(), "snapshotDigest": DIGEST}
    expiry = native.build_native_case_contract("otp-expiry", launch)
    assert expiry["minimumObservedWaitSeconds"] == 300 and expiry["runnerTimeoutSeconds"] >= 330
    changed = {**expiry, "minimumObservedWaitSeconds": 299}
    changed["contractDigest"] = native._digest({k: v for k, v in changed.items() if k != "contractDigest"})
    with pytest.raises(ValueError, match="wait budget"):
        native.validate_native_case_contract(changed, launch=launch)
    restart = native.build_native_case_contract("identity-restart", launch)
    assert restart["restartPolicy"] == "cold-restart-new-launch-attempt-and-pid"
