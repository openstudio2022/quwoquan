#!/usr/bin/env python3
"""
rm_daily_metrics 维度单一真相源校验。

SSOT：specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/
analytics-metric-dictionary/spec.md —— rm_daily_metrics 仅由热写路径
(content-service BehaviorService.ProcessBatch) 维护，维度集唯一、不得漂移，
且「同一指标只能有一个主口径」。

校验规则：
  A) daily_metrics_store.go 的 DailyMetricDimensions 常量集
     == behavior_service.go 热写 IncrementMetric 消费的维度常量集（无漂移）。
  B) 维度值集 == spec 业务维度 {action, content, author, intersection}。
  C) 'referral' 不得作为 daily-metric 维度（不在 spec 业务维度，曾是漂移源）。
  D) 批聚合死代码 RunAggregation 不得回归（它曾携带 referral，与单一真相源冲突）。

用法：
  python3 scripts/recommendation/verify_daily_metrics_dimension_consistency.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DAILY_METRICS_GO = (
    SERVICE_ROOT
    / "services"
    / "content-service"
    / "internal"
    / "infrastructure"
    / "persistence"
    / "daily_metrics_store.go"
)
BEHAVIOR_SERVICE_GO = (
    SERVICE_ROOT
    / "services"
    / "content-service"
    / "internal"
    / "application"
    / "behavior_service.go"
)

# analytics-metric-dictionary spec 业务维度（rm_daily_metrics 热写单一真相源）。
EXPECTED_SPEC_DIMENSIONS = {"action", "content", "author", "intersection"}

_CONST_RE = re.compile(r'DailyMetricDimension(\w+)\s*=\s*"([^"]+)"')
_SLICE_RE = re.compile(r"DailyMetricDimensions\s*=\s*\[\]string\{(.*?)\}", re.DOTALL)
_SLICE_REF_RE = re.compile(r"DailyMetricDimension(\w+)")
_BEHAVIOR_REF_RE = re.compile(r"persistence\.DailyMetricDimension(\w+)")
_RUNAGG_RE = re.compile(r"func\s+\([^)]*\)\s+RunAggregation\b")


def main() -> int:
    if not DAILY_METRICS_GO.is_file():
        print(f"ERROR: 缺失 {DAILY_METRICS_GO}", file=sys.stderr)
        return 2
    if not BEHAVIOR_SERVICE_GO.is_file():
        print(f"ERROR: 缺失 {BEHAVIOR_SERVICE_GO}", file=sys.stderr)
        return 2

    store_src = DAILY_METRICS_GO.read_text(encoding="utf-8")
    behavior_src = BEHAVIOR_SERVICE_GO.read_text(encoding="utf-8")

    errors: list[str] = []

    const_map = {name: val for name, val in _CONST_RE.findall(store_src)}
    if not const_map:
        errors.append("daily_metrics_store.go: 未找到 DailyMetricDimension* 常量")

    slice_match = _SLICE_RE.search(store_src)
    if not slice_match:
        errors.append("daily_metrics_store.go: 未找到 DailyMetricDimensions slice")
        slice_names: set[str] = set()
    else:
        slice_names = set(_SLICE_REF_RE.findall(slice_match.group(1)))

    behavior_names = set(_BEHAVIOR_REF_RE.findall(behavior_src))
    if not behavior_names:
        errors.append(
            "behavior_service.go: 未找到 persistence.DailyMetricDimension* 引用"
        )

    # A) 单一真相源：store slice 集 == 热写引用集
    for n in sorted(slice_names - behavior_names):
        errors.append(
            f"维度 DailyMetricDimension{n} 在 store slice 但热写未消费（漂移）"
        )
    for n in sorted(behavior_names - slice_names):
        errors.append(
            f"维度 DailyMetricDimension{n} 在热写消费但不在 store slice（漂移）"
        )

    # B) 维度值集 == spec 业务维度
    dim_values = {const_map[n] for n in slice_names if n in const_map}
    if dim_values and dim_values != EXPECTED_SPEC_DIMENSIONS:
        errors.append(
            f"维度值集 {sorted(dim_values)} 与 analytics-metric-dictionary spec "
            f"{sorted(EXPECTED_SPEC_DIMENSIONS)} 不一致"
        )

    # C) referral 不得作为 daily-metric 维度
    if "referral" in const_map.values():
        errors.append(
            "daily_metrics_store.go: 'referral' 不在 spec 业务维度，禁止作为 daily-metric 维度"
        )

    # D) 死代码批聚合 RunAggregation 不得回归
    if _RUNAGG_RE.search(store_src):
        errors.append(
            "daily_metrics_store.go: RunAggregation 批聚合死代码回归（与单一真相源冲突）"
        )

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("[verify_daily_metrics_dimension_consistency] FAIL", file=sys.stderr)
        return 1

    print("[verify_daily_metrics_dimension_consistency] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
