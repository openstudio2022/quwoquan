# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t4
from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.local_worktree_inventory import load_lane_ownership, ownership_owner
from quwoquan_ops.gate.commit_gate_select import (
    PYTEST_BUDGET_SECONDS,
    PYTEST_CAP,
    build_plan,
    classify,
    select_pytest_paths,
    static_checks,
)

ROOT = Path(__file__).resolve().parents[4]


def _checks(*paths: str) -> list[str]:
    return static_checks(classify(list(paths)), list(paths))


def test_workflow_toolchain_and_go_test_changes_do_not_run_unrelated_global_gates() -> None:
    checks = _checks(
        ".github/workflows/delivery-gate.yml",
        "quwoquan_app/.flutter-version",
        "quwoquan_service/services/content-service/tests/api_integration/example_test.go",
        "quwoquan_ops/tests/local_contract/ci/example_test.py",
    )

    assert "service_architecture" in checks
    assert "app_contract_handoff" in checks
    assert "feature_tree" not in checks
    assert "app_generated_manifest" not in checks
    assert "metadata_contract" not in checks
    assert not any(item.startswith("python_script_governance_") for item in checks)


def test_code_health_policy_is_owned_by_engineering_lane() -> None:
    rules = load_lane_ownership()
    assert ownership_owner("quwoquan_ops/policies/code_health_policy.yaml", rules) == "lane/engineering"


def test_source_changes_select_fast_code_health_but_docs_do_not() -> None:
    for path in (
        "quwoquan_app/lib/runtime/value.dart",
        "quwoquan_service/services/chat-service/internal/value.go",
        "quwoquan_data/scripts/content/value.py",
        "quwoquan_ops/ci/value.py",
        "quwoquan_ops/portal/src/value.ts",
    ):
        assert "code_health_delta_fast" in _checks(path), path
    assert "code_health_delta_fast" not in _checks("specs/feature-tree/runtime/spec.md")


def test_each_python_script_owner_runs_only_its_own_governance_scope() -> None:
    paths = {
        "app": "quwoquan_app/scripts/runtime/check.py",
        "service": "quwoquan_service/scripts/verify/check.py",
        "ops": "quwoquan_ops/cli/commands/check.py",
        "data": "quwoquan_data/scripts/content/check.py",
    }

    for scope, path in paths.items():
        checks = _checks(path)
        assert f"python_script_governance_{scope}" in checks
        assert sum(item.startswith("python_script_governance_") for item in checks) == 1


def test_contract_spec_and_dart_changes_keep_their_required_static_gates() -> None:
    spec_checks = _checks("specs/feature-tree/runtime/example/spec.md")
    assert "feature_tree" in spec_checks

    app_checks = _checks("quwoquan_app/lib/runtime/config/example.dart")
    assert "verify-app-mock-isolation" in app_checks
    assert "verify-app-assistant-search-weak-typing-ratchet" in app_checks
    assert "app_generated_manifest" not in app_checks

    contract_checks = _checks(
        "quwoquan_service/services/content-service/contracts/content/post/fields.yaml"
    )
    assert "app_generated_manifest" in contract_checks
    assert "metadata_contract" in contract_checks
    assert "commercial_contract" in contract_checks



def test_hotl_runtime_matrix_is_excluded_from_ordinary_commit_hard_gates() -> None:
    matrix_path = "specs/feature-tree/runtime/development-workflow-governance/design.md"
    checks = _checks(matrix_path)
    assert checks == ["branch_policy", "entrypoint_script_paths"]
    assert "feature_tree" not in checks
    assert "service_architecture" not in checks
    assert "agent_context_budget" not in checks
    assert "hotl_runtime_matrix" not in checks


def test_ordinary_commit_never_selects_worktree_lifecycle_static_gate() -> None:
    for paths in (
        ["README.md"],
        ["quwoquan_ops/hooks/worktree_add_guard.py"],
        ["quwoquan_ops/policies/worktree_policy.yaml"],
        ["quwoquan_ops/policies/lane_ownership.yaml"],
    ):
        assert "local_worktree_lifecycle" not in _checks(*paths)

    selected, deferred = select_pytest_paths(
        ["quwoquan_ops/policies/worktree_policy.yaml"]
    )
    assert selected == [
        "quwoquan_ops/tests/local_contract/gate/"
        "test_local_worktree_lifecycle__gate__local_contract_test.py"
    ]
    assert deferred == []

    assert select_pytest_paths(
        ["quwoquan_ops/policies/lane_ownership.yaml"]
    ) == (selected, deferred)
    assert select_pytest_paths(
        ["quwoquan_ops/cli/lane_worktree_commands.py"]
    ) == (selected, deferred)


def test_python_test_selection_defers_broad_owner_trees() -> None:
    assert select_pytest_paths(
        ["quwoquan_ops/policies/gates/assistant_search_weak_typing_baseline.json"]
    ) == ([], ["quwoquan_ops/tests/local_contract/gate"])
    assert select_pytest_paths(
        ["quwoquan_ops/cli/commands/dev_session_runtime.py"]
    ) == (
        [
            "quwoquan_ops/tests/local_contract/stackctl/"
            "test_stackctl_dev_session_mutable_startup_gate__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/stackctl/"
            "test_stackctl_dev_session_resume_compose__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/stackctl/"
            "test_stackctl_dev_session_runtime_reuse__local_contract_test.py",
        ],
        [],
    )
    assert select_pytest_paths(
        [
            "quwoquan_ops/tests/local_contract/ci/"
            "test_delivery_gate_ci_bootstrap__local_contract_test.py"
        ]
    ) == (
        [
            "quwoquan_ops/tests/local_contract/ci/"
            "test_delivery_gate_ci_bootstrap__local_contract_test.py"
        ],
        [],
    )


def test_commit_gate_changes_select_only_their_focused_contracts() -> None:
    expected = (
        [
            "quwoquan_ops/tests/local_contract/ci/"
            "test_commit_gate_fast_path__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/gate/"
            "test_commit_gate_select__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/gate/"
            "test_process_group_deadline__local_contract_test.py",
        ],
        [],
    )

    assert select_pytest_paths(["quwoquan_ops/gate/commit_gate.sh"]) == expected
    assert select_pytest_paths(["quwoquan_ops/gate/commit_gate_select.py"]) == expected


def test_supply_chain_gate_selects_its_release_contract() -> None:
    # 供应链门禁有两份 companion：规则合同（gate/）与 release 供应链证明（release/），
    # 只映射后者时新增的 job 上下文 / step 自引用规则回退在 L0 不可见。
    assert select_pytest_paths(
        ["quwoquan_ops/gate/verify_github_supply_chain.py"]
    ) == (
        [
            "quwoquan_ops/tests/local_contract/gate/"
            "test_github_supply_chain__contract__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/"
            "test_service_supply_chain_provenance__supply_chain__local_contract_test.py",
        ],
        [],
    )


def test_ruleset_readback_and_cli_argument_gates_select_their_exact_contracts() -> None:
    assert select_pytest_paths(["quwoquan_ops/ci/verify_hosted_integration_ruleset.py"]) == (
        ["quwoquan_ops/tests/local_contract/ci/test_hosted_integration_ruleset__local_contract_test.py"],
        [],
    )
    assert select_pytest_paths(["quwoquan_ops/gate/verify_workflow_cli_arguments.py"]) == (
        ["quwoquan_ops/tests/local_contract/gate/test_workflow_cli_arguments__gate__local_contract_test.py"],
        [],
    )
    assert select_pytest_paths(["quwoquan_ops/ci/verify_code_health_delivery.py"]) == (
        ["quwoquan_ops/tests/local_contract/ci/test_code_health_delivery__local_contract_test.py"],
        [],
    )


def test_code_health_delta_maps_to_every_code_health_contract() -> None:
    selected, deferred = select_pytest_paths(["quwoquan_ops/gate/code_health_delta/calibration.py"])
    names = {path.rsplit("/", 1)[-1] for path in selected + deferred}
    assert names == {
        "test_incremental_code_health__gate__local_contract_test.py",
        "test_code_health_file_size__gate__local_contract_test.py",
        "test_code_health_precision__gate__local_contract_test.py",
        "test_code_health_render_and_history__gate__local_contract_test.py",
        "test_code_health_calibration__gate__local_contract_test.py",
        "test_code_health_weekly__gate__local_contract_test.py",
        "test_code_health_hotspots__gate__local_contract_test.py",
        "test_code_health_delivery__local_contract_test.py",
        "test_code_health_integration__local_contract_test.py",
    }


def test_ordinary_gate_and_ci_sources_defer_directories_instead_of_running_them() -> None:
    for source, target in (
        (
            "quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py",
            "quwoquan_ops/tests/local_contract/gate",
        ),
        (
            "quwoquan_ops/ci/github_actions_timing.py",
            "quwoquan_ops/tests/local_contract/ci",
        ),
        (
            "quwoquan_ops/environments/prod/runtime.yaml",
            "quwoquan_ops/tests/local_contract/environment",
        ),
        (
            "quwoquan_ops/cli/commands/health.py",
            "quwoquan_ops/tests/local_contract/stackctl",
        ),
        (
            "quwoquan_data/scripts/content/execution/handler.py",
            "quwoquan_data/tests/local_contract/execution",
        ),
    ):
        selected, deferred = select_pytest_paths([source])
        assert selected == []
        assert target in deferred
        assert all(not (ROOT / item).is_dir() for item in selected)


def test_exact_source_mappings_and_direct_test_changes_stay_file_scoped() -> None:
    exact = (
        "quwoquan_ops/tests/local_contract/provider/"
        "test_provider_patrol_runtime_identity__contract__local_contract_test.py"
    )
    assert select_pytest_paths(
        ["quwoquan_ops/ci/provider_conformance/provider_patrol_lib/mutable_runtime.py"]
    ) == ([exact], [])

    direct = (
        "quwoquan_ops/tests/local_contract/ci/"
        "test_delivery_gate_ci_bootstrap__local_contract_test.py"
    )
    assert select_pytest_paths([direct]) == ([direct], [])


def test_parent_directory_is_deferred_without_duplicate_child_execution() -> None:
    direct = (
        "quwoquan_ops/tests/local_contract/gate/"
        "test_commit_gate_select__local_contract_test.py"
    )
    plan = build_plan(
        ["quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py", direct], 40
    )

    assert plan["pytest_paths"] == [direct]
    assert "quwoquan_ops/tests/local_contract/gate" in plan["deferred_to_ci"]
    assert not any(
        parent in plan["pytest_paths"] and child.startswith(parent + "/")
        for parent in plan["pytest_paths"]
        for child in plan["pytest_paths"]
    )


def test_known_slow_review_suites_are_deferred_before_l0_hard_timeout() -> None:
    slow = [
        "quwoquan_ops/tests/local_contract/gate/test_named_evidence_runner__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/gate/test_review_baseline__gate__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/gate/test_review_dispatch__cli__local_contract_test.py",
    ]
    plan = build_plan(slow, 40)

    assert plan["pytest_paths"] == [slow[0]]
    assert plan["deferred_to_ci"] == slow[1:]
    assert plan["estimated_pytest_seconds"] == 120
    by_target = {item["target"]: item for item in plan["pytest_target_estimates"]}
    assert by_target[slow[1]]["reason"] == "estimated_duration_budget"
    assert by_target[slow[2]]["reason"] == "estimated_duration_budget"


def test_estimated_duration_is_primary_budget_and_plan_is_stable() -> None:
    changed = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "quwoquan_ops/tests/local_contract/gate").glob("test_*.py")
    )[: PYTEST_CAP + 1]
    assert len(changed) * 18 > PYTEST_BUDGET_SECONDS

    first = build_plan(changed, 40)
    second = build_plan(list(reversed(changed)), 40)

    assert first["pytest_budget_seconds"] == PYTEST_BUDGET_SECONDS
    assert first["estimated_pytest_seconds"] <= PYTEST_BUDGET_SECONDS
    assert first["pytest_estimate_schema"] == "commit-gate-pytest-estimate-v1"
    assert first["pytest_estimate_basis"] == (
        "configured_conservative_estimate_not_observed_p95"
    )
    assert any(
        item["decision"] == "deferred_to_ci"
        and item["reason"] == "estimated_duration_budget"
        for item in first["pytest_target_estimates"]
    )
    assert len(first["pytest_paths"]) < PYTEST_CAP
    assert first["pytest_paths"] == second["pytest_paths"]
    assert first["deferred_to_ci"] == second["deferred_to_ci"]
    assert first["pytest_target_estimates"] == second["pytest_target_estimates"]
