# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` canonical rule 求值语义的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：达标放行、超容差下降阻断、涨太多要求收紧、未登记/陈旧
单元阻断、scope 与可测性漂移阻断。测试逐字搬移。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.tests.support.canonical_coverage_gate_test_support import (
    _app_metrics,
    _app_unit,
    _baseline_with,
    _block,
    _cloud_unit,
    _label,
)


# ---------------------------------------------------------------------------
# canonical rule 语义
# ---------------------------------------------------------------------------


def test_summary_keeps_line_branch_and_file_denominators() -> None:
    unit = _app_unit()
    metrics = _app_metrics(41.0, 23.0, 67.0)

    summary = vcr.summarize({unit: metrics}, [unit])

    assert summary["units"][unit] == {
        metric: metrics[metric] for metric in ("branch", "file", "line")
    }
    for metric in ("line", "branch", "file"):
        assert set(summary["units"][unit][metric]) == {
            "covered",
            "total",
            "percent",
        }


def test_meeting_the_baseline_passes_and_a_small_rise_passes_too() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    assert vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit]) == []
    assert vcr.diff({unit: _app_metrics(42.0, 22.0, 62.0)}, baseline, [unit]) == []


def test_a_drop_beyond_the_tolerance_blocks_per_metric() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    # 容差内的浮动不阻断。
    assert vcr.diff({unit: _app_metrics(39.8, 20.0, 60.0)}, baseline, [unit]) == []

    failures = vcr.diff({unit: _app_metrics(39.4, 16.0, 60.0)}, baseline, [unit])

    assert sorted(_label(entry) for entry in failures) == [
        f"{unit}/branch",
        f"{unit}/line",
    ]


def test_branch_coverage_is_enforced_independently_of_line_coverage() -> None:
    """只堆无分支的直线代码把行覆盖率糊上去，救不了掉下去的分支覆盖率。"""
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    failures = vcr.diff({unit: _app_metrics(40.5, 12.0, 60.0)}, baseline, [unit])

    assert [_label(entry) for entry in failures] == [f"{unit}/branch"]


def test_a_rise_beyond_the_slack_blocks_so_the_baseline_cannot_rot() -> None:
    unit = _cloud_unit()
    baseline = _baseline_with(unit, {"statement": _block(13.0)})

    failures = vcr.diff({unit: {"statement": _block(19.0)}}, baseline, [unit])

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}/statement:")
    assert "--write-baseline" in failures[0]


def test_the_granularity_floor_only_widens_thresholds_for_tiny_buckets() -> None:
    """小桶动一个分支就是几个百分点；大桶不受影响，约束力不被削弱。"""
    policy = {
        "tolerance_percentage_points": 0.3,
        "improvement_slack_percentage_points": 3.0,
        "granularity_units": 2.0,
    }

    tiny_tolerance, tiny_slack = vcr.thresholds(policy, 40)
    large_tolerance, large_slack = vcr.thresholds(policy, 20000)

    # 40 个分支：一个分支是 2.5pp，两个是 5pp。
    assert tiny_tolerance == pytest.approx(5.0)
    assert tiny_slack == pytest.approx(5.0)
    # 两万条语句：两个单位只有 0.01pp，配置值继续生效。
    assert large_tolerance == pytest.approx(0.3)
    assert large_slack == pytest.approx(3.0)


def test_an_unregistered_unit_blocks_instead_of_passing_by_default() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"].pop(unit)

    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        baseline,
        [unit],
        known_units=[unit],
    )

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}: 未登记单元")


def test_a_stale_baseline_unit_blocks_and_must_be_converged_explicitly() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    retired = "app:retired/context/object"
    baseline["units"][retired] = baseline["units"][unit]

    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        baseline,
        [unit],
        known_units=[unit],
    )

    assert len(failures) == 1
    assert failures[0].startswith(f"{retired}: 基线里的陈旧单元")


def test_collection_scope_drift_blocks_instead_of_comparing_incomparable_numbers() -> (
    None
):
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["scope"] = "quwoquan_app: flutter test --coverage"

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert len(failures) == 1
    assert "采集范围漂移" in failures[0]


def test_the_scope_pins_the_attribution_rule_so_a_rule_change_forces_recollection() -> (
    None
):
    """归属规则一变，同一份 lcov 的分桶结果就不可比，必须重采而不是比大小。"""
    assert opm.RULE_ID in vcr.unit_scope(_app_unit())


def test_a_provisional_baseline_entry_blocks_until_it_is_recollected() -> None:
    """采集时测试没全绿写下的暂定值不得长期挂账。"""
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["measuredFromGreenTests"] = False

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}: 基线是暂定值")


def test_a_baseline_entry_without_receipt_provenance_blocks() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit].pop("receiptDigests")

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert [_label(entry) for entry in failures] == [unit]
    assert "provenance 无法复核" in failures[0]


def test_a_missing_metric_axis_blocks_rather_than_being_skipped() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["metrics"].pop("branch")

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert failures == [f"{unit}/branch: 基线缺少该维度"]


def test_measurability_transitions_block_in_both_directions() -> None:
    """可测 → 不可测（测试被删）与不可测 → 可测（该登记真实数字）都必须阻断。"""
    unit = _app_unit()
    unmeasured = {"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "没有测试触达"}

    measured_baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    lost = dict(_app_metrics(40.0, 20.0, 60.0), line=unmeasured)
    failures = vcr.diff({unit: lost}, measured_baseline, [unit])
    assert len(failures) == 1
    assert "现在测不出来了" in failures[0]

    unmeasured_baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    unmeasured_baseline["units"][unit]["metrics"]["line"] = unmeasured
    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)}, unmeasured_baseline, [unit]
    )
    assert len(failures) == 1
    assert "现在可测了" in failures[0]
    assert "--write-baseline" in failures[0]

    # 两个未知不能相互证明覆盖率达标；file 轴也不能替代 line 轴的真实结果。
    failures = vcr.diff({unit: lost}, unmeasured_baseline, [unit])
    assert len(failures) == 1
    assert "两个 unmeasured 不能相互证明" in failures[0]
