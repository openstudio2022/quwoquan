"""求值与 CLI 入口：阈值、基线比对、汇总输出、argparse 与 ``main``。

求值路径没有 warn-only、没有关闭开关、没有环境变量旁路、没有「产物缺失就放行」
的分支——求值不到数据一律 BLOCK。除 import 重组外与拆分前逐字一致；被测试
monkeypatch 的符号（``resolve_units``、``collect``、``discover_*``、
``BASELINE_PATH``）经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Sequence

import quwoquan_ops.gate.canonical_coverage as cc

from .constants import (
    APP_UNIT_PREFIX,
    CLOUD_UNIT_PREFIX,
    METRICS_BY_KIND,
    METRIC_STATUS_UNMEASURED,
    RULE_ID,
    CoverageError,
    RedTestRun,
    _display,
)
from .attribution import measure
from .baseline import (
    _validate_baseline_receipt_registry,
    _validate_unit_receipt_refs,
    load_baseline,
    write_baseline,
)
from .collection import collect
from .units import collection_targets, unit_kind, unit_scope


def thresholds(policy: dict, total: int) -> tuple[float, float]:
    """返回该分母下生效的 ``(容差, slack)``，含「一个可数单位」的粒度下限。

    领域桶的分母跨三个数量级：`content` 有上万行，`notification` 只有几十个分支。
    固定的 pp 阈值在小桶上等于噪声放大器——动一个分支就是好几个百分点。因此阈值
    取「配置 pp」与「`granularity_units` 个可数单位折算出的 pp」的较大者：测不出
    比一个语句/分支更细的差别，就不该拿比它更细的阈值去阻断。
    """
    unit_pp = 100.0 / total
    granularity = float(policy["granularity_units"]) * unit_pp
    return (
        max(float(policy["tolerance_percentage_points"]), granularity),
        max(float(policy["improvement_slack_percentage_points"]), granularity),
    )


def diff(
    measured: dict[str, dict[str, dict]],
    baseline: dict,
    units: Sequence[str],
    *,
    known_units: Sequence[str] | None = None,
) -> list[str]:
    """返回阻断原因列表；空列表表示通过。"""
    policy = baseline.get("policy") or {}
    recorded_units = baseline.get("units") or {}
    failures: list[str] = []
    try:
        receipt_registry = _validate_baseline_receipt_registry(baseline.get("receipts"))
    except ValueError as error:
        return [f"baseline provenance 无法复核: {error}"]

    for unit in units:
        recorded = recorded_units.get(unit)
        if recorded is None:
            failures.append(
                f"{unit}: 未登记单元（仓库里存在，基线里没有）；用 --write-baseline 登记"
            )
            continue
        try:
            _validate_unit_receipt_refs(unit, recorded, receipt_registry)
        except ValueError as error:
            failures.append(f"{unit}: baseline provenance 无法复核: {error}")
            continue
        if recorded.get("kind") != unit_kind(unit):
            failures.append(
                f"{unit}: kind 漂移，基线 {recorded.get('kind')!r} != 现状 {unit_kind(unit)!r}"
            )
            continue
        if recorded.get("scope") != unit_scope(unit):
            failures.append(
                f"{unit}: 采集范围漂移，基线与现状不可比；\n"
                f"    baseline: {recorded.get('scope')}\n"
                f"    current : {unit_scope(unit)}"
            )
            continue
        if not recorded.get("measuredFromGreenTests", False):
            failures.append(
                f"{unit}: 基线是暂定值（measuredFromGreenTests=false，采集时测试没全绿）；"
                "测试已绿则用 --collect --write-baseline 重新采集"
            )
            continue
        recorded_metrics = recorded.get("metrics") or {}
        for metric in METRICS_BY_KIND[unit_kind(unit)]:
            if metric not in recorded_metrics:
                failures.append(f"{unit}/{metric}: 基线缺少该维度")
                continue
            failures += _diff_metric(
                unit, metric, measured[unit][metric], recorded_metrics[metric], policy
            )

    if known_units is not None:
        includes_app = any(unit.startswith(APP_UNIT_PREFIX) for unit in units)
        includes_cloud = any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units)
        recorded_in_scope = {
            unit
            for unit in recorded_units
            if (includes_app and unit.startswith(APP_UNIT_PREFIX))
            or (includes_cloud and unit.startswith(CLOUD_UNIT_PREFIX))
        }
        stale = sorted(recorded_in_scope - set(known_units))
        failures += [
            f"{unit}: 基线里的陈旧单元（仓库里已不存在）；用 --write-baseline 收敛"
            for unit in stale
        ]
    return failures


def _diff_metric(
    unit: str,
    metric: str,
    current: dict,
    recorded: dict,
    policy: dict,
) -> list[str]:
    """比对单个维度；可测性在任一方向变化都阻断，绝不把不可测折成 0%。"""
    current_unmeasured = current.get("status") == METRIC_STATUS_UNMEASURED
    recorded_unmeasured = recorded.get("status") == METRIC_STATUS_UNMEASURED
    if current_unmeasured and recorded_unmeasured:
        return [
            f"{unit}/{metric}: 基线与现状都不可测（{current.get('reason')}）；"
            "两个 unmeasured 不能相互证明覆盖率达标，必须由全绿采集产生实测值"
        ]
    if current_unmeasured:
        return [
            f"{unit}/{metric}: 基线有实测值 {recorded.get('percent')}%，现在测不出来了"
            f"（{current.get('reason')}）；测不出与归零对准出等价，不得放行"
        ]
    if recorded_unmeasured:
        return [
            f"{unit}/{metric}: 基线登记为不可测，现在可测了（{current['percent']:.2f}%，"
            f"{current['covered']}/{current['total']}）；用 --write-baseline 登记真实数字"
        ]
    if int(recorded.get("covered", 0)) <= 0:
        return [
            f"{unit}/{metric}: 基线是非法 0/{recorded.get('total')}；"
            "未触达 production 代码不能成为可准出下限，须由全绿采集重建"
        ]
    if int(current.get("covered", 0)) <= 0:
        return [
            f"{unit}/{metric}: 现状实测 0/{current.get('total')}；"
            "未触达 production 代码不得借粒度容差通过棘轮"
        ]
    floor = float(recorded["percent"])
    value = float(current["percent"])
    if metric == "file":
        # file 轴专门堵住「删掉覆盖差的测试 import，让 lcov 分母缩水」的路径。
        # 一个小桶可能只有两三个文件；若沿用两个可数单位的粒度下限，删掉其中
        # 一个会落在 50%~100% 的容差内，恰好把这条防线架空。
        tolerance = float(policy["tolerance_percentage_points"])
        slack = float(policy["improvement_slack_percentage_points"])
    else:
        tolerance, slack = thresholds(policy, int(current["total"]))
    if value < floor - tolerance:
        return [
            f"{unit}/{metric}: 覆盖率下降 {value:.2f}% < 基线 {floor:.2f}% "
            f"- 容差 {tolerance:.2f}pp（{current['covered']}/{current['total']}）"
        ]
    if value > floor + slack:
        return [
            f"{unit}/{metric}: 覆盖率已升到 {value:.2f}%，超出基线 {floor:.2f}% "
            f"+ slack {slack:.2f}pp；用 --write-baseline 收紧基线"
            f"（{current['covered']}/{current['total']}）"
        ]
    return []


def summarize(measured: dict[str, dict[str, dict]], units: Sequence[str]) -> dict:
    return {
        "ruleId": RULE_ID,
        "units": {
            unit: {
                metric: dict(measured[unit][metric])
                for metric in sorted(measured[unit])
            }
            for unit in units
        },
    }


def known_units_for(units: Sequence[str]) -> tuple[str, ...]:
    """返回所选 family 的完整当前名册，用于陈旧 baseline 检查。"""
    known: tuple[str, ...] = ()
    if any(unit.startswith(APP_UNIT_PREFIX) for unit in units):
        known += cc.discover_app_units()
    if any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units):
        known += cc.discover_cloud_units()
    return known


def resolve_units(scope: str, requested: Iterable[str] | None) -> list[str]:
    if requested:
        selected = tuple(dict.fromkeys(requested))
        invalid = sorted(
            unit
            for unit in selected
            if not unit.startswith((APP_UNIT_PREFIX, CLOUD_UNIT_PREFIX))
        )
        if invalid:
            raise ValueError(f"无法识别的单元 {invalid}")
        known = known_units_for(selected)
        unknown = sorted(set(selected) - set(known))
        if unknown:
            raise ValueError(f"未知单元 {unknown}；可用单元 {known}")
        return [unit for unit in known if unit in set(selected)]
    if scope == "app":
        return list(cc.discover_app_units())
    if scope in {"cloud", "service"}:
        return list(cc.discover_cloud_units())
    return list(cc.discover_units())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "唯一 canonical coverage rule（App/Cloud 按 service/context/object 计量）"
        )
    )
    parser.add_argument(
        "--scope",
        choices=("all", "app", "cloud", "service"),
        default="all",
        help="求值范围；`--unit` 优先于 `--scope`",
    )
    parser.add_argument(
        "--unit",
        action="append",
        default=None,
        help=(
            "只处理该单元（可重复），例如 "
            "app:circle_service/circle_management/gathering / "
            "cloud:circle_service/circle_management/gathering"
        ),
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="先跑测试采集覆盖率再求值；不带该参数时复用已落盘产物",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="仅用 App/Cloud/Python/Ops 全单元同次全绿实测值整体写入唯一 baseline",
    )
    parser.add_argument(
        "--app-shards",
        type=int,
        default=None,
        help=(
            "端侧采集切成几片顺序执行（默认由测试文件数派生）。"
            "纯容量旋钮：所有测试文件都会被执行一次，合并结果与全量运行等价，"
            "因此片数不进 scope，也不能用来跳过任何测试"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        units = cc.resolve_units(arguments.scope, arguments.unit)
    except (ValueError, CoverageError) as error:
        print(f"verify_canonical_coverage: BLOCK: {error}", file=sys.stderr)
        return 2

    if arguments.write_baseline and not arguments.collect:
        # 基线里的 `measuredFromGreenTests` 只有本次真的跑过测试才说得出口；
        # 复用旧产物写基线等于凭空断言 provenance。
        print(
            "verify_canonical_coverage: BLOCK: --write-baseline 必须搭配 --collect，"
            "基线只能由本次实跑的测试写入",
            file=sys.stderr,
        )
        return 2

    if arguments.app_shards is not None and arguments.app_shards < 1:
        print(
            "verify_canonical_coverage: BLOCK: --app-shards 必须 >= 1；"
            "分片是执行方式，不是跳过测试的手段",
            file=sys.stderr,
        )
        return 2

    if arguments.collect:
        for target in collection_targets(units):
            try:
                print(f"verify_canonical_coverage: collecting {target} ...", flush=True)
                cc.collect(target, app_shards=arguments.app_shards)
            except RedTestRun as error:
                print(
                    f"verify_canonical_coverage: BLOCK: {target}: {error}",
                    file=sys.stderr,
                )
                return 1
            except CoverageError as error:
                print(
                    f"verify_canonical_coverage: BLOCK: {target}: {error}",
                    file=sys.stderr,
                )
                return 1

    try:
        measured, extras = measure(units)
    except CoverageError as error:
        print(f"verify_canonical_coverage: BLOCK: {error}", file=sys.stderr)
        return 1

    if arguments.write_baseline:
        try:
            write_baseline(
                measured,
                units=units,
                unit_receipts=extras["unitReceipts"],
                known_units=known_units_for(units),
            )
        except (CoverageError, ValueError, json.JSONDecodeError) as error:
            print(f"verify_canonical_coverage: GATE_BLOCK: {error}", file=sys.stderr)
            return 2
        print(f"verify_canonical_coverage: wrote baseline -> {_display(cc.BASELINE_PATH)}")
        print(
            json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True)
        )
        return 0

    try:
        baseline = load_baseline()
    except FileNotFoundError:
        print(
            "verify_canonical_coverage: BLOCK: missing "
            f"{cc.BASELINE_PATH} (run once with --collect --write-baseline)",
            file=sys.stderr,
        )
        return 2
    except (ValueError, json.JSONDecodeError) as error:
        print(f"verify_canonical_coverage: FAIL load baseline: {error}", file=sys.stderr)
        return 1

    failures = diff(
        measured,
        baseline,
        units,
        known_units=known_units_for(units),
    )
    if failures:
        print("verify_canonical_coverage: BLOCK: canonical coverage rule", file=sys.stderr)
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        print(
            "  覆盖率只增不减：新增代码必须带测试。修不动时补测试，"
            "不要下调基线；覆盖率真的提升了就用 --write-baseline 收紧。",
            file=sys.stderr,
        )
        return 1

    print(f"verify_canonical_coverage: OK ({len(units)} unit(s))")
    print(json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True))
    return 0
