"""The release policy selects one minimal capability slice, never all environments.

由 1000 行硬顶拆分：本文件保留 readiness policy 与 health/verify 探针拓扑组；
readiness 命令探针组见 test_content_release_readiness__command_probes__reliability__local_contract_test.py；
data release 证据组见 test_content_release_readiness__data_release_evidence__reliability__local_contract_test.py。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeSource,
    ReadinessCapability,
    ReadinessPhase,
    VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
)


def test_content_release_readiness__maps_phase_to_environment_capabilities__local_contract() -> (
    None
):
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
    alpha_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="alpha",
    )
    prod_consumer = policy.requirement_for(
        phase=ReadinessPhase.CONSUMER,
        environment="prod",
    )
    gamma_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="gamma",
    )
    alpha_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="alpha",
    )
    beta_commercial = policy.requirement_for(
        phase=ReadinessPhase.COMMERCIAL,
        environment="beta",
    )

    assert alpha_import.workload == "content-release"
    assert beta_import.workload == "content-release"
    assert alpha_consumer.target == "alpha-local"
    assert gamma_consumer.health_scope == "content-consumer"
    assert prod_consumer.target == "prod-hosted"
    assert ReadinessCapability.TELEMETRY_LOG_SINK not in beta_import.capabilities
    assert ReadinessCapability.TELEMETRY_LOG_SINK in gamma_commercial.capabilities
    assert alpha_commercial.workload == "full"
    assert beta_commercial.workload == "full"


def test_content_release_readiness__binds_probe_for_every_capability__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()

    for capability in ReadinessCapability:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE:
            assert binding.health_scope
        elif binding.source is ProbeSource.COMMERCIAL_DOCTOR:
            assert binding.source is ProbeSource.COMMERCIAL_DOCTOR
            assert binding.health_scope is None
        elif binding.source is ProbeSource.RESEARCH_ISOLATION:
            assert capability is ReadinessCapability.RESEARCH_ACCESS_ISOLATION
            assert binding.health_scope is None
            assert binding.control_action is None
        else:
            assert binding.source is ProbeSource.LOG_SINK_CONTROL
            assert binding.control_action == "all"

    assert (
        policy.probe_binding_for(ReadinessCapability.CONTENT_SERVICES).health_scope
        == "content-import"
    )
    assert (
        policy.probe_binding_for(ReadinessCapability.TELEMETRY_LOG_SINK).source
        is ProbeSource.LOG_SINK_CONTROL
    )


def test_content_release_readiness__doctor_bound_capabilities_are_commercial_only__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()

    for requirement in policy.requirements:
        for capability in requirement.capabilities:
            binding = policy.probe_binding_for(capability)
            if requirement.phase is ReadinessPhase.COMMERCIAL:
                continue
            if requirement.phase is ReadinessPhase.RESEARCH:
                assert binding.source in {
                    ProbeSource.HEALTH_SCOPE,
                    ProbeSource.RESEARCH_ISOLATION,
                }
            else:
                assert binding.source is ProbeSource.HEALTH_SCOPE


def test_content_release_readiness__rejects_undefined_phase_environment__local_contract() -> (
    None
):
    policy = load_content_release_readiness_policy()
    try:
        policy.requirement_for(phase=ReadinessPhase.IMPORT, environment="prod")
    except ValueError as exc:
        assert "does not define" in str(exc)
    else:
        raise AssertionError("undefined phase/environment must be rejected")


def test_prod_hosted_content_service_has_a_real_import_scope_probe__local_contract() -> (
    None
):
    checks = stackctl._content_data_plane_health_checks("prod-hosted")

    assert checks == [
        {
            "name": "content-service-public",
            "scope": "content-import",
            "url": "https://api.quwoquan.com/healthz",
        }
    ]


def test_media_edge_health_uses_edge_root_not_carrier_path_base__local_contract() -> (
    None
):
    topology = stackctl.load_environment_topology()
    for target_name in ("alpha-local", "beta-local", "gamma-local"):
        checks = stackctl._health_checks_for_target(
            topology,
            target_name,
            "content-import",
            workload="content-release",
        )
        media = next(item for item in checks if item["name"] == "media-edge-health")
        assert media["url"].endswith("/healthz")
        assert not media["url"].endswith("/media/image/healthz")
        assert "/media/image/" not in media["url"]
        assert "/media/avatar/" not in media["url"]
        assert "/media/video/" not in media["url"]


def test_content_release_import_plane_excludes_tag_and_search__local_contract(
    monkeypatch,
) -> None:
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-import",
        workload="content-release",
    )
    names = {str(item["name"]) for item in checks}
    assert "content-service" in names
    assert "entity-service" in names
    assert "tag-service" not in names
    assert "search-service" not in names

    composition = compile_provider_runtime_composition(
        environment="alpha",
        target="alpha-local",
    )
    monkeypatch.setattr(
        stackctl,
        "_active_provider_runtime",
        lambda _environment, _target: {"composition": composition},
    )
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        lambda _target: {
            "status": "running",
            "workload": "full",
            "providerRuntimeDigest": composition["runtimeCompositionDigest"],
        },
    )

    full_plane = {
        str(item["name"])
        for item in stackctl._content_data_plane_health_checks(
            "alpha-local",
            workload="full",
        )
    }
    assert "tag-service" in full_plane
    assert "search-service" in full_plane


def test_content_consumer_feed_health_uses_canonical_homepage_route__local_contract() -> None:
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-consumer",
        workload="content-release",
    )
    feed = next(item for item in checks if item["name"] == "content-feed")
    parsed = urlparse(str(feed["url"]))
    assert parsed.path == "/content/feed"
    assert parse_qs(parsed.query) == {
        "sort": ["recommend"],
        "channelId": ["recommend"],
        "limit": ["1"],
        "sessionId": ["stackctl-content-consumer-health"],
    }


def test_content_commercial_health_adds_product_ops_without_full_plane__local_contract() -> (
    None
):
    topology = stackctl.load_environment_topology()
    checks = stackctl._health_checks_for_target(
        topology,
        "alpha-local",
        "content-commercial",
        workload="content-commercial",
    )
    names = {str(item["name"]) for item in checks}

    assert {
        "api-health",
        "product-ops-health",
        "media-edge-health",
        "content-service",
        "entity-service",
        "app-config",
        "content-feed",
        "product-ops-service",
    }.issubset(names)
    assert "assistant-service" not in names
    assert "platform-ops-service" not in names
    assert "integration-service" not in names


def test_content_consumer_nonempty_feed_probe_skips_commercial_checks__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_probe(
        topology,
        target_name,
        report_dir,
        *,
        require_non_empty_content_feed=False,
        release_post_expectations=None,
        release_readiness_path=None,
        only_checks=(),
        probe_name="integration-readonly",
        timeout_seconds=None,
    ):
        captured["only_checks"] = only_checks
        captured["require_non_empty_content_feed"] = require_non_empty_content_feed
        return (
            {"name": probe_name, "ok": True, "scope": "content-consumer"},
            "ok",
            [],
        )

    monkeypatch.setattr(stackctl, "_run_environment_integration_probe", _fake_probe)
    topology = stackctl.load_environment_topology()
    statuses, _, findings = stackctl._script_probes_for_target(
        topology,
        "alpha-local",
        "content-consumer",
        tmp_path,
        require_non_empty_content_feed=True,
    )
    assert findings == []
    assert statuses
    assert captured["require_non_empty_content_feed"] is True
    assert captured["only_checks"] == (
        "content_feed",
        "video_book_feed",
    )
    assert "premium_feed" not in captured["only_checks"]
    assert "global_search" not in captured["only_checks"]


def test_baseline_verify__does_not_read_disposable_release_output__local_contract() -> (
    None
):
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
        if any(part.endswith("verify_prod_package_purity.py") for part in command)
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]
    media_command = next(
        command
        for command in commands
        if any(part.endswith("verify_media_delivery_contract.py") for part in command)
    )
    assert media_command[-2:] == ["--env", "alpha"]


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
        if any(part.endswith("verify_prod_package_purity.py") for part in command)
    )
    assert purity_command[-2:] == ["--target", "prod-hosted"]
