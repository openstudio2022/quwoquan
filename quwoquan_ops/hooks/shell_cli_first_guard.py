#!/usr/bin/env python3
"""Harness sensor（beforeShellExecution）：拦截绕过 CLI-first 的直跑业务脚本。

数据工程军规：quwoquan_data 业务能力必须经 `qwq-data`(=cli.py) 暴露，禁止新增可直跑
业务入口（verify_cli_first.py 的运行期对应物）。本 sensor 在 shell 执行前观测命令字符串：
直接 `python3 quwoquan_data/scripts/<域>/<x>.py` 跑业务脚本（非 cli.py、非 tests/、非
已 allowlist 的 verify 直跑）→ 标记并提示。

观测态（observe-only）：始终 permission=allow，仅附 agent_message；不阻断。
保持 observe-only，不升级为 ask/deny。读 JSON(stdin) → 写 JSON(stdout) → exit 0（fail open）。
"""
from __future__ import annotations

import json
import re
import sys

# 直跑 quwoquan_data 业务脚本（排除 cli.py / tests / verify 直跑 allowlist）。
_DIRECT_RUN_RE = re.compile(
    r"python3?\s+[^\n]*quwoquan_data/scripts/(?!.*cli\.py)(?!verify/)([a-z_]+)/[a-z_]+\.py",
    re.IGNORECASE,
)


def main() -> int:
    raw = sys.stdin.read() or "{}"
    command = ""
    try:
        command = str(json.loads(raw).get("command") or "")
    except ValueError:
        command = raw
    out: dict[str, object] = {"permission": "allow"}
    if _DIRECT_RUN_RE.search(command):
        out["agent_message"] = (
            "CLI-first 提醒：检测到疑似直跑 quwoquan_data 业务脚本，应改经 `qwq-data <command>`（cli.py）。"
            "若为一次性调试可忽略；新增能力必须沉淀为 CLI 子命令。"
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
