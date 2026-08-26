#!/usr/bin/env python3
"""gate_repo.sh 结构化 summary 发射器。

gate_repo.sh 是 `set -e` 的 bash 编排链：要么全绿跑完，要么在首个失败命令处退出。
本脚本由其 EXIT trap 调用，把最终结果按 `gate_output` 统一 schema 落盘到
`.qwq_output/env/repo/runs/gate/gate-repo-<scope>.json`，使 AI 能机器消费
门禁链结果而不必解析自由文本。

- 每个 scope 独立落盘（all/service/app/portal/data/patrol），CI 分片互不覆盖。
- `--failed-command` 是主 shell ERR trap 捕获的 best-effort 信息：子 shell
  （如 `(cd quwoquan_service && make gate)`）内部的失败命令不可见，此时只有
  退出码与 scope 可信。
- 落盘失败不改变门禁退出语义（gate_output.emit_gate_result 自身兜底）。

用法（由 gate_repo.sh 接线，人工调试可直跑）：
    python3 -B quwoquan_ops/gate/emit_gate_repo_summary.py \
        --scope all --exit-code 1 --failed-command "python3 xx.py"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))
from gate_output import emit_gate_result, finding  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--failed-command", default="")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="落盘根（默认仓库根；测试用临时目录隔离）",
    )
    args = parser.parse_args(argv)

    findings: list[dict] = []
    if args.exit_code != 0:
        message = f"gate_repo --scope {args.scope} 失败（exit={args.exit_code}）"
        if args.failed_command:
            message += f"：最后失败命令 `{args.failed_command}`（主 shell best-effort）"
        findings.append(
            finding(
                message,
                fix=(
                    "按 stdout 中该命令的失败输出定位修复后复跑 "
                    f"bash quwoquan_ops/gate/gate_repo.sh --scope {args.scope}"
                ),
            )
        )
    emit_gate_result(f"gate-repo-{args.scope}", findings, args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
