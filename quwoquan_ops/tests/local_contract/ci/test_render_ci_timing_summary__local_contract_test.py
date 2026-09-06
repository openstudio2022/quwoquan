# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-003
from __future__ import annotations

from quwoquan_ops.ci import render_ci_timing_summary as renderer


def base_arguments() -> dict:
    return {
        "title": "03. Delivery Gate",
        "gate_key": "03.delivery_gate",
        "workflow": "03. Delivery Gate",
        "workflow_run_id": "42",
        "source_git_sha": "a" * 40,
        "candidate_digest": "sha256:" + "b" * 64,
        "gate_budget": {
            "budgetSeconds": 300,
            "hardFailSeconds": 1800,
            "criticalPath": "promotionReadyAt -> mainReadbackAt",
            "phaseBudgetsSeconds": {"promotion": 300},
            "timingPolicy": "promotion_timing_ratchet",
        },
        "budget_profile": "",
        "machine_critical_path_seconds": 240,
        "critical_path_source": "github_run_calendar",
        "timestamps": {key: "2026-09-05T00:00:00Z" for key in renderer.TIMESTAMP_ARGUMENTS},
        "optional_durations": {key: 240 for key in renderer.OPTIONAL_DURATION_ARGUMENTS},
        "phases": [("promotion", 240)],
        "upstream_missing_evidence": [],
        "notes": [],
        "functional_outcome": "pass",
    }


def test_promotion_timing_policy_is_accepted_as_diagnostic_only() -> None:
    payload = renderer.build_payload(**base_arguments())
    assert payload["budget"]["policy"] == "promotion_timing_ratchet"
    assert payload["outcomePolicy"]["timing"] == "DIAGNOSTIC_ONLY"
    assert renderer.DIAGNOSTIC_ONLY_NOTE in payload["notes"]


def test_generic_summary_cannot_claim_ratchet_authority_when_over_budget() -> None:
    arguments = base_arguments()
    arguments["optional_durations"] = {
        key: 1900 for key in renderer.OPTIONAL_DURATION_ARGUMENTS
    }
    payload = renderer.build_payload(**arguments)
    assert payload["status"] == "failed"
    assert payload["outcomePolicy"]["timing"] == "DIAGNOSTIC_ONLY"
    assert "promotion_timing_sample" in renderer.DIAGNOSTIC_ONLY_NOTE
