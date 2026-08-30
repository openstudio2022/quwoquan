# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019.t9
"""GWT-019：bootstrap authority、composition 与状态机边界。

覆盖 `t1` 的 authority 固定与不读取日常 runtime default/历史 capacity 数值、`t2`
与 `t3` 的「每个测量对象独立 timing 终态 + passed fleet report」准入形状、`t4` 的
typed blocker 与零 capacity receipt，以及 `t9` 的 authority 不可被日常入口选择。

真实 M100 measurement soak 与 100 次 Provider probe 需要外部 Provider 额度，属于
`OPEN-006` 的剩余缺口；本文件只锁边界，不以受控输入冒充那份实测。
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

import pytest

from content.execution.planning.capacity_bootstrap import (
    CapacityBootstrapError,
    CapacityBootstrapStatusQuery,
    build_capacity_bootstrap_composition,
    load_measurement_safety_policy,
)
from content.execution.planning.capacity_bootstrap_cli import (
    register_capacity_bootstrap_parser,
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


def _imported_modules(module_file: str) -> set[str]:
    """取出一个模块 import 到的模块名，按 AST 判定而不按文本匹配。"""
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names)
    return imported


def test_bootstrap_does_not_read_daily_runtime_defaults_or_historic_capacity() -> None:
    """GWT-019.t1：authority 只读自己的 measurement safety policy。

    反向（日常侧不读 bootstrap）已由上一条覆盖；这一条锁正向：bootstrap 不得从
    日常 execution policy、calibration 产物或历史 capacity 数值取任何输入，否则
    「空工作区自举」会退回成读旧值。
    """
    from content.execution.planning import capacity_bootstrap

    imported = _imported_modules(capacity_bootstrap.__file__)

    assert not {
        name
        for name in imported
        for daily in (
            "capacity_calibration",
            "capacity_policy",
            "spec_execution_policy",
        )
        if daily in name
    }
    policy, path, _digest = load_measurement_safety_policy()
    assert path.name == "capacity_bootstrap_measurement_safety.policy.yaml"
    assert policy["authority"] == "measurement_only"


def test_daily_execution_entries_cannot_select_measurement_only_authority() -> None:
    """GWT-019.t9：bootstrap authority 不能被日常 task、retry 或环境入口选择。

    `measurement_only` 只由 `task capacity-bootstrap` 子命令的 create-once 写者
    物化。日常 capacity 侧既不 import bootstrap，也没有任何入参能选到它；
    bootstrap 子命令自己的入参里也不存在 authority 开关可供改写。
    """
    from content.execution.planning import (
        capacity_calibration,
        capacity_calibration_cli,
        capacity_policy,
        spec_execution_policy,
    )

    for module in (
        capacity_calibration,
        capacity_calibration_cli,
        capacity_policy,
        spec_execution_policy,
    ):
        assert not {
            name
            for name in _imported_modules(module.__file__)
            if "capacity_bootstrap" in name
        }, module.__name__

    parser = argparse.ArgumentParser()
    register_capacity_bootstrap_parser(parser.add_subparsers(dest="task_command"))
    bootstrap_options = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    assert not {option for option in bootstrap_options if "authority" in option}
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "capacity-bootstrap",
                "prepare",
                "--bootstrap-run-id",
                "bootstrap-local-006",
                "--host-class",
                "local-apple-silicon",
                "--provider-tier",
                "cursor_grok",
                "--semantic-selection-id",
                "daily-runtime-default",
                "--workload-digest",
                DIGEST,
            ]
        )


def test_measured_requires_per_object_timings_and_a_passed_fleet_report(
    tmp_path: Path,
) -> None:
    """GWT-019.t2/t3：缺逐对象 timing 终态或缺 passed fleet report 都到不了 measured。"""
    _policy, _path, policy_digest = load_measurement_safety_policy()

    def _finalize(run_id: str, evidence: dict[str, object]) -> str:
        composition = build_capacity_bootstrap_composition(output_root=tmp_path)
        composition.command_writer.prepare(
            bootstrap_run_id=run_id,
            host_class="local-apple-silicon",
            provider_tier="cursor_grok",
            semantic_selection_id="cursor_grok",
            workload_digest=DIGEST,
        )
        composition.command_writer.run(run_id)
        evidence_path = tmp_path / f"{run_id}-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        with pytest.raises(CapacityBootstrapError) as failure:
            composition.command_writer.finalize(run_id, evidence_path=evidence_path)
        return failure.value.code

    short = _passed_evidence("bootstrap-local-004", policy_digest)
    short["objectTimings"] = short["objectTimings"][:99]  # type: ignore[index]
    assert _finalize("bootstrap-local-004", short) == (
        "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID"
    )

    unpassed = _passed_evidence("bootstrap-local-005", policy_digest)
    unpassed["fleetReport"]["outcome"] = "failed"  # type: ignore[index]
    assert _finalize("bootstrap-local-005", unpassed) == (
        "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID"
    )

    assert not tuple(tmp_path.rglob("governed_capacity_calibration_receipt.json"))


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
