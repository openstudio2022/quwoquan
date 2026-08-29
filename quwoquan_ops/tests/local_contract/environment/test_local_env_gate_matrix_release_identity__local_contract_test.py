"""local_contract：三环境 release train 与 target package baseline 身份。

spec_ref: runtime/runtime-config/environment-topology-and-packaging/GWT-002
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod
from quwoquan_ops.cli.lib.local_env_gate_matrix import orchestrator

RELEASE_TRAIN_ID = f"sha256:{'9' * 64}"
PACKAGE_DIGEST = f"sha256:{'8' * 64}"
TARGET_BASELINES = {
    "alpha-local": f"sha256:{'a' * 64}",
    "beta-local": f"sha256:{'b' * 64}",
    "gamma-local": f"sha256:{'c' * 64}",
}
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}


def _release_attestation(
    *,
    release_id: str,
    digest_char: str,
    release_class: str = "commercial",
    release_kind: str = "standard",
    contains_unverified_assets: bool = False,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "releaseKind": release_kind,
        "payloadSha256": f"sha256:{digest_char * 64}",
        "releaseClass": release_class,
        "productLifecycleState": release_class,
        "containsUnverifiedAssets": contains_unverified_assets,
    }


def _active_candidate_snapshot(
    target: str,
    *,
    release_train_id: str = RELEASE_TRAIN_ID,
) -> dict[str, object]:
    baseline = TARGET_BASELINES[target]
    candidate_dir = f"/tmp/quwoquan-matrix/{target}/{baseline}"
    return {
        "target": target,
        "baselineId": baseline,
        "candidateDir": candidate_dir,
        "manifest": {
            "target": target,
            "environment": TARGET_ENVIRONMENTS[target],
            "baselineId": baseline,
            "packageDigest": PACKAGE_DIGEST,
            "environmentArtifact": {
                "target": target,
                "environment": TARGET_ENVIRONMENTS[target],
                "releaseTrainId": release_train_id,
                "packageDigest": PACKAGE_DIGEST,
                "environmentArtifactDigest": f"sha256:{'7' * 64}",
                "sourceCapsule": {"baselineId": baseline},
            },
        },
    }


def _package_payload(target: str) -> dict[str, object]:
    snapshot = _active_candidate_snapshot(target)
    return {
        "baselineId": TARGET_BASELINES[target],
        "candidateDir": snapshot["candidateDir"],
        "packageDigest": PACKAGE_DIGEST,
    }


def test_three_target_baselines_share_one_release_train() -> None:
    package_baselines: dict[str, str] = {}
    release_train_id = ""
    for target in matrix_mod.CANONICAL_TARGETS:
        identity = matrix_mod._package_candidate_release_identity(
            _package_payload(target),
            _active_candidate_snapshot(target),
            target=target,
        )
        release_train_id = matrix_mod._freeze_matrix_package_identity(
            identity,
            release_train_id=release_train_id,
            package_baselines=package_baselines,
        )

    assert release_train_id == RELEASE_TRAIN_ID
    assert package_baselines == TARGET_BASELINES
    assert len(set(package_baselines.values())) == 3


def test_release_train_drift_is_rejected_before_patrol() -> None:
    package_baselines: dict[str, str] = {}
    alpha = matrix_mod._package_candidate_release_identity(
        _package_payload("alpha-local"),
        _active_candidate_snapshot("alpha-local"),
        target="alpha-local",
    )
    release_train_id = matrix_mod._freeze_matrix_package_identity(
        alpha,
        release_train_id="",
        package_baselines=package_baselines,
    )
    beta = matrix_mod._package_candidate_release_identity(
        _package_payload("beta-local"),
        _active_candidate_snapshot(
            "beta-local",
            release_train_id=f"sha256:{'6' * 64}",
        ),
        target="beta-local",
    )

    with pytest.raises(ValueError, match="releaseTrainId drifted"):
        matrix_mod._freeze_matrix_package_identity(
            beta,
            release_train_id=release_train_id,
            package_baselines=package_baselines,
        )
    assert package_baselines == {
        "alpha-local": TARGET_BASELINES["alpha-local"]
    }


def test_target_baseline_drift_is_rejected_before_patrol() -> None:
    drifted = _active_candidate_snapshot("beta-local")
    manifest = drifted["manifest"]
    assert isinstance(manifest, dict)
    manifest["baselineId"] = f"sha256:{'5' * 64}"

    with pytest.raises(ValueError, match="manifest/sourceCapsule"):
        matrix_mod._package_candidate_release_identity(
            _package_payload("beta-local"),
            drifted,
            target="beta-local",
        )


@pytest.mark.parametrize(
    ("drift", "failure_category"),
    (("release_train", "release_train_drift"), ("target_baseline", "package_identity")),
)
def test_matrix_freezes_all_package_identities_before_any_patrol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift: str,
    failure_category: str,
) -> None:
    candidate = tmp_path / "candidate.json"
    rollback = tmp_path / "rollback.json"
    for path, release_id, digest_char in (
        (candidate, "candidate-release", "1"),
        (rollback, "rollback-release", "2"),
    ):
        path.write_text(
            json.dumps(
                _release_attestation(
                    release_id=release_id,
                    digest_char=digest_char,
                )
            ),
            encoding="utf-8",
        )

    package_targets: list[str] = []

    def package(args: object) -> dict[str, object]:
        target = str(args.target)
        package_targets.append(target)
        return {"exitCode": 0, **_package_payload(target)}

    def active(target: str) -> dict[str, object]:
        snapshot = _active_candidate_snapshot(
            target,
            release_train_id=(
                f"sha256:{'6' * 64}"
                if drift == "release_train" and target == "beta-local"
                else RELEASE_TRAIN_ID
            ),
        )
        if drift == "target_baseline" and target == "beta-local":
            manifest = snapshot["manifest"]
            assert isinstance(manifest, dict)
            manifest["baselineId"] = f"sha256:{'5' * 64}"
        return snapshot

    runtime_runner = mock.Mock(return_value={"exitCode": 0})
    down_runner = mock.Mock(return_value={"exitCode": 0})
    patrol_runner = mock.Mock(return_value={"exitCode": 0})
    matrix_dir = tmp_path / "matrix"

    def write_timing(path: Path, **_kwargs: object) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        timing_path = path / "timing.json"
        timing_path.write_text("{}\n", encoding="utf-8")
        return timing_path

    monkeypatch.setattr(orchestrator, "_docker_daemon_ready", lambda: (True, "ok"))
    monkeypatch.setattr(orchestrator, "_repo_matrix_dir", lambda _run_id: matrix_dir)
    monkeypatch.setattr(matrix_mod, "write_timing_bundle", write_timing)
    monkeypatch.setattr(matrix_mod, "active_deployment_candidate_snapshot", active)

    result = orchestrator._run_local_env_gate_matrix(
        package_fn=package,
        up_fn=runtime_runner,
        health_fn=runtime_runner,
        verify_fn=runtime_runner,
        down_fn=down_runner,
        app_uat_fn=patrol_runner,
        include_l0=False,
        release_attestation=str(candidate),
        rollback_release_attestation=str(rollback),
        execution_class="contract-simulation",
        matrix_run_id=f"matrix-{drift}",
    )

    receipt = json.loads((matrix_dir / "matrix.json").read_text(encoding="utf-8"))
    assert result["exitCode"] == 2
    assert receipt["failureCategory"] == failure_category
    assert package_targets == ["alpha-local", "beta-local"]
    runtime_runner.assert_not_called()
    assert down_runner.call_count == 6
    patrol_runner.assert_not_called()


def test_uat_identity_uses_exact_target_baseline_not_empty_scalar() -> None:
    beta_baseline = TARGET_BASELINES["beta-local"]
    valid = {
        "releaseTrainId": RELEASE_TRAIN_ID,
        "packageBaselines": TARGET_BASELINES,
        "runtimeBindings": {
            target: {"candidateDigest": baseline}
            for target, baseline in TARGET_BASELINES.items()
        },
    }
    assert matrix_mod._uat_matches_package_identity(
        valid,
        target="beta-local",
        release_train_id=RELEASE_TRAIN_ID,
        baseline_id=beta_baseline,
    )
    invalid_receipts = (
        {**valid, "packageBaselines": {}, "packageBaseline": ""},
        {
            **valid,
            "packageBaselines": {
                "alpha-local": TARGET_BASELINES["alpha-local"]
            },
        },
        {
            **valid,
            "runtimeBindings": {
                **valid["runtimeBindings"],
                "beta-local": {
                    "candidateDigest": TARGET_BASELINES["alpha-local"]
                },
            },
        },
    )
    assert all(
        not matrix_mod._uat_matches_package_identity(
            receipt,
            target="beta-local",
            release_train_id=RELEASE_TRAIN_ID,
            baseline_id=beta_baseline,
        )
        for receipt in invalid_receipts
    )


def _write_matrix_receipt(
    matrix_dir: Path,
    *,
    package_baselines: dict[str, str],
    device_profile: str,
) -> tuple[dict[str, object], dict[str, object]]:
    result = matrix_mod._write_matrix_result(
        matrix_dir=matrix_dir,
        phases=[{"name": "matrix", "status": "passed"}],
        environments={target: {} for target in matrix_mod.CANONICAL_TARGETS},
        budgets={"softBudgetSeconds": 600, "hardBudgetSeconds": 1800},
        wall_seconds=1.0,
        exit_code=0,
        failure_category="",
        release_train_id=RELEASE_TRAIN_ID,
        package_baselines=package_baselines,
        release={
            "releaseId": "release-identity",
            "releaseDigest": f"sha256:{'4' * 64}",
        },
        matrix_run_id="matrix-release-identity",
        execution_class="live",
        device_profile=device_profile,
    )
    receipt = json.loads((matrix_dir / "matrix.json").read_text(encoding="utf-8"))
    return result, receipt


def test_matrix_receipt_persists_release_train_and_target_baselines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        matrix_mod,
        "write_timing_bundle",
        lambda *_args, **_kwargs: tmp_path / "timing.json",
    )
    bindings = matrix_mod._device_uat_bindings(
        device_profile=matrix_mod.DEVICE_PROFILE_EMULATOR_ONLY,
        ios_simulator_device="ios-simulator-udid",
        android_emulator_device="emulator-5554",
        android_physical_device="",
    )
    result, receipt = _write_matrix_receipt(
        tmp_path,
        package_baselines=TARGET_BASELINES,
        device_profile=matrix_mod.DEVICE_PROFILE_EMULATOR_ONLY,
    )

    assert tuple(key for key, _, _ in bindings) == (
        "iosSimulatorUAT",
        "androidEmulatorUAT",
    )
    assert result["claim"] == matrix_mod.EMULATOR_ONLY_CLAIM
    assert result["releaseTrainId"] == RELEASE_TRAIN_ID
    assert receipt["packageBaselines"] == TARGET_BASELINES
    assert "baselineId" not in receipt
    assert receipt["nonPromotable"] is True


def test_matrix_receipt_rejects_incomplete_target_baseline_map(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        matrix_mod,
        "write_timing_bundle",
        lambda *_args, **_kwargs: tmp_path / "timing.json",
    )
    result, receipt = _write_matrix_receipt(
        tmp_path,
        package_baselines={"alpha-local": TARGET_BASELINES["alpha-local"]},
        device_profile=matrix_mod.DEVICE_PROFILE_FULL,
    )

    assert result["claim"] == "GATE_BLOCK"
    assert receipt["failureCategory"] == "receipt_identity"


def test_release_binding_validates_and_returns_lifecycle_identity(
    tmp_path: Path,
) -> None:
    attestation = tmp_path / "research.json"
    attestation.write_text(
        json.dumps(
            _release_attestation(
                release_id="research-release",
                digest_char="3",
                release_class="research",
                contains_unverified_assets=True,
            )
        ),
        encoding="utf-8",
    )

    binding = matrix_mod._release_binding(str(attestation), label="candidate")

    assert binding["releaseClass"] == "research"
    assert binding["productLifecycleState"] == "research"
    assert binding["containsUnverifiedAssets"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("releaseClass", "preview"),
        ("productLifecycleState", "preview"),
        ("containsUnverifiedAssets", "false"),
    ),
)
def test_release_binding_rejects_invalid_lifecycle_identity(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    attestation = tmp_path / f"invalid-{field}.json"
    payload = _release_attestation(release_id="invalid-release", digest_char="4")
    payload[field] = value
    attestation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="lifecycle identity is invalid"):
        matrix_mod._release_binding(str(attestation), label="candidate")


@pytest.mark.parametrize(
    ("candidate_class", "rollback_class", "rollback_kind"),
    (
        ("research", "commercial", "standard"),
        ("commercial", "research", "empty_baseline"),
    ),
)
def test_matrix_rejects_research_release_before_any_mutation(
    tmp_path: Path,
    candidate_class: str,
    rollback_class: str,
    rollback_kind: str,
) -> None:
    candidate = tmp_path / "candidate.json"
    rollback = tmp_path / "rollback.json"
    candidate.write_text(
        json.dumps(
            _release_attestation(
                release_id="candidate-release",
                digest_char="1",
                release_class=candidate_class,
            )
        ),
        encoding="utf-8",
    )
    rollback.write_text(
        json.dumps(
            _release_attestation(
                release_id="rollback-release",
                digest_char="2",
                release_class=rollback_class,
                release_kind=rollback_kind,
            )
        ),
        encoding="utf-8",
    )
    package = mock.Mock(return_value={"exitCode": 0})
    runtime = mock.Mock(return_value={"exitCode": 0})
    down = mock.Mock(return_value={"exitCode": 0})
    data = mock.Mock(return_value={"exitCode": 0})

    result = orchestrator._run_local_env_gate_matrix(
        package_fn=package,
        up_fn=runtime,
        health_fn=runtime,
        verify_fn=runtime,
        down_fn=down,
        data_fn=data,
        include_l0=False,
        release_attestation=str(candidate),
        rollback_release_attestation=str(rollback),
        execution_class="contract-simulation",
        matrix_run_id="matrix-research-must-fail-fast",
    )

    assert result["exitCode"] == 2
    assert result["claim"] == "GATE_BLOCK"
    assert result["failureCategory"] == "research_lifecycle_unsupported"
    assert "matrix is commercial-only" in result["details"][0]
    assert "canonical Research lifecycle" in result["details"][0]
    package.assert_not_called()
    runtime.assert_not_called()
    down.assert_not_called()
    data.assert_not_called()
