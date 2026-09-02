# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-003.t2
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "quwoquan_ops/ci") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/ci"))

from impact_planner_core import (  # noqa: E402
    INTEGRATION_DEPTHS,
    ImpactPlannerError,
    classify_impacts,
    derive_integration_depth,
)
from quwoquan_ops.gate.verify_app_cloud_closure import (  # noqa: E402
    ClosureContractError,
    evaluate_app_cloud_closure,
)

GATE_SCRIPT = ROOT / "quwoquan_ops/gate/verify_app_cloud_closure.py"
CANDIDATE = "sha256:" + "c" * 64
OTHER_CANDIDATE = "sha256:" + "d" * 64


def launch_receipt(**overrides: Any) -> dict[str, Any]:
    value = {
        "candidate_digest": CANDIDATE,
        "status": "launched",
        "runtimeHealthStatus": "healthy",
        "configurationState": "complete",
        "device_class": "real_device",
    }
    value.update(overrides)
    return value


def api_case(**overrides: Any) -> dict[str, Any]:
    value = {
        "case_id": "content-feed-api-integration",
        "candidate_digest": CANDIDATE,
        "transport": "real_service",
        "status": "passed",
        "executed": 3,
        "failed": 0,
        "skipped": 0,
    }
    value.update(overrides)
    return value


def journey_readback(**overrides: Any) -> dict[str, Any]:
    value = {
        "journey_id": "home-feed-open-post",
        "candidate_digest": CANDIDATE,
        "readback_verified": True,
    }
    value.update(overrides)
    return value


def bundle(**overrides: Any) -> dict[str, Any]:
    value = {
        "candidate_digest": CANDIDATE,
        "integration_depth": "alpha_integration",
        "launch_receipt": launch_receipt(),
        "required_case_ids": ["content-feed-api-integration"],
        "api_integration_cases": [api_case()],
        "required_journey_ids": ["home-feed-open-post"],
        "journey_readbacks": [journey_readback()],
    }
    value.update(overrides)
    return value


# --- G2 档位由 typed impact 派生，不得人工降档 ---


@pytest.mark.parametrize(
    ("changed_path", "expected_depth"),
    [
        ("quwoquan_data/scripts/content/release/publish.py", "abg_release_sensitive"),
        ("quwoquan_ops/environments/topology.yaml", "abg_release_sensitive"),
        ("quwoquan_app/lib/ui/chat/pages/chat_page.dart", "alpha_integration"),
        ("quwoquan_service/services/user-service/internal/account/service.go", "alpha_integration"),
        ("quwoquan_ops/portal/src/main.ts", "abg_release_sensitive"),
        ("docs/ci/delivery-gate.md", "no_live"),
    ],
)
def test_integration_depth_is_derived_from_typed_impact(changed_path: str, expected_depth: str) -> None:
    classification = classify_impacts([changed_path])
    depth = derive_integration_depth(classification)
    assert depth in INTEGRATION_DEPTHS
    assert depth == expected_depth


@pytest.mark.parametrize(
    "classification",
    [
        None,
        {},
        {"scopes": {"service": True}},
        {"scopes": {"service": True, "app": True, "portal": True, "topology": True, "data": "yes"}},
        {"scopes": {"service": True, "app": True, "portal": True, "topology": True, "data": True, "extra": True}},
    ],
)
def test_integration_depth_fails_closed_on_malformed_scopes(classification: Any) -> None:
    with pytest.raises(ImpactPlannerError):
        derive_integration_depth(classification)  # type: ignore[arg-type]


# --- GWT-003.t1 三项证据齐备且绑定同一候选摘要时放行 ---


def test_complete_real_device_closure_passes_and_is_promotable() -> None:
    result = evaluate_app_cloud_closure(bundle())
    assert result["status"] == "pass"
    assert result["blockers"] == []
    assert result["promotable"] is True
    assert result["candidate_digest"] == CANDIDATE


def test_simulator_closure_passes_for_integration_but_is_non_promotable() -> None:
    result = evaluate_app_cloud_closure(
        bundle(launch_receipt=launch_receipt(device_class="simulator"))
    )
    assert result["status"] == "pass"
    assert result["blockers"] == []
    assert result["promotable"] is False


# --- GWT-003.t2 缺任一项、skipped>0 或候选摘要漂移时保持 GATE_BLOCK ---


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        launch_receipt(status="failed"),
        launch_receipt(runtimeHealthStatus="unhealthy"),
        launch_receipt(configurationState="incomplete"),
    ],
)
def test_missing_or_unhealthy_launch_receipt_blocks(receipt: dict[str, Any] | None) -> None:
    result = evaluate_app_cloud_closure(bundle(launch_receipt=receipt))
    assert result["status"] == "blocked"
    assert "APP_LAUNCH_RECEIPT_MISSING" in result["blockers"]
    assert result["promotable"] is False


@pytest.mark.parametrize(
    "cases",
    [
        [],
        [api_case(transport="in_process_fake")],
        [api_case(transport="widget"), api_case(transport="analyzer")],
    ],
)
def test_structural_or_fake_api_evidence_never_counts_as_real_service(cases: list[dict[str, Any]]) -> None:
    result = evaluate_app_cloud_closure(bundle(api_integration_cases=cases))
    assert result["status"] == "blocked"
    assert "REAL_SERVICE_CASE_RESULT_MISSING" in result["blockers"]


@pytest.mark.parametrize(
    "case",
    [api_case(executed=0), api_case(skipped=1), api_case(executed=0, skipped=2)],
)
def test_required_case_skipped_or_not_executed_blocks(case: dict[str, Any]) -> None:
    result = evaluate_app_cloud_closure(bundle(api_integration_cases=[case]))
    assert result["status"] == "blocked"
    assert "REQUIRED_CASE_SKIPPED" in result["blockers"]


@pytest.mark.parametrize(
    "case",
    [
        api_case(status="passed", failed=1),
        api_case(status="failed", failed=0),
        api_case(status="error", failed=0),
    ],
)
def test_status_or_failed_count_independently_blocks_required_case(case: dict[str, Any]) -> None:
    result = evaluate_app_cloud_closure(bundle(api_integration_cases=[case]))
    assert result["status"] == "blocked"
    assert "REQUIRED_CASE_FAILED" in result["blockers"]


def test_missing_required_case_id_blocks_even_when_another_real_case_passes() -> None:
    result = evaluate_app_cloud_closure(
        bundle(
            required_case_ids=[
                "content-feed-api-integration",
                "content-detail-api-integration",
            ],
            api_integration_cases=[api_case()],
        )
    )
    assert result["status"] == "blocked"
    assert "REAL_SERVICE_CASE_RESULT_MISSING" in result["blockers"]


@pytest.mark.parametrize(
    "readbacks",
    [
        [],
        [journey_readback(readback_verified=False)],
        [journey_readback(journey_id="unrelated-journey")],
    ],
)
def test_missing_required_journey_readback_blocks(readbacks: list[dict[str, Any]]) -> None:
    result = evaluate_app_cloud_closure(bundle(journey_readbacks=readbacks))
    assert result["status"] == "blocked"
    assert "JOURNEY_READBACK_MISSING" in result["blockers"]


@pytest.mark.parametrize(
    "extra",
    [
        journey_readback(journey_id="unrelated-journey"),
        journey_readback(journey_id="unrelated-journey", readback_verified=False),
        journey_readback(journey_id="unrelated-journey", candidate_digest=OTHER_CANDIDATE),
    ],
)
def test_extra_journey_readback_breaks_exact_coverage(extra: dict[str, Any]) -> None:
    result = evaluate_app_cloud_closure(
        bundle(journey_readbacks=[journey_readback(), extra])
    )
    assert result["status"] == "blocked"
    assert "JOURNEY_READBACK_MISSING" in result["blockers"]


@pytest.mark.parametrize(
    "duplicate",
    [
        journey_readback(readback_verified=False),
        journey_readback(candidate_digest=OTHER_CANDIDATE),
        journey_readback(),
    ],
)
def test_all_duplicate_journey_readbacks_fail_closed(
    duplicate: dict[str, Any],
) -> None:
    with pytest.raises(ClosureContractError, match="Journey readback 重复"):
        evaluate_app_cloud_closure(
            bundle(journey_readbacks=[duplicate, journey_readback()])
        )


@pytest.mark.parametrize(
    ("overrides", "companion_blocker"),
    [
        ({"launch_receipt": launch_receipt(candidate_digest=OTHER_CANDIDATE)}, "APP_LAUNCH_RECEIPT_MISSING"),
        ({"api_integration_cases": [api_case(candidate_digest=OTHER_CANDIDATE)]}, "REAL_SERVICE_CASE_RESULT_MISSING"),
        ({"journey_readbacks": [journey_readback(candidate_digest=OTHER_CANDIDATE)]}, "JOURNEY_READBACK_MISSING"),
    ],
)
def test_evidence_bound_to_other_candidate_digest_blocks(
    overrides: dict[str, Any], companion_blocker: str,
) -> None:
    result = evaluate_app_cloud_closure(bundle(**overrides))
    assert result["status"] == "blocked"
    assert "CANDIDATE_DIGEST_MISMATCH" in result["blockers"]
    assert companion_blocker in result["blockers"]
    assert result["promotable"] is False


def test_all_five_negative_classes_report_together_deterministically() -> None:
    result = evaluate_app_cloud_closure(
        bundle(
            launch_receipt=None,
            api_integration_cases=[api_case(candidate_digest=OTHER_CANDIDATE)],
            journey_readbacks=[],
        )
    )
    assert result["status"] == "blocked"
    assert result["blockers"] == [
        "APP_LAUNCH_RECEIPT_MISSING",
        "REAL_SERVICE_CASE_RESULT_MISSING",
        "JOURNEY_READBACK_MISSING",
        "CANDIDATE_DIGEST_MISMATCH",
    ]


# --- 合同边界 fail-closed ---


@pytest.mark.parametrize(
    "broken",
    [
        bundle(candidate_digest="sha256:short"),
        bundle(integration_depth="no_live"),
        bundle(integration_depth="manual_downgrade"),
        bundle(launch_receipt=launch_receipt(device_class="emulator_farm")),
        bundle(api_integration_cases=[api_case(transport="")]),
        bundle(api_integration_cases=[api_case(executed=-1)]),
        bundle(api_integration_cases=[api_case(executed=True)]),
        bundle(api_integration_cases=[api_case(status="unknown")]),
        bundle(api_integration_cases=[api_case(), api_case()]),
        bundle(required_case_ids=[]),
        bundle(required_case_ids=["duplicate", "duplicate"]),
        bundle(required_journey_ids=[]),
        bundle(required_journey_ids=["duplicate", "duplicate"]),
        bundle(api_integration_cases="not-a-list"),
        bundle(journey_readbacks="not-a-list"),
        bundle(journey_readbacks=[journey_readback(journey_id="")]),
    ],
)
def test_malformed_bundle_fails_closed(broken: dict[str, Any]) -> None:
    with pytest.raises(ClosureContractError):
        evaluate_app_cloud_closure(broken)


# --- CLI gate 出口语义 ---


def run_gate(payload: object, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-B", str(GATE_SCRIPT), str(bundle_path)],
        text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_cli_passes_complete_bundle_and_reports_promotion(tmp_path: Path) -> None:
    completed = run_gate(bundle(), tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "promotion=promotable" in completed.stdout
    simulator = run_gate(bundle(launch_receipt=launch_receipt(device_class="simulator")), tmp_path)
    assert simulator.returncode == 0, simulator.stderr
    assert "promotion=nonPromotable" in simulator.stdout


def test_cli_blocks_incomplete_bundle_with_one_line_per_blocker(tmp_path: Path) -> None:
    completed = run_gate(bundle(launch_receipt=None, journey_readbacks=[]), tmp_path)
    assert completed.returncode == 1
    lines = [line for line in completed.stderr.splitlines() if "GATE_BLOCK" in line]
    assert len(lines) == 2
    assert any("blocker=APP_LAUNCH_RECEIPT_MISSING" in line for line in lines)
    assert any("blocker=JOURNEY_READBACK_MISSING" in line for line in lines)
    assert all("code=EVIDENCE.APP_CLOUD_CLOSURE_BLOCKED" in line for line in lines)
    assert all("recovery=" in line for line in lines)


def test_cli_fails_closed_on_contract_invalid_bundle(tmp_path: Path) -> None:
    completed = run_gate(bundle(integration_depth="no_live"), tmp_path)
    assert completed.returncode == 1
    assert "code=EVIDENCE.APP_CLOUD_CONTRACT_INVALID" in completed.stderr
    assert "recovery=repair_evidence_bundle_contract" in completed.stderr
