"""Alpha 合入不得用日志、单平台或服务回读代替离线页面矩阵。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
"""

import copy
import json
import base64
import hashlib
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands.app_preflight_uat_offline import OFFLINE_REQUIRED_CASES, OFFLINE_SPEC_REF
from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import (
    offline_case_outcome, validate_native_page_result, validate_offline_page_coverage,
)
from quwoquan_ops.cli.lib.target_uat_binding import build_offline_target_uat_binding, target_uat_binding_digest

_DIGEST = "sha256:" + "a" * 64
_CANDIDATE = {"candidateId": _DIGEST, "commit": "b" * 40, "tree": "c" * 40}
_TIME = "2026-09-10T02:00:00Z"
_SCREENSHOT = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9o0AAAAASUVORK5CYII=")
_SCREENSHOT_DIGEST = "sha256:" + hashlib.sha256(_SCREENSHOT).hexdigest()


def _matrix():
    results, bindings = [], []
    for platform in ("android", "ios"):
        device_class = "emulator" if platform == "android" else "simulator"
        binding = build_offline_target_uat_binding(
            candidate_digest=_DIGEST, commit_sha=_CANDIDATE["commit"], tree_sha=_CANDIDATE["tree"],
            runtime_config_digest=_DIGEST, snapshot={"ref": "snapshot/manifest.json", "digest": _DIGEST},
            launch_attempt={"ref": f"attempt/{platform}.json", "digest": _DIGEST},
            artifact={"class": "production_behavior", "digest": _DIGEST,
                      "applicationId": "com.example.app", "buildMode": "debug", "buildProfile": "nonprod"},
            platform=platform, device={"identity": platform + "-device", "class": device_class, "registered": False},
            runner={"identity": "app-content-uat", "sourcePath": "quwoquan_ops/cli/commands/app_preflight_uat_offline_pages.py",
                    "digest": _DIGEST, "registered": False}, created_at=_TIME,
        )
        bindings.append(binding)
        for case in OFFLINE_REQUIRED_CASES:
            results.append({
                "objectId": "app_runtime", "specRef": OFFLINE_SPEC_REF, "caseId": case,
                "producer": "app", "layer": "user_acceptance", "status": "passed",
                "target": {"kind": "page", "id": "home"}, "commitSha": _CANDIDATE["commit"],
                "contractGraphSourceHash": "d" * 64, "deploymentTarget": "alpha-local", "environment": "alpha",
                "contentSource": "bundled_snapshot", "candidateDigest": _DIGEST,
                "targetUatBindingDigest": target_uat_binding_digest(binding),
                "entrySurface": "direct_or_object_route", "carrier": "homepage", "platform": platform,
                "deviceClass": device_class, "deviceRegistered": False, "deviceIdentity": platform + "-device",
                "startedAt": _TIME, "completedAt": _TIME, "runnerIdentity": "app-content-uat",
                "artifactSha256": "a" * 64, "artifactPath": f"cases/{platform}/{case}.json",
                "uatProfile": "rehearsal", "nonPromotable": True, "artifactClass": "production_behavior",
                "physicalDevice": False, "observedOutcome": offline_case_outcome(case),
            })
    return results, bindings


def test_dual_platform_required_matrix_passes_only_with_all_exact_cases():
    results, bindings = _matrix()
    validate_offline_page_coverage(results=results, bindings=bindings, candidate=_CANDIDATE)
    with pytest.raises(ValueError, match="incomplete"):
        validate_offline_page_coverage(results=results[:-1], bindings=bindings, candidate=_CANDIDATE)
    with pytest.raises(ValueError, match="incomplete"):
        validate_offline_page_coverage(results=results[:len(OFFLINE_REQUIRED_CASES)], bindings=bindings, candidate=_CANDIDATE)
    with pytest.raises(ValueError, match="duplicated"):
        validate_offline_page_coverage(results=results + results[:1], bindings=bindings, candidate=_CANDIDATE)


@pytest.mark.parametrize("field,value", [
    ("commitSha", "e" * 40), ("candidateDigest", "sha256:" + "f" * 64),
    ("artifactSha256", "0" * 64), ("deviceIdentity", "another-device"), ("observedOutcome", "empty"),
])
def test_matrix_rejects_cross_candidate_artifact_device_and_outcome(field, value):
    results, bindings = _matrix()
    results[0][field] = value
    with pytest.raises(ValueError):
        validate_offline_page_coverage(results=results, bindings=bindings, candidate=_CANDIDATE)


def test_native_terminal_requires_exact_process_plan_and_step_coverage():
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import document_digest
    plan = {"schema": "quwoquan_ops.offline_page_case.v1", "caseId": "default-entry",
            "steps": [{"operation": "visible", "selector": "qwq.surface.home"}]}
    launch = {"platform": "android", "applicationId": "com.example.app", "canonicalProcessId": 123,
              "candidateDigest": _DIGEST, "artifactDigest": _DIGEST, "deviceId": "android-device", "launchAttemptId": "android"}
    plan.update(launch)
    plan["planDigest"] = document_digest(plan)
    terminal = {"schema": "quwoquan_ops.offline_native_page_result.v1", "caseId": "default-entry",
                **{key: launch[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
                "screenshotDigest": _SCREENSHOT_DIGEST, "screenshotByteLength": len(_SCREENSHOT),
                "planDigest": plan["planDigest"], "platform": "android", "applicationId": "com.example.app",
                "processIdBefore": 123, "processIdAfter": 123, "status": "passed",
                "observations": [{"operation": "visible", "selector": "qwq.surface.home", "observed": "qwq.surface.home 首页"}]}
    encode = lambda value: "QWQ_OFFLINE_PAGE " + json.dumps(value)
    assert validate_native_page_result(encode(terminal), plan=plan, launch=launch) == terminal
    for field, value in (("processIdAfter", 124), ("planDigest", "stale"), ("observations", []), ("status", "failed")):
        changed = {**terminal, field: value}
        with pytest.raises(ValueError):
            validate_native_page_result(encode(changed), plan=plan, launch=launch)
    with pytest.raises(ValueError, match="exactly one"):
        validate_native_page_result(encode(terminal) + "\n" + encode(terminal), plan=plan, launch=launch)


def _receipt_matrix(root):
    from quwoquan_ops.cli.integration_run import exact_file_digest
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import document_digest, build_offline_page_plans

    app_root = Path(__file__).resolve().parents[4] / "quwoquan_app"
    snapshot = json.loads((app_root / "assets/content/alpha/manifest.json").read_bytes())

    def write(ref, value):
        path = root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True) + "\n").encode())
        return {"ref": ref, "digest": exact_file_digest(path)}

    results, bindings = _matrix()
    receipts = {}
    for binding in bindings:
        platform = binding["platform"]
        binding["snapshot"] = write("snapshot.json", snapshot)
        attempt = {"attemptId": platform, "status": "passed"}
        binding["launchAttempt"] = write(f"{platform}/attempt.json", attempt)
        binding.pop("bindingId")
        binding["bindingId"] = document_digest({k: v for k, v in binding.items() if k != "createdAt"})
        binding_ref = write(f"{platform}/binding.json", binding)
        launch = {"candidateDigest": _DIGEST, "artifactDigest": _DIGEST, "deviceId": platform + "-device",
                  "platform": platform, "applicationId": "com.example.app", "canonicalProcessId": 123, "launchAttemptId": platform}
        launch.update(sourceGitSha=_CANDIDATE["commit"], runtimeConfigPackageDigest=_DIGEST,
                      launchAttemptDigest=document_digest(attempt))
        launch_ref = write(f"{platform}/launch.json", launch)
        driver_ref = write(f"{platform}/driver.json", {"driver": "native"})
        from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import build_tested_app_artifact_binding
        aut = build_tested_app_artifact_binding(platform=platform, device_id=platform + "-device",
            command_application_id="com.example.app", build_application_id="com.example.app",
            build_artifact_path="build/app", build_artifact_digest=_DIGEST, installed_application_id="com.example.app",
            installed_artifact_digest=_DIGEST, installed_readback_method="device-readback", installed_locator_digest=_DIGEST,
            host_source={"root": "quwoquan_app/test_host/patrol", "rootIdentityDigest": _DIGEST, "sourceDigest": _DIGEST, "sourceFileCount": 1})
        plans = {plan["caseId"]: plan for plan in build_offline_page_plans(snapshot=snapshot, app_root=app_root, launch=launch)}
        raw_refs, raw_digests, pages = [], [], []
        for result in results:
            if result["platform"] != platform:
                continue
            result["targetUatBindingDigest"] = target_uat_binding_digest(binding)
            case = result["caseId"]
            plan = plans[case]
            result["target"]["id"] = plan["route"]
            result["carrier"] = plan["carrier"]
            observations = []
            for step in plan["steps"]:
                observed = step["selector"].removeprefix("text-prefix:")
                if step["operation"] == "playback":
                    observed += " 2:07 / 2:07"
                elif step["operation"] == "seek":
                    observed += " 0:30 / 2:07"
                observations.append({**step, "observed": observed})
            native = {"schema": "quwoquan_ops.offline_native_page_result.v1", "caseId": case, "planDigest": plan["planDigest"],
                      **{key: launch[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
                      "screenshotDigest": _SCREENSHOT_DIGEST, "screenshotByteLength": len(_SCREENSHOT),
                      "platform": platform, "applicationId": "com.example.app", "status": "passed",
                      "processIdBefore": 123, "processIdAfter": 123,
                      "observations": observations}
            prefix = f"{platform}/{case}"
            execution = {"plan": write(prefix + "/plan.json", plan), "nativeResult": write(prefix + "/native.json", native),
                         "launchBinding": launch_ref, "targetUatBinding": binding_ref,
                         "nativeDriverBinding": driver_ref,
                         "autBefore": aut, "autAfter": aut, "command": {"exitCode": 0},
                         "screenshot": write(prefix + "/screenshot.png", _SCREENSHOT),
                         "log": write(prefix + "/native.log", ("QWQ_OFFLINE_SCREENSHOT " + plan["planDigest"] + " 0 "
                            + base64.b64encode(_SCREENSHOT).decode() + "\nQWQ_OFFLINE_PAGE " + json.dumps(native)).encode())}
            evidence = write(result["artifactPath"], execution)
            raw_ref = write(f"{platform}/raw/{case}.json", result)
            slot = platform + ":" + case
            raw_refs.append({"slotId": slot, "ref": raw_ref["ref"]})
            raw_digests.append({"slotId": slot, "digest": raw_ref["digest"]})
            pages.append({"slotId": slot, "result": raw_ref, "evidence": evidence})
        receipts[platform] = write(f"{platform}/receipt.json", {
            "schema": "quwoquan_ops.app_content_uat_receipt", "profile": "rehearsal", "status": "passed", "exitCode": 0,
            "targets": ["alpha-local"], "contentSource": "bundled_snapshot", "nonPromotable": True,
            "rawResultRefs": {"alpha-local": raw_refs}, "rawResultDigests": {"alpha-local": raw_digests},
            "pageResultRefs": pages, "targetUatBindingRefs": {"alpha-local": binding_ref},
            "launchBindingRef": launch_ref, "nativeDriverBindingRef": driver_ref,
        })
    return receipts, write


def test_acceptance_consumes_actual_dual_platform_raw_closure(tmp_path):
    from quwoquan_ops.cli.lib.integration_app_launch import offline_receipt_evidence
    receipts, _ = _receipt_matrix(tmp_path)
    evidence = offline_receipt_evidence(root=tmp_path, receipts=receipts, candidate=_CANDIDATE,
                                        devices={"android": "android-device", "ios": "ios-device"})
    assert len(evidence["cases"]) == 26
    assert len(evidence["bindings"]) == 2
    assert all(result["nonPromotable"] for result in evidence["results"])
    assert not any("packageDigest" in result for result in evidence["results"])
    for result in evidence["results"]:
        if result["caseId"] in {"login-unavailable", "private-unavailable"}:
            assert result["target"]["id"] == "/login"
        elif result["caseId"] == "write-unavailable":
            assert result["target"]["id"] == "/"
    for platform in ("android", "ios"):
        plan = json.loads((tmp_path / platform / "private-unavailable/plan.json").read_bytes())
        assert plan["steps"][-1]["selector"] == "capability-unavailable:account_authentication:openChat"
        plan = json.loads((tmp_path / platform / "write-unavailable/plan.json").read_bytes())
        assert plan["steps"][-2]["selector"].startswith("post-like:")
        assert plan["steps"][-1]["selector"] == "capability-unavailable:like"


@pytest.mark.parametrize("damage", ["planned", "dry-run", "failed", "raw-missing", "raw-drift", "device", "execution",
                                    "screenshot-rehashed", "native-screenshot-absent"])
def test_acceptance_rejects_nonexecuted_incomplete_or_drifted_offline_receipts(tmp_path, damage):
    from quwoquan_ops.cli.lib.integration_app_launch import offline_receipt_evidence
    receipts, write = _receipt_matrix(tmp_path)
    exact = receipts["android"]
    receipt = json.loads((tmp_path / exact["ref"]).read_bytes())
    devices = {"android": "android-device", "ios": "ios-device"}
    if damage == "planned":
        receipt["status"] = "planned"
    elif damage == "dry-run":
        receipt["dryRun"] = True
    elif damage == "failed":
        receipt["exitCode"] = 2
    elif damage == "raw-missing":
        receipt["rawResultRefs"]["alpha-local"].pop()
    elif damage == "raw-drift":
        path = tmp_path / receipt["rawResultRefs"]["alpha-local"][0]["ref"]
        path.write_bytes(path.read_bytes() + b" ")
    elif damage == "device":
        devices["android"] = "unrelated-emulator"
    elif damage in {"screenshot-rehashed", "native-screenshot-absent"}:
        row = receipt["pageResultRefs"][0]["evidence"]
        execution = json.loads((tmp_path / row["ref"]).read_bytes())
        if damage == "screenshot-rehashed":
            execution["screenshot"] = write(execution["screenshot"]["ref"], _SCREENSHOT + b"different screenshot bytes")
        else:
            log = (tmp_path / execution["log"]["ref"]).read_bytes().split(b"\n", 1)[1]
            execution["log"] = write(execution["log"]["ref"], log)
        receipt["pageResultRefs"][0]["evidence"] = write(row["ref"], execution)
    else:
        row = receipt["pageResultRefs"][0]["evidence"]
        receipt["pageResultRefs"][0]["evidence"] = write(row["ref"], {"status": "planned"})
    receipts["android"] = write(exact["ref"], receipt)
    with pytest.raises((ValueError, KeyError)):
        offline_receipt_evidence(root=tmp_path, receipts=receipts, candidate=_CANDIDATE, devices=devices)


def test_integration_offline_orchestration_forwards_exact_candidate_and_devices(tmp_path, monkeypatch):
    from argparse import Namespace
    from quwoquan_ops.cli import integration_run as subject
    receipts, _ = _receipt_matrix(tmp_path)
    commands = []
    def stackctl(*args, **kwargs):
        commands.append(args)
        platform = "android" if "android" in args else "ios"
        return subject.StackctlResult("app-content-uat", {"exitCode": 0, "reportDir": str(tmp_path / platform)}, "")
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "_store", lambda: tmp_path / "store")
    monkeypatch.setattr(subject, "_stackctl", stackctl)
    candidate_ref = {"ref": "candidates/exact.json", "digest": _DIGEST}
    axis = subject._alpha_offline_pages(candidate=_CANDIDATE, candidate_ref=candidate_ref,
        args=Namespace(android_device_id="android-device", ios_device_id="ios-device"), run_dir=tmp_path, phases=subject.Phases())
    assert [command[command.index("--device-id") + 1] for command in commands] == ["android-device", "ios-device"]
    assert all(command[command.index("--candidate") + 1] == "candidates/exact.json=" + _DIGEST for command in commands)
    assert all(command[0] == "app-content-uat" and "--dry-run" not in command for command in commands)
    refs = subject._validate_offline_axis(store=tmp_path / "store", axis=axis, candidate=_CANDIDATE)
    assert len(axis["cases"]) == 26 and refs
    with pytest.raises(subject.IntegrationRunError):
        subject._validate_offline_axis(store=tmp_path / "store", axis=axis, candidate={**_CANDIDATE, "tree": "f" * 40})
    store = tmp_path / "store"
    runtime = subject._write_canonical(store / "runtime.json", {"source": {"offlinePages": axis}})
    fact = {"environment": "alpha", "runtimeIdentity": runtime, "caseResultRefs": axis["cases"]}
    with pytest.raises(subject.IntegrationRunError, match="cannot replace required Alpha API"):
        subject._offline_fact_refs(store=store, fact=fact, candidate=_CANDIDATE)
    service = subject._write_canonical(store / "service.json", {
        "caseId": "content-readback:home-feed+video-book", "producer": "ops", "layer": "environment_acceptance",
        "status": "passed", "candidateDigest": _DIGEST, "commitSha": _CANDIDATE["commit"],
    })
    fact["caseResultRefs"] = [*axis["cases"], service]
    assert subject._offline_fact_refs(store=store, fact=fact, candidate=_CANDIDATE) == refs
    (store / axis["cases"][0]["ref"]).write_bytes(b"{}")
    with pytest.raises(subject.IntegrationRunError, match="drifted"):
        subject._offline_fact_refs(store=store, fact=fact, candidate=_CANDIDATE)


def test_make_and_parser_pass_explicit_candidate_and_two_devices():
    from quwoquan_ops.cli import integration_run as subject
    args = subject._parser().parse_args(["--mode", "acceptance", "--candidate-ref", "candidate.json=" + _DIGEST,
                                        "--android-device-id", "emulator-1", "--ios-device-id", "SIM-1"])
    assert args.android_device_id == "emulator-1" and args.ios_device_id == "SIM-1"
    makefile = (subject.ROOT / "Makefile").read_text()
    app_uat = makefile.split("\napp-uat:\n", 1)[1].split("\nstackctl-up:", 1)[0]
    assert '--candidate "$(CANDIDATE)"' in app_uat
    accept = makefile.split("\naccept:\n", 1)[1].split("\nintegrate:", 1)[0]
    for flag in ("--candidate-ref", "--android-device-id", "--ios-device-id", "--release-handoff-ref", "--rollback-release-attestation"):
        assert flag in accept


def test_existing_candidate_uses_exact_claim_without_reacquire(tmp_path, monkeypatch):
    from quwoquan_ops.cli import integration_run as subject
    from quwoquan_ops.ci.scoped_candidate import exact_digest
    _, write = _receipt_matrix(tmp_path)
    claim = {"paths": ["quwoquan_app/lib/main.dart"], "expectedParent": "0" * 40, "ownerIdentityRef": "owner-exact"}
    claim_ref = write("claims/claimed.json", claim)
    candidate = {"schema": subject._CANDIDATE_SCHEMA, **_CANDIDATE, **claim,
                 "claimRef": claim_ref["ref"], "claimDigest": claim_ref["digest"], "impactPlanDigest": _DIGEST}
    candidate["candidateId"] = exact_digest({k: v for k, v in candidate.items() if k != "candidateId"})
    exact = write("candidate.json", candidate)
    monkeypatch.setattr(subject, "_store", lambda: tmp_path)
    identity = {"commit": candidate["commit"], "tree": candidate["tree"], "parent": "0" * 40}
    ref, loaded = subject._existing_candidate(exact=exact["ref"] + "=" + exact["digest"], identity=identity, impact_plan_digest=_DIGEST)
    assert ref == exact and loaded == candidate
    with pytest.raises(subject.IntegrationRunError, match="drifted"):
        subject._existing_candidate(exact=exact["ref"] + "=" + exact["digest"], identity={**identity, "tree": "f" * 40}, impact_plan_digest=_DIGEST)


@pytest.mark.parametrize("created,generation", [(False, "existing"), (None, ""), (True, "new-generation")])
def test_environment_failure_cleans_only_owned_exact_generation(tmp_path, monkeypatch, created, generation):
    from argparse import Namespace
    from quwoquan_ops.cli import integration_run as subject
    commands = []
    prefix = tmp_path / "deploy/alpha-local"
    prefix.mkdir(parents=True)
    manifest = {"release": {}, "sourceRevision": _CANDIDATE["commit"]}
    (prefix / "manifest.json").write_text(json.dumps(manifest))
    (prefix / "active-runtime-candidate.json").write_text(json.dumps({"candidateDir": str(prefix), "baselineId": "baseline"}))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path / "deploy"))
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "_store", lambda: tmp_path / "store")
    monkeypatch.setattr(subject, "_acceptance_release_inputs", lambda args: {"release": {}})
    monkeypatch.setattr(subject, "_assert_package_identity", lambda **kwargs: None)
    monkeypatch.setattr(subject, "_package_with_dependency_recovery", lambda **kwargs: subject.StackctlResult("package", {}, ""))
    def stackctl(*args, **kwargs):
        commands.append(args)
        return subject.StackctlResult(args[0], {"exitCode": 2, "runtimeCreated": created,
            "runtimeReused": created is False, "instanceGeneration": generation}, "")
    monkeypatch.setattr(subject, "_stackctl", stackctl)
    summary = {"runId": "ownership", "environments": {}}
    with pytest.raises(subject.IntegrationRunError) as blocked:
        subject._run_environment(environment="alpha", profile="integration", candidate=_CANDIDATE,
            impact_plan_digest=_DIGEST, args=Namespace(workload="full"), run_dir=tmp_path / "run",
            phases=subject.Phases(), summary=summary)
    assert blocked.value.code == "INTEGRATION_RUN.UP_FAILED"
    down = [command for command in commands if command[0] == "down"]
    if created:
        assert down[0][down[0].index("--expected-generation") + 1] == generation
        assert "cleanupBlocker" in summary["environments"]["alpha"]
    else:
        assert not down


def test_missing_offline_matrix_blocks_before_any_service_mutation(tmp_path, monkeypatch):
    from argparse import Namespace
    from unittest.mock import Mock
    from quwoquan_ops.cli import integration_run as subject
    monkeypatch.setattr(subject, "_store", lambda: tmp_path)
    monkeypatch.setattr(subject, "_acceptance_release_inputs", lambda args: {})
    stackctl = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(subject, "_stackctl", stackctl)
    with pytest.raises(subject.IntegrationRunError, match="offline evidence axis"):
        subject._run_environment(environment="alpha", profile="integration", candidate=_CANDIDATE,
            impact_plan_digest=_DIGEST, args=Namespace(), run_dir=tmp_path, phases=subject.Phases(),
            summary={"environments": {}}, scopes=("app",))
    stackctl.assert_not_called()
