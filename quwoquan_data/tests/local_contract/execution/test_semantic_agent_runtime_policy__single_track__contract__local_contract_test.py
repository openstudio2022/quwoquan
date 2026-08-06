from __future__ import annotations

from content.execution.model_contract import execution_model_pair
from content.execution.preflight import handler as preflight_handler
from content.execution.recipe import load_recipe
from content.execution.scale_semantic_promotion import scale_calibration_sample_count
from core.control_types import AgentProvider
from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.runtime_policy import active_runtime_policy


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
    assert policy.semantic_capacity.account_scope_id == "primary-semantic-account"
    assert policy.semantic_capacity.host_scope_id == "local-data-host"
    assert policy.semantic_capacity.requests_per_minute == 60
    assert policy.semantic_capacity.burst_limit == 4
    assert policy.semantic_capacity.lane_concurrency_limit == 2
    assert policy.semantic_capacity.receipt_ttl_seconds == 600
    assert policy.runtime_evidence.process_inspection_timeout_seconds == 5.0
    assert policy.runtime_evidence.queue_fault_event_timeout_seconds == 120.0
    assert policy.semantic_agent_runtime.value == "local"
    assert policy.process_environment()["QWQ_SEMANTIC_AGENT_PROVIDER"] == "codex_sdk"
    assert policy.process_environment()["QWQ_SEMANTIC_AGENT_MODEL"] == "gpt-5.6-terra"
    assert not hasattr(policy, "cursor_provider")
    assert not hasattr(policy, "cursor_model_selection")


def test_scale_calibration_sample_count_matches_runtime_policy() -> None:
    policy = active_runtime_policy().semantic_calibration
    for accepted_count in (0, 1, 9, 10, 11, 100, 101, 1000):
        assert scale_calibration_sample_count(accepted_count) == policy.sample_count(
            accepted_count
        )


def test_cursor_auto_is_explicit_and_allows_first_execution() -> None:
    selection = active_runtime_policy().explicit_semantic_selection("cursor_auto")

    assert selection.binding.provider is AgentProvider.CURSOR_SDK
    assert selection.binding.model == "auto"
    assert selection.runtime.value == "local"
    assert selection.requires_new_retry_of is False


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


def test_capacity_soak_dispatches_codex_terra_without_silent_fallback(
    monkeypatch,
) -> None:
    policy = active_runtime_policy()
    observed: dict[str, object] = {}

    def probe_suite(**kwargs):
        observed.update(kwargs)
        return {
            "attempts": policy.startup_probe_suite_attempts,
            "successCount": policy.startup_probe_suite_attempts,
            "effectiveConcurrency": policy.campaign_lane_workers,
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
    assert report["capacityContract"]["provider"] == "codex_sdk"
    assert (
        report["capacityContract"]["requiredConcurrency"]
        == policy.campaign_lane_workers
    )
