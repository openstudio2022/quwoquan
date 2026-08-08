"""单 execution 内的写作分组编排。

评审痛点：逐实体 prepare→创作→review 往返太慢。写作分组把 N 个文章/主页对象的写作契约聚合成一份
writer-group prompt，让同一个会话 agent 在一次会话内产出 N 篇，分别写回各对象 `4.draft/draft.article.md`，
再统一过 annotate-entities / review 门 + 结构化记录。

CLI 仍不拼接任何正文：只聚合 per-ref writing_pack 摘要 + 回写协议 + 跨篇多样性约束。
图片作品不进入正文写作分组，它们由 sourceCollection/assets/caption 结构化证据包直接物化。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from content.post.article.draft_io import (
    draft_article_path,
    is_placeholder,
    prompt_path,
    read_draft_article,
    read_writing_pack,
    writing_pack_path,
)
from core.io import write_json
from core.paths import execution_command_root, execution_root

WRITER_GROUP_PACK_SCHEMA = "quwoquan_data.execution_writer_group"


def _ref_rel(execution_id: str, ref: str, path: Path) -> str:
    """会话写回路径：对象布局相对 execution 根。"""
    base = execution_root(execution_id)
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def partition_writer_groups(refs: Sequence[str], writer_group_size: int) -> list[list[str]]:
    """把 refs 均匀切成每组至多 writer_group_size 个（writer_group_size<1 视为 1）。"""
    size = max(1, int(writer_group_size))
    items = [str(r) for r in refs if r]
    return [items[i : i + size] for i in range(0, len(items), size)]


def writer_group_dir(execution_id: str) -> Path:
    return execution_command_root(execution_id, "post") / "writer_groups"


def build_writer_group_pack(execution_id: str, seq: int, group_refs: Sequence[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for ref in group_refs:
        pack = read_writing_pack(execution_id, ref) or {}
        items.append(
            {
                "ref": ref,
                "title": pack.get("title"),
                "styleFamily": pack.get("styleFamily"),
                "creativeBrief": pack.get("creativeBrief") or {},
                "mustIncludeFacts": list(pack.get("mustIncludeFacts") or [])[:6],
                "writingPack": _ref_rel(execution_id, ref, writing_pack_path(execution_id, ref)),
                "prompt": _ref_rel(execution_id, ref, prompt_path(execution_id, ref)),
                "articleOut": _ref_rel(execution_id, ref, draft_article_path(execution_id, ref)),
                "hasPack": bool(pack),
            }
        )
    return {
        "schema": WRITER_GROUP_PACK_SCHEMA,
        "writerGroupSequence": seq,
        "refCount": len(items),
        "items": items,
    }


def render_writer_group_prompt(pack: Mapping[str, Any]) -> str:
    items = pack.get("items") or []
    lines = [
        f"# 单 execution 写作分组（{len(items)} 篇）",
        "",
        "在**同一个会话**内逐篇创作以下文章；每篇都要：",
        "- 严格遵循该篇 `writingPack` / `prompt` 的事实、证据与约束；",
        "- 逐篇先形成 2-3 个内容构思，选择最能兑现该篇 `creativeBrief.readerPromise` 的结构；",
        "- 按该篇 `styleFamily` 自选合适开篇策略，**跨篇之间开篇与章节结构必须显著不同**（避免千篇一律，会过跨篇相似度门）；",
        "- 创作完成后把正文**覆盖写回**该篇 `articleOut`（generator=agent），并在 `draft_meta` 记录 styleFamily / openingStrategy / extractedEntities / creativePlan / selfCritique。",
        "",
        "完成全部后由 execution orchestrator 进入 review 与 promotion。",
        "",
        "## 篇目清单",
    ]
    for index, item in enumerate(items, 1):
        lines.append(
            f"{index}. ref=`{item.get('ref')}` | 标题：{item.get('title') or '(见 pack)'} | "
            f"文风：{item.get('styleFamily') or '(自选)'}"
        )
        lines.append(f"   - 契约：`{item.get('writingPack')}`，指令：`{item.get('prompt')}`，写回：`{item.get('articleOut')}`")
        facts = item.get("mustIncludeFacts") or []
        if facts:
            lines.append(f"   - 必含事实（节选）：{('；'.join(map(str, facts)))}")
        creative = item.get("creativeBrief") or {}
        if creative.get("readerPromise"):
            lines.append(f"   - readerPromise：{creative.get('readerPromise')}")
        moves = creative.get("allowedMoves") or []
        if moves:
            lines.append(f"   - 可自主选择的表达动作：{(' / '.join(map(str, moves[:5])))}")
    return "\n".join(lines) + "\n"


def write_writer_group(execution_id: str, seq: int, group_refs: Sequence[str]) -> dict[str, Any]:
    pack = build_writer_group_pack(execution_id, seq, group_refs)
    out_dir = writer_group_dir(execution_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / f"{seq}.writer_group_pack.json", pack)
    (out_dir / f"{seq}.writer_group_prompt.md").write_text(render_writer_group_prompt(pack), encoding="utf-8")
    return pack


def writer_group_issues(pack: Mapping[str, Any]) -> list[str]:
    """写作分组完整性：非空、各 ref 已 prepare（有 writing_pack）、回写路径齐备。"""
    issues: list[str] = []
    items = pack.get("items") or []
    if not items:
        issues.append("writer group has no items")
    for item in items:
        ref = item.get("ref")
        if not item.get("hasPack"):
            issues.append(f"ref missing writing_pack (先跑 compose-brief): {ref}")
        if not item.get("articleOut"):
            issues.append(f"ref missing articleOut path: {ref}")
    return issues


def writer_group_completion_status(execution_id: str, group_refs: Sequence[str]) -> dict[str, Any]:
    """统计该写作分组创作进度（done=非占位草稿，pending=尚未创作）。"""
    done: list[str] = []
    pending: list[str] = []
    for ref in group_refs:
        article = read_draft_article(execution_id, ref)
        (pending if is_placeholder(article) else done).append(ref)
    return {"total": len(list(group_refs)), "done": done, "pending": pending}


__all__ = [
    "WRITER_GROUP_PACK_SCHEMA",
    "partition_writer_groups",
    "writer_group_dir",
    "build_writer_group_pack",
    "render_writer_group_prompt",
    "write_writer_group",
    "writer_group_issues",
    "writer_group_completion_status",
]
