#!/usr/bin/env python3
"""门禁：禁止版本化 / 任务-区域硬编码回归到统一主线。

扫描 quwoquan_data/scripts 与 schema，拦截以下回归：
- `publish/v1`、`PUBLISH_ROOT / "v1"`、`publish_version_root`、`publish_active_version`
- objectKey 里的 `/v{N}/` 版本段（如 media/image/post/x/v1/cover.jpg）
- chuanxi / sichuan_v5 / *_v5 等任务/区域专属硬编码标识

允许：通用 `version` 字段（taxonomy/blueprint schema）、注释里说明历史的引用。
"""
from __future__ import annotations


import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent
SCHEMA_ROOT = SCRIPTS_ROOT.parent / "schema"
SELF = Path(__file__).name

FORBIDDEN = [
    (re.compile(r"publish/v\d+"), "publish/v{N} 版本目录（应为单一 publish/ 主线）"),
    (re.compile(r'PUBLISH_ROOT\s*/\s*"v\d+"'), 'PUBLISH_ROOT / "v{N}"'),
    (re.compile(r"publish_version_root|publish_active_version"), "已废弃版本函数"),
    (re.compile(r"media/image/post/[^\"']*?/v\d+/"), "objectKey 版本段 /v{N}/"),
    (re.compile(r"chuanxi", re.IGNORECASE), "chuanxi 任务专属硬编码"),
    (re.compile(r"四川旅行_v5|泰国旅行_v5|欧洲旅行_v5|_v5\b"), "*_v5 区域样例任务硬编码"),
]


def scan() -> list[str]:
    offenders: list[str] = []
    roots = [SCRIPTS_ROOT, SCHEMA_ROOT]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".json", ".yaml", ".yml"):
                continue
            if path.name == SELF:
                continue
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                for pat, desc in FORBIDDEN:
                    if pat.search(line):
                        offenders.append(f"{path.relative_to(SCRIPTS_ROOT.parent)}:{lineno}: {desc} :: {stripped[:80]}")
    return offenders


def main() -> None:
    offenders = scan()
    if offenders:
        print(f"[hardcode-guard] FAILED ({len(offenders)} hit(s))", file=sys.stderr)
        for o in offenders:
            print(f"  - {o}", file=sys.stderr)
        sys.exit(1)
    print("[hardcode-guard] PASSED")


if __name__ == "__main__":
    main()
