"""CLI 入口：参数解析、主流程编排与退出码。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import yaml

from .gate_classify import run_page_quality_gates
from .models import REPOSITORY_ROOT, ContractError
from .moved_path import _run_git
from .repo_reuse import (
    _default_report_dir,
    _load_disk_scan_paths,
    _load_shape_resolver,
)
from .reporting import render_report, write_run_report
from .sync_flow import sync


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="同步 page_object_contract.yaml 的 source_path 到磁盘真相"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检测不写入；存在 drift 即失败",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="把 REVIEW（多对象页面落单对象 presentation、页面扫描集缺口）也视为失败",
    )
    parser.add_argument("--json", action="store_true", help="额外输出机器可读报告")
    parser.add_argument(
        "--with-gate",
        action="store_true",
        help="同步后顺带只读跑页面横向质量门禁并按「谁能修」分类失败",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="运行报告目录（默认 .qwq_output/env/repo/runs/page-object-source-path）",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不落运行报告（默认落 .qwq_output 下的一次性可重建报告）",
    )
    parser.add_argument(
        "--repository-root",
        default=None,
        help="覆盖仓库根（测试与工具链自检用）",
    )
    arguments = parser.parse_args(argv)

    repository_root = (
        Path(arguments.repository_root).resolve()
        if arguments.repository_root
        else REPOSITORY_ROOT
    )

    try:
        report = sync(
            repository_root,
            write=not arguments.check,
            shape_of=_load_shape_resolver(repository_root),
            disk_scan_paths=_load_disk_scan_paths(repository_root),
        )
    except (ContractError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"[page-object-source-path] BLOCK: {error}", file=sys.stderr)
        return 2

    print(render_report(report, write=not arguments.check))
    if arguments.json:
        print(json.dumps(report.as_json(), ensure_ascii=False, indent=2, sort_keys=True))

    payload = {
        "schema": "page-object-source-path-sync-run",
        "scanAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headCommit": _run_git(repository_root, ["rev-parse", "HEAD"]).strip()
        or "unknown",
        "mode": "check" if arguments.check else "write",
        "sync": report.as_json(),
    }
    if arguments.with_gate:
        payload["gate"] = run_page_quality_gates(repository_root)
        for entry in payload["gate"]["gates"]:
            print(f"[page-quality-gate] {entry['script']} exit={entry['exitCode']}")
            for bucket, messages in sorted(entry["failuresByClass"].items()):
                print(f"  {bucket}: {len(messages)}")
                for message in messages:
                    print(f"    - {message}")
    if not arguments.no_report:
        report_dir = (
            Path(arguments.report_dir).resolve()
            if arguments.report_dir
            else _default_report_dir(repository_root)
        )
        write_run_report(report_dir, payload)
        print(f"[page-object-source-path] report -> {report_dir}")

    if report.manual:
        return 1
    if arguments.check and report.fixes:
        return 1
    if arguments.fail_on_review and report.review:
        return 1
    return 0
