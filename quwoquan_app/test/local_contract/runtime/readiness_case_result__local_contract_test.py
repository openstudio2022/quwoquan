"""Gamma canonical ReadinessCaseResult migration local contract.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_app.scripts.gamma import gamma_case_result as subject
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    canonical_json_bytes,
    validate_readiness_result_bundle,
    write_create_once_json,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    build_target_uat_binding,
    canonical_target_uat_binding_bytes,
    target_uat_binding_digest,
)

ROOT = Path(__file__).resolve().parents[4]


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _identity() -> dict[str, str]:
    return {
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": _digest("1"),
        "attemptId": "attempt-gamma-1",
        "packageDigest": _digest("2"),
        "configurationDigest": _digest("3"),
        "runtimeConfigDigest": _digest("4"),
        "providerRuntimeDigest": _digest("5"),
        "observabilityLogSinkDigest": _digest("6"),
        "imageDigest": _digest("7"),
        "sourceRevision": "8" * 40,
        "contractGraphSourceHash": "9" * 64,
        "candidateManifestSha256": "a" * 64,
    }


def _binding(*, device_id: str = "emulator-5554") -> dict[str, object]:
    runner = {
        "identity": "gamma-patrol-release-homepage",
        "sourcePath": subject.RUNNER_SOURCE_PATH,
        "digest": _digest("9"),
        "registered": False,
    }
    runtime = {
        "releaseId": "release-gamma-a",
        "manifestDigest": _digest("b"),
        "environment": "gamma",
        "target": "gamma-local",
        "candidateDigest": _digest("1"),
        "packageDigest": _digest("2"),
        "runtimeConfigDigest": _digest("4"),
        "environmentRuntimeDigest": _digest("5"),
        "startupIdentity": {"configurationDigest": _digest("3")},
    }
    launch = {
        "platform": "android",
        "deviceId": device_id,
        "target": "gamma-local",
        "environment": "gamma",
        "artifactDigest": _digest("1"),
        "applicationId": "com.quwoquan.gamma",
    }
    sample_plan = {
        "releaseId": "release-gamma-a",
        "releaseUatSamplePlanRef": "data/releases/release-gamma-a/uat-plan.json",
        "releaseUatSamplePlanDigest": _digest("d"),
    }
    return build_target_uat_binding(
        runtime,
        launch,
        sample_plan,
        active_cas={"ref": "env/gamma/runs/activation/active-cas.json", "digest": _digest("e")},
        readback={"ref": "env/gamma/runs/readback.json", "digest": _digest("f")},
        artifact_class="production_behavior",
        build_mode="debug",
        build_profile="nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": False,
            "conformanceEvidence": {
                "ref": "env/provider/conformance.json",
                "digest": _digest("f"),
            },
        },
        device={"identity": device_id, "class": "simulator", "registered": False},
        runner=runner,
        profile="rehearsal",
        non_promotable=True,
        created_at="2026-08-29T07:00:00Z",
    )


def _patrol(*, device_id: str = "emulator-5554", include_run_device: bool = True) -> dict[str, object]:
    artifact = {
        "status": "passed",
        "deviceId": device_id,
        "buildArtifact": {
            "path": "env/gamma/runs/patrol/app.apk",
            "artifactDigest": _digest("1"),
        },
    }
    execution = {"executed": 2, "skipped": 0, "failed": 0}
    run: dict[str, object] = {
        "exitCode": 0,
        "testExecution": execution,
    }
    if include_run_device:
        run["deviceId"] = device_id
        run["testedAppArtifactBinding"] = artifact
    return {
        "status": "passed",
        "startedAt": "2026-08-29T07:00:00Z",
        "endedAt": "2026-08-29T07:01:00Z",
        "environmentAlias": "local-gamma",
        "runtimeEnv": "gamma",
        "apiContractEnv": "gamma",
        "composition": "production_remote",
        "evidenceClass": "user_acceptance_remote",
        "devices": [
            {
                "id": device_id,
                "targetPlatform": "android-arm64",
                "emulator": True,
            }
        ],
        "runs": [run],
        "caseResults": [
            {
                "deviceId": device_id,
                "status": "passed",
                "testExecution": execution,
            }
        ],
        "testedAppArtifactBinding": {"bindings": [artifact]},
    }


def test_per_cell_result_bundle_passes_canonical_schema(tmp_path: Path) -> None:
    binding = _binding()
    binding_digest = target_uat_binding_digest(binding)
    bundle = subject.build_readiness_result_bundle(
        subject.results_from_patrol(
            report_path=tmp_path / "result.json",
            payload=_patrol(),
            identity=_identity(),
            binding=binding,
            binding_digest=binding_digest,
        ),
        generated_at="2026-08-29T07:01:00Z",
    )
    schema = json.loads(
        (
            ROOT
            / "quwoquan_service/contracts/metadata/_schemas/readiness_result_bundle.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(bundle)
    result = bundle["results"][0]
    assert result["status"] == "passed"
    assert result["specRef"] == subject.SPEC_REF
    assert result["targetUatBindingDigest"] == binding_digest
    assert result["entrySurface"] == "direct_or_object_route"
    assert result["carrier"] == "homepage"
    assert "schema" not in result
    assert "specRefs" not in result


def test_missing_independent_run_cell_is_blocked_not_guessed_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subject, "output_root", lambda: tmp_path)
    binding = _binding()
    results = subject.results_from_patrol(
        report_path=tmp_path / "env/gamma/runs/result.json",
        payload=_patrol(include_run_device=False),
        identity=_identity(),
        binding=binding,
        binding_digest=target_uat_binding_digest(binding),
    )
    assert [result["status"] for result in results] == ["blocked"]
    assert (tmp_path / results[0]["artifactPath"]).is_file()
    validate_readiness_result_bundle(
        {"generatedAt": results[0]["completedAt"], "results": results}
    )


def test_binding_bytes_must_be_canonical_and_exact_target(tmp_path: Path) -> None:
    binding = _binding()
    path = tmp_path / "binding.json"
    path.write_bytes(canonical_target_uat_binding_bytes(binding))
    loaded, digest = subject.load_target_uat_binding(path)
    assert loaded == binding
    assert digest == target_uat_binding_digest(binding)

    path.write_text(json.dumps(binding, indent=2), encoding="utf-8")
    with pytest.raises(subject.GammaCaseResultError, match="canonical"):
        subject.load_target_uat_binding(path)


def test_create_once_allows_exact_replay_and_rejects_any_status_rewrite(
    tmp_path: Path,
) -> None:
    value = {"generatedAt": "2026-08-29T07:01:00Z", "results": []}
    destination = write_create_once_json(tmp_path / "raw.json", value)
    inode = destination.stat().st_ino
    assert write_create_once_json(destination, dict(value)).stat().st_ino == inode
    changed = {"generatedAt": "2026-08-29T07:02:00Z", "results": []}
    with pytest.raises(ReadinessCaseResultError, match="different bytes"):
        write_create_once_json(destination, changed)
    assert destination.read_bytes() == canonical_json_bytes(value)


def test_multiple_devices_require_separate_exact_bindings(tmp_path: Path) -> None:
    binding = _binding(device_id="emulator-5554")
    patrol = _patrol(device_id="emulator-5554")
    patrol["devices"].append(
        {"id": "emulator-5556", "targetPlatform": "android-arm64", "emulator": True}
    )
    results = subject.results_from_patrol(
        report_path=tmp_path / "result.json",
        payload=patrol,
        identity=_identity(),
        binding=binding,
        binding_digest=target_uat_binding_digest(binding),
    )
    assert len(results) == 1
    assert results[0]["platform"] == "android"
    assert results[0]["deviceClass"] == "simulator"


def test_blocker_artifact_digest_binds_exact_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "output_root", lambda: tmp_path)
    digest, ref = subject.write_blocker_artifact(
        report_path=tmp_path / "env/gamma/runs/result.json",
        reason="target binding field is missing",
        slot_identity={"platform": "android", "deviceClass": "simulator"},
    )
    assert hashlib.sha256((tmp_path / ref).read_bytes()).hexdigest() == digest
