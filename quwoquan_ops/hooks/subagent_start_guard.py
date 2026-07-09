#!/usr/bin/env python3
"""Harness sensor（subagentStart）：在 Subagent 启动时注入隔离 + 最小工具集纪律。

马具工程 execution 层：把"单 ref 隔离、最小工具集 allow-list、Ralph 出口判据"作为
硬钩子注入每个 Subagent，而不只在 prompt 叮嘱（"知道规则却违反 → 加 sensor"）。

观测态（observe-only）：始终 permission=allow，仅附 user_message 提醒；不阻断。
稳定后可改为对越权 subagent 返回 ask/deny。读 JSON(stdin) → 写 JSON(stdout) → exit 0。
"""
from __future__ import annotations

import json
import sys

MIN_TOOLSET = ["read_ref_packet", "search_web", "write_draft", "run_review_gate"]


def main() -> int:
    try:
        json.loads(sys.stdin.read() or "{}")
    except ValueError:
        pass  # fail open：输入异常也不阻断
    print(
        json.dumps(
            {
                "permission": "allow",
                "user_message": (
                    "single-ref 隔离：只读本 ref 的 packet/SOP/source，禁止读取同批其它文章正文作为底稿；"
                    f"最小工具集={MIN_TOOLSET}；出口判据=ref_review_gate.passed==approved 或超墙钟标 timeout。"
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
