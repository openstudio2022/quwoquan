"""Representative-path eval grader and gate companion.

Clause bindings stay next to the test that actually asserts each outcome.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.human_agent_delivery.eval_runner import evaluate_policy, load_eval_policy, run_eval  # noqa: E402


def policy() -> dict[str, object]:
    return load_eval_policy()


def run_entrypoint(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(
        ROOT / ".qwq_output/env/repo/local/human-agent-delivery/cache/bytecode"
    )
    return subprocess.run(
        [sys.executable, "-B", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def assert_entrypoint_passed(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    combined_output = completed.stdout + completed.stderr
    assert completed.returncode == 0, combined_output
    assert "Traceback" not in combined_output
    assert "ModuleNotFoundError" not in combined_output
    report = json.loads(completed.stdout.splitlines()[0])
    assert report["status"] == "pass"
    assert report["passed_checks"] == report["hard_invariant_denominator"] == 250
    return report


def test_canonical_gate_subprocess_resolves_repo_and_cli_packages() -> None:
    completed = run_entrypoint("quwoquan_ops/gate/verify_human_agent_delivery_eval.py")
    assert_entrypoint_passed(completed)


def test_human_agent_delivery_eval_cli_resolves_repo_and_cli_packages() -> None:
    completed = run_entrypoint("quwoquan_ops/cli/human_agent_delivery.py", "eval")
    assert_entrypoint_passed(completed)


def test_canonical_policy_passes_fixed_denominator_and_keeps_human_calibration_honest(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t1
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t2
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t3
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t4
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t5
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t7
    report = run_eval(report_path=tmp_path / "report.json")
    assert report["status"] == "pass"
    assert report["fixture_count"] == 30
    assert report["family_counts"] == {"A": 3, "B": 3, "C": 2, "D": 3, "E": 3, "F": 3, "G": 8, "H": 5}
    assert report["passed_checks"] == report["hard_invariant_denominator"] == 250
    assert report["machine_score"] == report["threshold"] == 1.0
    assert report["human_calibration"]["status"] == "not_observed"
    assert report["human_calibration"]["qualifying_role_session_count"] == 0
    assert report["human_calibration"]["machine_baseline_is_human_usability_evidence"] is False


def test_every_declared_legal_branch_is_reachable_without_reprompting() -> None:
    report = evaluate_policy(policy())
    for result in report["fixture_results"]:
        assert result["passed"], result
        assert result["selected_probe_option_id"] in result["legal_option_ids"]
        assert {probe["selected_option_id"] for probe in result["branch_probes"]} == set(result["legal_option_ids"])
        assert all(probe["legal"] and probe["reprompted"] is False for probe in result["branch_probes"])
        assert result["reprompted"] is False


def test_wrong_fixture_expectation_blocks() -> None:
    mutated = deepcopy(policy())
    mutated["fixtures"][0]["expected_route"] = {"result": "no_human_needed"}
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert any(item["check_id"] == "A01.route" for item in report["failed_checks"])


def test_recommendation_bias_or_second_inducement_blocks() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t4
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t5
    mutated = deepcopy(policy())
    fixture = next(item for item in mutated["fixtures"] if item["id"] == "B01")
    fixture["card"]["agent_recommendation"] = {"option_id": "minimal_scope", "reason": "推荐"}
    fixture["card"]["independent_inputs_sealed"] = True
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert any(item["check_id"] == "B01.bias_and_language" for item in report["failed_checks"])


def test_internal_term_leak_blocks() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-002.t2
    mutated = deepcopy(policy())
    mutated["fixtures"][0]["card"]["question"] = "业务发起人，请选择 router 路径？"
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert any(item["check_id"] == "A01.bias_and_language" for item in report["failed_checks"])


def test_zero_sample_blocks() -> None:
    mutated = deepcopy(policy())
    mutated["evaluation"]["expected_fixture_count"] = 0
    mutated["evaluation"]["expected_family_counts"] = {}
    mutated["evaluation"]["hard_invariant_denominator"] = 10
    mutated["fixtures"] = []
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert report["machine_score"] < 1.0
    assert any(item["check_id"] == "global.nonzero_samples" for item in report["failed_checks"])


def test_omitting_one_representative_path_blocks_fixed_denominator() -> None:
    mutated = deepcopy(policy())
    mutated["fixtures"] = mutated["fixtures"][:-1]
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert report["fixture_count"] == 29
    assert any(item["check_id"] in {"global.policy_shape", "global.fixed_denominator", "global.family_coverage"} for item in report["failed_checks"])


def test_role_interaction_eval_has_four_events_same_track_and_injectable_replay() -> None:
    loaded = policy()
    interactions = loaded["role_interaction_evaluation"]
    assert interactions["expected_fixture_count"] == len(interactions["fixtures"]) == 4
    assert {item["payload"]["event_type"] for item in interactions["fixtures"]} == {
        "progress_update", "decision_request", "exception_escalation", "completion_report",
    }
    replay = loaded["conversation_replay"]
    assert replay["input_mode"] == "injectable_json_object"
    assert replay["canonical_private_transcript_fixture"] is False
    assert replay["reads_private_transcript_paths"] is False
    report = evaluate_policy(loaded)
    assert report["status"] == "pass"
    assert report["human_calibration"]["status"] == "not_observed"
    assert report["human_calibration"]["qualifying_role_session_count"] == 0


def test_upper_layer_pass_cannot_project_user_or_business_availability() -> None:
    mutated = deepcopy(policy())
    completion = next(
        item for item in mutated["role_interaction_evaluation"]["fixtures"]
        if item["payload"]["event_type"] == "completion_report"
    )
    completion["payload"]["proof"] = ["本地测试通过，因此用户已经可用。"]
    completion["payload"]["limits"] = ["无其他限制。"]
    # 代表样例必须保留责任域限制；错误样例与预期 payload 不再相等，从而阻断。
    report = evaluate_policy(mutated)
    assert report["status"] == "block"
    assert any(item["check_id"] == "global.role_interaction_fixtures" for item in report["failed_checks"])

