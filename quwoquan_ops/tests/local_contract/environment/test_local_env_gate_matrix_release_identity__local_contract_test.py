"""local_contract：三环境 release train 与 target package baseline 身份。

spec_ref: runtime/runtime-config/environment-topology-and-packaging/GWT-002
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
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
    release_kind: str = "content",
    contains_unverified_assets: bool = False,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "releaseKind": release_kind,
        "payloadSha256": f"sha256:{digest_char * 64}",
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
    from quwoquan_ops.tests.local_contract.environment.test_local_env_gate_matrix__local_contract_test import _matrix_release_inputs

    inputs = _matrix_release_inputs(tmp_path)
    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)

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
        **inputs,
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


@pytest.mark.parametrize("contains_unverified_assets", [False, True])
def test_release_binding_preserves_rights_without_category_projection(
    tmp_path: Path, contains_unverified_assets: bool,
) -> None:
    attestation = tmp_path / "release.json"
    attestation.write_text(json.dumps(_release_attestation(
        release_id="default-release", digest_char="3",
        contains_unverified_assets=contains_unverified_assets,
    )), encoding="utf-8")

    binding = matrix_mod._release_binding(str(attestation), label="candidate")

    assert binding == {
        "releaseId": "default-release", "releaseDigest": f"sha256:{'3' * 64}",
        "containsUnverifiedAssets": contains_unverified_assets,
        "attestation": str(attestation),
    }

@pytest.mark.parametrize("value", [None, "false", 0, 1])
def test_release_binding_rejects_invalid_rights_identity(tmp_path: Path, value: object) -> None:
    attestation = tmp_path / "invalid-rights.json"
    payload = _release_attestation(release_id="invalid-release", digest_char="4")
    payload["containsUnverifiedAssets"] = value
    attestation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="rights identity is invalid"):
        matrix_mod._release_binding(str(attestation), label="candidate")


@pytest.mark.parametrize("prefix", ["candidate", "rollback"])
@pytest.mark.parametrize("field", ["releaseClass", "productLifecycleState", "readinessPhase"])
@pytest.mark.parametrize("value", [None, "production", "research"])
def test_retired_category_fields_block_before_any_environment_action(
    tmp_path: Path, prefix: str, field: str, value: object,
) -> None:
    paths = {}
    for label, digest_char in (("candidate", "1"), ("rollback", "2")):
        payload = _release_attestation(release_id=f"{label}-release", digest_char=digest_char)
        if label == prefix:
            payload[field] = value
        path = tmp_path / f"{label}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[label] = str(path)
    effect = mock.Mock(side_effect=AssertionError("environment must not execute"))
    result = orchestrator._run_local_env_gate_matrix(
        package_fn=effect, up_fn=effect, health_fn=effect, verify_fn=effect, down_fn=effect,
        release_attestation=paths["candidate"], rollback_release_attestation=paths["rollback"],
        execution_class="contract-simulation", matrix_run_id="retired-category",
    )
    assert result["exitCode"] == 2 and result["executed"] == 0
    assert "retired category fields" in " ".join(result["details"])
    effect.assert_not_called()


@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma", "prod"])
@pytest.mark.parametrize("kind", ["apply", "activate", "rollback", "verify"])
def test_actual_data_parser_has_no_release_category_or_readiness_phase(environment, kind):
    from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import _parse_data_args

    argv = ["ship", kind, "--handoff-ref",
            f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}",
            "--env", environment, "--run-id", "parser-contract"]
    if kind != "apply":
        argv.extend(("--import-run-id", "exact-predecessor"))
    if kind == "rollback":
        argv.extend(("--from-release-id", "current-release", "--from-manifest-digest",
                     f"sha256:{'3' * 64}", "--from-revision", "7"))
    args = _parse_data_args(argv)
    assert args.ship_command == kind and args.env == environment
    assert not {"readiness_phase", "release_class", "product_lifecycle_state"}.intersection(vars(args))
    with pytest.raises(SystemExit) as rejected:
        _parse_data_args([*argv, "--readiness-phase", "production"])
    assert rejected.value.code == 2


@pytest.mark.parametrize("passed", [True, False])
def test_homepage_evidence_requires_passed_default_readiness(tmp_path, passed):
    from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import _homepage_release_evidence

    path = tmp_path / "release-readiness.json"
    path.write_text(json.dumps({
        "schema": "quwoquan_data.environment_release_readiness", "environment": "alpha",
        "releaseId": "default-release", "passed": passed,
        "feedQueries": [{"name": "homepage_recommend", "status": 200,
                         "releaseBound": True, "matchedPostIds": ["post-1"]}],
    }))
    result = _homepage_release_evidence(readiness_path=path, environment="alpha", release_id="default-release")
    assert result["exitCode"] == (0 if passed else 2)


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
@pytest.mark.parametrize("drift", ["", "prepared-as-activated", "query-release", "query-digest", "query-revision",
                                   "replay-digest", "rollback-predecessor", "candidate-verify"])
def test_data_lifecycle_parser_exact_predecessors_and_first_error(tmp_path, monkeypatch, drift):
    from quwoquan_ops.tests.local_contract.environment.test_local_env_gate_matrix__local_contract_test import (
        _matrix_data_runner, _matrix_release_inputs,
    )
    from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import _run_data_lifecycle, _parse_data_args
    from quwoquan_ops.cli.lib.local_env_gate_matrix.input_validation import _release_admission_binding

    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)
    inputs = _matrix_release_inputs(tmp_path)
    bindings = []
    for prefix in ("release", "rollback_release"):
        binding = matrix_mod._release_binding(inputs[f"{prefix}_attestation"], label=prefix)
        bindings.append(_release_admission_binding(
            binding, handoff_ref="", system_attestation_ref=inputs[f"{prefix}_system_attestation_ref"],
            system_attestation_digest=inputs[f"{prefix}_system_attestation_digest"],
        ))
    calls, phases, block = [], [], {}
    ids = matrix_mod._data_run_ids("contract-matrix", "alpha")
    exit_code, category = _run_data_lifecycle(
        phases=phases, block=block, target="alpha-local", environment="alpha",
        candidate=bindings[0], rollback=bindings[1], data_ids=ids,
        data_fn=_matrix_data_runner(tmp_path, calls, drift=drift),
    )
    args = [_parse_data_args(call["argv"][2:]) for call in calls if call["argv"]]
    assert args[0].ship_command == "apply"
    assert args[1].ship_command == "activate"
    assert args[1].import_run_id == args[0].run_id
    if not drift:
        assert (exit_code, category) == (0, "")
        assert [arg.ship_command for arg in args] == [
            "apply", "activate", "verify", "apply", "rollback", "verify", "apply", "activate", "verify"]
        assert all(not hasattr(arg, "readiness_phase") for arg in args)
        assert all("--readiness-phase" not in call["argv"] for call in calls)
        assert all(not {"releaseClass", "productLifecycleState", "readinessPhase"}.intersection(
            item.get("result", {})) for item in block.values())
        assert args[2].import_run_id == args[1].run_id
        assert args[4].import_run_id == args[3].run_id
        assert args[4].from_release_id == bindings[0]["releaseId"]
        assert args[4].from_manifest_digest == bindings[0]["releaseDigest"]
        assert args[4].from_revision == 1
        assert args[5].import_run_id == args[4].run_id
        assert args[6].system_attestation_ref == args[0].system_attestation_ref
        assert args[6].system_attestation_digest == args[0].system_attestation_digest
        assert args[8].import_run_id == args[7].run_id
    else:
        assert exit_code != 0 and category
        expected_last = {"prepared-as-activated": "candidate-activate", "query-release": "rollback-active-query",
                         "query-digest": "rollback-active-query", "query-revision": "rollback-active-query",
                         "replay-digest": "replay-activate",
                         "rollback-predecessor": "rollback-apply", "candidate-verify": "candidate-verify"}
        assert calls[-1]["action"] == expected_last[drift]
        if drift == "candidate-verify":
            assert exit_code == 17


@pytest.mark.parametrize("missing", ["none", "both", "pair-ref", "pair-digest", "handoff-with-digest"])
def test_explicit_admission_is_required_and_exclusive_before_mutation(tmp_path, monkeypatch, missing):
    from quwoquan_ops.tests.local_contract.environment.test_local_env_gate_matrix__local_contract_test import _matrix_release_inputs

    inputs = _matrix_release_inputs(tmp_path)
    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)
    if missing in {"none", "pair-digest"}:
        inputs.pop("release_system_attestation_ref")
    if missing in {"none", "pair-ref", "both"}:
        inputs.pop("release_system_attestation_digest")
    if missing in {"both", "handoff-with-digest"}:
        inputs["release_handoff_ref"] = f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}"
    if missing == "handoff-with-digest":
        inputs.pop("release_system_attestation_ref")
    effect = mock.Mock(side_effect=AssertionError("environment must not execute"))
    result = orchestrator._run_local_env_gate_matrix(
        package_fn=effect, up_fn=effect, health_fn=effect, verify_fn=effect, down_fn=effect,
        **inputs, execution_class="contract-simulation", matrix_run_id="invalid-admission",
    )
    assert result["exitCode"] == 2 and result["executed"] == 0
    effect.assert_not_called()


@pytest.mark.parametrize("field", ["releaseId", "releaseDigest", "attestation"])
def test_admission_revalidates_current_full_package_identity(tmp_path, monkeypatch, field):
    from quwoquan_ops.tests.local_contract.environment.test_local_env_gate_matrix__local_contract_test import _matrix_release_inputs
    from quwoquan_ops.cli.lib.local_env_gate_matrix.input_validation import _release_admission_binding

    inputs = _matrix_release_inputs(tmp_path)
    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)
    binding = matrix_mod._release_binding(inputs["release_attestation"], label="candidate")
    if field == "attestation":
        package = tmp_path / "package.json"
        payload = json.loads(Path(inputs["release_attestation"]).read_text())
        payload["recordedAt"] = "2026-09-06T00:00:00Z"
        package.write_text(json.dumps(payload))
        binding[field] = str(package)
    else:
        binding[field] = "wrong-identity"
    with pytest.raises(ValueError, match="differs from package attestation identity"):
        _release_admission_binding(
            binding, handoff_ref="", system_attestation_ref=inputs["release_system_attestation_ref"],
            system_attestation_digest=inputs["release_system_attestation_digest"],
        )


def test_handoff_admission_uses_current_data_authority(tmp_path, monkeypatch):
    from quwoquan_data.scripts import cli  # noqa: F401
    from quwoquan_data.tests.local_contract.release.test_ship_handoff_admission__contract__local_contract_test import (
        _release_and_handoff, _authority_ref, _sha,
    )
    from content.release.environment import release_runtime
    from quwoquan_ops.cli.lib.local_env_gate_matrix.input_validation import _release_admission_binding

    release, handoff, document = _release_and_handoff(tmp_path)
    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)
    validate = mock.Mock(return_value={"artifacts": [str(handoff)]})
    monkeypatch.setattr(release_runtime.handoff_store, "read", lambda *_a, **_kw: b"authority")
    monkeypatch.setattr(release_runtime.handoff_consumer, "validate_published_bytes", validate)
    monkeypatch.setattr(release_runtime.handoff_store, "resolve_unique_artifact", lambda *_a, **_kw: (
        "data/releases/release-a/producer_release_handoff.json", handoff, handoff.read_bytes(), _sha(handoff)))
    monkeypatch.setattr(release_runtime, "read_producer_release_handoff", lambda *_a, **_kw: document)
    attestation = release / "attestations/release.json"
    attestation.parent.mkdir(parents=True)
    attestation.write_text(json.dumps({**_release_attestation(release_id="release-a", digest_char="1"),
                                      "payloadSha256": document["release"]["payloadDigest"]}))
    binding = matrix_mod._release_binding(str(attestation), label="candidate")
    admitted = _release_admission_binding(binding, handoff_ref=_authority_ref(),
                                        system_attestation_ref="", system_attestation_digest="")
    assert admitted["admissionArgv"] == ["--handoff-ref", _authority_ref()]
    assert admitted["admissionEnvelope"]["handoffRef"] == _authority_ref()
    assert validate.call_args.kwargs["validate_current"] is True


def test_matrix_parser_delegates_explicit_candidate_and_rollback_admission(monkeypatch):
    import argparse
    import sys
    from types import SimpleNamespace
    from quwoquan_ops.cli.commands import matrix_domain

    captured = mock.Mock(return_value={"exitCode": 0})
    facade = SimpleNamespace(
        PROFILE_LOCAL_ENV_GATE=matrix_mod.PROFILE_LOCAL_ENV_GATE,
        CANONICAL_LOCAL_GATE_TARGETS=matrix_mod.CANONICAL_TARGETS,
        LOCAL_GATE_DEVICE_PROFILE_FULL=matrix_mod.DEVICE_PROFILE_FULL,
        LOCAL_GATE_DEVICE_PROFILES=matrix_mod.DEVICE_PROFILES,
        run_local_env_gate_matrix=captured,
    )
    for name in ("package", "up", "health", "verify", "down", "product_telemetry_log_sink",
                 "provider_conformance", "app_content_uat", "filter_catalog"):
        setattr(facade, f"command_{name}", mock.Mock())
    import quwoquan_ops.cli as ops_cli
    monkeypatch.setitem(sys.modules, "quwoquan_ops.cli.stackctl", facade)
    monkeypatch.setattr(ops_cli, "stackctl", facade, raising=False)
    parser = argparse.ArgumentParser()
    matrix_domain.register_parser(parser.add_subparsers(dest="command", required=True))
    root = ["matrix", "--targets", "alpha-local,beta-local,gamma-local",
            "--release-attestation", "candidate.json", "--rollback-release-attestation", "rollback.json",
            "--test-data-request", "alpha-local=request.json", "--test-data-handoff", "alpha-local=handoff.json",
            "--ios-simulator-device", "sim", "--android-emulator-device", "emulator"]
    handoff = f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}"
    explicit = ["--release-handoff-ref", handoff, "--rollback-release-system-attestation-ref",
                "data/releases/empty/attestations/release.json", "--rollback-release-system-attestation-digest",
                f"sha256:{'3' * 64}"]
    for missing in (root, root + explicit[:2]):
        with pytest.raises(SystemExit):
            parser.parse_args(missing)
    with pytest.raises(SystemExit):
        parser.parse_args(root + explicit + ["--release-system-attestation-ref", "conflict"])
    args = parser.parse_args(root + explicit)
    assert matrix_domain.command_matrix(args) == {"exitCode": 0}
    assert captured.call_args.kwargs["release_handoff_ref"] == handoff
    assert captured.call_args.kwargs["rollback_release_system_attestation_digest"] == f"sha256:{'3' * 64}"
    assert captured.call_args.kwargs["targets"] == matrix_mod.CANONICAL_TARGETS


def test_cleanup_failure_does_not_replace_first_data_blocker(tmp_path, monkeypatch):
    from quwoquan_ops.tests.local_contract.environment.test_local_env_gate_matrix__local_contract_test import (
        _matrix_release_inputs, _matrix_data_runner,
    )
    from types import SimpleNamespace

    inputs = _matrix_release_inputs(tmp_path)
    monkeypatch.setattr(matrix_mod, "output_root", lambda: tmp_path)
    monkeypatch.setattr(matrix_mod, "active_deployment_candidate_snapshot", _active_candidate_snapshot)
    monkeypatch.setattr(matrix_mod, "probe_migration_drift", lambda *_: SimpleNamespace(has_drift=False, detail="simulation"))
    monkeypatch.setattr(orchestrator, "_docker_daemon_ready", lambda: (True, "simulation"))
    calls = []
    started = []
    def up(_args):
        started.append(True)
        return {"exitCode": 0}
    result = orchestrator._run_local_env_gate_matrix(
        package_fn=lambda args: {"exitCode": 0, **_package_payload(args.target)},
        up_fn=up, health_fn=lambda *_: {"exitCode": 0}, verify_fn=mock.Mock(),
        down_fn=lambda *_: {"exitCode": 19 if started else 0},
        data_fn=_matrix_data_runner(tmp_path, calls, drift="candidate-verify"),
        **inputs, include_l0=False, execution_class="contract-simulation", matrix_run_id="first-error",
    )
    receipt = json.loads((Path(result["reportDir"]) / "matrix.json").read_text())
    assert result["exitCode"] == 17
    assert receipt["failureCategory"] == "data_candidate_verify"
    assert calls[-1]["action"] == "candidate-verify"
    assert receipt["nonPromotable"] is True

def test_promotion_device_profile_requires_android_and_ios_physical_bindings(monkeypatch) -> None:
    calls = []
    def run(argv, **_kwargs):
        calls.append(argv)
        if argv[1:3] == ["simctl", "list"]:
            return mock.Mock(returncode=0, stdout=json.dumps({"devices": {"runtime": [{"udid": "sim-1", "isAvailable": True}]}}))
        if argv[1:3] == ["devicectl", "list"]:
            return mock.Mock(returncode=0, stdout=json.dumps({"devices": [{"identifier": "ios-physical-1"}]}))
        if "get-state" in argv:
            return mock.Mock(returncode=0, stdout="device\n")
        if "ro.kernel.qemu" in argv:
            return mock.Mock(returncode=0, stdout="1\n" if "emulator-1" in argv else "0\n")
        return mock.Mock(returncode=0, stdout="0\n")
    monkeypatch.setattr(matrix_mod.subprocess, "run", run)
    assert matrix_mod._device_binding_errors(
        device_profile=matrix_mod.DEVICE_PROFILE_FULL, ios_simulator_device="sim-1",
        android_emulator_device="emulator-1", android_physical_device="android-physical-1",
        ios_physical_device="ios-physical-1",
    ) == []
    bindings = matrix_mod._device_uat_bindings(
        device_profile=matrix_mod.DEVICE_PROFILE_FULL, ios_simulator_device="sim-1",
        android_emulator_device="emulator-1", android_physical_device="android-physical-1",
        ios_physical_device="ios-physical-1",
    )
    assert ("iosPhysicalUAT", "ios-physical", "ios-physical-1") in bindings
