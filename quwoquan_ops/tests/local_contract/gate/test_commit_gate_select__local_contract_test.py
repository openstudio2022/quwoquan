from __future__ import annotations

from quwoquan_ops.gate.commit_gate_select import (
    classify,
    select_pytest_paths,
    static_checks,
)


def _checks(*paths: str) -> list[str]:
    return static_checks(classify(list(paths)))


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


def test_python_test_selection_uses_the_narrow_owner_tree() -> None:
    assert select_pytest_paths(
        ["quwoquan_ops/policies/gates/assistant_search_weak_typing_baseline.json"]
    ) == ["quwoquan_ops/tests/local_contract/gate"]
    assert select_pytest_paths(
        ["quwoquan_ops/cli/commands/dev_session_runtime.py"]
    ) == ["quwoquan_ops/tests/local_contract/stackctl"]
    assert select_pytest_paths(
        [
            "quwoquan_ops/tests/local_contract/ci/"
            "test_delivery_gate_ci_bootstrap__local_contract_test.py"
        ]
    ) == [
        "quwoquan_ops/tests/local_contract/ci/"
        "test_delivery_gate_ci_bootstrap__local_contract_test.py"
    ]
