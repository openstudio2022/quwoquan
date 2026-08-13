"""五条规则求值、strict-zero 违规汇总与 CLI ``main`` 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from quwoquan_ops.gate import object_path_map as opm  # noqa: F401  # 供归属真相源同源引用

from .attribution import AppSourceIndex, load_roster, scan_top_level_violations
from .constants import (
    BASELINE_PATH,
    DOMAIN_RULES,
    RULE_CROSS_OBJECT_PRIVATE_IMPORT,
    RULE_ID,
    RULE_PHYSICAL_REVERSE_IMPORT,
    RULE_RUNTIME_DI_PRESENTATION_PURITY,
    RULE_TARGET_REVERSE_IMPORT,
    RULE_TOP_LEVEL,
    SHARED_RULES,
)
from .rules import (
    scan_cross_object_private_import_violations,
    scan_reverse_import_violations,
    scan_runtime_di_presentation_purity_violations,
)


# ---------------------------------------------------------------------------
# 违规汇总与基线比对
# ---------------------------------------------------------------------------


def evaluate(roster: opm.ObjectRoster) -> dict:
    """求值五条规则，返回 ``{"shared": {...}, "domains": {...}}``。"""
    index = AppSourceIndex(roster)
    target_reverse = scan_reverse_import_violations(index, physical=False)
    physical_reverse = scan_reverse_import_violations(index, physical=True)
    cross_object_private = scan_cross_object_private_import_violations(index)

    domains: dict[str, dict[str, list[str]]] = {}
    for domain in sorted(
        set(target_reverse) | set(physical_reverse) | set(cross_object_private)
    ):
        domains[domain] = {
            RULE_TARGET_REVERSE_IMPORT: target_reverse.get(domain, []),
            RULE_PHYSICAL_REVERSE_IMPORT: physical_reverse.get(domain, []),
            RULE_CROSS_OBJECT_PRIVATE_IMPORT: cross_object_private.get(domain, []),
        }
    return {
        "shared": {
            RULE_TOP_LEVEL: scan_top_level_violations(roster),
            RULE_RUNTIME_DI_PRESENTATION_PURITY: (
                scan_runtime_di_presentation_purity_violations()
            ),
        },
        "domains": domains,
    }


def verify_retired_baseline_absent() -> None:
    """迁移期 baseline 已退休；重新出现即是第二条准入真相源。"""
    if BASELINE_PATH.exists():
        raise ValueError(
            f"{BASELINE_PATH}: retired baseline must remain absent; "
            "R1-R5 are strict-zero"
        )


def _normalized(document: dict) -> dict:
    """规范化违规文档：条目去重排序，空 domain 分区剔除。

    去重只合并完全相同的 authored edge；R4 条目含 directive kind，因此
    同一 source/target 的 import、export、part 仍是三条不同证据。
    """
    shared = {
        rule: sorted(set(document.get("shared", {}).get(rule, []) or []))
        for rule in SHARED_RULES
    }
    domains: dict[str, dict[str, list[str]]] = {}
    for domain, section in sorted((document.get("domains") or {}).items()):
        entries = {
            rule: sorted(set(section.get(rule, []) or [])) for rule in DOMAIN_RULES
        }
        if any(entries.values()):
            domains[domain] = entries
    return {"shared": shared, "domains": domains}


def _rule_entries(document: dict, domain: str | None, rule: str) -> set[str]:
    if rule in SHARED_RULES:
        return set(document.get("shared", {}).get(rule, []) or [])
    section = (document.get("domains") or {}).get(domain) or {}
    return set(section.get(rule, []) or [])


def scoped_domains(current: dict, domain: str | None) -> list[str]:
    if domain is not None:
        return [domain]
    return sorted(current.get("domains") or {})


def violation_entries(current: dict, domain: str | None) -> list[str]:
    """返回 scope 内全部 strict-zero 违规；不存在 baseline 差分。"""
    entries = [
        f"{rule}: {entry}"
        for rule in SHARED_RULES
        for entry in sorted(_rule_entries(current, None, rule))
    ]
    for scoped_domain in scoped_domains(current, domain):
        for rule in DOMAIN_RULES:
            entries += [
                f"{rule}[{scoped_domain}]: {entry}"
                for entry in sorted(_rule_entries(current, scoped_domain, rule))
            ]
    return entries


def summarize(current: dict, domain: str | None) -> dict:
    """派生本次求值的违规计数摘要。"""
    domains = scoped_domains(current, domain)
    counts = {rule: len(_rule_entries(current, None, rule)) for rule in SHARED_RULES}
    for rule in DOMAIN_RULES:
        counts[rule] = sum(
            len(_rule_entries(current, scoped_domain, rule))
            for scoped_domain in domains
        )
    by_domain = {
        scoped_domain: {
            rule: len(_rule_entries(current, scoped_domain, rule))
            for rule in DOMAIN_RULES
        }
        for scoped_domain in domains
        if any(_rule_entries(current, scoped_domain, rule) for rule in DOMAIN_RULES)
    }
    return {
        "ruleId": RULE_ID,
        "scope": domain or "all",
        "violations": counts,
        "violationsByDomain": by_domain,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "端侧对象化架构门禁 v1（顶层白名单 + 横切面反向 import + "
            "跨对象 public seam + runtime/di presentation purity）"
        )
    )
    parser.add_argument(
        "--domain",
        default=None,
        help=(
            "只比对该 domain 名下的 R2/R3/R4 违规；"
            "R1/R5 共享规则始终全量求值"
        ),
    )
    arguments = parser.parse_args(argv)

    roster = load_roster()
    if arguments.domain is not None and arguments.domain not in roster.domains:
        print(
            f"verify_app_architecture: BLOCK: 未知 domain {arguments.domain!r}，"
            f"ContractGraph roster 只有 {sorted(roster.domains)}",
            file=sys.stderr,
        )
        return 2

    try:
        current = _normalized(evaluate(roster))
    except (OSError, ValueError) as error:
        print(
            f"verify_app_architecture: FAIL Dart dependency scan: {error}",
            file=sys.stderr,
        )
        return 1

    try:
        verify_retired_baseline_absent()
    except ValueError as error:
        print(f"verify_app_architecture: BLOCK: {error}", file=sys.stderr)
        return 1

    violations = violation_entries(current, arguments.domain)
    if violations:
        print("verify_app_architecture: BLOCK: strict-zero violation", file=sys.stderr)
        for entry in violations:
            print(f"  violation: {entry}", file=sys.stderr)
        print(
            "  lib/ 顶层只允许 service/、runtime/、design_system/、l10n/ 与 "
            "main*.dart；runtime/** 与 design_system/** 不得依赖任何 "
            "lib/service/<service>/<context>/<object>/**"
            "（组合根 runtime/di/** 与入口除外）。"
            "不同业务对象之间只能 import 目标对象 application/public/**；"
            "runtime/di/** 只能定义 provider/factory/typed WidgetBuilder/composition，"
            "不得定义 Widget、业务文案或业务状态。R1-R5 全部 strict-zero，"
            "不接受 baseline/allowance。",
            file=sys.stderr,
        )
        return 1

    summary = summarize(current, arguments.domain)
    print(f"verify_app_architecture: OK (scope={summary['scope']})")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0
