# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution.planning.capacity_bootstrap import (
    CapacityBootstrapError,
    CapacityBootstrapStatusQuery,
    build_capacity_bootstrap_composition,
    load_measurement_safety_policy,
)


DIGEST = "sha256:" + "a" * 64


def _passed_evidence(run_id: str, policy_digest: str) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.capacity_calibration_bootstrap",
        "documentKind": "evidence",
        "bootstrapRunId": run_id,
        "authority": "measurement_only",
        "hostClass": "local-apple-silicon",
        "providerTier": "cursor_grok",
        "semanticSelectionId": "cursor_grok",
        "workload": {"scale": "M100", "objectCount": 100, "digest": DIGEST},
        "policyDigest": policy_digest,
        "objectTimings": [
            {
                "objectRef": f"measurement-object-{index:03d}",
                "outcome": "succeeded",
                "durationMilliseconds": index + 1,
            }
            for index in range(100)
        ],
        "fleetReport": {
            "outcome": "passed",
            "total": 100,
            "peakConcurrentWorkers": 1,
            "wallClockMilliseconds": 10_000,
            "resourceSamples": [
                {"rssBytes": 1024, "cpuPercent": 1.0, "capturedAt": "2026-08-20T00:00:00Z"}
            ],
        },
        "blockers": [],
    }


def test_policy_is_versioned_measurement_only_and_fixed_to_one_worker() -> None:
    policy, _path, _digest = load_measurement_safety_policy()

    assert policy == {
        "schema": "quwoquan_data.capacity_bootstrap_measurement_safety_policy",
        "policyId": "capacity-bootstrap-measurement-safety",
        "authority": "measurement_only",
        "workload": {"scale": "M100", "objectCount": 100},
        "maxConcurrentWorkers": 1,
        "allowedSemanticSelectionIds": ["cursor_grok"],
    }
    assert not {
        "autoResearchMaxConcurrentWorkers",
        "fleetMaxConcurrentWorkers",
        "objectWallClockSeconds",
        "completionGraceSeconds",
    } & policy.keys()


def test_create_once_state_machine_and_composition_have_no_production_writers(
    tmp_path: Path,
) -> None:
    composition = build_capacity_bootstrap_composition(output_root=tmp_path)
    assert set(vars(composition)) == {"command_writer", "status_query"}
    assert not any(
        token in type(value).__module__
        for value in vars(composition).values()
        for token in ("publish", "release", "environment", "author", "review")
    )

    prepared = composition.command_writer.prepare(
        bootstrap_run_id="bootstrap-local-001",
        host_class="local-apple-silicon",
        provider_tier="cursor_grok",
        semantic_selection_id="cursor_grok",
        workload_digest=DIGEST,
    )
    replay = composition.command_writer.prepare(
        bootstrap_run_id="bootstrap-local-001",
        host_class="local-apple-silicon",
        provider_tier="cursor_grok",
        semantic_selection_id="cursor_grok",
        workload_digest=DIGEST,
    )
    assert prepared["status"] == "prepared"
    assert replay == prepared

    running = composition.command_writer.run("bootstrap-local-001")
    assert running["status"] == "running"
    assert composition.status_query.get("bootstrap-local-001") == running

    _policy, _path, policy_digest = load_measurement_safety_policy()
    evidence_path = tmp_path / "passed-evidence.json"
    evidence_path.write_text(
        json.dumps(_passed_evidence("bootstrap-local-001", policy_digest)),
        encoding="utf-8",
    )
    measured = composition.command_writer.finalize(
        "bootstrap-local-001", evidence_path=evidence_path
    )
    assert measured["status"] == "measured"
    assert not tuple(tmp_path.rglob("governed_capacity_calibration_receipt.json"))

    with pytest.raises(CapacityBootstrapError) as collision:
        composition.command_writer.prepare(
            bootstrap_run_id="bootstrap-local-001",
            host_class="other-host",
            provider_tier="cursor_grok",
            semantic_selection_id="cursor_grok",
            workload_digest=DIGEST,
        )
    assert collision.value.code == "DATA.CAPACITY.BOOTSTRAP_CREATE_ONCE_CONFLICT"


def test_failed_evidence_is_typed_and_daily_policy_does_not_read_bootstrap(
    tmp_path: Path,
) -> None:
    composition = build_capacity_bootstrap_composition(output_root=tmp_path)
    prepared = composition.command_writer.prepare(
        bootstrap_run_id="bootstrap-local-002",
        host_class="local-apple-silicon",
        provider_tier="cursor_grok",
        semantic_selection_id="cursor_grok",
        workload_digest=DIGEST,
    )
    composition.command_writer.run("bootstrap-local-002")
    _policy, _path, policy_digest = load_measurement_safety_policy()
    evidence = _passed_evidence("bootstrap-local-002", policy_digest)
    evidence["objectTimings"][0]["outcome"] = "failed"  # type: ignore[index]
    evidence["objectTimings"][0]["blocker"] = {  # type: ignore[index]
        "code": "DATA.CAPACITY.BOOTSTRAP_PROVIDER_FAILED",
        "recovery": "retry_with_new_bootstrap_run",
    }
    evidence["fleetReport"]["outcome"] = "failed"  # type: ignore[index]
    evidence["blockers"] = [
        {
            "code": "DATA.CAPACITY.BOOTSTRAP_PROVIDER_FAILED",
            "recovery": "retry_with_new_bootstrap_run",
        }
    ]
    evidence_path = tmp_path / "failed-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    failed = composition.command_writer.finalize(
        "bootstrap-local-002", evidence_path=evidence_path
    )
    assert failed["status"] == "failed"
    assert failed["blocker"]["code"] == "DATA.CAPACITY.BOOTSTRAP_PROVIDER_FAILED"

    from content.execution.planning import capacity_calibration, capacity_policy

    for module in (capacity_calibration, capacity_policy):
        assert "capacity_bootstrap" not in Path(module.__file__).read_text(encoding="utf-8")


def test_cancel_is_create_once_terminal_and_missing_status_is_typed(tmp_path: Path) -> None:
    composition = build_capacity_bootstrap_composition(output_root=tmp_path)
    composition.command_writer.prepare(
        bootstrap_run_id="bootstrap-local-003",
        host_class="local-apple-silicon",
        provider_tier="cursor_grok",
        semantic_selection_id="cursor_grok",
        workload_digest=DIGEST,
    )
    canceled = composition.command_writer.cancel(
        "bootstrap-local-003", reason="operator_requested"
    )
    assert canceled["status"] == "canceled"
    assert composition.command_writer.cancel(
        "bootstrap-local-003", reason="operator_requested"
    ) == canceled

    with pytest.raises(CapacityBootstrapError) as missing:
        CapacityBootstrapStatusQuery(output_root=tmp_path).get("missing-run")
    assert missing.value.code == "DATA.CAPACITY.BOOTSTRAP_NOT_FOUND"
