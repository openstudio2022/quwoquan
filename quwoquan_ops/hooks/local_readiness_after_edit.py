#!/usr/bin/env python3
"""Short-lived after-edit hook: enqueue exact path identity and return."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.local_readiness import LocalReadinessError, enqueue_paths  # noqa: E402


def _paths(payload: dict) -> list[str]:
    values: list[str] = []
    for key in ("file_path", "filePath", "path", "file"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    for edit in payload.get("edits", []) if isinstance(payload.get("edits"), list) else []:
        if isinstance(edit, dict):
            values.extend(str(edit[key]) for key in ("file_path", "filePath", "path", "file") if isinstance(edit.get(key), str) and edit[key])
    result: list[str] = []
    for raw in values:
        path = Path(raw)
        try:
            result.append(str(path.resolve().relative_to(ROOT)))
        except ValueError:
            continue
    return sorted(set(result))


def _draft_context(payload: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_ops/hooks/draft_quickcheck.py")],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    try:
        value = json.loads(proc.stdout or "{}")
    except ValueError:
        return ""
    return str(value.get("additional_context") or "") if isinstance(value, dict) else ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook payload 必须为 object")
        paths = _paths(payload)
        context = _draft_context(payload)
        if not paths:
            print(json.dumps({"additional_context": context}, ensure_ascii=False) if context else "{}")
            return 0
        queue = enqueue_paths(paths, reason="after_edit_script")
        message = (
            f"local readiness 已入队 {len(paths)} 个路径；待办总数 {len(queue['items'])}。"
            "空闲时运行：python3 quwoquan_ops/cli/local_readiness.py worker --once；"
            "诊断：python3 quwoquan_ops/cli/local_readiness.py inspect。"
        )
        if context:
            message += "\n" + context
        print(json.dumps({"additional_context": message}, ensure_ascii=False))
        return 0
    except (LocalReadinessError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"additional_context": f"local readiness 入队失败：{exc}；未生成 readiness PASS。"}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
