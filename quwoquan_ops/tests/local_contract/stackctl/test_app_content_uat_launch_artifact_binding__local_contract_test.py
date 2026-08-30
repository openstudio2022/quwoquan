"""app-content-uat 对 canonical launch/AppArtifact 的逐 target 绑定。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_app.scripts.device.startup_terminal_receipt import (
    build_startup_terminal_receipt,
    canonical_document_digest,
    marker_digest,
    write_startup_terminal_receipt,
)
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch
from quwoquan_ops.cli.commands.app_preflight_uat import (
    _app_content_canonical_launch_command,
)
from quwoquan_ops.cli.commands.app_preflight_uat_binding import (
    _app_content_launch_binding,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import (
    _verified_dependency_projection_binding,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    record_app_launch_attempt_observation,
    transition_app_launch_attempt,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_projection_contract import (
    COMPONENT_LOGICAL_PATHS,
    environment_identity,
)
from quwoquan_ops.tests.support.patrol_command_envelope_test_support import (
    sealed_patrol_command_fixture,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


SOURCE_REVISION = "a" * 40
SOURCE_CAPSULE_DIGEST = _digest("1")
ARTIFACT_DIGEST = _digest("2")
TRUST_DIGEST = _digest("3")
PACKAGE_DIGEST = _digest("4")
LAUNCH_DIGEST = _digest("5")
CANDIDATE_DIGEST = _digest("c")
SOURCE_PROJECTION_DIGEST = _digest("f")
DERIVED_OUTPUT_DIGEST = _digest("7")
DERIVED_OUTPUT_POLICY_DIGEST = _digest("8")
BUILD_PROJECTION_DIGEST = _digest("9")
CONTRACT_GRAPH_BYTES = json.dumps(
    {
        "operations": [
            {
                "id": "content.post.GetFeed",
                "errorCodes": ["CONTENT.SYSTEM.required_dependency_unavailable"],
            }
        ]
    },
    separators=(",", ":"),
).encode("utf-8")
CONTRACT_GRAPH_DIGEST = "sha256:" + hashlib.sha256(CONTRACT_GRAPH_BYTES).hexdigest()


def _write_private_evidence(path: Path, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    path.chmod(0o600)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_dependency_markers() -> list[dict[str, object]]:
    return sorted(
        (
            {
                "logicalPath": COMPONENT_LOGICAL_PATHS[name],
                "digest": _digest(marker),
                "size": 1,
            }
            for name, marker in (
                ("androidGradle", "6"),
                ("patrolPub", "8"),
                ("productionPub", "7"),
            )
        ),
        key=lambda item: str(item["logicalPath"]),
    )


def _dependency_projection_evidence(
    projection_root: Path,
    *,
    source_manifest_digest: str,
    source_manifest_ref: Path,
) -> dict[str, str]:
    state = projection_root / "quwoquan_app/.dart_tool/qwq_android_dependency_state"
    expectation_path = state / "dependency-projection-expectation.json"
    prebuild_path = state / "dependency-projection-prebuild-readback.json"
    postbuild_path = state / "dependency-projection-postbuild-readback.json"
    pub_identity = {
        "manifestDigest": _digest("a"),
        "treeDigest": _digest("b"),
        "entryCount": 19,
        "directoryCount": 7,
        "lockDigest": _digest("c"),
    }
    gradle_manifest = {
        "treeDigest": _digest("e"),
        "entryCount": 31,
    }
    gradle_manifest_encoded = json.dumps(
        gradle_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    gradle_identity = {
        "manifestDigest": "sha256:"
        + hashlib.sha256(gradle_manifest_encoded).hexdigest(),
        "treeDigest": _digest("e"),
        "entryCount": 31,
    }
    components = {
        "androidGradle": {
            "kind": "androidGradle",
            "treePath": "quwoquan_app/.dart_tool/qwq_android_dependency_state/gradle",
            "manifest": gradle_manifest,
            **gradle_identity,
        },
        "productionPub": {
            "kind": "pub",
            "treePath": "quwoquan_app/.dart_tool/qwq_android_dependency_state/pub",
            "lockPath": "quwoquan_app/pubspec.lock",
            **pub_identity,
        },
        "patrolPub": {
            "kind": "pub",
            "treePath": "quwoquan_app/.dart_tool/qwq_android_dependency_state/patrol-pub",
            "lockPath": "quwoquan_app/test_host/patrol/pubspec.lock",
            **pub_identity,
        },
    }
    patrol_environment = {"FLUTTER_SWIFT_PACKAGE_MANAGER": "false"}
    command_envelope, command_envelope_digest = sealed_patrol_command_fixture(
        patrol_environment
    )
    expectation_digest = _write_private_evidence(
        expectation_path,
        {
            "schema": "stackctl-app-dependency-projection-expectation.v2",
            "projectionRoot": str(projection_root),
            "source": {
                "manifestDigest": source_manifest_digest,
                "manifestPath": str(source_manifest_ref),
                "baselineId": _digest("0"),
                "inputDigest": _digest("1"),
                "inputCount": 2,
                "dependencyMarkers": _source_dependency_markers(),
            },
            "components": components,
            "environments": {
                "patrol": environment_identity(patrol_environment),
                "production": environment_identity(
                    {"FLUTTER_SWIFT_PACKAGE_MANAGER": "false"}
                ),
            },
            "patrolCommandEnvelope": command_envelope,
        },
    )
    readback = {
        "schema": "stackctl-app-dependency-projection-readback.v2",
        "expectationDigest": expectation_digest,
        "projectionRoot": str(projection_root),
        "sourceManifestDigest": source_manifest_digest,
        "components": {
            "androidGradle": gradle_identity,
            "patrolPub": pub_identity,
            "productionPub": pub_identity,
        },
        "patrolCommandEnvelopeDigest": command_envelope_digest,
    }
    prebuild_digest = _write_private_evidence(prebuild_path, readback)
    postbuild_digest = _write_private_evidence(postbuild_path, readback)
    return {
        "dependencyProjectionExpectationRef": str(expectation_path),
        "dependencyProjectionExpectationDigest": expectation_digest,
        "dependencyProjectionPrebuildReadbackRef": str(prebuild_path),
        "dependencyProjectionPrebuildReadbackDigest": prebuild_digest,
        "dependencyProjectionPostbuildReadbackRef": str(postbuild_path),
        "dependencyProjectionPostbuildReadbackDigest": postbuild_digest,
    }


def _write_launch_pair(
    root: Path,
) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
    attempt_path = root / "alpha-local/canonical-launch/attempt-1/attempt.json"
    report_path = root / "alpha-local/canonical-launch/attempt-1/report.json"
    create_app_launch_attempt(
        attempt_path,
        environment="alpha",
        target="alpha-local",
        platform="android",
        build_profile="nonprod",
        build_mode="debug",
        run_mode="content-live",
        launch_provenance="canonical_launcher",
        runtime_config_supply_mode="external_runtime_package",
        runtime_config_trust_envelope_digest=TRUST_DIGEST,
        runtime_config_package_digest=PACKAGE_DIGEST,
        application_id="com.leadwise.quwoquan.nonprod.debug",
        flutter_version="3.35.1",
        command_resolution_digest=_digest("6"),
        device_id="emulator-5554",
        launch_digest=LAUNCH_DIGEST,
    )
    for status in (
        "compiling",
        "compiled",
        "installing",
        "installed",
        "configuring",
        "configured",
        "launching",
        "launched",
    ):
        transition_app_launch_attempt(
            attempt_path,
            status,
            artifact_digest=(ARTIFACT_DIGEST if status == "compiled" else None),
        )
    launched_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    terminal_path = attempt_path.with_name("startup-terminal.json")
    terminal = build_startup_terminal_receipt(
        launch_attempt=launched_attempt,
        startup_attempt_id="cold-a1",
        configuration_state="complete",
        surface="router_shell",
        canonical_terminal="routerShell",
        hot_restart=False,
        observed_marker_digest=marker_digest("canonical cold safe terminal"),
    )
    write_startup_terminal_receipt(terminal_path, terminal)
    record_app_launch_attempt_observation(
        attempt_path,
        configuration_state="complete",
        runtime_health_status="healthy",
        startup_terminal_attempt_id="cold-a1",
        startup_terminal_evidence_digest=canonical_document_digest(terminal),
        startup_terminal_evidence_ref=str(terminal_path),
    )
    transition_app_launch_attempt(attempt_path, "stopped")
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt_digest = stackctl._canonical_document_checksum(attempt)
    capsule_manifest_path = root / "candidate/input-capsule/manifest.json"
    capsule_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    contract_graph_entry = {
        "logicalPath": "quwoquan_service/generated/contract_graph.json",
        "capsulePath": "repo/quwoquan_service/generated/contract_graph.json",
        "kind": "file",
        "digest": CONTRACT_GRAPH_DIGEST,
        "mode": 0o444,
        "size": len(CONTRACT_GRAPH_BYTES),
    }
    capsule_manifest = {
        "baselineId": _digest("0"),
        "deploymentInputDigest": _digest("1"),
        "deploymentInputFileCount": 2,
        "entries": [*_source_dependency_markers(), contract_graph_entry],
    }
    capsule_manifest_path.write_text(
        json.dumps(capsule_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    capsule_manifest_digest = stackctl._canonical_document_checksum(capsule_manifest)
    capsule_manifest_raw_digest = (
        "sha256:" + hashlib.sha256(capsule_manifest_path.read_bytes()).hexdigest()
    )
    projection_root = root / "alpha-local/canonical-launch/source-projection"
    projection_root.mkdir(parents=True)
    contract_graph_ref = (
        projection_root / "quwoquan_service/generated/contract_graph.json"
    )
    contract_graph_ref.parent.mkdir(parents=True)
    contract_graph_ref.write_bytes(CONTRACT_GRAPH_BYTES)
    projection_evidence_path = projection_root.parent / "source-projection.json"
    projection_evidence = {
        "schema": "quwoquan_ops.app_content_uat_source_projection.v1",
        "candidateDigest": CANDIDATE_DIGEST,
        "packageDigest": PACKAGE_DIGEST,
        "sourceRevision": SOURCE_REVISION,
        "sourceCapsuleDigest": SOURCE_CAPSULE_DIGEST,
        "sourceCapsuleWorkspaceStatusDigest": _digest("d"),
        "sourceCapsuleManifestDigest": capsule_manifest_digest,
        "sourceCapsuleManifestRef": str(capsule_manifest_path),
        "sourceProjectionRoot": str(projection_root),
        "sourceProjectionDigest": SOURCE_PROJECTION_DIGEST,
        "sourceProjectionFileCount": 4,
    }
    projection_evidence_path.write_text(
        json.dumps(projection_evidence, sort_keys=True),
        encoding="utf-8",
    )
    projection: dict[str, object] = {
        **projection_evidence,
        "sourceProjectionEvidenceDigest": stackctl._canonical_document_checksum(
            projection_evidence
        ),
        "sourceProjectionEvidenceRef": str(projection_evidence_path),
    }
    dependency_projection_evidence = _dependency_projection_evidence(
        projection_root,
        source_manifest_digest=capsule_manifest_raw_digest,
        source_manifest_ref=capsule_manifest_path,
    )
    build_projection_seal_path = attempt_path.with_name("build-projection-seal.json")
    build_projection_seal = {
        "schema": "quwoquan_ops.app_build_projection_seal.v1",
        "policyId": launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        "sourceProjectionDigest": SOURCE_PROJECTION_DIGEST,
        "sourceEntryCount": 4,
        "derivedOutputDigest": DERIVED_OUTPUT_DIGEST,
        "derivedOutputPolicyDigest": DERIVED_OUTPUT_POLICY_DIGEST,
        "derivedEntryCount": 12,
        "buildProjectionDigest": BUILD_PROJECTION_DIGEST,
    }
    build_projection_seal_path.write_text(
        json.dumps(build_projection_seal, sort_keys=True),
        encoding="utf-8",
    )
    build_projection_seal_digest = stackctl._canonical_document_checksum(
        build_projection_seal
    )
    control_path = attempt_path.with_name("control.json")
    control = {
        "schema": "quwoquan_ops.app_content_uat_launch_control.v1",
        "actor": "app-content-uat",
        "environment": "alpha",
        "target": "alpha-local",
        "platform": "android",
        "deviceId": "emulator-5554",
        "candidateDigest": CANDIDATE_DIGEST,
        "packageDigest": PACKAGE_DIGEST,
        "sourceRevision": SOURCE_REVISION,
        "sourceCapsuleDigest": SOURCE_CAPSULE_DIGEST,
        "sourceCapsuleManifestDigest": projection["sourceCapsuleManifestDigest"],
        "sourceCapsuleManifestRef": projection["sourceCapsuleManifestRef"],
        "sourceProjectionRoot": projection["sourceProjectionRoot"],
        "sourceProjectionEvidenceDigest": projection["sourceProjectionEvidenceDigest"],
        "sourceProjectionEvidenceRef": projection["sourceProjectionEvidenceRef"],
        "buildProjectionPolicyId": (launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID),
        "buildProjectionSealRef": str(build_projection_seal_path),
        "expectedBuildProjectionDigest": None,
        "launchAttemptRef": str(attempt_path),
        "launchReportRef": str(report_path),
        "startupTerminalReceiptRef": str(terminal_path),
    }
    control_path.write_text(json.dumps(control, sort_keys=True), encoding="utf-8")
    report: dict[str, object] = {
        "schema": "quwoquan_app.test_live_launch",
        "environment": "alpha",
        "target": "alpha-local",
        "platform": "android",
        "deviceKind": "android-emulator",
        "deviceId": "emulator-5554",
        "runMode": "content-live",
        "nonPromotable": True,
        "launchPolicy": "test_live",
        "compileStatus": "compiled",
        "installStatus": "installed",
        "launchStatus": "launched",
        "runtimeStatus": "healthy",
        "lifecycleStatus": "stopped",
        "firstBlocker": "",
        "exitCode": 0,
        "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": "external_runtime_package",
        "runtimeConfigTrustEnvelopeDigest": TRUST_DIGEST,
        "runtimeConfigPackageDigest": PACKAGE_DIGEST,
        "effectiveLaunchManifestDigest": LAUNCH_DIGEST,
        "applicationId": "com.leadwise.quwoquan.nonprod.debug",
        "sourceGitSha": SOURCE_REVISION,
        "sourceTreeDigest": SOURCE_CAPSULE_DIGEST,
        "launchAttemptId": attempt["attemptId"],
        "launchAttemptRef": str(attempt_path),
        "launchAttemptDigest": attempt_digest,
        "artifactDigest": ARTIFACT_DIGEST,
        "runtimeWarnings": [],
        "startupTerminalAttemptId": "cold-a1",
        "startupTerminalEvidenceDigest": canonical_document_digest(terminal),
        "startupTerminalEvidenceRef": str(terminal_path),
        "candidateDigest": CANDIDATE_DIGEST,
        "candidatePackageDigest": PACKAGE_DIGEST,
        "sourceCapsuleManifestDigest": projection["sourceCapsuleManifestDigest"],
        "sourceProjectionEvidenceDigest": projection["sourceProjectionEvidenceDigest"],
        "sourceProjectionEvidenceRef": projection["sourceProjectionEvidenceRef"],
        "sourceProjectionDigest": SOURCE_PROJECTION_DIGEST,
        "sourceProjectionFileCount": 4,
        "prebuildProjectionDigest": _digest("0"),
        "buildProjectionSeal": build_projection_seal,
        "buildProjectionSealDigest": build_projection_seal_digest,
        "buildProjectionSealRef": str(build_projection_seal_path),
        "canonicalLaunchControlDigest": stackctl._canonical_document_checksum(control),
        "canonicalLaunchControlRef": str(control_path),
        **dependency_projection_evidence,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    teardown_path = attempt_path.with_name("teardown.json")
    teardown_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_app.launch_teardown.v1",
                "launchAttemptRef": str(attempt_path),
                "exitCode": 0,
                "status": "passed",
                "warnings": [],
                "completedAt": "2026-08-28T00:00:00+00:00",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return attempt_path, report_path, report, projection


def _patch_projection_seal_verifier(
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, object],
) -> None:
    payload = report["buildProjectionSeal"]
    assert isinstance(payload, dict)
    verified = {
        **payload,
        "buildProjectionSealDigest": report["buildProjectionSealDigest"],
        "buildProjectionSealRef": report["buildProjectionSealRef"],
    }
    monkeypatch.setattr(
        launch,
        "verify_app_content_projection_build_seal",
        lambda **_kwargs: dict(verified),
    )


def _runtime_binding() -> dict[str, object]:
    return {
        "launchPolicy": "immutable_candidate",
        "environment": "alpha",
        "target": "alpha-local",
        "sourceRevision": SOURCE_REVISION,
        "sourceCapsuleDigest": SOURCE_CAPSULE_DIGEST,
        "sourceCapsuleWorkspaceStatusDigest": _digest("d"),
        "candidateDigest": CANDIDATE_DIGEST,
        "packageDigest": PACKAGE_DIGEST,
        "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
    }


def _canonical_process_observer(**kwargs: object) -> int:
    assert kwargs == {
        "platform": "android",
        "device_id": "emulator-5554",
        "application_id": "com.leadwise.quwoquan.nonprod.debug",
    }
    return 4312


def test_launch_binding_persists_exact_artifact_and_attempt_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_path, report_path, report, projection = _write_launch_pair(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    _patch_projection_seal_verifier(monkeypatch, report)

    binding = _app_content_launch_binding(
        runtime_binding=_runtime_binding(),
        report_ref=report_path,
        attempt_ref=attempt_path,
        platform="android",
        device_id="emulator-5554",
        launch_provenance="canonical_launcher",
        launch_projection=projection,
        process_observer=_canonical_process_observer,
    )

    assert binding == {
        "environment": "alpha",
        "target": "alpha-local",
        "platform": "android",
        "deviceId": "emulator-5554",
        "applicationId": "com.leadwise.quwoquan.nonprod.debug",
        "canonicalProcessId": 4312,
        "sourceGitSha": SOURCE_REVISION,
        "sourceTreeDigest": SOURCE_CAPSULE_DIGEST,
        "launchAttemptId": report["launchAttemptId"],
        "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": "external_runtime_package",
        "artifactDigest": ARTIFACT_DIGEST,
        "runtimeConfigTrustEnvelopeDigest": TRUST_DIGEST,
        "runtimeConfigPackageDigest": PACKAGE_DIGEST,
        "effectiveLaunchManifestDigest": LAUNCH_DIGEST,
        "launchAttemptDigest": report["launchAttemptDigest"],
        "launchAttemptRef": str(attempt_path),
        "startupTerminalAttemptId": "cold-a1",
        "startupTerminalEvidenceDigest": report["startupTerminalEvidenceDigest"],
        "startupTerminalEvidenceRef": report["startupTerminalEvidenceRef"],
        "candidateDigest": CANDIDATE_DIGEST,
        "candidatePackageDigest": PACKAGE_DIGEST,
        "sourceCapsuleManifestDigest": projection["sourceCapsuleManifestDigest"],
        "sourceCapsuleManifestRef": projection["sourceCapsuleManifestRef"],
        "sourceProjectionEvidenceDigest": projection["sourceProjectionEvidenceDigest"],
        "sourceProjectionEvidenceRef": projection["sourceProjectionEvidenceRef"],
        "sourceProjectionDigest": SOURCE_PROJECTION_DIGEST,
        "sourceProjectionFileCount": 4,
        "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
        "contractGraphRef": str(
            Path(str(projection["sourceProjectionRoot"]))
            / "quwoquan_service/generated/contract_graph.json"
        ),
        "contractGraphOperationCount": 1,
        "sourceProjectionRoot": projection["sourceProjectionRoot"],
        "dependencyProjectionExpectationRef": report[
            "dependencyProjectionExpectationRef"
        ],
        "dependencyProjectionExpectationDigest": report[
            "dependencyProjectionExpectationDigest"
        ],
        "dependencyProjectionPrebuildReadbackRef": report[
            "dependencyProjectionPrebuildReadbackRef"
        ],
        "dependencyProjectionPrebuildReadbackDigest": report[
            "dependencyProjectionPrebuildReadbackDigest"
        ],
        "dependencyProjectionPostbuildReadbackRef": report[
            "dependencyProjectionPostbuildReadbackRef"
        ],
        "dependencyProjectionPostbuildReadbackDigest": report[
            "dependencyProjectionPostbuildReadbackDigest"
        ],
        "buildProjectionSeal": report["buildProjectionSeal"],
        "buildProjectionSealDigest": report["buildProjectionSealDigest"],
        "buildProjectionSealRef": report["buildProjectionSealRef"],
        "canonicalLaunchControlDigest": report["canonicalLaunchControlDigest"],
        "canonicalLaunchControlRef": report["canonicalLaunchControlRef"],
        "teardownReceiptDigest": stackctl._canonical_document_checksum(
            json.loads(
                attempt_path.with_name("teardown.json").read_text(encoding="utf-8")
            )
        ),
        "teardownReceiptRef": str(attempt_path.with_name("teardown.json")),
        "launchReportDigest": stackctl._canonical_document_checksum(report),
        "launchReportRef": str(report_path),
    }


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("target", "beta-local", "target"),
        ("platform", "ios", "platform"),
        ("deviceId", "other-device", "device"),
        ("sourceGitSha", "b" * 40, "source"),
        ("sourceTreeDigest", _digest("7"), "source"),
        ("artifactDigest", _digest("8"), "artifact"),
        ("runtimeConfigTrustEnvelopeDigest", _digest("9"), "trust"),
        ("runtimeConfigPackageDigest", _digest("a"), "package"),
        ("launchAttemptDigest", _digest("b"), "attempt digest"),
    ),
)
def test_launch_binding_rejects_any_cross_identity_or_stale_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: str,
    message: str,
) -> None:
    attempt_path, report_path, report, projection = _write_launch_pair(tmp_path)
    report[field] = replacement
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    _patch_projection_seal_verifier(monkeypatch, report)

    with pytest.raises(ValueError, match=message):
        _app_content_launch_binding(
            runtime_binding=_runtime_binding(),
            report_ref=report_path,
            attempt_ref=attempt_path,
            platform="android",
            device_id="emulator-5554",
            launch_provenance="canonical_launcher",
            launch_projection=projection,
            process_observer=_canonical_process_observer,
        )


def test_android_uat_command_cannot_bypass_canonical_launcher(tmp_path: Path) -> None:
    attempt_path = tmp_path / "attempt.json"
    report_path = tmp_path / "report.json"

    command, environment = _app_content_canonical_launch_command(
        environment="alpha",
        target="alpha-local",
        device_id="emulator-5554",
        attempt_path=attempt_path,
        report_path=report_path,
        output_root=tmp_path,
    )

    assert command[0:2] == ["bash", str(stackctl.ROOT / "quwoquan_app/run.sh")]
    assert command[-2:] == ["-d", "emulator-5554"]
    assert command[command.index("--launch-receipt") + 1] == str(attempt_path)
    assert command[command.index("--test-live-report") + 1] == str(report_path)
    assert "--exit-after-launch" in command
    assert environment == {
        "QWQ_OUTPUT_ROOT": str(tmp_path.resolve()),
        "QWQ_CANONICAL_LAUNCH_ACTOR": "app-content-uat",
        "QWQ_APP_LAUNCH_PROVENANCE": "canonical_launcher",
    }


def test_launch_binding_rejects_test_live_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_path, report_path, report, projection = _write_launch_pair(tmp_path)
    report["runtimeWarnings"] = ["CONTENT.SYSTEM.required_dependency_unavailable"]
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    _patch_projection_seal_verifier(monkeypatch, report)

    with pytest.raises(ValueError, match="warnings are forbidden"):
        _app_content_launch_binding(
            runtime_binding=_runtime_binding(),
            report_ref=report_path,
            attempt_ref=attempt_path,
            platform="android",
            device_id="emulator-5554",
            launch_provenance="canonical_launcher",
            launch_projection=projection,
            process_observer=_canonical_process_observer,
        )


def test_launch_binding_rejects_attempt_that_has_not_fully_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_path, report_path, report, projection = _write_launch_pair(tmp_path)
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["status"] = "launched"
    assert attempt["transitions"][-1]["status"] == "stopped"
    attempt["transitions"].pop()
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    report["lifecycleStatus"] = "launched"
    report["launchAttemptDigest"] = stackctl._canonical_document_checksum(attempt)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    _patch_projection_seal_verifier(monkeypatch, report)

    with pytest.raises(ValueError, match="lifecycle is not healthy"):
        _app_content_launch_binding(
            runtime_binding=_runtime_binding(),
            report_ref=report_path,
            attempt_ref=attempt_path,
            platform="android",
            device_id="emulator-5554",
            launch_provenance="canonical_launcher",
            launch_projection=projection,
            process_observer=_canonical_process_observer,
        )


def test_launch_binding_rejects_teardown_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt_path, report_path, _report, projection = _write_launch_pair(tmp_path)
    teardown_path = attempt_path.with_name("teardown.json")
    teardown = json.loads(teardown_path.read_text(encoding="utf-8"))
    teardown.update(
        {
            "status": "warning",
            "warnings": ["failed to release runtime consumer lease."],
        }
    )
    teardown_path.write_text(json.dumps(teardown), encoding="utf-8")
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _patch_projection_seal_verifier(monkeypatch, report)

    with pytest.raises(ValueError, match="teardown is not clean"):
        _app_content_launch_binding(
            runtime_binding=_runtime_binding(),
            report_ref=report_path,
            attempt_ref=attempt_path,
            platform="android",
            device_id="emulator-5554",
            launch_provenance="canonical_launcher",
            launch_projection=projection,
            process_observer=_canonical_process_observer,
        )


@pytest.mark.parametrize(
    "field",
    (
        "dependencyProjectionExpectationRef",
        "dependencyProjectionExpectationDigest",
        "dependencyProjectionPrebuildReadbackRef",
        "dependencyProjectionPrebuildReadbackDigest",
        "dependencyProjectionPostbuildReadbackRef",
        "dependencyProjectionPostbuildReadbackDigest",
    ),
)
def test_strict_launch_binding_requires_every_dependency_evidence_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    attempt_path, report_path, report, projection = _write_launch_pair(tmp_path)
    report.pop(field)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    _patch_projection_seal_verifier(monkeypatch, report)

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _app_content_launch_binding(
            runtime_binding=_runtime_binding(),
            report_ref=report_path,
            attempt_ref=attempt_path,
            platform="android",
            device_id="emulator-5554",
            launch_provenance="canonical_launcher",
            launch_projection=projection,
            process_observer=_canonical_process_observer,
        )


def test_dependency_evidence_rejects_linked_and_cross_projection_readbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _attempt_path, _report_path, report, projection = _write_launch_pair(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    original_expectation = Path(str(report["dependencyProjectionExpectationRef"]))
    linked_expectation = original_expectation.with_name("linked-expectation.json")
    linked_expectation.symlink_to(original_expectation)
    report["dependencyProjectionExpectationRef"] = str(linked_expectation)

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection=projection,
            platform="android",
        )

    report["dependencyProjectionExpectationRef"] = str(original_expectation)
    other_root = tmp_path / "other-attempt/source-projection"
    other_root.mkdir(parents=True)
    other = _dependency_projection_evidence(
        other_root,
        source_manifest_digest=(
            "sha256:"
            + hashlib.sha256(
                Path(str(projection["sourceCapsuleManifestRef"])).read_bytes()
            ).hexdigest()
        ),
        source_manifest_ref=Path(str(projection["sourceCapsuleManifestRef"])),
    )
    report["dependencyProjectionPostbuildReadbackRef"] = other[
        "dependencyProjectionPostbuildReadbackRef"
    ]
    report["dependencyProjectionPostbuildReadbackDigest"] = other[
        "dependencyProjectionPostbuildReadbackDigest"
    ]

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection=projection,
            platform="android",
        )


def test_dependency_evidence_rejects_postbuild_component_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _attempt_path, _report_path, report, projection = _write_launch_pair(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    postbuild_path = Path(str(report["dependencyProjectionPostbuildReadbackRef"]))
    postbuild = json.loads(postbuild_path.read_text(encoding="utf-8"))
    postbuild["components"]["androidGradle"]["treeDigest"] = _digest("0")
    report["dependencyProjectionPostbuildReadbackDigest"] = _write_private_evidence(
        postbuild_path, postbuild
    )

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection=projection,
            platform="android",
        )


def test_ios_dependency_evidence_requires_exact_dual_host_component_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _attempt_path, _report_path, report, projection = _write_launch_pair(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    with pytest.raises(
        ValueError,
        match=r"APP\.LAUNCH\.receipt_invalid:.*invalid ios-simulator component set",
    ):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection=projection,
            platform="ios-simulator",
        )
