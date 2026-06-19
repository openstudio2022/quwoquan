#!/usr/bin/env python3
"""交集 kind 注册表单一真相源门禁（Phase 0 漂移收口 §20d）。

唯一真相源:
  contracts/metadata/recommendation/rec_model/intersection_kind_registry.yaml

校验项:
  1. 注册表本身结构完整（每个 kind 必填 valueTier/computability/evidenceRank 等枚举字段且取值合法）。
  2. content-service intersection_service.go 的 evidenceKindRank switch 中出现的每个 kind
     必须已在注册表登记，且 rank 与注册表 evidenceRank 完全一致（消除「markdown+switch」双源）。

退出码: 0 通过 / 1 失败。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/recommendation/rec_model/intersection_kind_registry.yaml"
)
GO_SWITCH = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/internal/application/intersection_service.go"
)

VALUE_TIERS = {"T1", "T2", "T3", "T4"}
COMPUTABILITY = {"R1", "R2", "R3", "R4"}
LEVELS = {"sharedFact", "bridgeFact", "impactFact", "affinity"}
CLASSES = {"fact", "affinity"}
OBJECT_KINDS = {"person", "circle", "school", "place", "enterprise"}
STATUSES = {"active", "deferred"}
REQUIRED = [
    "kind",
    "entry",
    "level",
    "intersectionClass",
    "dimensions",
    "objectKind",
    "valueTier",
    "computability",
    "evidenceRank",
    "status",
]


def fail(msg: str) -> None:
    print(f"[verify-intersection-kind-registry] FAIL: {msg}")
    sys.exit(1)


def load_registry() -> dict[str, dict]:
    if not REGISTRY.exists():
        fail(f"missing registry: {REGISTRY}")
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    kinds = data.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        fail("registry.kinds must be a non-empty list")
    by_kind: dict[str, dict] = {}
    for item in kinds:
        for field in REQUIRED:
            if field not in item or item[field] in ("", None):
                fail(f"kind {item.get('kind', '?')} missing required field {field}")
        if item["valueTier"] not in VALUE_TIERS:
            fail(f"kind {item['kind']} invalid valueTier {item['valueTier']}")
        if item["computability"] not in COMPUTABILITY:
            fail(f"kind {item['kind']} invalid computability {item['computability']}")
        if item["level"] not in LEVELS:
            fail(f"kind {item['kind']} invalid level {item['level']}")
        if item["intersectionClass"] not in CLASSES:
            fail(f"kind {item['kind']} invalid intersectionClass {item['intersectionClass']}")
        if item["objectKind"] not in OBJECT_KINDS:
            fail(f"kind {item['kind']} invalid objectKind {item['objectKind']}")
        if item["status"] not in STATUSES:
            fail(f"kind {item['kind']} invalid status {item['status']}")
        if not isinstance(item["evidenceRank"], int):
            fail(f"kind {item['kind']} evidenceRank must be int")
        if item["kind"] in by_kind:
            fail(f"duplicate kind {item['kind']}")
        by_kind[item["kind"]] = item
    return by_kind


def parse_go_switch() -> dict[str, int]:
    """提取 evidenceKindRank 函数体内 case "k1","k2": return N 的 kind→rank。"""
    src = GO_SWITCH.read_text(encoding="utf-8")
    m = re.search(r"func evidenceKindRank\(kind, pointClass string\) int \{(.*?)\n\}", src, re.S)
    if not m:
        fail("cannot locate evidenceKindRank function body")
    func_body = m.group(1)
    # 只解析 `switch kind { ... }` 块，排除前置 pointClass=="recommended" 守卫。
    sw = re.search(r"switch kind \{(.*?)\n\t\}", func_body, re.S)
    if not sw:
        fail("cannot locate `switch kind` block in evidenceKindRank")
    body = sw.group(1)
    out: dict[str, int] = {}
    pending: list[str] = []
    for line in body.splitlines():
        cases = re.findall(r'"([A-Za-z0-9_]+)"', line)
        if cases:
            pending.extend(cases)
        ret = re.search(r"return\s+(\d+)", line)
        if ret and pending:
            rank = int(ret.group(1))
            for k in pending:
                out[k] = rank
            pending = []
    if not out:
        fail("no kind cases parsed from evidenceKindRank")
    return out


def main() -> int:
    registry = load_registry()
    go_ranks = parse_go_switch()

    problems: list[str] = []
    for kind, rank in go_ranks.items():
        reg = registry.get(kind)
        if reg is None:
            problems.append(f"Go switch kind '{kind}' not registered in registry yaml")
            continue
        if reg["evidenceRank"] != rank:
            problems.append(
                f"kind '{kind}' evidenceRank drift: registry={reg['evidenceRank']} go_switch={rank}"
            )

    if problems:
        for p in problems:
            print(f"[verify-intersection-kind-registry] FAIL: {p}")
        return 1

    print(
        f"[verify-intersection-kind-registry] OK: {len(registry)} kinds registered, "
        f"{len(go_ranks)} go-switch kinds aligned (single source = intersection_kind_registry.yaml)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
