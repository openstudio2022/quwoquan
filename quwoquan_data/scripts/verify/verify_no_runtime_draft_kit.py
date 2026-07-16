#!/usr/bin/env python3
"""扫描门：禁止正式链路复用测试专用的正文骨架（agent_draft_kit），
并禁止普通脚本直接调用 ``write_agent_draft()`` 冒充创作 agent写回正文，
亦禁止重新引入「脚本拼实体主页正文」的机械骨架函数。

背景（整改计划第一阶段）：四川 10e20c 批次的文章正文实际由 runtime 批次脚本
`from support.helpers.agent_draft_kit import route_article/entity_article` 拼接派生，
以 generator=agent 落盘，绕过"正文只由创作 agent创作"的原则，导致机械模板稿过门；
实体主页 `page.md` 早期也由脚本按固定模板小标题切句凑字，产出千篇一律的模板主页。

本门保证：除 `tests/` 外，任何 `scripts/ tasks/ runtime/` 下的 .py 都不得：
  - import agent_draft_kit（测试专用 fixture builder）；
  - 调用 route_article/entity_article/gallery_article 这类 kit 骨架函数；
  - 复刻 kit 的固定段落骨架指纹句；
  - 调用 `write_agent_draft()`（除 `core/draft_io.py` 自身定义外）；正文写回只能由创作 agent/外部 runner 执行，
    编排/verify/普通 CLI 脚本不得伪造 generator=agent；
  - 定义「脚本拼实体主页正文」的机械骨架函数（如 `_compose_*page* / _render_*page_body /
    _build_*page_body / _pad_*page* / _homepage_body* / _homepage_paragraph* / _synthesize_*page* /
    _stitch_*page*`）。实体主页正文同文章一样必须由创作 agent在 4.draft/page.md 创作（generator=agent），
    build_homepage 只下发 prompt.md + 占位 page.md，finalize 只注入封面与结构化 summary。
    注意：读取/解析 agent 写回正文的辅助（prompt 渲染、summary/section 映射、贴合度门）不在禁列。

runtime/** 是本地产物（.gitignore），CI 上通常不存在 → 门会自动跳过不存在的根；
但本地一旦残留"脚本拼正文/拼主页"路径即 FAIL，逼迫改回创作 agent单篇创作。

可直接运行：python3 quwoquan_data/scripts/verify/verify_no_runtime_draft_kit.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"

# kit 是测试专用，唯一合法位置是 tests/support/helpers/agent_draft_kit.py 及 tests/ 内消费者。
_KIT_IMPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:from\s+(?:tests\.)?helpers\.agent_draft_kit\s+import|import\s+agent_draft_kit|from\s+agent_draft_kit\s+import)"
)
_KIT_FUNC_RE = re.compile(r"\b(?:route_article|entity_article|gallery_article)\s*\(")
_WRITE_AGENT_DRAFT_RE = re.compile(r"\bwrite_agent_draft\s*\(")
# 实体主页正文机械骨架函数符号黑名单：命中的 def 名即「脚本拼主页正文」回归。
# 仅匹配会合成主页正文的 builder 命名，刻意避开当前正当辅助
# （_render_entity_page_prompt 渲染人读 prompt、_homepage_summary/_homepage_gate_body 仅做映射/门，不匹配）。
_HOMEPAGE_BODY_BUILDER_DEF_RE = re.compile(
    r"\bdef\s+(?:"
    r"_compose_\w*page\w*"          # _compose_homepage / _compose_entity_page_body
    r"|_render_\w*page_body\w*"     # _render_entity_page_body（≠ _render_entity_page_prompt）
    r"|_build_\w*page_body\w*"      # _build_homepage_body
    r"|_pad_\w*page\w*"             # _pad_homepage / _pad_page（凑字）
    r"|_homepage_body\w*"          # _homepage_body / _homepage_body_text（≠ _homepage_gate_body）
    r"|_homepage_paragraph\w*"     # _homepage_paragraphs
    r"|_homepage_narrative\w*"
    r"|_synthesize_\w*page\w*"
    r"|_stitch_\w*page\w*"
    r")\s*\("
)
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


def scan(root: Path | None = None) -> list[str]:
    scan_root = Path(root) if root is not None else ROOT
    data_root = scan_root / "quwoquan_data"
    scan_roots = [data_root / "scripts", data_root / "tasks", data_root / "runtime"]
    offenders: list[str] = []
    for base in scan_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_test_path(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
            rel = path.relative_to(scan_root)
            if _KIT_IMPORT_RE.search(text):
                offenders.append(f"{rel}: imports test-only agent_draft_kit (body must be authored by the session model)")
            elif _KIT_FUNC_RE.search(text) and "def route_article" not in text and "def entity_article" not in text:
                offenders.append(f"{rel}: calls draft-kit skeleton function (script-spliced body is forbidden)")
            elif (
                _WRITE_AGENT_DRAFT_RE.search(text)
                and rel.as_posix() != "quwoquan_data/scripts/core/draft_io.py"
                and "def write_agent_draft" not in text
            ):
                offenders.append(
                    f"{rel}: calls write_agent_draft directly (only session-model author / external runner may write agent drafts)"
                )
            hb = _HOMEPAGE_BODY_BUILDER_DEF_RE.search(text)
            if hb:
                offenders.append(
                    f"{rel}: defines mechanical homepage body builder {hb.group(0).split()[-1].rstrip('(')!r} "
                    "(homepage page.md body must be authored by the session model; build_homepage only emits prompt + placeholder)"
                )
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
            "\nFix: delete the runtime execution script and let the session model author each draft "
            "(produce --stage compose-brief → agent writes 4.draft/draft.article.md).",
            file=sys.stderr,
        )
        return 1
    print("[verify-no-runtime-draft-kit] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
