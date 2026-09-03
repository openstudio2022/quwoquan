#!/usr/bin/env python3
"""棘轮基线的治理留痕门禁。

棘轮基线是「债只减不增」的唯一凭据，而它最容易被绕开的方式不是把数字调大——那
太显眼——而是**悄悄换度量口径再重建基线**。换口径之后新旧数字不可比，漂移被重新
归零，门禁全程显示绿色。仓库里已经发生过两次：

- assistant 弱类型棘轮在旧口径下漂移到 292/522，CI 全程没拦；
- `ui_map_literal_budget` 的旧口径只扫 `lib/ui`，该目录随 UI 迁走后计数静默归零，
  预算 4 长期假绿。

因此每个基线都必须声明：

- `owner`：谁负责把它降到零；
- `reason`：为什么这笔债被允许暂存；
- `expires_when`：什么条件下删除这个文件；
- `measure`：当前度量口径，必须具体到扫描范围与判定规则，能据此复算。

并且 `measure` 一旦相对 HEAD 发生变化，同一次提交必须写下 `superseded_measure`，
说明旧口径是什么、为什么换、以及**旧口径下的实测值**。没有这句话，换口径就等于
无痕销账。

治理留痕齐备并不等于债务在下降，所以本门禁还直接比对 HEAD：**债务计数型基线的
任何条目变大、或出现新条目，一律失败。** 只有这一条是机械判定的，写得再完整的
`reason` 也不能替代它。

「债务计数型」按键的形状识别：顶层键是文件路径（含 `/`）时，值里的整数是违规处数，
只能减少；键是场景名的耗时预算不在其列——预算随机器和产品形态变化，它的正当性由
`superseded_measure` 承载，不该被当成债务。

spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#req-004
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]

#: 棘轮基线的物理位置。新增基线必须落在这里，否则不受治理约束。
BASELINE_PATHS = (
    "quwoquan_ops/policies/gates",
    "quwoquan_app/scripts/runtime/page",
    "quwoquan_app/scripts/runtime/observability",
    "quwoquan_service/scripts/verify/structure",
    "quwoquan_ops/environments",
)
BASELINE_SUFFIXES = {".json", ".yaml"}

#: 棘轮基线的命名标记。按名字而不是按豁免名单识别，是为了让新增的基线自动落入
#: 治理范围：漏登记一个豁免只会放过一个文件，而漏更新一份「纳入名单」会放过全部
#: 新增基线。清单、manifest、策略声明这类不承载可增长计数的文件天然不匹配。
RATCHET_NAME_MARKERS = ("baseline", "budget", "allowlist", "ratchet")

#: 名字带标记、但只声明架构策略而不承载任何计数的文件。
NON_RATCHET_POLICIES = frozenset(
    {
        "cloud_runtime_single_path_policy.json",
    }
)

REQUIRED_FIELDS = ("owner", "reason", "expires_when", "measure")

#: 不对应任何规格节点的横向治理职能。
#:
#: 有些债确实归属职能而不是产品能力（门禁耗时、仓库结构、契约治理），强行塞进某个
#: 产品节点只会造成错误归属。但白名单必须是封闭的：`owner` 曾经写着
#: `cross-domain-architecture`，那个名字在规格树和这里都不存在，等于字段填了却无人
#: 负责 —— 治理留痕最容易被架空的方式，就是写一个看起来像 owner 的字符串。
GOVERNANCE_FUNCTIONS = frozenset(
    {
        "cloud-contract-governance",
        "delivery-gate",
        "feature-tree-governance",
        "repository-architecture",
    }
)


def known_owners() -> frozenset[str]:
    """规格树里的真实节点名，并上横向治理职能。"""
    tree = ROOT / "specs" / "feature-tree"
    nodes = {path.name for path in tree.rglob("*") if path.is_dir()} if tree.is_dir() else set()
    return frozenset(nodes | GOVERNANCE_FUNCTIONS)


def baseline_files() -> list[Path]:
    files: list[Path] = []
    for relative in BASELINE_PATHS:
        directory = ROOT / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix not in BASELINE_SUFFIXES:
                continue
            if path.name in NON_RATCHET_POLICIES:
                continue
            if not any(marker in path.name for marker in RATCHET_NAME_MARKERS):
                continue
            files.append(path)
    return files


def governance_block(path: Path) -> dict[str, str]:
    """抽出治理块。

    JSON 用 `_governance`，YAML 用顶层 `governance:`。这里刻意不引入 YAML 解析器：
    只认这两种固定形状，能让「治理块长什么样」本身无法被悄悄改写。
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        document = json.loads(text)
        block = document.get("_governance")
        return block if isinstance(block, dict) else {}

    fields: dict[str, str] = {}
    inside = False
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("governance:"):
            inside = True
            continue
        if inside and line and not line.startswith((" ", "\t")):
            break
        if not inside:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("  ") and not line.startswith("    ") and ":" in stripped:
            key, _, value = stripped.partition(":")
            current = key.strip()
            fields[current] = value.strip()
        elif current:
            fields[current] = f"{fields[current]} {stripped}".strip()
    return fields


def head_revision(relative: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def debt_entries(document: object) -> dict[str, int]:
    """债务计数型条目，展平成 `身份 -> 计数`。

    键含 `/` 才算——债务基线的键是文件路径，耗时预算的键是场景名。值支持两种形状：
    直接是计数，或是 `{identity -> count}`（细到函数/字段，使同文件内的位置替换也
    藏不住）。
    """
    if not isinstance(document, dict):
        return {}
    entries: dict[str, int] = {}
    if document.get("schema") == "single-track-exact-fingerprint-baseline":
        findings = document.get("findings")
        if not isinstance(findings, list):
            return entries
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            path = finding.get("path")
            fingerprint = finding.get("fingerprint")
            count = finding.get("count")
            if (
                isinstance(path, str)
                and "/" in path
                and isinstance(fingerprint, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
            ):
                entries[f"{path}::{fingerprint}"] = count
        return entries
    for key, value in document.items():
        if key == "_governance" or not isinstance(key, str) or "/" not in key:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            entries[key] = value
        elif isinstance(value, dict):
            for identity, count in value.items():
                if isinstance(count, int) and not isinstance(count, bool):
                    entries[f"{key}::{identity}"] = count
    return entries


def debt_growth(path: Path, relative: str) -> list[str]:
    """相对 HEAD 变大或新增的债务条目。文件在 HEAD 不存在时无从比较。"""
    body = head_revision(relative)
    if body is None or path.suffix != ".json":
        return []
    try:
        before = debt_entries(json.loads(body))
        after = debt_entries(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeError):
        return []
    if not before and not after:
        return []
    growth: list[str] = []
    for identity in sorted(after):
        was = before.get(identity, 0)
        if after[identity] > was:
            growth.append(f"{identity}: {was} -> {after[identity]}")
    return growth


def measure_of_head(path: Path, relative: str) -> str | None:
    """取 HEAD 版本的 measure，用于判断本次是否换了口径。"""
    body = head_revision(relative)
    if body is None:
        return None
    # 进程唯一命名：并发 gate 进程处理同名 baseline 时禁止共享 scratch 文件互删。
    scratch = (
        ROOT
        / ".qwq_output/env/repo/local/ratchet-governance"
        / f"{os.getpid()}-{uuid.uuid4().hex[:8]}-{path.name}"
    )
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text(body, encoding="utf-8")
    try:
        return governance_block(scratch).get("measure")
    except (json.JSONDecodeError, UnicodeError):
        return None
    finally:
        scratch.unlink(missing_ok=True)


def main() -> int:
    failures: list[str] = []
    checked = 0
    owners = known_owners()
    for path in baseline_files():
        relative = path.relative_to(ROOT).as_posix()
        checked += 1
        try:
            block = governance_block(path)
        except json.JSONDecodeError as error:
            failures.append(f"{relative}: 无法解析（{error}）")
            continue

        missing = [field for field in REQUIRED_FIELDS if not block.get(field)]
        if missing:
            failures.append(
                f"{relative}: 治理块缺 {', '.join(missing)}；"
                "棘轮基线必须能被独立复算，否则换口径重建就无痕"
            )
            continue

        owner = block["owner"]
        if owner not in owners:
            failures.append(
                f"{relative}: owner {owner!r} 既不是 specs/feature-tree 下的节点，"
                "也不在 GOVERNANCE_FUNCTIONS 里；无法追责的 owner 等于没有 owner"
            )

        previous = measure_of_head(path, relative)
        if previous is not None and previous != block["measure"]:
            if not block.get("superseded_measure"):
                failures.append(
                    f"{relative}: measure 相对 HEAD 已变更，但没有 superseded_measure；"
                    "换度量口径必须同批写下旧口径是什么、为什么换、旧口径下的实测值"
                )

        growth = debt_growth(path, relative)
        if growth:
            listed = "；".join(growth[:5])
            more = f"（另有 {len(growth) - 5} 项）" if len(growth) > 5 else ""
            failures.append(
                f"{relative}: {len(growth)} 处债务条目相对 HEAD 变大或新增 —— "
                f"{listed}{more}；棘轮只能下降，先消化债务再谈基线"
            )

    if failures:
        print(f"[ratchet-baseline-governance] FAIL: {len(failures)} 项")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"[ratchet-baseline-governance] OK: {checked} 个棘轮基线治理留痕完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
