# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 端侧对象计量与采集失败阻断的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：App 对象只计量自己拥有的文件、分母为 0 绝不折成 0%、
`file` 轴堵住分母缩水，以及缺产物/零分子/陌生 lcov 来源一律在 measure 阶段
阻断。测试逐字搬移。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.tests.support.canonical_coverage_gate_test_support import (
    _APP_UNIT,
    _app_unit,
    _attribution,
    _baseline_with,
    _cloud_unit,
    _identity,
    _label,
    _receipt,
)


# ---------------------------------------------------------------------------
# 端侧对象计量与 file 轴
# ---------------------------------------------------------------------------


def test_app_object_measurement_only_counts_files_owned_by_that_unit() -> None:
    attribution = _attribution({"a.dart": _APP_UNIT, "b.dart": "app:other/c/o"})
    lcov = {
        "lib/a.dart": {"line": (7, 10), "branch": (2, 4)},
        "lib/b.dart": {"line": (9, 10), "branch": (4, 4)},
    }

    metrics = vcr._measure_app_unit(_APP_UNIT, lcov, attribution)

    # 邻对象的高覆盖率不得漏进本对象——这正是 domain 聚合平均数的病。
    assert metrics["line"] == {"covered": 7, "total": 10, "percent": 70.0}
    assert metrics["branch"] == {"covered": 2, "total": 4, "percent": 50.0}
    assert metrics["file"] == {"covered": 1, "total": 1, "percent": 100.0}


def test_an_object_no_test_ever_loaded_is_unmeasured_not_zero_percent() -> None:
    """从未被触达的对象：`file` 是实测的 0/N，其他轴如实标不可测。"""
    attribution = _attribution({"a.dart": _APP_UNIT, "b.dart": _APP_UNIT})

    metrics = vcr._measure_app_unit(_APP_UNIT, {}, attribution)

    # 0/2 是磁盘上的事实，不是猜测，照实登记。
    assert metrics["file"] == {"covered": 0, "total": 2, "percent": 0.0}
    for metric in ("line", "branch"):
        assert metrics[metric]["status"] == vcr.METRIC_STATUS_UNMEASURED
        assert "percent" not in metrics[metric], "分母为 0 时绝不写 0%"
        assert metrics[metric]["reason"]

    with pytest.raises(vcr.CoverageError, match="App coverage 不可准出"):
        vcr._require_app_unit_measured(_APP_UNIT, metrics)


def test_app_zero_numerator_or_any_unmeasured_axis_blocks_before_baseline() -> None:
    zero_branch = {
        "file": {"covered": 1, "total": 1, "percent": 100.0},
        "line": {"covered": 2, "total": 3, "percent": 66.67},
        "branch": {"covered": 0, "total": 2, "percent": 0.0},
    }
    with pytest.raises(vcr.CoverageError, match="branch=0/2"):
        vcr._require_app_unit_measured(_APP_UNIT, zero_branch)

    unmeasured_branch = dict(
        zero_branch,
        branch={"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "no branches"},
    )
    with pytest.raises(vcr.CoverageError, match="branch=unmeasured"):
        vcr._require_app_unit_measured(_APP_UNIT, unmeasured_branch)

    vcr._require_app_unit_measured(
        _APP_UNIT,
        dict(
            zero_branch,
            branch={"covered": 1, "total": 2, "percent": 50.0},
        ),
    )


def test_an_app_unit_without_any_production_file_is_not_a_measurement_unit() -> None:
    with pytest.raises(vcr.CoverageError, match="没有 production source"):
        vcr._measure_app_unit("app:missing/context/object", {}, _attribution({}))


def test_the_file_axis_closes_the_shrinking_denominator_loophole() -> None:
    """删掉覆盖低的测试会让 lcov 分母变小、line 反而上升；file 轴必须拦住。"""
    attribution = _attribution({"well.dart": _APP_UNIT, "poorly.dart": _APP_UNIT})
    before = vcr._measure_app_unit(
        _APP_UNIT,
        {
            "lib/well.dart": {"line": (10, 10), "branch": (2, 2)},
            "lib/poorly.dart": {"line": (1, 10), "branch": (0, 2)},
        },
        attribution,
    )
    # 摘掉 poorly.dart 的 import 后它整个离开 lcov 分母。
    after = vcr._measure_app_unit(
        _APP_UNIT,
        {"lib/well.dart": {"line": (10, 10), "branch": (2, 2)}},
        attribution,
    )

    assert before["line"]["percent"] == 55.0
    assert after["line"]["percent"] == 100.0, "行覆盖率确实会被这么做抬上去"

    baseline = _baseline_with(_app_unit(), before)
    failures = vcr.diff({_app_unit(): after}, baseline, [_app_unit()])

    labels = [_label(entry) for entry in failures]
    assert f"{_app_unit()}/file" in labels
    # line 看起来上升也会要求收紧基线；关键是 file 轴必须独立识别触达文件减少。
    assert f"{_app_unit()}/line" in labels
    assert "50.00%" in failures[0]


# ---------------------------------------------------------------------------
# 采集失败一律阻断
# ---------------------------------------------------------------------------


def test_missing_artifact_blocks_instead_of_degrading_to_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([_cloud_unit()])
    with pytest.raises(vcr.CoverageError):
        vcr.measure([_app_unit()])


def test_measure_blocks_an_app_zero_numerator_before_loading_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vcr, "AppAttribution", lambda _roster: _attribution({"a.dart": _APP_UNIT})
    )
    monkeypatch.setattr(vcr, "parse_lcov", lambda _text: {})
    monkeypatch.setattr(
        vcr, "_read_artifact", lambda _target: ("unused", _receipt("app"))
    )

    with pytest.raises(vcr.CoverageError, match="file=0/1"):
        vcr.measure([_APP_UNIT])


def test_an_empty_go_denominator_blocks_because_collection_did_not_take_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    unit = _cloud_unit()
    attribution = vcr.CloudAttribution(vcr._roster())
    source = sorted(attribution.files_by_unit[unit])[0]
    for target in vcr.cloud_collection_targets_for_unit(unit):
        vcr.artifact_path(target).write_text(
            f"mode: atomic\nquwoquan_service/{source}:1.1,3.2 0 0\n",
            encoding="utf-8",
        )
        vcr._write_artifact_receipt(target, tests_green=True)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([unit])


def test_an_lcov_source_outside_the_derived_roster_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """归属派生器与产物不同源时必须阻断，不能把陌生文件悄悄丢掉。"""
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    monkeypatch.setattr(
        vcr,
        "AppAttribution",
        lambda _roster: SimpleNamespace(known=lambda _source: False),
    )
    vcr.artifact_path(vcr.APP_COLLECTION_TARGET).write_text(
        "SF:vendor/elsewhere.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(vcr.APP_COLLECTION_TARGET, tests_green=True)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([_app_unit()])
