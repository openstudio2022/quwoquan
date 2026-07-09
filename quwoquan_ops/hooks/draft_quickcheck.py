#!/usr/bin/env python3
"""Harness sensor（afterFileEdit）：草稿落盘后即跑联系方式/机械标题快检。

把 contact/heading 两类高频人工返工项做成"编辑即检"的反馈层 sensor，让 Subagent
在写完草稿的同一时刻就看到问题，缩短 Ralph 自纠环延迟。

观测态（observe-only）：只对 article.md / draft.article.md 生效；命中即在 stdout 附
additional_context 提示；其余文件立即放行。读 JSON(stdin) → 写 JSON(stdout) → exit 0。
轻量优先：非草稿文件不加载门库（避免每次 Write 的启动开销）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DRAFT_NAMES = ("article.md", "draft.article.md")


def _edited_path(payload: dict) -> str:
    for key in ("file_path", "filePath", "path", "file"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    edits = payload.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict):
                for key in ("file_path", "path"):
                    if isinstance(e.get(key), str):
                        return e[key]
    return ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("{}")
        return 0
    path = _edited_path(payload if isinstance(payload, dict) else {})
    name = Path(path).name if path else ""
    if name not in _DRAFT_NAMES or not Path(path).is_file():
        print("{}")  # 非草稿：零成本放行
        return 0

    # 仅在确为草稿时才加载门库
    here = Path(__file__).resolve()
    root = next((p for p in here.parents if (p / "quwoquan_data").is_dir()), None)
    if root is None:
        print("{}")
        return 0
    scripts = root / "quwoquan_data" / "scripts"
    for p in (root / "quwoquan_data", scripts):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        from _common import quality_gates as qg  # noqa: E402

        article = Path(path).read_text(encoding="utf-8")
        issues = qg.contact_info_issues(article) + qg.mechanical_heading_issues(article)
    except Exception:  # noqa: BLE001  fail open：sensor 不得影响编辑落盘
        print("{}")
        return 0

    if issues:
        print(json.dumps({"additional_context": "草稿快检命中：\n- " + "\n- ".join(issues)}, ensure_ascii=False))
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
