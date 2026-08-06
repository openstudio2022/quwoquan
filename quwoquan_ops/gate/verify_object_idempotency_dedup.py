#!/usr/bin/env python3
"""声明 `idempotency: required` 的对象必须真的去重，且未去重的数量只减不增。

`operations.yaml` 里 233 个操作声明了 `idempotency: required`，覆盖 80 个对象。声明本身
只是意图——真正决定重放会不会被吸收的，是实现里有没有 receipt 查询、冲突哨兵、`ON CONFLICT`
或等价物。此前没有任何维度把这两件事连起来。

## 判定为什么不按名字找

本仓已有五次「声明侧标识符在实现中查无 ⇒ 判为未实现」的假阳，形态各不相同。幂等这一类
至少踩到三种：

* `greeting_request` 的去重键叫 `n_key` 不叫 `idempotency_key`，查 `idempotency` 全落空，
  但 `SELECT ... WHERE actor_persona_id=$1 AND n_key=$2` 加 `pgx.ErrNoRows` 分支就是完整的
  重放短路，并且落了 "greeting receipt"。
* `contact_discovery_record` 的 INSERT 根本不在 `internal/`，在 `generated/` 的 codegen store 里，
  只扫 `internal/` 会把整条写路径看漏。
* `connection` 是 runtime_session，没有聚合存储，重放保护是 redis 上的一次性 ticket
  （`TicketStore.Consume`），既无 receipt 表也无 `ON CONFLICT`。

所以本门禁只认**去重语义的实现形态**（`DEDUP_SIGNALS`），并且同时扫 `internal/` 与
`generated/`。仅仅把 `Idempotency-Key` 从 header 透传到 service 不算去重——透传证明的是
意图，不是重放被吸收，这正是上一轮把 6 个对象误判为「未实现」的原因。

## 语言可见性

判定走文本信号而不是 Go AST，所以 Python store 天然可见：`recommendation_model_release`
与 `ranked_recommendation_window` 都是纯 `.py` 命中。为了不让「看不见」静默变成「达标」，
`SCANNED_SUFFIXES` 之外的实现语言会直接阻断，而不是当作无实现或无声通过。

## 只减不增

剩余未去重的对象进 `MISSING_BASELINE`，不 fail-closed（存量不阻断整仓，
`verify_object_evidence_closure.py` 因 521 条缺口把仓库永久阻断、最后只能回滚就是先例）：

* 声明 required、无去重信号、且不在基线 —— 新对象忘了去重，阻断。
* 在基线里但已经有去重信号 —— 修好了必须同步删基线，否则基线退化成永久豁免，阻断。
* 基线条目已经不再声明 required —— 基线与声明不同源，阻断。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = ROOT / "quwoquan_service/services"

# 只扫这些后缀；出现其它实现语言时宁可阻断也不静默放过。
SCANNED_SUFFIXES = frozenset({".go", ".py"})
IMPLEMENTATION_SUFFIXES = frozenset({".go", ".py", ".ts", ".java", ".kt", ".rs", ".rb"})

# 去重语义的实现形态。每一条都必须是「重放被吸收或被拒绝」的证据，
# 而不是「幂等键被传下去」的证据。
DEDUP_SIGNALS: dict[str, re.Pattern[str]] = {
    # receipt 表：写入命令结果并在重放时回放首次结果。异名键（n_key 等）也会落在这里，
    # 因为回执本身仍然叫 receipt。
    "receipt": re.compile(r"receipt", re.IGNORECASE),
    # 冲突哨兵：重放被识别为冲突并翻译成契约错误码。
    "conflict_sentinel": re.compile(
        r"ErrIdempotency\w*|IdempotencyConflict|ErrDuplicate\w*|ErrAlreadyExists"
    ),
    # 关系库 upsert：重放落到同一行。
    "sql_upsert": re.compile(r"ON\s+CONFLICT", re.IGNORECASE),
    # 文档库 upsert：同上。
    "document_upsert": re.compile(r"SetUpsert\(|\$setOnInsert|upsert\s*=\s*True", re.IGNORECASE),
    # 唯一键冲突被显式捕获并翻译，而不是漏成 500。
    "duplicate_key": re.compile(
        r"IsDuplicateKeyError|ErrDuplicateKey|23505|duplicate key|UniqueViolation",
        re.IGNORECASE,
    ),
    # 一次性凭据消费：runtime_session 对象没有聚合存储，重放靠凭据只能被消费一次来挡。
    "single_use_token": re.compile(r"ConsumeTicket|func \(\w+ \*?\w*Ticket\w*\) Consume\("),
}

# 当前没有已知未去重对象。后续新增声明 required 却缺少去重实现的对象必须直接阻断，
# 不得重新扩大基线。
MISSING_BASELINE: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class ObjectScan:
    """一个对象的去重扫描结果。"""

    service: str
    relative: str
    # 命中的去重形态 -> 首个证据文件（仓库相对路径）。
    signals: dict[str, str]
    # 实现目录里出现过的文件后缀，用于语言可见性核查。
    suffixes: frozenset[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.service, self.relative)

    @property
    def deduplicates(self) -> bool:
        return bool(self.signals)


def objects_requiring_idempotency() -> list[tuple[str, str]]:
    """`operations.yaml` 中任一操作声明 `idempotency: required` 的对象。"""
    found: list[tuple[str, str]] = []
    for path in sorted(SERVICES_ROOT.rglob("operations.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not _declares_required(document):
            continue
        parts = path.relative_to(SERVICES_ROOT).parts
        if "contracts" not in parts:
            continue
        index = parts.index("contracts")
        found.append((parts[0], "/".join(parts[index + 1 : -1])))
    return found


def _declares_required(node: object) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "idempotency" and value == "required":
                return True
            if _declares_required(value):
                return True
    elif isinstance(node, list):
        return any(_declares_required(item) for item in node)
    return False


def scan_object(service: str, relative: str) -> ObjectScan:
    """在 internal/ 与 generated/ 两处实现目录里找去重形态。"""
    signals: dict[str, str] = {}
    suffixes: set[str] = set()
    for root in (
        SERVICES_ROOT / service / "internal" / relative,
        SERVICES_ROOT / service / "generated" / relative,
    ):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "_test" in path.name:
                continue
            if path.suffix in IMPLEMENTATION_SUFFIXES:
                suffixes.add(path.suffix)
            if path.suffix not in SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, pattern in DEDUP_SIGNALS.items():
                if name not in signals and pattern.search(text):
                    signals[name] = str(path.relative_to(ROOT))
    return ObjectScan(service, relative, signals, frozenset(suffixes))


def validate(
    scans: list[ObjectScan],
    baseline: frozenset[tuple[str, str]],
) -> list[str]:
    issues: list[str] = []
    declared = {scan.key for scan in scans}

    for key in sorted(baseline - declared):
        issues.append(
            f"{key[0]} {key[1]} 在 MISSING_BASELINE 里却已不再声明 idempotency: required，"
            "基线与声明不同源，请删除该基线条目"
        )

    for scan in sorted(scans, key=lambda item: item.key):
        invisible = scan.suffixes - SCANNED_SUFFIXES
        if invisible:
            issues.append(
                f"{scan.service} {scan.relative} 的实现包含未被扫描的语言 "
                f"{sorted(invisible)}：判定看不见它，不能当作达标，请先扩展 SCANNED_SUFFIXES"
            )
            continue
        if scan.deduplicates and scan.key in baseline:
            form, evidence = sorted(scan.signals.items())[0]
            issues.append(
                f"{scan.service} {scan.relative} 已实现去重（{form} @ {evidence}），"
                "请从 MISSING_BASELINE 删除该条目，避免基线退化成永久豁免"
            )
        if not scan.deduplicates and scan.key not in baseline:
            issues.append(
                f"{scan.service} {scan.relative} 声明 idempotency: required 却没有任何去重实现："
                "重放会产生第二份事实。透传 Idempotency-Key 不算去重，"
                f"需要 {sorted(DEDUP_SIGNALS)} 之一"
            )
    return issues


def main() -> int:
    declared = objects_requiring_idempotency()
    if not declared:
        print("[verify_object_idempotency_dedup] FAIL")
        print("  - 未找到任何声明 idempotency: required 的对象，判定已失效")
        return 1

    scans = [scan_object(service, relative) for service, relative in declared]
    issues = validate(scans, MISSING_BASELINE)

    if issues:
        print("[verify_object_idempotency_dedup] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    covered = [scan for scan in scans if scan.deduplicates]
    python_only = [
        scan for scan in covered if scan.suffixes and scan.suffixes <= frozenset({".py"})
    ]
    print(
        f"[verify_object_idempotency_dedup] OK "
        f"(声明 required {len(scans)} 个对象；已去重 {len(covered)}；"
        f"未去重基线 {len(MISSING_BASELINE)}；纯 Python 实现 {len(python_only)} 个可见)"
    )
    for scan in sorted(scans, key=lambda item: item.key):
        if scan.key in MISSING_BASELINE:
            print(f"  · {scan.service} {scan.relative}: 待补去重")
    return 0


if __name__ == "__main__":
    sys.exit(main())
