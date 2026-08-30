# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 无逃逸口与仓库基线自洽的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：CLI 无 warn-only/skip 选项、不读环境变量旁路、Delivery Gate
真实采集 Cloud 覆盖、红测试不能写基线、仓库基线 provenance 自洽且阈值未被
架空。测试逐字搬移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.tests.support.canonical_coverage_gate_test_support import (
    _app_metrics,
    _app_unit,
    _baseline_with,
    _cloud_unit,
    _gate_source_files,
    _identity,
)


DELIVERY_GATE_PATH = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"


# ---------------------------------------------------------------------------
# 无逃逸口 + 仓库基线自洽
# ---------------------------------------------------------------------------


def test_the_gate_exposes_no_warn_only_or_skip_escape() -> None:
    options = {
        option
        for action in vcr.build_parser()._actions
        for option in action.option_strings
    }

    # `--app-shards` 只决定端侧采集分几次进程跑完同一批测试文件，是容量旋钮而非
    # 逃逸口；它的无逃逸性由 test_canonical_coverage_app_sharding__gate__* 证明。
    assert options == {
        "-h",
        "--help",
        "--scope",
        "--unit",
        "--collect",
        "--write-baseline",
        "--app-shards",
    }


def test_the_gate_reads_no_environment_switch_that_could_turn_it_off() -> None:
    """门禁行为只由参数决定；不得存在「设个环境变量就放行」的旁路。"""
    for source_path in _gate_source_files():
        source = source_path.read_text(encoding="utf-8")

        if source_path.name == "app_runtime.py":
            # App coverage 必须继承工具链所需的宿主环境，再显式清除所有会改变
            # runtime/test selection 的键；对应清除行为由 app sharding contract
            # 逐键验证。这里只允许这一处受控读取，禁止把它扩散成旁路开关。
            assert source.count("os.environ") == 1
            assert "dict(os.environ if base is None else base)" in source
        else:
            assert "os.environ" not in source, source_path.name
        assert "getenv" not in source, source_path.name


def test_unknown_unit_is_rejected_instead_of_silently_passing() -> None:
    assert vcr.main(["--unit", "cloud:not-a-domain"]) == 2


def test_cloud_measurement_keeps_neighbor_objects_and_cross_cutting_separate() -> None:
    attribution = vcr.CloudAttribution(vcr._roster())
    object_units = [
        unit
        for unit in sorted(attribution.files_by_unit)
        if not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    ]
    first, second = object_units[:2]
    first_source = sorted(attribution.files_by_unit[first])[0]
    second_source = sorted(attribution.files_by_unit[second])[0]
    cmd_source = sorted(attribution.files_by_unit[vcr.cloud_cross_cutting_unit("cmd")])[
        0
    ]
    profile = {
        f"quwoquan_service/{first_source}": (3, 10),
        f"quwoquan_service/{second_source}": (9, 10),
        f"quwoquan_service/{cmd_source}": (10, 10),
    }

    measured = vcr._measure_cloud_unit(first, [("probe", profile)], attribution)

    assert measured == {"statement": {"covered": 3, "total": 10, "percent": 30.0}}


def test_cloud_zero_statement_numerator_blocks_before_baseline() -> None:
    attribution = vcr.CloudAttribution(vcr._roster())
    unit = next(
        candidate
        for candidate in sorted(attribution.files_by_unit)
        if not candidate.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    )
    source = sorted(attribution.files_by_unit[unit])[0]

    with pytest.raises(vcr.CoverageError, match="statement 实测 0/7"):
        vcr._measure_cloud_unit(
            unit,
            [("probe", {f"quwoquan_service/{source}": (0, 7)})],
            attribution,
        )


def test_delivery_gate_collects_cloud_object_coverage_instead_of_preblocking() -> None:
    """Delivery Gate 必须执行真实 Cloud 采集，不能保留未接线占位阻断。"""
    delivery_gate = DELIVERY_GATE_PATH.read_text(encoding="utf-8")
    collector = "\n".join(
        source.read_text(encoding="utf-8") for source in _gate_source_files()
    )

    assert (
        "python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope cloud"
    ) in delivery_gate
    assert "CLOUD_OBJECT_COVERAGE_GAP" not in collector


def test_write_baseline_requires_a_real_collection_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不跑测试就写基线 = 凭空断言 provenance。"""
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [_app_unit()])
    assert vcr.main(["--write-baseline", "--unit", _app_unit()]) == 2


def test_a_red_test_run_blocks_verification_and_cannot_write_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: _identity())
    unit = _app_unit()
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [unit])
    baseline_path.write_text(
        json.dumps(
            _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0)),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original_baseline = baseline_path.read_bytes()

    def _red_collect(target: str, **_shard_options) -> None:
        vcr.artifact_path(target).write_text(
            "mode: atomic\npkg/a.go:1.1,3.2 5 1\npkg/a.go:5.1,6.2 5 0\n",
            encoding="utf-8",
        )
        vcr._write_artifact_receipt(target, tests_green=False)
        raise vcr.RedTestRun("测试没全绿")

    monkeypatch.setattr(vcr, "collect", _red_collect)

    # 求值路径：红着的测试测出来的覆盖率不是准出证据。
    assert vcr.main(["--collect", "--unit", unit]) == 1

    # 登记路径同样阻断，且 tracked baseline 必须保持原字节不变。
    assert vcr.main(["--collect", "--write-baseline", "--unit", unit]) == 1
    assert baseline_path.read_bytes() == original_baseline


def test_scope_selection_narrows_units_without_dropping_any_axis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_app = (_app_unit(),)
    expected_cloud = (_cloud_unit(),)
    monkeypatch.setattr(vcr, "discover_app_units", lambda: expected_app)
    monkeypatch.setattr(vcr, "discover_cloud_units", lambda: expected_cloud)
    monkeypatch.setattr(vcr, "discover_units", lambda: expected_app + expected_cloud)
    app_units = vcr.resolve_units("app", None)
    cloud_units = vcr.resolve_units("cloud", None)

    assert all(unit.startswith(vcr.APP_UNIT_PREFIX) for unit in app_units)
    assert all(unit.startswith(vcr.CLOUD_UNIT_PREFIX) for unit in cloud_units)
    assert app_units + cloud_units == list(vcr.discover_units())
    assert vcr.resolve_units("all", None) == list(vcr.discover_units())
    assert vcr.resolve_units("all", [_cloud_unit()]) == [_cloud_unit()]
    assert vcr.resolve_units("service", None) == cloud_units


def test_each_kind_carries_the_axes_it_can_actually_measure() -> None:
    # 端侧三轴；云侧 Go/Python 都只有语句覆盖，且采集器都保留未触达文件分母。
    assert vcr.METRICS_BY_KIND[vcr.KIND_FLUTTER_LCOV] == ("branch", "file", "line")
    assert vcr.METRICS_BY_KIND[vcr.KIND_CLOUD_STATEMENT] == ("statement",)


def test_repository_baseline_is_provenance_bound_or_explicitly_gate_blocked() -> None:
    if not vcr.BASELINE_PATH.is_file():
        with pytest.raises(FileNotFoundError):
            vcr.load_baseline()
        return
    baseline = vcr.load_baseline()

    governance = baseline["_governance"]
    for key in ("owner", "reason", "expires_when", "measure"):
        assert str(governance.get(key) or "").strip(), f"_governance.{key} 不得为空"
    # 采集范围必须在 governance 里如实交代，不得谎称全量。
    assert vcr.APP_TEST_TARGET in governance["reason"]
    assert "BRDA" in governance["reason"]

    for unit, entry in baseline["units"].items():
        assert entry["kind"] == vcr.unit_kind(unit)
        assert entry["scope"] == vcr.unit_scope(unit)
        assert entry["measuredFromGreenTests"] is True
        assert entry["receiptDigests"]
        assert sorted(entry["metrics"]) == sorted(vcr.METRICS_BY_KIND[entry["kind"]])
        for metric, values in entry["metrics"].items():
            assert values.get("status") != vcr.METRIC_STATUS_UNMEASURED, (
                f"{unit}/{metric} 不可测状态只能作为当前阻断原因，不能进入 baseline"
            )
            assert values["covered"] > 0, (
                f"{unit}/{metric} 0/N 不能成为可准出 baseline"
            )
            assert values["total"] > 0, f"{unit}/{metric} 分母必须是实测值"
            assert 0 <= values["covered"] <= values["total"]
            assert values["percent"] == vcr.percent(
                values["covered"], values["total"]
            ), f"{unit}/{metric} percent 与 covered/total 不自洽"


def test_repository_baseline_thresholds_are_not_disabled() -> None:
    """阈值必须反映真实现状，不得被设成 0 或用巨大容差架空。"""
    policy = (
        vcr.load_baseline()["policy"]
        if vcr.BASELINE_PATH.is_file()
        else vcr.CANONICAL_POLICY
    )

    assert 0 < policy["tolerance_percentage_points"] <= 1.0
    assert 0 < policy["improvement_slack_percentage_points"] <= 5.0
    # 粒度下限只为小桶兜底；放大到几十个单位就成了逃逸口。
    assert 0 < policy["granularity_units"] <= 3.0
