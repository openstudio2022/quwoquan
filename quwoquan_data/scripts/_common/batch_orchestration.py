"""单会话多实体批处理编排 ——「日产 10 万级」的吞吐路径（不引入外部模型，仍是会话 agent）。

评审痛点：逐实体 prepare→创作→review 往返太慢。批处理把 N 个文章/主页对象的写作契约聚合成一份
batch prompt，让同一个会话 agent 在一次会话内产出 N 篇，分别写回各对象 `4.draft/draft.article.md`，
再统一过 annotate-entities / review 门 + 结构化记录。

CLI 仍不拼接任何正文：只聚合 per-ref writing_pack 摘要 + 回写协议 + 跨篇多样性约束。
图片作品不进入正文批处理，它们由 sourceCollection/assets/caption 结构化证据包直接物化。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.draft_io import (
    draft_article_path,
    is_placeholder,
    prompt_path,
    read_draft_article,
    read_writing_pack,
    writing_pack_path,
)
from _common.io import write_json
from _common.paths import batch_root

BATCH_PACK_SCHEMA = "quwoquan_data.batch_pack"


def _ref_rel(task_id: str, batch_id: str, ref: str, path: Path) -> str:
    """会话写回路径：对象布局相对 batch 根。"""
    base = batch_root(task_id, batch_id)
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def plan_batches(refs: Sequence[str], batch_size: int) -> list[list[str]]:
    """把 refs 均匀切成每组至多 batch_size 个（batch_size<1 视为 1）。"""
    size = max(1, int(batch_size))
    items = [str(r) for r in refs if r]
    return [items[i : i + size] for i in range(0, len(items), size)]


def batch_dir(task_id: str, batch_id: str) -> Path:
    return batch_root(task_id, batch_id) / "_batch"


def build_batch_pack(task_id: str, batch_id: str, seq: int, group_refs: Sequence[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for ref in group_refs:
        pack = read_writing_pack(task_id, batch_id, ref) or {}
        items.append(
            {
                "ref": ref,
                "title": pack.get("title"),
                "styleFamily": pack.get("styleFamily"),
                "creativeBrief": pack.get("creativeBrief") or {},
                "mustIncludeFacts": list(pack.get("mustIncludeFacts") or [])[:6],
                "writingPack": _ref_rel(task_id, batch_id, ref, writing_pack_path(task_id, batch_id, ref)),
                "prompt": _ref_rel(task_id, batch_id, ref, prompt_path(task_id, batch_id, ref)),
                "articleOut": _ref_rel(task_id, batch_id, ref, draft_article_path(task_id, batch_id, ref)),
                "hasPack": bool(pack),
            }
        )
    return {
        "schemaVersion": BATCH_PACK_SCHEMA,
        "batchSeq": seq,
        "refCount": len(items),
        "items": items,
    }


def render_batch_prompt(pack: Mapping[str, Any]) -> str:
    items = pack.get("items") or []
    lines = [
        f"# 批量单会话创作（本批 {len(items)} 篇）",
        "",
        "在**同一个会话**内逐篇创作以下文章；每篇都要：",
        "- 严格遵循该篇 `writingPack` / `prompt` 的事实、证据与约束；",
        "- 逐篇先形成 2-3 个内容构思，选择最能兑现该篇 `creativeBrief.readerPromise` 的结构；",
        "- 按该篇 `styleFamily` 自选合适开篇策略，**跨篇之间开篇与章节结构必须显著不同**（避免千篇一律，会过跨篇相似度门）；",
        "- 创作完成后把正文**覆盖写回**该篇 `articleOut`（generator=agent），并在 `draft_meta` 记录 styleFamily / openingStrategy / extractedEntities / creativePlan / selfCritique。",
        "",
        "完成全部后运行：`qwq-data data produce --stage annotate-entities` 再 `--stage review --materialize`。",
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


def write_batch(task_id: str, batch_id: str, seq: int, group_refs: Sequence[str]) -> dict[str, Any]:
    pack = build_batch_pack(task_id, batch_id, seq, group_refs)
    out_dir = batch_dir(task_id, batch_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / f"{seq}.batch_pack.json", pack)
    (out_dir / f"{seq}.batch_prompt.md").write_text(render_batch_prompt(pack), encoding="utf-8")
    return pack


def batch_pack_issues(pack: Mapping[str, Any]) -> list[str]:
    """批 pack 完整性：非空、各 ref 已 prepare（有 writing_pack）、回写路径齐备。"""
    issues: list[str] = []
    items = pack.get("items") or []
    if not items:
        issues.append("batch pack has no items")
    for item in items:
        ref = item.get("ref")
        if not item.get("hasPack"):
            issues.append(f"ref missing writing_pack (先跑 compose-brief): {ref}")
        if not item.get("articleOut"):
            issues.append(f"ref missing articleOut path: {ref}")
    return issues


def batch_completion_status(task_id: str, batch_id: str, group_refs: Sequence[str]) -> dict[str, Any]:
    """统计该批 agent 创作进度（done=非占位草稿，pending=尚未创作）。"""
    done: list[str] = []
    pending: list[str] = []
    for ref in group_refs:
        article = read_draft_article(task_id, batch_id, ref)
        (pending if is_placeholder(article) else done).append(ref)
    return {"total": len(list(group_refs)), "done": done, "pending": pending}


__all__ = [
    "BATCH_PACK_SCHEMA",
    "plan_batches",
    "batch_dir",
    "build_batch_pack",
    "render_batch_prompt",
    "write_batch",
    "batch_pack_issues",
    "batch_completion_status",
]
