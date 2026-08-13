"""一次性报告的输入绑定校验、落盘与人类可读缺口打印。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .constants import (
    REPORT_BLIND_SPOT_REGISTRY_FIELD,
    REPORT_GRAPH_FIELD,
    SHA256_PATTERN,
)
from .graph_source import verify_graph_digest
from .models import Gap, display_path, sha256_file


def validate_report_graph_binding(report: Path, graph_path: Path) -> None:
    """一次性 report 必须精确绑定本次读取的 graph path 与原始字节摘要。"""
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取对象证据报告 {report}: {error}") from error
    binding = document.get(REPORT_GRAPH_FIELD)
    if not isinstance(binding, dict):
        raise SystemExit(
            f"GATE_BLOCK 对象证据报告缺少 {REPORT_GRAPH_FIELD}.path/sha256，"
            "未绑定输入 ContractGraph 的报告不得复用"
        )
    reported_path = str(binding.get("path") or "")
    reported_digest = str(binding.get("sha256") or "")
    if reported_path != display_path(graph_path):
        raise SystemExit(
            "GATE_BLOCK 对象证据报告绑定了另一份 ContractGraph："
            f"report={reported_path!r} actual={display_path(graph_path)!r}"
        )
    if not SHA256_PATTERN.fullmatch(reported_digest):
        raise SystemExit(
            f"GATE_BLOCK 对象证据报告缺少合法 {REPORT_GRAPH_FIELD}.sha256"
        )
    try:
        actual_digest = sha256_file(graph_path)
    except OSError as error:
        raise SystemExit(
            f"GATE_BLOCK 无法复核报告绑定的 ContractGraph {graph_path}: {error}"
        ) from error
    if actual_digest != reported_digest:
        raise SystemExit(
            "GATE_BLOCK 对象证据报告与 ContractGraph 摘要不一致："
            f"report={reported_digest} actual={actual_digest}"
        )


def _report_input_binding(path: Path, digest: str | None) -> dict[str, str]:
    if digest is None:
        return {"path": display_path(path), "status": "absent"}
    return {"path": display_path(path), "sha256": digest}


def verify_optional_input_digest(
    path: Path, expected: str | None, label: str
) -> None:
    """复核 policy input 在判定期间没有出现、消失或换字节。"""
    if expected is None:
        if path.exists():
            raise SystemExit(
                f"GATE_BLOCK {label} 在对象证据判定期间从 absent 变为存在："
                f"path={display_path(path)}"
            )
        return
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise SystemExit(
            f"GATE_BLOCK 无法复核 {label} {path}: {error}"
        ) from error
    if actual != expected:
        raise SystemExit(
            f"GATE_BLOCK {label} 在对象证据判定期间发生漂移："
            f"expected={expected} actual={actual} path={display_path(path)}"
        )


def validate_report_policy_bindings(
    report: Path,
    registry_path: Path,
    registry_digest: str | None,
) -> None:
    """report 必须绑定本次实际消费的 blindspot registry 字节。"""
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取对象证据报告 {report}: {error}") from error
    expected = {
        REPORT_BLIND_SPOT_REGISTRY_FIELD: _report_input_binding(
            registry_path, registry_digest
        ),
    }
    for field, binding in expected.items():
        if document.get(field) != binding:
            raise SystemExit(
                f"GATE_BLOCK 对象证据报告的 {field} 输入绑定不一致："
                f"report={document.get(field)!r} expected={binding!r}"
            )
    verify_optional_input_digest(registry_path, registry_digest, "盲点登记册")

def cells_from_gaps(gaps: list[Gap]) -> dict[str, dict[str, int]]:
    """缺口 → 「维度 × 对象 kind」计数格。棘轮的比对单位。"""
    counter: Counter[tuple[str, str]] = Counter(
        (gap.dimension, gap.kind) for gap in gaps
    )
    cells: dict[str, dict[str, int]] = defaultdict(dict)
    for (dimension, kind), count in counter.items():
        cells[dimension][kind] = count
    return {
        dimension: dict(sorted(kinds.items()))
        for dimension, kinds in sorted(cells.items())
    }


def write_reports(
    report_dir: Path,
    graph_path: Path,
    graph_digest: str,
    registry_path: Path,
    registry_digest: str | None,
    graph: dict,
    gaps: list[Gap],
    cells: dict[str, dict[str, int]],
    dynamic_readiness: dict | None = None,
) -> Path:
    verify_graph_digest(graph_path, graph_digest)
    verify_optional_input_digest(registry_path, registry_digest, "盲点登记册")
    report_dir.mkdir(parents=True, exist_ok=True)
    stages = Counter(
        entry.get("stage", "unknown") for entry in graph.get("objectReadiness") or []
    )
    payload = {
        REPORT_GRAPH_FIELD: {
            "path": display_path(graph_path),
            "sha256": graph_digest,
        },
        REPORT_BLIND_SPOT_REGISTRY_FIELD: _report_input_binding(
            registry_path, registry_digest
        ),
        "objects": len(graph.get("objects") or []),
        "evidencePackets": len(graph.get("readinessEvidence") or []),
        "stages": dict(sorted(stages.items())),
        "gapsByDimension": dict(
            sorted(Counter(gap.dimension for gap in gaps).items())
        ),
        "gapsByKind": dict(sorted(Counter(gap.kind for gap in gaps).items())),
        "gapsByDimensionKind": cells,
        "structuralPolicy": {
            "mode": "strict_zero",
            "allowedGapCount": 0,
        },
        "dynamicReadiness": dynamic_readiness or {
            "status": "not_evaluated",
            "commercialReady": False,
            "resultBundle": None,
            "reason": (
                "commercial evaluation was not requested; static structure never "
                "implies a trusted readiness result"
            ),
        },
        "gaps": [gap.as_dict() for gap in gaps],
    }
    report = report_dir / "object_evidence_closure.json"
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    validate_report_graph_binding(report, graph_path)
    validate_report_policy_bindings(
        report,
        registry_path,
        registry_digest,
    )
    return report


def print_gap_inventory(gaps: list[Gap]) -> None:
    by_dimension: dict[str, list[Gap]] = defaultdict(list)
    for gap in gaps:
        by_dimension[gap.dimension].append(gap)
    for dimension in sorted(by_dimension, key=lambda key: (-len(by_dimension[key]), key)):
        items = by_dimension[dimension]
        kinds = " ".join(
            f"{kind}={count}"
            for kind, count in sorted(Counter(gap.kind for gap in items).items())
        )
        print(f"  {dimension}: {len(items)} 条 [{kinds}]")


def print_result_layer(gaps: list[Gap]) -> None:
    """结果证据只报告不阻断：它要真实环境跑出来才存在，静态派生拿不到。"""
    if not gaps:
        return
    print(
        f"结果证据（不阻断）{len(gaps)} 条：需要真实环境运行才能产出，"
        "由 runner / stackctl 附加，静态派生永远拿不到"
    )
    print_gap_inventory(gaps)


def print_blind_spots(gaps: list[Gap], registry: dict[tuple[str, str], dict]) -> None:
    """维度盲点必须可见；只有 SHA-bound 证明实现存在的 scanner false-negative 可放行。"""
    if not gaps:
        return
    print(f"维度盲点（已登记 {len(registry)} 条）{len(gaps)} 条：")
    for gap in sorted(gaps, key=lambda entry: (entry.dimension, entry.object_id)):
        entry = registry.get((gap.object_id, gap.dimension)) or {}
        attested = entry.get("attested_scope", "未登记")
        classification = entry.get("classification", "未登记")
        print(f"  {gap.dimension} / {gap.object_id}: {gap.detail}")
        print(f"    classification: {classification}")
        print(f"    attested_scope: {attested}")


def print_structural_gaps(gaps: list[Gap]) -> None:
    print(
        f"GATE_BLOCK STRUCTURAL 严格零值要求未满足：{len(gaps)} 条缺口，"
        f"覆盖 {len({gap.object_id for gap in gaps})} 个对象"
    )
    print_gap_inventory(gaps)
    for gap in sorted(gaps, key=lambda entry: (entry.dimension, entry.object_id)):
        print(
            f"    - {gap.dimension} / {gap.object_id} ({gap.kind}, {gap.stage}): "
            f"{gap.detail}"
        )
    print(
        "修复路径：按对象补齐实现 seam、精确 runner/marker 与三层测试入口，"
        "或撤回引入缺口的改动。门禁不读取任何基线，"
        "禁止为结构缺口发放额度。"
    )
