"""The release policy selects one minimal capability slice, never all environments."""
from __future__ import annotations

import argparse
from pathlib import Path

from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeSource,
    ReadinessCapability,
    ReadinessPhase,
    VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli import stackctl


def test_content_release_readiness__maps_phase_to_environment_capabilities__local_contract() -> None:
    policy = load_content_release_readiness_policy()

    alpha_import = policy.requirement_for(
        phase=ReadinessPhase.IMPORT,
        environment="alpha",
    )
    beta_import = policy.requirement_for(
        phase=ReadinessPhase.IMPORT,
        environment="beta",
    )
    gamma_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="gamma",
    )
    gamma_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="gamma",
    )
    beta_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="beta",
    )

    assert alpha_import.workload == "content-release"
    assert beta_import.workload == "content-release"
    assert gamma_consumer.health_scope == "content-consumer"
    assert ReadinessCapability.TELEMETRY_SLS not in beta_import.capabilities
    assert ReadinessCapability.TELEMETRY_SLS in gamma_commercial.capabilities
    assert beta_commercial.workload == "full"


def test_content_release_readiness__binds_probe_for_every_capability__local_contract() -> None:
    policy = load_content_release_readiness_policy()

    for capability in ReadinessCapability:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE:
            assert binding.health_scope
        else:
            assert binding.source is ProbeSource.COMMERCIAL_DOCTOR
            assert binding.health_scope is None

    assert policy.probe_binding_for(ReadinessCapability.CONTENT_SERVICES).health_scope == "content-import"
    assert policy.probe_binding_for(ReadinessCapability.TELEMETRY_SLS).source is ProbeSource.COMMERCIAL_DOCTOR


def test_content_release_readiness__doctor_bound_capabilities_are_commercial_only__local_contract() -> None:
    policy = load_content_release_readiness_policy()

    for requirement in policy.requirements:
        if requirement.phase is ReadinessPhase.COMMERCIAL:
            continue
        for capability in requirement.capabilities:
            assert policy.probe_binding_for(capability).source is ProbeSource.HEALTH_SCOPE


def test_content_release_readiness__rejects_undefined_phase_environment__local_contract() -> None:
    policy = load_content_release_readiness_policy()
    try:
        policy.requirement_for(phase=ReadinessPhase.CONSUMER, environment="alpha")
    except ValueError as exc:
        assert "does not define" in str(exc)
    else:
        raise AssertionError("undefined phase/environment must be rejected")


def test_alpha_content_release_runtime__uses_import_health_scope__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "content-release.json"
    state_path.write_text('{"workload":"content-release"}', encoding="utf-8")
    monkeypatch.setattr(stackctl, "target_process_dir", lambda _target: tmp_path)

    assert stackctl._current_runtime_health_scope("alpha-local") == "content-import"


def test_baseline_verify__does_not_read_disposable_release_output__local_contract() -> None:
    commands = stackctl._selected_verify_commands(
        "all",
        profile=VerificationProfile.BASELINE,
    )

    rendered = "\n".join(" ".join(command) for command in commands)
    assert "verify_environment_packaging_contract.py" not in rendered
    assert "verify_env_artifact_isolation.py" not in rendered


def test_non_prod_verify__binds_prod_purity_to_prod_target__local_contract() -> None:
    commands = stackctl._selected_verify_commands(
        "all",
        env_name="alpha",
        target_name="alpha-local",
        profile=VerificationProfile.SMOKE,
    )

    purity_command = next(
        command
        for command in commands
        if any(
            part.endswith("verify_prod_package_purity.py")
            for part in command
        )
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]


def test_prod_verify__passes_prod_target_to_prod_purity__local_contract() -> None:
    commands = stackctl._selected_verify_commands(
        "all",
        env_name="prod",
        target_name="prod-hosted",
        profile=VerificationProfile.RELEASE,
    )

    purity_command = next(
        command
        for command in commands
        if any(
            part.endswith("verify_prod_package_purity.py")
            for part in command
        )
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]


_IMPORT_SCOPE_CHECKS = [
    {"name": "api-health", "scope": "edge"},
    {"name": "media-edge-health", "scope": "media"},
    {"name": "entity-service", "scope": "content-import"},
]


def test_content_release_readiness__import_ignores_commercial_doctor__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": list(_IMPORT_SCOPE_CHECKS)},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(AssertionError("import must not call doctor")),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 0
    assert result["outcome"] == "PASS"
    assert result["phase"] == "import"
    assert result["schema"] == "quwoquan_ops.ship_readiness_receipt"


def test_content_release_readiness__missing_declared_probe_is_gate_block__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """健康门绿但缺少能力声明的探针时必须 fail-closed，不得凭空 PASS。"""
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {"checks": [{"name": "api-health", "scope": "edge"}]},
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: (_ for _ in ()).throw(AssertionError("import must not call doctor")),
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="import",
            env="beta",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
    assert any("content_services" in item for item in result["details"])


def test_content_release_readiness__commercial_missing_capability_is_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda _args: {"exitCode": 0, "details": [], "reportDir": "health"},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_json_object",
        lambda _path: {
            "checks": list(_IMPORT_SCOPE_CHECKS)
            + [{"name": "content-feed", "scope": "content-consumer"}]
        },
    )
    monkeypatch.setattr(
        stackctl,
        "command_doctor",
        lambda _args: {"exitCode": 1, "details": ["SLS is unavailable"]},
    )

    result = stackctl.command_content_readiness(
        argparse.Namespace(
            phase="commercial",
            env="gamma",
            report_dir=str(tmp_path),
            output_format="json",
        )
    )

    assert result["exitCode"] == 2
    assert result["outcome"] == "GATE_BLOCK"
