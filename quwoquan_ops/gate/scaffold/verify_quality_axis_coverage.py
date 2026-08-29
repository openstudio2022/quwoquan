#!/usr/bin/env python3
"""四质量轴（性能/可靠/体验/观测）复合标签覆盖棘轮与热力图派生。

门禁模式（默认）：
- 按文件名复合标签统计 canonical 测试树的四轴覆盖数量，对照棘轮基线只增不减；
- 校验四轴共享基建（性能采样 harness、typed fault 注入、loadgen、drill 编排）物理存在。

热力图模式（--report）：
- 从 services/*/contracts/*/*/object.yaml 实时派生业务对象清单（不建 registry）；
- 输出「对象 × 质量轴 × 测试层」的 covered/missing 幂等热力图到 .qwq_output/env/repo/runs/；
- missing 单元格由 runtime-test-pyramid OPEN-003 全局承载，铺开时逐格转 covered。

spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from nonfunctional_coverage_lib import ROOT
from test_directory_layout_lib import iter_canonical_files

AXIS_TAGS = {
    "performance": "__performance__",
    "reliability": "__reliability__",
    "a11y": "__a11y__",
    "visual": "__visual__",
    "observability": "__observability__",
}
LAYERS = ("local_contract", "api_integration", "user_acceptance")
BASELINE_PATH = ROOT / "quwoquan_ops/policies/gates/quality_axis_ratchet_baseline.json"
HEATMAP_PATH = ROOT / ".qwq_output/env/repo/runs/quality_axis_heatmap.json"
SERVICES_ROOT = ROOT / "quwoquan_service/services"
GAP_OWNER_OPEN = "specs/feature-tree/runtime/runtime-test-pyramid/spec.md#open-003"

REQUIRED_INFRA = (
    (
        "quwoquan_app/test/support/runtime/performance/performance_budget_probe.dart",
        "App 性能预算采样 harness",
    ),
    (
        "quwoquan_app/test/support/runtime/fault/typed_fault_injection.dart",
        "App typed fault 注入基建",
    ),
    ("quwoquan_service/tools/loadgen/main.go", "契约驱动压测 loadgen"),
    (
        "quwoquan_ops/cli/lib/loadtest_orchestration.py",
        "stackctl loadtest 编排",
    ),
    (
        "quwoquan_ops/cli/lib/fault_drill_orchestration.py",
        "stackctl drill 故障演练编排",
    ),
)


def _axis_counts() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {
        axis: {layer: 0 for layer in LAYERS} for axis in AXIS_TAGS
    }
    for _, path, layer in iter_canonical_files():
        name = path.name
        for axis, tag in AXIS_TAGS.items():
            if tag in name:
                counts[axis][layer] += 1
    return counts


def _axis_totals(counts: dict[str, dict[str, int]]) -> dict[str, int]:
    return {axis: sum(layers.values()) for axis, layers in counts.items()}


def _derive_object_catalog() -> list[dict[str, str]]:
    objects: list[dict[str, str]] = []
    for object_yaml in sorted(SERVICES_ROOT.glob("*/contracts/*/*/object.yaml")):
        parts = object_yaml.relative_to(SERVICES_ROOT).parts
        service, _, context, object_name = parts[0], parts[1], parts[2], parts[3]
        objects.append(
            {"service": service, "context": context, "object": object_name}
        )
    return objects


def _object_axis_coverage(
    objects: list[dict[str, str]],
) -> dict[str, dict[str, dict[str, str]]]:
    tagged_paths: list[tuple[str, str, str]] = []
    for _, path, layer in iter_canonical_files():
        rel = path.relative_to(ROOT).as_posix()
        for axis, tag in AXIS_TAGS.items():
            if tag in path.name:
                tagged_paths.append((axis, layer, rel))
    coverage: dict[str, dict[str, dict[str, str]]] = {}
    for entry in objects:
        object_key = f"{entry['service']}/{entry['context']}/{entry['object']}"
        # App 测试树使用 snake_case service 目录（content-service -> content_service）。
        app_service = entry["service"].replace("-", "_")
        needles = (
            f"quwoquan_service/services/{entry['service']}/tests/",
            f"quwoquan_app/test/",
        )
        object_segment = f"/{entry['context']}/{entry['object']}/"
        app_segment = f"/{app_service}/{entry['context']}/{entry['object']}/"
        cells: dict[str, dict[str, str]] = {}
        for axis in AXIS_TAGS:
            cells[axis] = {}
            for layer in LAYERS:
                covered = any(
                    tagged_axis == axis
                    and tagged_layer == layer
                    and rel.startswith(needles[0] if rel.startswith("quwoquan_service/") else needles[1])
                    and (object_segment in rel or app_segment in rel)
                    for tagged_axis, tagged_layer, rel in tagged_paths
                )
                cells[axis][layer] = "covered" if covered else "missing"
        coverage[object_key] = cells
    return coverage


def _load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.is_file():
        return {}
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline = payload.get("minimumAxisTotals", {})
    return {axis: int(value) for axis, value in baseline.items()}


#: 首次建基线时写入的治理块。仅在文件不存在时使用。
#:
#: 已存在的治理块必须逐字保留：把它硬编码在写入路径里，等于每次 `--update-baseline`
#: 都用一份过时副本静默还原编辑——`measure` 就是这样被抹掉的。而 measure 恰恰是
#: `verify_ratchet_baseline_governance` 用来防止「换口径重建基线」无痕销账的字段。
_INITIAL_GOVERNANCE = {
    "owner": "runtime-test-pyramid",
    "reason": "quality axis tagged-test coverage ratchet (totals may only grow)",
    "expires_when": "replaced atomically by a re-captured higher baseline",
    "measure": (
        "verify_quality_axis_coverage.py counts tests carrying each axis tag across "
        "the local_contract / api_integration / user_acceptance trees; a total below "
        "minimumAxisTotals blocks."
    ),
}


def _existing_governance() -> dict[str, object]:
    if not BASELINE_PATH.is_file():
        return dict(_INITIAL_GOVERNANCE)
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    block = document.get("_governance")
    return block if isinstance(block, dict) and block else dict(_INITIAL_GOVERNANCE)


def _write_baseline(totals: dict[str, int]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_governance": _existing_governance(),
        "schema": "quality-axis-ratchet-baseline",
        "policy": "totals may only grow; regressions block",
        "minimumAxisTotals": {axis: totals[axis] for axis in sorted(totals)},
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_heatmap(
    counts: dict[str, dict[str, int]],
    coverage: dict[str, dict[str, dict[str, str]]],
) -> None:
    missing_cells = sum(
        1
        for cells in coverage.values()
        for layers in cells.values()
        for state in layers.values()
        if state == "missing"
    )
    covered_cells = sum(
        1
        for cells in coverage.values()
        for layers in cells.values()
        for state in layers.values()
        if state == "covered"
    )
    payload = {
        "schema": "quwoquan.quality-axis-heatmap",
        "axes": sorted(AXIS_TAGS),
        "layers": list(LAYERS),
        "axisLayerCounts": counts,
        "objects": coverage,
        "summary": {
            "objectCount": len(coverage),
            "coveredCells": covered_cells,
            "missingCells": missing_cells,
            "missingGapOwner": GAP_OWNER_OPEN,
        },
    }
    HEATMAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEATMAP_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"[verify] heatmap: {len(coverage)} objects, {covered_cells} covered cells, "
        f"{missing_cells} missing cells (gap owner: {GAP_OWNER_OPEN})"
    )
    print(f"[verify] written: {HEATMAP_PATH.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="derive the object x axis x layer heatmap into .qwq_output/env/repo/runs/",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="capture the current axis totals as the new ratchet baseline",
    )
    args = parser.parse_args()

    counts = _axis_counts()
    totals = _axis_totals(counts)

    if args.write_baseline:
        _write_baseline(totals)
        print(f"[verify] baseline written: {BASELINE_PATH.relative_to(ROOT)}")
        return 0

    if args.report:
        coverage = _object_axis_coverage(_derive_object_catalog())
        _write_heatmap(counts, coverage)
        return 0

    failures: list[str] = []
    for rel_path, label in REQUIRED_INFRA:
        if not (ROOT / rel_path).is_file():
            failures.append(f"missing {label}: {rel_path}")
    baseline = _load_baseline()
    if not baseline:
        failures.append(
            "missing ratchet baseline: "
            + str(BASELINE_PATH.relative_to(ROOT))
            + " (run with --write-baseline once and commit it)"
        )
    for axis, minimum in sorted(baseline.items()):
        actual = totals.get(axis, 0)
        if actual < minimum:
            failures.append(
                f"quality axis '{axis}' regressed: {actual} tagged tests < ratchet {minimum}"
            )
    if failures:
        for item in failures:
            print(f"[verify] FAIL: {item}")
        return 1
    summary = ", ".join(f"{axis}={totals[axis]}" for axis in sorted(totals))
    print(f"[verify] OK: quality axis coverage ratchet holds ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
