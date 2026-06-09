#!/usr/bin/env python3
"""扫描门：禁止正式链路复用测试专用的正文骨架（agent_draft_kit）。

背景（整改计划第一阶段）：四川 10e20c 批次的正文实际由 runtime 批次脚本
`from helpers.agent_draft_kit import route_article/entity_article` 拼接派生，
以 generator=agent 落盘，绕过"正文只由会话模型创作"的原则，导致机械模板稿过门。

本门保证：除 `tests/` 外，任何 `scripts/ tasks/ runtime/` 下的 .py 都不得：
  - import agent_draft_kit（测试专用 fixture builder）；
  - 调用 route_article/entity_article/gallery_article 这类 kit 骨架函数；
  - 复刻 kit 的固定段落骨架指纹句。

runtime/** 是本地产物（.gitignore），CI 上通常不存在 → 门会自动跳过不存在的根；
但本地一旦残留"脚本拼正文"路径即 FAIL，逼迫改回会话模型单篇创作。

可直接运行：python3 quwoquan_data/scripts/verify/verify_no_runtime_draft_kit.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"
SCAN_ROOTS = [DATA_ROOT / "scripts", DATA_ROOT / "tasks", DATA_ROOT / "runtime"]

# kit 是测试专用，唯一合法位置是 tests/helpers/agent_draft_kit.py 及 tests/ 内消费者。
_KIT_IMPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:from\s+(?:tests\.)?helpers\.agent_draft_kit\s+import|import\s+agent_draft_kit|from\s+agent_draft_kit\s+import)"
)
_KIT_FUNC_RE = re.compile(r"\b(?:route_article|entity_article|gallery_article)\s*\(")
# kit 标志性骨架句（复刻即视为脚本拼正文）。
_KIT_FINGERPRINTS = (
    "出发前我犹豫了很久",
    "安静看展的松弛感",
    "走完这条线的取舍",
    "讲解扎堆",
    "愿意为节奏让路",
    "去过{name}之后想说的",
)


_SELF = Path(__file__).resolve()


def _is_test_path(path: Path) -> bool:
    if path.resolve() == _SELF:
        return True  # 本门自身存有指纹字面量，跳过避免自指
    parts = set(path.parts)
    return "tests" in parts or path.name.startswith("test_")


def scan() -> list[str]:
    offenders: list[str] = []
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_test_path(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
            rel = path.relative_to(ROOT)
            if _KIT_IMPORT_RE.search(text):
                offenders.append(f"{rel}: imports test-only agent_draft_kit (body must be authored by the session model)")
            elif _KIT_FUNC_RE.search(text) and "def route_article" not in text and "def entity_article" not in text:
                offenders.append(f"{rel}: calls draft-kit skeleton function (script-spliced body is forbidden)")
            for fp in _KIT_FINGERPRINTS:
                if fp in text:
                    offenders.append(f"{rel}: replicates draft-kit skeleton phrase: {fp!r}")
                    break
    return offenders


def main() -> int:
    offenders = scan()
    if offenders:
        print("[verify-no-runtime-draft-kit] FAILED: script-spliced body path detected", file=sys.stderr)
        for row in offenders:
            print(f"  - {row}", file=sys.stderr)
        print(
            "\nFix: delete the runtime batch script and let the session model author each draft "
            "(produce --stage compose-brief → agent writes 4.draft/draft.article.md).",
            file=sys.stderr,
        )
        return 1
    print("[verify-no-runtime-draft-kit] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
