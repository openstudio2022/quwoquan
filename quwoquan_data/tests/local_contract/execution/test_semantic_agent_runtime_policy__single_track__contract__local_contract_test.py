from __future__ import annotations

import yaml

from content.execution.model_contract import execution_model_pair
from content.execution.preflight import handler as preflight_handler
from content.execution.planning.recipe.model import load_recipe
from content.execution.scale.semantic_promotion import scale_calibration_sample_count
from core.control_types import AgentProvider
from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.runtime_policy import active_runtime_policy, runtime_profile_path


def test_semantic_agent_runtime_policy_binds_terra_roles_and_sol_calibration() -> None:
    policy = active_runtime_policy()
    assert policy.profile_id == "semantic_agent_local_calibrated"
    assert policy.semantic_author.provider is AgentProvider.CODEX_SDK
    assert policy.semantic_author.model == "gpt-5.6-terra"
    assert policy.semantic_reviewer.provider is AgentProvider.CODEX_SDK
    assert policy.semantic_reviewer.model == "gpt-5.6-terra"
    assert policy.semantic_calibration.binding.provider is AgentProvider.CODEX_SDK
    assert policy.semantic_calibration.binding.model == "gpt-5.6-sol"
    assert policy.semantic_calibration.sample_count(3) == 3
    assert policy.semantic_calibration.sample_count(9) == 9
    assert policy.semantic_calibration.sample_count(10) == 10
    assert policy.semantic_calibration.sample_count(11) == 10
    assert policy.semantic_calibration.sample_count(100) == 10
    assert policy.semantic_calibration.sample_count(101) == 11
    assert policy.semantic_calibration.sample_count(1000) == 100
    assert policy.semantic_fallback_policy == "forbidden"
    assert policy.runtime_evidence.process_inspection_timeout_seconds == 5.0
    assert policy.runtime_evidence.queue_fault_event_timeout_seconds == 120.0
    assert policy.runtime_evidence.semantic_preflight_receipt_ttl_seconds == 600
    assert policy.semantic_agent_runtime.value == "local"
    environment = policy.process_environment()
    assert environment["QWQ_SEMANTIC_AGENT_PROVIDER"] == "codex_sdk"
    assert environment["QWQ_SEMANTIC_AGENT_MODEL"] == "gpt-5.6-terra"
    assert "QWQ_MANAGED_LOCAL_SEMANTIC_AGENT_MAX_WORKERS" not in environment
    assert "QWQ_CURSOR_BRIDGE_INSTANCES" not in environment
    assert not hasattr(policy, "semantic_capacity")
    assert not hasattr(policy, "author_workers")
    assert not hasattr(policy, "reviewer_workers")
    assert not hasattr(policy, "research_workers")
    assert not hasattr(policy, "download_concurrency")
    assert not hasattr(policy, "partitions_per_worker")
    assert not hasattr(policy, "research_wave_size")
    assert not hasattr(policy, "research_max_waves_per_run")
    assert not hasattr(policy, "source_plan_recovery_workers")
    assert not hasattr(policy, "cold_start_max_workers")
    assert not hasattr(policy, "worker_stagger_seconds")
    assert not hasattr(policy, "research_wave_budget_seconds")
    assert not hasattr(policy, "campaign_lane_workers")
    assert not hasattr(policy, "cursor_bridge_instances")
    assert not hasattr(policy, "cursor_provider")
    assert not hasattr(policy, "cursor_model_selection")


def test_runtime_profile_has_no_static_semantic_capacity_or_worker_limits() -> None:
    document = yaml.safe_load(
        runtime_profile_path("semantic_agent_local_calibrated").read_text(
            encoding="utf-8"
        )
    )
    semantic_agent = document["policy"]["semanticAgent"]
    runtime_policy = document["policy"]

    assert "capacity" not in semantic_agent
    assert "coordination" not in semantic_agent
    assert "workers" not in runtime_policy
    assert not {
        "requestsPerMinute",
        "burstLimit",
        "laneConcurrencyLimit",
        "receiptTtlSeconds",
    }.intersection(semantic_agent)
    assert not {
        "researchWaveSize",
        "researchMaxWavesPerRun",
        "sourcePlanRecoveryWorkers",
        "coldStartMaxWorkers",
        "workerStaggerSeconds",
        "researchWaveBudgetSeconds",
        "campaignLaneTimeoutSeconds",
    }.intersection(runtime_policy["budgets"])
    assert "overpassConcurrency" not in runtime_policy["coverageDiscovery"]
    assert (
        document["policy"]["runtimeEvidence"][
            "semanticPreflightReceiptTtlSeconds"
        ]
        == 600
    )


def test_scale_calibration_sample_count_matches_runtime_policy() -> None:
    policy = active_runtime_policy().semantic_calibration
    for accepted_count in (0, 1, 9, 10, 11, 100, 101, 1000):
        assert scale_calibration_sample_count(accepted_count) == policy.sample_count(
            accepted_count
        )


def test_cursor_grok_is_primary_and_cursor_auto_requires_a_new_retry() -> None:
    primary = active_runtime_policy().explicit_semantic_selection("cursor_grok")
    retry = active_runtime_policy().explicit_semantic_selection("cursor_auto")

    assert primary.binding.provider is AgentProvider.CURSOR_SDK
    # The grok family is governed; the version and reasoning tier are profile
    # values proven against the account catalog by preflight, not constants.
    assert primary.binding.model.startswith("grok-")
    assert all(
        parameter.id and parameter.value
        for parameter in primary.binding.model_parameters
    )
    assert primary.runtime.value == "local"
    assert primary.requires_new_retry_of is False
    assert retry.binding.provider is AgentProvider.CURSOR_SDK
    assert retry.binding.model == "auto"
    assert retry.binding.model_parameters == ()
    assert retry.runtime.value == "local"
    assert retry.requires_new_retry_of is True


def test_legacy_cursor_profile_is_not_a_second_truth_source() -> None:
    assert not (CONTROL_PLANE_SHARED_ROOT / "cursor_local_calibrated.runtime.yaml").exists()
    assert (CONTROL_PLANE_SHARED_ROOT / "semantic_agent_local_calibrated.runtime.yaml").is_file()


def test_four_recipes_bind_terra_for_independent_author_and_reviewer() -> None:
    for carrier in ("homepage", "article", "image", "video"):
        recipe = load_recipe(f"content/travel/{carrier}/{carrier}")
        assert recipe["runtimeProfile"] == "semantic_agent_local_calibrated"
        pair = execution_model_pair(recipe)
        assert pair.author.provider is AgentProvider.CODEX_SDK
        assert pair.author.model_id == "gpt-5.6-terra"
        assert pair.author.family.value == "gpt"
        assert pair.reviewer.provider is AgentProvider.CODEX_SDK
        assert pair.reviewer.model_id == "gpt-5.6-terra"
        assert pair.reviewer.family.value == "gpt"


def test_capacity_probe_dispatches_codex_terra_without_silent_fallback(
    monkeypatch,
) -> None:
    policy = active_runtime_policy()
    observed: dict[str, object] = {}

    def probe_suite(**kwargs):
        observed.update(kwargs)
        return {
            "attempts": policy.startup_probe_suite_attempts,
            "successCount": policy.startup_probe_suite_attempts,
            "effectiveConcurrency": policy.startup_probe_suite_attempts,
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        }

    monkeypatch.setattr(preflight_handler, "semantic_agent_probe_suite", probe_suite)
    report = preflight_handler._capacity_soak_report()

    assert observed["provider"] is AgentProvider.CODEX_SDK
    assert observed["model"].to_sdk_document() == {
        "id": "gpt-5.6-terra",
        "params": [],
    }
    assert "include_catalog" not in observed
    assert report["ready"] is True
    assert report["probeIntent"]["provider"] == "codex_sdk"
    assert "requiredConcurrency" not in report["probeIntent"]
