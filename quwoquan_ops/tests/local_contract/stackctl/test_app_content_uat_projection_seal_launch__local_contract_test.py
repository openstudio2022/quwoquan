"""Canonical UAT launch must CAS-bind every admitted build projection byte.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

import json
import stat
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEPENDENCY_PROJECTION_EVIDENCE_FIELDS = (
    "dependencyProjectionExpectationRef",
    "dependencyProjectionExpectationDigest",
    "dependencyProjectionPrebuildReadbackRef",
    "dependencyProjectionPrebuildReadbackDigest",
    "dependencyProjectionPostbuildReadbackRef",
    "dependencyProjectionPostbuildReadbackDigest",
)


def test_run_sh_has_no_unmanifested_projection_escape_hatch() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")

    assert "reject_unmanifested=False" not in launcher
    assert "seal_app_content_projection_build" in launcher
    assert "prepare_workspace_launch_projection.py" in launcher
    assert 'PROJECTED_APP_DIR="$QWQ_WORKSPACE_PROJECTION_ROOT/quwoquan_app"' in launcher
    assert (
        'exec "$PROJECTED_APP_DIR/run.sh" "${ORIGINAL_LAUNCH_ARGUMENTS[@]}"'
        in launcher
    )
    assert 'EXPECTED_PRIVATE_PUB_CACHE="$APP_DIR/.dart_tool/qwq_pub_cache"' in launcher
    assert "prepare_flutter_dependencies.py" in launcher
    assert "--source-capsule-manifest" in launcher
    assert "pod install --deployment" not in launcher
    assert "FLUTTER_SWIFT_PACKAGE_MANAGER=false" in launcher
    assert launcher.index("prepare_flutter_dependencies.py") < launcher.index(
        "seal_app_content_projection_build predependency"
    )
    assert launcher.index("seal_app_content_projection_build predependency") < (
        launcher.index("seal_app_content_projection_build prebuild")
    )
    assert launcher.index(
        "seal_app_content_projection_build prebuild"
    ) < launcher.index('"${SUPERVISOR_CMD[@]}"')
    assert launcher.index('"${SUPERVISOR_CMD[@]}"') < launcher.index(
        "seal_app_content_projection_build evidence"
    )


def test_initial_dependency_projection_prepares_expectation_and_readback() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    preparer = (
        _REPO_ROOT / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
    ).read_text(encoding="utf-8")

    prepare_call = launcher.index("prepare_flutter_dependencies.py")
    evaluate_exports = launcher.index('eval "$DEPENDENCY_EXPORTS"', prepare_call)
    seal_predependency = launcher.index(
        "seal_app_content_projection_build predependency",
        evaluate_exports,
    )
    assert prepare_call < evaluate_exports < seal_predependency

    evidence_prepare = preparer.index(
        "prepare_dependency_projection_cas_evidence_with_observed_components("
    )
    initial_readback = preparer.index(
        "readback_from_expectation(", evidence_prepare
    )
    write_readback = preparer.index(
        "write_dependency_projection_cas_readback(", initial_readback
    )
    reload_readback = preparer.index(
        "load_dependency_projection_cas_readback(", write_readback
    )
    assert evidence_prepare < initial_readback < write_readback < reload_readback

    for field in (
        "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF",
        "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST",
        "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF",
        "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST",
    ):
        assert field in preparer
        assert field in launcher
    assert (
        "initial pre-build dependency readback is incomplete"
        in launcher[evaluate_exports:seal_predependency]
    )


def test_retry_validates_expected_full_tree_before_fresh_prebuild_readback() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    seal_function = launcher[
        launcher.index("seal_app_content_projection_build()") : launcher.index(
            "verify_dependency_projection_after_command()"
        )
    ]
    retry_start = launcher.index("DEPENDENCY_RETRY=1")
    expectation_reload = launcher.index(
        "load_dependency_projection_cas_evidence(", retry_start
    )
    expected_full_tree_seal = launcher.index(
        "seal_app_content_projection_build prebuild", expectation_reload
    )
    fresh_prebuild_readback = launcher.index(
        "verify_dependency_projection_after_command prebuild",
        expected_full_tree_seal,
    )

    assert "expected_build_projection_digest=(" in seal_function
    assert '(expected_digest or None) if phase != "evidence" else None' in (
        seal_function
    )
    assert expectation_reload < expected_full_tree_seal < fresh_prebuild_readback
    assert (
        'if [[ "$DEPENDENCY_RETRY" == "1" ]]'
        in launcher[expected_full_tree_seal:fresh_prebuild_readback]
    )
    assert (
        "mktemp -d"
        in launcher[
            launcher.index(
                "verify_dependency_projection_after_command()"
            ) : launcher.index("print_usage()")
        ]
    )


def test_ios_initial_and_retry_preserve_one_complete_cocoapods_identity() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    preparer = (
        _REPO_ROOT / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
    ).read_text(encoding="utf-8")
    identity_keys = (
        "QWQ_COCOAPODS_EXECUTABLE",
        "QWQ_COCOAPODS_VERSION",
        "QWQ_COCOAPODS_EXECUTABLE_DIGEST",
        "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST",
        "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST",
        "QWQ_COCOAPODS_BINDING_SEAL",
    )

    retry_start = launcher.index("DEPENDENCY_RETRY=1")
    supervisor = launcher.index('"${SUPERVISOR_CMD[@]}"', retry_start)
    retry_contract = launcher[retry_start:supervisor]
    assert "resolve_cocoapods_identity" not in retry_contract
    assert "resolve_cocoapods_executable" not in retry_contract
    assert "verify_cocoapods_launch_identity || exit 2" in retry_contract
    assert launcher.index("verify_cocoapods_launch_identity || exit 2") < supervisor
    for key in identity_keys:
        assert key in preparer
        assert key in launcher


def test_ios_retry_missing_identity_fails_without_ambient_resolution() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    verifier = launcher[
        launcher.index("verify_cocoapods_launch_identity()") : launcher.index(
            "print_usage()"
        )
    ]

    assert "validate_cocoapods_child_environment(os.environ)" in verifier
    assert "resolve_cocoapods_identity" not in verifier
    assert "shutil.which" not in verifier
    assert "APP.DEPENDENCY.cocoapods_mixed" in verifier


def test_real_supervisor_is_followed_by_mandatory_postbuild_revalidation() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    supervisor = launcher.index('"${SUPERVISOR_CMD[@]}" --')
    captured_exit = launcher.index("FLUTTER_RUN_EXIT_CODE=$?", supervisor)
    postbuild = launcher.index(
        "verify_dependency_projection_after_command postbuild", captured_exit
    )
    projection_seal = launcher.index(
        "seal_app_content_projection_build evidence", postbuild
    )
    report = launcher.index('"dependencyProjectionExpectationRef":', projection_seal)

    assert supervisor < captured_exit < postbuild < projection_seal < report
    assert 'python3 "$APP_DIR/scripts/device/verify_flutter_dependencies.py"' in (
        launcher
    )
    assert '--phase "$phase"' in launcher


def test_dependency_projection_cas_failure_cannot_produce_success_report() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    postbuild_start = launcher.index(
        "if ! verify_dependency_projection_after_command postbuild; then"
    )
    postbuild_end = launcher.index("\nfi", postbuild_start) + len("\nfi")
    failure_branch = launcher[postbuild_start:postbuild_end]
    report_start = launcher.index(
        '"dependencyProjectionExpectationRef":', postbuild_end
    )

    assert 'exit "$FLUTTER_RUN_EXIT_CODE"' in failure_branch
    assert "exit 2" in failure_branch
    assert "projection_cas_drift" in failure_branch
    assert postbuild_end < report_start


def test_launch_report_and_strict_uat_bind_all_dependency_cas_fields() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    binding = (
        _REPO_ROOT / "quwoquan_ops/cli/commands/app_preflight_uat_launch_binding.py"
    ).read_text(encoding="utf-8")

    for field in _DEPENDENCY_PROJECTION_EVIDENCE_FIELDS:
        assert field in launcher
        assert field in binding
    assert "flutter_exit_code,\n    flutter_exit_code," not in launcher
    assert "_verified_dependency_projection_binding(" in binding
    assert "load_canonical_projection_evidence(" in binding
    assert "load_dependency_projection_cas_evidence_bytes(" in binding
    assert binding.count("load_dependency_projection_cas_readback_bytes(") >= 2


def test_control_and_report_bind_exact_build_projection_seal_fields() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    binding = (
        _REPO_ROOT / "quwoquan_ops/cli/commands/app_preflight_uat_launch_binding.py"
    ).read_text(encoding="utf-8") + (
        _REPO_ROOT / "quwoquan_ops/cli/commands/app_preflight_uat_binding_contract.py"
    ).read_text(encoding="utf-8")

    for field in (
        "buildProjectionPolicyId",
        "buildProjectionSealRef",
        "expectedBuildProjectionDigest",
        "derivedOutputPolicyDigest",
        "derivedOutputDigest",
        "buildProjectionDigest",
        "buildProjectionSealDigest",
    ):
        assert field in launcher
        assert field in binding


def test_ios_retry_requires_complete_stopped_attempt_one_binding() -> None:
    orchestrator = (
        _REPO_ROOT / "quwoquan_ops/cli/commands/app_preflight_uat_platform.py"
    ).read_text(encoding="utf-8")
    binding = (
        _REPO_ROOT / "quwoquan_ops/cli/commands/app_preflight_uat_launch_binding.py"
    ).read_text(encoding="utf-8")
    retry_start = orchestrator.index("direct_retry_reports.append")
    retry_end = orchestrator.index(
        "launch_attempt_path = (",
        retry_start,
    )
    retry_contract = orchestrator[retry_start:retry_end]

    assert "launch_binding_reader(" in retry_contract
    assert "_verified_app_content_projection_build_seal(" not in retry_contract
    assert 'attempt.get("status") != "stopped"' in binding
    assert 'not in {"launched", "stopped"}' not in binding


def test_fresh_launch_report_is_private_and_race_never_replaces_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    report_path = output_root / "attempt-1/report.json"
    report = {
        "schema": "quwoquan_app.test_live_launch",
        "launchStatus": "launched",
    }
    written = launch.write_app_content_launch_report(
        report=report,
        output_root=output_root,
        report_path=report_path,
    )

    assert written["launchReportRef"] == str(report_path)
    assert written["launchReportDigest"].startswith("sha256:")
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="must be fresh"):
        launch.write_app_content_launch_report(
            report=report,
            output_root=output_root,
            report_path=report_path,
        )

    raced_path = output_root / "attempt-2/report.json"
    outside = tmp_path / "outside.json"
    outside.write_text("preserve\n", encoding="utf-8")
    original_fresh_path_under = launch._fresh_path_under

    def create_racing_symlink(path: Path, root: Path, *, label: str) -> Path:
        candidate = original_fresh_path_under(path, root, label=label)
        candidate.symlink_to(outside)
        return candidate

    monkeypatch.setattr(launch, "_fresh_path_under", create_racing_symlink)
    with pytest.raises(FileExistsError):
        launch.write_app_content_launch_report(
            report=report,
            output_root=output_root,
            report_path=raced_path,
        )
    assert outside.read_text(encoding="utf-8") == "preserve\n"
    assert raced_path.is_symlink()
    assert not list(raced_path.parent.glob(".*.tmp"))


def test_postbuild_seal_keeps_supervisor_blocker_primary() -> None:
    launcher = (_REPO_ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    failure_branch = launcher[
        launcher.index('if [[ -n "$first_launch_blocker" ]]') : launcher.index(
            'eval "$seal_exports"'
        )
    ]

    assert failure_branch.index('echo "[run] $first_launch_blocker:') < (
        failure_branch.index("APP.LAUNCH.receipt_invalid: secondary")
    )
    assert 'exit "$FLUTTER_RUN_EXIT_CODE"' in launcher
    assert "write_app_content_launch_report" in launcher
    assert "path.write_text(" not in launcher


def test_fresh_seal_evidence_is_private_and_reread_against_current_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seal = launch.ProjectionBuildSeal(
        policy_id=launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        source_projection_digest="sha256:" + "1" * 64,
        source_entry_count=7,
        derived_output_digest="sha256:" + "2" * 64,
        derived_output_policy_digest="sha256:" + "3" * 64,
        derived_entry_count=11,
        build_projection_digest="sha256:" + "4" * 64,
    )
    output_root = tmp_path / "output"
    projection_root = output_root / "source-projection"
    projection_root.mkdir(parents=True)
    seal_path = output_root / "attempt-1/build-projection-seal.json"
    written = launch.write_app_content_projection_build_seal(
        seal=seal,
        output_root=output_root,
        seal_path=seal_path,
    )
    observed: dict[str, object] = {}

    def recompute(
        _manifest_path: Path,
        _projection_root: Path,
        *,
        policy_id: str,
        expected_build_projection_digest: str | None = None,
    ) -> launch.ProjectionBuildSeal:
        observed.update(
            {
                "policyId": policy_id,
                "expectedBuildProjectionDigest": (expected_build_projection_digest),
            }
        )
        return seal

    monkeypatch.setattr(launch, "seal_projection_build", recompute)
    verified = launch.verify_app_content_projection_build_seal(
        manifest_path=tmp_path / "candidate/input-capsule/manifest.json",
        projection_root=projection_root,
        output_root=output_root,
        seal_path=seal_path,
        expected_seal_digest=str(written["buildProjectionSealDigest"]),
        expected_policy_id=seal.policy_id,
    )

    assert stat.S_IMODE(seal_path.stat().st_mode) == 0o600
    assert verified == written
    assert observed == {
        "policyId": seal.policy_id,
        "expectedBuildProjectionDigest": seal.build_projection_digest,
    }

    tampered = json.loads(seal_path.read_text(encoding="utf-8"))
    tampered["derivedEntryCount"] += 1
    seal_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="seal digest drifted"):
        launch.verify_app_content_projection_build_seal(
            manifest_path=tmp_path / "candidate/input-capsule/manifest.json",
            projection_root=projection_root,
            output_root=output_root,
            seal_path=seal_path,
            expected_seal_digest=str(written["buildProjectionSealDigest"]),
            expected_policy_id=seal.policy_id,
        )


def test_retry_control_mandatorily_binds_expected_projection_digest(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    source_evidence = output_root / "source-projection.json"
    source_evidence.parent.mkdir(parents=True)
    source_evidence.write_text("{}\n", encoding="utf-8")
    control = launch.write_app_content_launch_control(
        runtime_binding={
            "environment": "alpha",
            "target": "alpha-local",
            "candidateDigest": "sha256:" + "a" * 64,
            "packageDigest": "sha256:" + "b" * 64,
            "sourceRevision": "c" * 40,
            "sourceCapsuleDigest": "sha256:" + "d" * 64,
        },
        projection={
            "sourceCapsuleManifestDigest": "sha256:" + "e" * 64,
            "sourceCapsuleManifestRef": str(tmp_path / "capsule/manifest.json"),
            "sourceProjectionRoot": str(output_root / "source-projection"),
            "sourceProjectionEvidenceDigest": "sha256:" + "f" * 64,
            "sourceProjectionEvidenceRef": str(source_evidence),
        },
        output_root=output_root,
        control_path=output_root / "attempt-2/control.json",
        attempt_path=output_root / "attempt-2/attempt.json",
        report_path=output_root / "attempt-2/report.json",
        terminal_receipt_path=output_root / "attempt-2/startup-terminal.json",
        platform="android",
        device_id="emulator-5554",
        build_projection_policy_id=(launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID),
        build_projection_seal_path=(
            output_root / "attempt-2/build-projection-seal.json"
        ),
        expected_build_projection_digest="sha256:" + "9" * 64,
    )

    assert control["expectedBuildProjectionDigest"] == "sha256:" + "9" * 64
    assert not Path(str(control["buildProjectionSealRef"])).exists()
    with pytest.raises(ValueError, match="policy/platform mismatch"):
        launch.write_app_content_launch_control(
            runtime_binding={},
            projection={},
            output_root=output_root,
            control_path=output_root / "wrong/control.json",
            attempt_path=output_root / "wrong/attempt.json",
            report_path=output_root / "wrong/report.json",
            terminal_receipt_path=output_root / "wrong/startup-terminal.json",
            platform="android",
            device_id="emulator-5554",
            build_projection_policy_id=(
                launch.FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
            ),
            build_projection_seal_path=(
                output_root / "wrong/build-projection-seal.json"
            ),
            expected_build_projection_digest=None,
        )
