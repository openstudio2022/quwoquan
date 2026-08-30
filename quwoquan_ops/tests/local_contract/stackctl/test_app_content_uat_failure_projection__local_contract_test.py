"""App content UAT failure projection and evidence retention contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import app_preflight_uat as uat
from quwoquan_ops.cli.commands.app_preflight_uat_blockers import (
    APP_CONTENT_UAT_RECEIPT_INVALID,
    app_content_uat_cli_profile,
    app_content_uat_non_promotable,
    first_canonical_app_blocker,
)
from quwoquan_ops.cli.commands.app_preflight_uat_receipt import (
    build_app_content_uat_receipt,
    project_app_content_uat_raw_authority,
)
from quwoquan_ops.cli.lib.readiness_case_result import canonical_json_bytes
from quwoquan_ops.cli.commands.app_preflight_uat_platform import (
    IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER,
    IOS_DIRECT_FLUTTER_TIMEOUT_CLASS,
    _ios_direct_flutter_failure_projection,
    execute_canonical_platform_launch,
)


def test_preflight_first_cause_precedes_later_generic_run_code() -> None:
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[
            {
                "status": "gate_block",
                "exitCode": 2,
                "firstBlocker": "APP.LAUNCH.runtime_dependency_unavailable",
            }
        ],
        runs=[
            {
                "status": "failed",
                "exitCode": 2,
                "errorCode": "APP.LAUNCH.launch_failed",
            }
        ],
    )
    assert blocker == "APP.LAUNCH.runtime_dependency_unavailable"
    assert audit == {"source": "preflight", "index": 0, "fallback": False}


def test_canonical_dependency_blocker_is_accepted_without_patrol_union() -> None:
    import inspect

    from quwoquan_ops.cli.commands import app_preflight_uat_blockers as blockers

    source = inspect.getsource(blockers)
    assert "PATROL_DEPENDENCY_BLOCKERS" not in source
    assert "LAUNCH_BLOCKERS.union" not in source

    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[
            {
                "status": "gate_block",
                "exitCode": 2,
                "firstBlocker": "APP.DEPENDENCY.cocoapods_missing",
            }
        ],
        runs=[],
    )
    assert blocker == "APP.DEPENDENCY.cocoapods_missing"
    assert audit == {"source": "preflight", "index": 0, "fallback": False}

    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[
            {
                "status": "gate_block",
                "exitCode": 2,
                "firstBlocker": "APP.DEPENDENCY.sync_failed",
            }
        ],
        runs=[],
    )
    assert blocker == APP_CONTENT_UAT_RECEIPT_INVALID
    assert audit["fallback"] is True


def test_launch_attempt_first_cause_precedes_run_error_code(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt.json"
    attempt.write_text(
        json.dumps(
            {
                "schema": "quwoquan_app.app_launch_attempt",
                "invalid": "minimal fixture is intentionally unreadable",
            }
        ),
        encoding="utf-8",
    )
    run = {
        "status": "failed",
        "suite": "canonical-launch",
        "exitCode": 2,
        "launchAttemptEvidence": {
            "firstBlocker": "APP.LAUNCH.install_failed",
        },
        "launchAttemptRef": str(attempt),
        "errorCode": "APP.LAUNCH.launch_failed",
    }
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[],
        runs=[run],
    )
    assert blocker == "APP.LAUNCH.install_failed"
    assert audit["source"] == "launch_attempt"


def test_inner_page_typed_blocker_precedes_generic_run_code() -> None:
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[],
        runs=[
            {
                "status": "failed",
                "exitCode": 2,
                "errorCode": "APP.LAUNCH.launch_failed",
                "contractGraphDigest": "sha256:" + "a" * 64,
                "evidence": {
                    "typedBlocker": {
                        "errorCode": "CONTENT.SYSTEM.required_dependency_unavailable",
                        "sourceOperationId": "content.post.GetFeed",
                        "httpStatus": 503,
                    }
                },
            }
        ],
    )
    assert blocker == "CONTENT.SYSTEM.required_dependency_unavailable"
    assert audit["source"] == "page_evidence.typedBlocker"


def test_null_flutter_exit_without_native_launch_has_stable_timeout_class() -> None:
    long_issue = "dependency projection interrupted before native launch: " + "x" * 1200
    evidence = {
        "status": "failed",
        "reportPath": "/evidence/report.json",
        "flutterRunLog": "/evidence/flutter-run.log",
        "iosStartupLog": "/evidence/ios-startup.log",
        "flutterProcessGroupId": 61052,
        "flutterProcessGroupStoppedBySigint": False,
        "flutterRunExitCode": None,
        "nativeDidFinishLaunchingCount": 0,
        "runtimeIdentitySnapshots": [],
        "issues": [long_issue],
    }

    projection = _ios_direct_flutter_failure_projection(
        evidence=evidence,
        binding_issue="",
    )

    assert projection["firstBlocker"] == IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER
    assert projection["failureClass"] == IOS_DIRECT_FLUTTER_TIMEOUT_CLASS
    assert projection["issues"] == [long_issue]
    assert len(projection["issues"][0]) > 800
    assert projection["flutterRunLogRef"] == "/evidence/flutter-run.log"
    assert projection["iosStartupLogRef"] == "/evidence/ios-startup.log"


def test_literal_runner_failure_is_retained_and_selected_by_parent() -> None:
    long_issue = "projection stalled: " + "y" * 1200
    evidence = {
        "status": "failed",
        "environment": "alpha",
        "launchProvenance": "workspace_flutter_run",
        "runtimeConfigSupplyMode": "external_runtime_package",
        "consumerLeaseId": "sha256:" + "7" * 64,
        "reportPath": "/evidence/report.json",
        "flutterRunLog": "/evidence/flutter-run.log",
        "iosStartupLog": "/evidence/ios-startup.log",
        "flutterProcessGroupId": 61052,
        "flutterProcessGroupStoppedBySigint": False,
        "flutterRunExitCode": None,
        "nativeDidFinishLaunchingCount": 0,
        "runtimeIdentitySnapshots": [],
        "attempts": [],
        "issues": [long_issue],
    }

    class _Lock:
        def close(self) -> None:
            pass

    fake_stackctl = SimpleNamespace(
        acquire_patrol_execution_lock=lambda **_kwargs: _Lock(),
        run=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, json.dumps(evidence), ""
        ),
        _ios_direct_flutter_log_reader_retryable=lambda _evidence: False,
        _DATA_READINESS_DIGEST_RE=re.compile(r"^sha256:[0-9a-f]{64}$"),
    )
    issues: list[str] = []
    runs: list[dict[str, object]] = []
    passed = execute_canonical_platform_launch(
        args=SimpleNamespace(platform="ios-simulator", dry_run=False),
        stackctl=fake_stackctl,
        environment="alpha",
        target="alpha-local",
        device_id="SIMULATOR-UDID",
        launch_attempt_path=Path("/evidence/attempt.json"),
        launch_report_path=Path("/evidence/launch-report.json"),
        launch_control={
            "sourceCapsuleManifestRef": "/candidate/manifest.json",
            "controlRef": "/evidence/control.json",
            "controlDigest": "sha256:" + "1" * 64,
            "startupTerminalReceiptRef": "/evidence/startup-terminal.json",
        },
        canonical_output_root=Path("/evidence"),
        launch_app_root=Path("/candidate/quwoquan_app"),
        runtime_binding={},
        launch_projection={},
        build_projection_policy_id="ios-policy",
        report_dir=Path("/evidence/uat"),
        issues=issues,
        runs=runs,
        launch_bindings={},
        canonical_launch_command=lambda **_kwargs: ([], {}),
        launch_binding_reader=lambda **_kwargs: {},
        write_launch_control=lambda **_kwargs: {},
    )

    assert passed is False
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "failed"
    assert run["firstBlocker"] == IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER
    assert run["failureClass"] == IOS_DIRECT_FLUTTER_TIMEOUT_CLASS
    assert run["failureEvidence"]["issues"] == [long_issue]
    assert long_issue in issues[0]
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[],
        runs=runs,
    )
    assert blocker == IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER
    assert audit == {"source": "run.firstBlocker", "index": 0, "fallback": False}


def test_page_evidence_receipt_invalid_is_a_canonical_run_blocker() -> None:
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[],
        runs=[
            {
                "status": "failed",
                "exitCode": 2,
                "evidence": {
                    "typedBlocker": {
                        "errorCode": "APP.LAUNCH.receipt_invalid",
                    }
                },
            }
        ],
    )
    assert blocker == APP_CONTENT_UAT_RECEIPT_INVALID
    assert audit["source"] == "page_evidence.typedBlocker"
    assert audit["fallback"] is False


def test_unmapped_free_text_falls_back_without_losing_raw_audit_evidence() -> None:
    preflight = {
        "status": "gate_block",
        "exitCode": 2,
        "firstBlocker": "container exited: secret detail is not a stable code",
        "details": ["raw underlying cause remains readable here"],
    }
    blocker, audit = first_canonical_app_blocker(
        status="gate_block",
        preflights=[preflight],
        runs=[],
    )
    assert blocker == APP_CONTENT_UAT_RECEIPT_INVALID
    assert audit == {
        "source": "parent_receipt_validation",
        "fallback": True,
        "reason": "gate_block_without_canonical_child_code",
    }
    assert preflight["details"] == ["raw underlying cause remains readable here"]


def test_gate_block_receipt_wires_empty_raw_authority_projection(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "preflight-blocked"
    child_payload = {
        "schema": "quwoquan_ops.app_debug_preflight",
        "status": "gate_block",
        "exitCode": 2,
        "firstBlocker": "APP.LAUNCH.runtime_dependency_unavailable",
        "details": ["required runtime dependency is unavailable"],
    }

    with patch.object(
        stackctl,
        "command_app_debug_preflight",
        return_value=child_payload,
    ):
        result = stackctl._command_app_content_uat(
            argparse.Namespace(
                targets="alpha-local",
                platform="ios-simulator",
                device_id="SIMULATOR-UDID",
                dry_run=False,
                report_dir=str(report_dir),
            )
        )

    assert result["status"] == "gate_block"
    assert result["targetUatBindingRefs"] == {}
    assert result["rawResultRefs"] == {"alpha-local": []}
    assert result["rawResultDigests"] == {"alpha-local": []}
    assert result["rawCoverage"] == {
        "alpha-local": {"expected": 0, "present": 0, "missing": 0}
    }
    assert result["rawGaps"] == {
        "alpha-local": ["expected raw coverage is empty"]
    }


def test_prod_target_is_rejected_before_receipt_construction(tmp_path: Path) -> None:
    report_dir = tmp_path / "prod-rejected"

    with patch.object(
        stackctl,
        "command_app_debug_preflight",
        side_effect=AssertionError("unsupported target reached preflight"),
    ), patch(
        "quwoquan_ops.cli.commands.app_preflight_uat.build_app_content_uat_receipt",
        side_effect=AssertionError("unsupported target reached receipt construction"),
    ):
        result = stackctl._command_app_content_uat(
            argparse.Namespace(
                targets="prod-hosted",
                platform="ios-simulator",
                device_id="SIMULATOR-UDID",
                dry_run=False,
                report_dir=str(report_dir),
            )
        )

    assert result["status"] == "gate_block"
    assert result["exitCode"] == 2
    assert result["details"] == [
        "unsupported App content UAT targets: prod-hosted"
    ]
    assert not report_dir.exists()


def test_gate_block_parent_writes_nonempty_blocker_and_preserves_failed_subreport(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "uat-run"
    child_report = report_dir / "alpha-local/preflight/report.json"
    child_report.parent.mkdir(parents=True)
    child_payload = {
        "schema": "quwoquan_ops.app_debug_preflight",
        "status": "gate_block",
        "exitCode": 2,
        "firstBlocker": "APP.LAUNCH.runtime_dependency_unavailable",
        "details": ["required runtime dependency is unavailable"],
    }

    def preflight(_args: argparse.Namespace) -> dict[str, object]:
        stackctl.write_json(child_report, child_payload)
        return dict(child_payload)

    with patch.object(stackctl, "command_app_debug_preflight", side_effect=preflight):
        result = stackctl._command_app_content_uat(
            argparse.Namespace(
                targets="alpha-local",
                platform="ios-simulator",
                device_id="SIMULATOR-UDID",
                dry_run=False,
                report_dir=str(report_dir),
            )
        )

    assert result["status"] == "gate_block"
    assert result["firstBlocker"] == "APP.LAUNCH.runtime_dependency_unavailable"
    assert child_report.is_file()
    assert json.loads(child_report.read_text(encoding="utf-8")) == child_payload
    parent = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert parent["firstBlocker"] == result["firstBlocker"]
    assert parent["preflights"][0]["details"] == child_payload["details"]


def test_existing_failure_directory_is_not_cleaned_or_replaced(tmp_path: Path) -> None:
    report_dir = tmp_path / "existing-failure"
    retained = report_dir / "alpha-local/preflight/retained-failure.json"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'{"status":"gate_block","marker":"retained"}\n')
    original = retained.read_bytes()

    with patch.object(
        stackctl,
        "command_app_debug_preflight",
        return_value={
            "status": "gate_block",
            "exitCode": 2,
            "firstBlocker": "APP.LAUNCH.runtime_dependency_unavailable",
            "details": ["blocked"],
        },
    ):
        stackctl._command_app_content_uat(
            argparse.Namespace(
                targets="alpha-local",
                platform="ios-simulator",
                device_id="SIMULATOR-UDID",
                dry_run=False,
                report_dir=str(report_dir),
            )
        )

    assert retained.read_bytes() == original


def test_app_content_uat_parser_exposes_explicit_physical_profiles() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    from quwoquan_ops.cli.commands.app_preflight_uat_support import register_parser

    register_parser(subparsers)
    for platform in ("android-physical", "ios-physical"):
        args = parser.parse_args(
            [
                "app-content-uat",
                "--platform",
                platform,
                "--device-id",
                "opaque-device-id",
                "--device-registration-ref",
                "/evidence/device.lease.json",
            ]
        )
        assert args.platform == platform
        assert args.device_registration_ref == "/evidence/device.lease.json"


def _registered_device_lease(
    path: Path,
    *,
    platform: str,
    device_id: str,
    registered: bool = True,
) -> Path:
    device_digest = "sha256:" + hashlib.sha256(
        ("quwoquan-mobile-device\0" + device_id).encode("utf-8")
    ).hexdigest()
    host_digest = "sha256:" + "1" * 64
    lease_id = "sha256:" + "2" * 64
    lease_key = hashlib.sha256(
        f"{platform}\0{host_digest}\0{device_digest}".encode("utf-8")
    ).hexdigest()
    owner_path = path.parent / f"{platform}-{lease_key}" / "owner.json"
    owner_path.parent.mkdir(mode=0o700)
    owner_path.write_text(
        json.dumps(
            {
                "leaseId": lease_id,
                "tokenDigest": "sha256:" + "3" * 64,
                "runId": "test-run",
                "runAttempt": "1",
            }
        ),
        encoding="utf-8",
    )
    owner_path.chmod(0o600)
    payload = {
        "status": "held",
        "platform": platform,
        "hostDigest": host_digest,
        "deviceIdDigest": device_digest,
        "deviceClass": "physical",
        "deviceRegistered": registered,
        "targetPlatform": "ios" if platform == "ios" else "android-arm64",
        "leaseId": lease_id,
        "leaseOwnerRef": str(owner_path),
        "runnerLabel": f"mobile-{platform}",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_cli_platform_profiles_keep_virtual_devices_rehearsal_non_promotable() -> None:
    assert app_content_uat_cli_profile(
        platform="ios-simulator", device_id="SIMULATOR-UDID"
    ) == {
        "profile": "rehearsal",
        "deviceClass": "simulator",
        "deviceRegistered": False,
        "nonPromotable": True,
    }
    assert app_content_uat_cli_profile(
        platform="android", device_id="opaque-device-id"
    ) == {
        "profile": "rehearsal",
        "deviceClass": "emulator",
        "deviceRegistered": False,
        "nonPromotable": True,
    }


def test_cli_registered_physical_profiles_are_promotable_on_both_platforms(
    tmp_path: Path,
) -> None:
    for platform in ("android", "ios"):
        device_id = f"opaque-{platform}-device"
        lease = _registered_device_lease(
            tmp_path / f"{platform}.lease.json",
            platform=platform,
            device_id=device_id,
        )
        assert app_content_uat_cli_profile(
            platform=f"{platform}-physical",
            device_id=device_id,
            device_registration_ref=lease,
        ) == {
            "profile": "promotable",
            "deviceClass": "physical",
            "deviceRegistered": True,
            "nonPromotable": False,
        }


def test_cli_physical_profiles_fail_closed_without_matching_registration(
    tmp_path: Path,
) -> None:
    for platform in ("android", "ios"):
        with pytest.raises(ValueError, match="APP.UAT.device_registration_missing"):
            app_content_uat_cli_profile(
                platform=f"{platform}-physical",
                device_id=f"opaque-{platform}-device",
            )

        lease = _registered_device_lease(
            tmp_path / f"unregistered-{platform}.lease.json",
            platform=platform,
            device_id=f"opaque-{platform}-device",
            registered=False,
        )
        with pytest.raises(ValueError, match="APP.UAT.device_registration_invalid"):
            app_content_uat_cli_profile(
                platform=f"{platform}-physical",
                device_id=f"opaque-{platform}-device",
                device_registration_ref=lease,
            )

def test_cli_registration_cannot_be_guessed_from_device_id(tmp_path: Path) -> None:
    physical_looking_id = "emulator-5554"
    with pytest.raises(ValueError, match="APP.UAT.device_registration_missing"):
        app_content_uat_cli_profile(
            platform="android-physical",
            device_id=physical_looking_id,
        )

    lease = _registered_device_lease(
        tmp_path / "mismatched.lease.json",
        platform="android",
        device_id="different-device",
    )
    with pytest.raises(ValueError, match="APP.UAT.device_registration_invalid"):
        app_content_uat_cli_profile(
            platform="android-physical",
            device_id=physical_looking_id,
            device_registration_ref=lease,
        )


def test_registered_physical_profiles_are_promotable_and_production() -> None:
    assert (
        app_content_uat_non_promotable(
            profile="promotable", device_class="physical", registered=True
        )
        is False
    )
    assert (
        app_content_uat_non_promotable(
            profile="production", device_class="physical", registered=True
        )
        is False
    )
    with pytest.raises(ValueError, match="registered physical"):
        app_content_uat_non_promotable(
            profile="promotable", device_class="physical", registered=False
        )



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


def test_main_wiring_calls_raw_authority_producer_once_per_target(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    report_dir = output_root / "uat"
    runtime_binding = {
        "target": "alpha-local",
        "environment": "alpha",
        "releaseId": "release-a",
        "manifestDigest": "sha256:" + "1" * 64,
        "releaseTrainId": "sha256:" + "2" * 64,
        "packageBaseline": "sha256:" + "3" * 64,
        "candidateDigest": "sha256:" + "3" * 64,
        "sourceRevision": "a" * 40,
        "sourceCapsuleManifestRef": str(output_root / "candidate/input-capsule/manifest.json"),
        "startupIdentity": {"configurationDigest": "sha256:" + "4" * 64},
    }
    launch_binding = {
        "target": "alpha-local",
        "environment": "alpha",
        "platform": "android",
        "deviceId": "emulator-5554",
        "contractGraphDigest": "sha256:" + "5" * 64,
        "launchReportRef": str(output_root / "launch-report.json"),
        "launchAttemptRef": str(output_root / "launch-attempt.json"),
        "contractGraphRef": str(output_root / "contract-graph.json"),
    }
    app_uat_plan = {
        "releaseIdentity": {
            "releaseId": "release-a",
            "payloadSha256": "sha256:" + "1" * 64,
        },
        "carrierIdentities": {"video": "video-a"},
        "videoPagination": {"expectedWorkIds": ["video-a"]},
    }
    preflight = {
        "exitCode": 0,
        "target": "alpha-local",
        "environment": "alpha",
        "releaseId": "release-a",
        "manifestDigest": "sha256:" + "1" * 64,
        "releaseUatSamplePlanDigest": "sha256:" + "6" * 64,
        "releaseUatSamplePlanRef": str(output_root / "sample-plan.json"),
        "releaseHeaderRef": str(output_root / "release-header.json"),
        "releaseUatSamplePlan": {
            "schema": "fixture-plan",
            "releaseDigest": "sha256:" + "1" * 64,
            "selectionEvidence": {
                "sourceIdentitySetDigest": "sha256:" + "2" * 64
            },
        },
        "appUatPlan": app_uat_plan,
        "status": "passed",
    }
    (output_root / "sample-plan.json").write_text("sample-plan\n")
    (output_root / "contract-graph.json").write_text("contract-graph\n")
    candidate_manifest = output_root / "candidate/manifest.json"
    candidate_manifest.parent.mkdir(parents=True)
    candidate_manifest.write_text("candidate-manifest\n")
    target_binding = {"schema": "fixture-target-uat-binding"}
    target_binding_ref = {
        "ref": "target-uat-bindings/binding.json",
        "digest": "sha256:" + "7" * 64,
    }
    raw_source = {
        "slotId": "sha256:" + "8" * 64,
        "ref": "raw-readiness-case-results/result.json",
        "digest": "sha256:" + "9" * 64,
    }
    projection = {
        "rawResultRefs": {
            "alpha-local": [
                {"slotId": raw_source["slotId"], "ref": raw_source["ref"]}
            ]
        },
        "rawResultDigests": {
            "alpha-local": [
                {
                    "slotId": raw_source["slotId"],
                    "digest": raw_source["digest"],
                }
            ]
        },
        "rawCoverage": {
            "alpha-local": {"expected": 1, "present": 1, "missing": 0}
        },
        "rawGaps": {"alpha-local": []},
    }

    def execute_launch(**kwargs: object) -> bool:
        launch_bindings = kwargs["launch_bindings"]
        assert isinstance(launch_bindings, dict)
        launch_bindings["alpha-local"] = dict(launch_binding)
        return True

    patchers = [
        patch.object(stackctl, "output_root", return_value=output_root),
        patch.object(stackctl, "command_app_debug_preflight", return_value=preflight),
        patch.object(
            stackctl,
            "_app_content_test_live_runtime_binding",
            return_value=runtime_binding,
        ),
        patch.object(uat, "_app_content_readiness_path", return_value=output_root),
        patch.object(
            stackctl,
            "_run_app_content_release_probe",
            return_value={"target": "alpha-local", "exitCode": 0},
        ),
        patch.object(
            uat,
            "materialize_app_content_launch_projection",
            return_value={
                "sourceProjectionRoot": str(output_root),
                "sourceProjectionEvidenceRef": str(
                    output_root / "source-projection.json"
                ),
            },
        ),
        patch.object(uat, "verify_app_content_launch_projection", return_value={}),
        patch.object(uat, "write_app_content_launch_control", return_value={}),
        patch.object(
            uat,
            "execute_canonical_platform_launch",
            side_effect=execute_launch,
        ),
        patch.object(
            uat,
            "_target_uat_binding_for_execution",
            return_value=(target_binding, target_binding_ref),
        ),
        patch.object(uat, "expected_app_uat_raw_coverage", return_value=1),
        patch.object(
            stackctl, "_app_content_uat_requires_typed_actor", return_value=False
        ),
        patch.object(
            stackctl,
            "_environment_page_smoke_profile_command",
            side_effect=lambda _environment, target, _report_dir, **kwargs: {
                "argv": [
                    "patrol",
                    str(kwargs["suite_name"]),
                    "--gateway-base-url",
                    "https://alpha-api.example.test",
                ],
                "cwd": output_root,
                "reportPath": (
                    output_root / f"{target}-{kwargs['suite_name']}.json"
                ).as_posix(),
            },
        ),
        patch.object(
            uat,
            "execute_patrol_with_dependency_cas",
            return_value=(subprocess.CompletedProcess([], 0, "", ""), None, {}),
        ),
        patch.object(
            stackctl,
            "_app_content_patrol_evidence",
            return_value={
                "contractGraphDigest": launch_binding["contractGraphDigest"]
            },
        ),
        patch.object(
            uat,
            "_app_content_page_artifact_binding",
            return_value={"status": "passed"},
        ),
        patch.object(
            uat, "_controlled_edge_recovery_evidence_issue", return_value=""
        ),
        patch.object(uat, "collect_app_uat_case_execution_reports", return_value=[]),
        patch.object(
            uat,
            "emit_app_uat_raw_results",
            return_value=[dict(raw_source)],
        ),
        patch.object(
            stackctl,
            "_app_content_experience_screenshot_digests",
            return_value={},
        ),
        patch.object(uat, "_app_content_launch_binding", return_value=launch_binding),
        patch.object(
            uat,
            "project_app_content_uat_raw_authority",
            return_value=(projection, []),
        ),
    ]
    with ExitStack() as stack:
        started = [stack.enter_context(patcher) for patcher in patchers]
        emit_raw = started[18]
        result = uat._command_app_content_uat(
            argparse.Namespace(
                targets="alpha-local",
                platform="android",
                device_id="emulator-5554",
                dry_run=False,
                report_dir=str(report_dir),
            )
        )

    assert result["status"] == "complete"
    assert result["exitCode"] == 0
    emit_raw.assert_called_once_with(
        evidence_root=output_root,
        target_binding=target_binding,
        sample_plan=preflight["releaseUatSamplePlan"],
        case_execution_reports=[],
    )
    assert result["rawResultRefs"] == projection["rawResultRefs"]
    assert result["rawResultDigests"] == projection["rawResultDigests"]
