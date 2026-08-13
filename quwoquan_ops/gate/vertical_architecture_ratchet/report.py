"""垂类架构防回退门。

本门禁只读取物理源码、canonical domain owner metadata 与现存债务基线：

* 禁止新增按内容垂类拆分的 ``services/<vertical>-service``；
* 禁止业务代码新增垂类 ``switch/case`` 或 ``contentVertical ==`` 分叉；
* ``contentVertical`` 使用、``domain_taxonomy.yaml`` 运行时消费者只减不增；
* 已退役 travel-service 目录与 App、Assistant、api-edge、runtime auth、Ops 装配依赖永久保持为零。

基线不是服务/字段/消费者注册表，只保存允许现存命中的路径、计数摘要与退役责任。
删除命中会自动通过；新路径、计数增加或等量替换会阻断。travel-service 已完成日落，
其目录和五类调用方依赖不再接受任何 allowance、正计数或迁移期开关。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Mapping

from .baseline import load_baseline
from .constants import DEFAULT_BASELINE, RETIRED_TRAVEL_SERVICE, ROOT
from .models import HitSummary
from .retired_travel import (
    scan_app_travel_contract_ghosts,
    scan_contract_graph_travel_ghosts,
    scan_materialized_travel_owners,
)
from .scans import build_snapshot
from .taxonomy import _matches_vertical_service


def _path_in_scope(path: str, scope: str) -> bool:
    is_app = path.startswith("quwoquan_app/")
    if scope == "all":
        return True
    if scope == "app":
        return is_app
    return not is_app


def _compare_bucket(
    name: str,
    current: Mapping[str, HitSummary],
    baseline: Mapping[str, HitSummary],
    *,
    scope: str,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    reductions: list[str] = []
    for path, actual in sorted(current.items()):
        if not _path_in_scope(path, scope):
            continue
        allowed = baseline.get(path)
        if allowed is None:
            failures.append(
                f"{name}: 新增命中 {path} count={actual.count}\n      "
                + "\n      ".join(actual.samples)
            )
            continue
        if actual.count > allowed.count:
            failures.append(
                f"{name}: {path} 命中增加 baseline={allowed.count} "
                f"current={actual.count}\n      "
                + "\n      ".join(actual.samples)
            )
            continue
        if actual.count == allowed.count and actual.digest != allowed.digest:
            failures.append(
                f"{name}: {path} 等量命中摘要改变，疑似以新命中替换旧命中；"
                "不得横向搬运债务"
            )
            continue
        if actual.count < allowed.count:
            reductions.append(
                f"{name}: {path} {allowed.count}->{actual.count}"
            )
    for path, allowed in sorted(baseline.items()):
        if not _path_in_scope(path, scope) or path in current:
            continue
        reductions.append(f"{name}: {path} {allowed.count}->0")
    return failures, reductions


def _bucket_debt(bucket: Mapping[str, HitSummary], *, scope: str) -> dict[str, int]:
    filtered = {
        path: summary
        for path, summary in bucket.items()
        if _path_in_scope(path, scope)
    }
    return {
        "paths": len(filtered),
        "hits": sum(summary.count for summary in filtered.values()),
    }


def evaluate(
    root: Path,
    baseline_path: Path,
    *,
    scope: str = "all",
) -> tuple[list[str], dict]:
    snapshot, discovery_issues = build_snapshot(root)
    baseline, _document = load_baseline(baseline_path)
    failures = list(discovery_issues) if scope in {"all", "service"} else []
    reductions: list[str] = []
    graph_ghosts = (
        scan_contract_graph_travel_ghosts(root)
        if scope in {"all", "service"}
        else []
    )
    materialized_owners = (
        scan_materialized_travel_owners(root)
        if scope in {"all", "service"}
        else []
    )
    app_contract_ghosts = (
        scan_app_travel_contract_ghosts(root)
        if scope in {"all", "app"}
        else []
    )
    failures.extend(f"contract_graph_travel_ghost: {issue}" for issue in graph_ghosts)
    failures.extend(
        f"materialized_travel_owner: {issue}" for issue in materialized_owners
    )
    failures.extend(
        f"app_travel_contract_ghost: {issue}" for issue in app_contract_ghosts
    )

    retired_path = RETIRED_TRAVEL_SERVICE.as_posix()
    retired_service_path = root / RETIRED_TRAVEL_SERVICE
    if scope in {"all", "service"} and os.path.lexists(retired_service_path):
        failures.append(
            f"retired_travel_service: {retired_path} 路径已退役且必须永久不存在；"
            "不得通过目录、文件、symlink、旧 owner、源码或 digest 重新启用"
        )
    for service_path, domain in sorted(snapshot.service_domains.items()):
        if not _matches_vertical_service(
            service_path, domain, snapshot.vertical_terms
        ):
            continue
        failures.append(
            f"vertical_service: 禁止新增/恢复垂类服务 {service_path} "
            f"(domain owner={domain!r})；垂类必须由 Topic/Distribution/Skill/"
            "Presentation/ExperiencePackage 数据组合承载"
        )

    current_buckets = {
        "platform_vertical_branches": snapshot.platform_vertical_branches,
        "content_vertical_usage": snapshot.content_vertical_usage,
        "domain_taxonomy_runtime_consumers": (
            snapshot.domain_taxonomy_runtime_consumers
        ),
    }
    for name, current in current_buckets.items():
        bucket_failures, bucket_reductions = _compare_bucket(
            name,
            current,
            baseline[name],
            scope=scope,
        )
        failures.extend(bucket_failures)
        reductions.extend(bucket_reductions)

    for area, current in snapshot.travel_service_dependencies.items():
        if scope == "app" and area != "app":
            continue
        if scope == "service" and area == "app":
            continue
        for path, summary in sorted(current.items()):
            failures.append(
                f"travel_service_dependencies.{area}: 已退役依赖必须永久为零，"
                f"发现 {path} count={summary.count}\n      "
                + "\n      ".join(summary.samples)
            )

    report_buckets = {
        **current_buckets,
        **{
            f"travel_service_dependencies.{area}": dependencies
            for area, dependencies in snapshot.travel_service_dependencies.items()
        },
    }
    debt = {
        name: _bucket_debt(current, scope=scope)
        for name, current in report_buckets.items()
    }
    report = {
        "scope": scope,
        "vertical_term_count": len(snapshot.vertical_terms),
        "service_boundaries": len(snapshot.service_domains),
        "retired_travel_service_present": os.path.lexists(retired_service_path),
        "contract_graph_travel_ghosts": len(graph_ghosts),
        "materialized_travel_owners": len(materialized_owners),
        "app_travel_contract_ghosts": len(app_contract_ghosts),
        "debt": debt,
        "reductions": reductions,
    }
    return failures, report


def _print_report(report: Mapping[str, object]) -> None:
    print(f"[vertical-architecture-ratchet] scope={report['scope']}")
    print(
        "  owner metadata: "
        f"services={report['service_boundaries']} "
        f"vertical_terms_derived={report['vertical_term_count']} "
        "retired_travel_present="
        f"{str(report['retired_travel_service_present']).lower()}"
    )
    print(
        "  retired artifacts: "
        f"graph={report['contract_graph_travel_ghosts']} "
        f"materialized={report['materialized_travel_owners']} "
        f"app={report['app_travel_contract_ghosts']}"
    )
    debt = report["debt"]
    assert isinstance(debt, dict)
    for name, value in debt.items():
        assert isinstance(value, dict)
        print(f"  debt {name}: paths={value['paths']} hits={value['hits']}")
    reductions = report["reductions"]
    assert isinstance(reductions, list)
    if reductions:
        print(f"  ratchet reductions accepted automatically: {len(reductions)}")
        for reduction in reductions:
            print(f"    - {reduction}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--scope", choices=("all", "app", "service"), default="all")
    parser.add_argument("--json", action="store_true", help="输出机器可读报告")
    args = parser.parse_args()
    try:
        failures, report = evaluate(
            Path(args.root).resolve(),
            Path(args.baseline).resolve(),
            scope=args.scope,
        )
    except ValueError as exc:
        print(f"[vertical-architecture-ratchet] FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({**report, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    if failures:
        if not args.json:
            print("[vertical-architecture-ratchet] GATE_BLOCK")
            for index, failure in enumerate(failures, start=1):
                print(f"  {index}. {failure}")
        return 1
    if not args.json:
        print("[vertical-architecture-ratchet] OK")
    return 0
