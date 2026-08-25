"""GATE_BLOCK 机器可读输出——统一 schema 的唯一实现。

人类可读文本照旧走 stdout/stderr；本模块只额外把结构化结果落盘到
`.qwq_output/env/repo/runs/gate/<gate>.json`（覆盖式，最新一次结果），
不改变任何门禁的退出语义。schema：

    {
      "gate": "<make target 或脚本名>",
      "status": "pass" | "block",
      "findings": [
        {"message": str, "path": str|null, "line": int|null,
         "fix": str|null, "truth_ref": str|null}
      ],
      "generated_at": "<ISO8601 UTC>",
      "head_sha": "<git short sha>"
    }

findings 为空即 pass。path/line 定位失败点，fix 是建议动作，
truth_ref 指向裁定该项的真相源（spec 锚点、contracts 路径等）；
接入方拿不出的字段留 null，不得编造。
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

GATE_RUNS_RELATIVE = Path(".qwq_output/env/repo/runs/gate")

# 从自由文本 message 尽力提取仓库内路径（含可选 :line 后缀），提不出留 null。
_PATH_IN_MESSAGE_RE = re.compile(
    r"(?P<path>(?:specs|quwoquan_app|quwoquan_service|quwoquan_data|quwoquan_ops"
    r"|\.agents|\.claude|\.codex|\.cursor|\.github)/[\w./\-]+)(?::(?P<line>\d+))?"
)


def finding(
    message: str,
    *,
    path: str | None = None,
    line: int | None = None,
    fix: str | None = None,
    truth_ref: str | None = None,
) -> dict:
    if path is None:
        match = _PATH_IN_MESSAGE_RE.search(message)
        if match:
            path = match.group("path")
            if line is None and match.group("line"):
                line = int(match.group("line"))
    return {
        "message": message,
        "path": path,
        "line": line,
        "fix": fix,
        "truth_ref": truth_ref,
    }


def emit_gate_result(gate: str, findings: list[dict], repo_root: Path) -> Path | None:
    """写 <repo>/.qwq_output/env/repo/runs/gate/<gate>.json，返回落盘路径。

    落盘是附加观测，不是门禁判定的一部分：文件系统只读等 OSError 只告警不上抛，
    绝不因落盘失败改变门禁的退出语义（例如把通过的门弄挂）。失败时返回 None。
    """
    payload = {
        "gate": gate,
        "status": "block" if findings else "pass",
        "findings": findings,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "head_sha": _head_sha(repo_root),
    }
    try:
        out_dir = repo_root / GATE_RUNS_RELATIVE
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{gate}.json"
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as error:
        print(
            f"[gate_output] 警告：{gate} 结果落盘失败（{error}）；门禁退出语义不受影响",
            file=sys.stderr,
        )
        return None
    return out_path


def _head_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"
