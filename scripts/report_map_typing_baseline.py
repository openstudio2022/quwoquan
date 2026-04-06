#!/usr/bin/env python3
"""
Map / 弱类型基线报告（与 map-typing-remediation 规划对齐）。

输出 Markdown 到 stdout；CI/本地可重定向写入
specs/feature-tree/runtime/runtime-client-foundation/map-typing-remediation-baseline.md

用法:
  python3 scripts/report_map_typing_baseline.py > path/to/baseline.md
  python3 scripts/report_map_typing_baseline.py --run-page-abc-c  # 附录：门禁 C 结果
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "quwoquan_app" / "lib"
MAP_RE = re.compile(r"Map<String,\s*dynamic>")
SERVICE_YAML_DIRS = [
    ROOT / "quwoquan_service" / "contracts" / "metadata",
]


def scan_lib() -> tuple[int, int, dict[str, int], list[tuple[int, str]]]:
    """Returns (occurrences, file_count, by_bucket, sorted_files)."""
    by_bucket: dict[str, int] = defaultdict(int)
    per_file: dict[str, int] = defaultdict(int)
    occ = 0
    for path in LIB.rglob("*.dart"):
        if path.name.endswith(".g.dart"):
            continue
        rel = path.relative_to(LIB)
        text = path.read_text(encoding="utf-8", errors="replace")
        n = len(MAP_RE.findall(text))
        if n == 0:
            continue
        occ += n
        per_file[str(rel)] = n
        top = rel.parts[0] if rel.parts else "."
        by_bucket[top] += n
    files_sorted = sorted(per_file.items(), key=lambda x: (-x[1], x[0]))
    return occ, len(per_file), dict(by_bucket), files_sorted


def count_service_yaml() -> int:
    n = 0
    for d in SERVICE_YAML_DIRS:
        if not d.is_dir():
            continue
        for p in d.rglob("service.yaml"):
            n += 1
    return n


def repository_map_signatures() -> str:
    """Lightweight grep summary for core repos (hand-maintained patterns)."""
    targets = [
        "quwoquan_app/lib/cloud/services/content/content_repository.dart",
        "quwoquan_app/lib/cloud/services/circle/circle_repository.dart",
        "quwoquan_app/lib/cloud/services/chat/chat_repository_api.dart",
        "quwoquan_app/lib/cloud/services/user/user_profile_repository.dart",
        "quwoquan_app/lib/cloud/services/rtc/rtc_repository.dart",
    ]
    lines_out: list[str] = []
    fut_map = re.compile(r"Future<[^>]*Map<String,\s*dynamic>")
    for rel in targets:
        p = ROOT / rel
        if not p.is_file():
            lines_out.append(f"| `{rel}` | (missing) |")
            continue
        text = p.read_text(encoding="utf-8", errors="utf-8")
        hits = fut_map.findall(text)
        lines_out.append(f"| `{rel}` | ~{len(hits)} `Future<...Map<String,dynamic>>` shapes |")
    return "\n".join(lines_out)


def run_page_abc_c() -> str:
    script = ROOT / "scripts" / "verify_page_abc_governance.py"
    if not script.is_file():
        return "_verify_page_abc_governance.py not found_\n"
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--enforce-c"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        tail = (r.stdout + r.stderr)[-8000:]
        return (
            f"- **exit code**: `{r.returncode}` (0 = pass)\n"
            f"- **tail**:\n\n```\n{tail}\n```\n"
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"_failed to run: {e}_\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-page-abc-c",
        action="store_true",
        help="Run verify_page_abc_governance.py --enforce-c and append output",
    )
    args = ap.parse_args()

    occ, nfiles, buckets, files_sorted = scan_lib()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md: list[str] = [
        "# Map / 弱类型数据整改 — 基线快照",
        "",
        f"_Generated: {now}_ (`scripts/report_map_typing_baseline.py`)",
        "",
        "## 1. 口径",
        "",
        "- **扫描根**: `quwoquan_app/lib/**/*.dart`",
        "- **排除**: `*.g.dart`（codegen 内 `toMap` 等不计入待清零口径）",
        "- **匹配**: 字面量 `Map<String, dynamic>`（含中间有空格变体）",
        "",
        "## 2. 汇总",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| `Map<String, dynamic>` 出现次数 | **{occ}** |",
        f"| 涉及文件数 | **{nfiles}** |",
        f"| `contracts/metadata/**/service.yaml` 文件数（约） | **{count_service_yaml()}** |",
        "",
        "## 3. 按顶层目录（lib 下第一级）",
        "",
        "| 目录 | 次数 |",
        "|------|------|",
    ]
    for k in sorted(buckets, key=lambda x: -buckets[x]):
        md.append(f"| `{k}/` | {buckets[k]} |")
    md.extend(
        [
            "",
            "## 4. 热点文件 Top 40（按次数）",
            "",
            "| 次数 | 路径 |",
            "|------|------|",
        ]
    )
    for n, rel in files_sorted[:40]:
        md.append(f"| {n} | `{rel}` |")

    md.extend(
        [
            "",
            "## 5. Repository `Future<...Map<String,dynamic>>` 粗检",
            "",
            "以下为抽象/实现文件中 `Future<...Map<String, dynamic>>` 形态的大致计数（非语义分析）。",
            "",
            "| 文件 | 粗计数 |",
            "|------|--------|",
            repository_map_signatures(),
            "",
            "## 6. Content / Circle / User / Chat 与 service.yaml",
            "",
            "详细 API 级缺口表应随 PR 在 `contracts/metadata/<domain>/.../service.yaml` 与 "
            "`Abstract *Repository` 之间做 diff；本脚本仅提供 **service.yaml 文件总数** 与 **Repository 粗检** 作为索引。",
            "",
            "## 7. 页面门禁 C（64 路径）",
            "",
            "规范: `specs/gates/session_c_page_typing.md`",
            "",
            "命令:",
            "",
            "```bash",
            "python3 scripts/verify_page_abc_governance.py --enforce-c",
            "# 或",
            "make verify-app-page-abc-governance",
            "```",
            "",
        ]
    )

    if args.run_page_abc_c:
        md.append("### 本次运行结果\n")
        md.append(run_page_abc_c())
    else:
        md.append(
            "_附录：使用 `python3 scripts/report_map_typing_baseline.py --run-page-abc-c` "
            "生成时可附带执行门禁 C 并写入 tail。_\n"
        )

    sys.stdout.write("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
