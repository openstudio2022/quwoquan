"""Draft IO 规范：会话模型创作正文的落盘契约。

produce 三段式中间产物全部放在 produce/drafts/ 下：
  {ref}.writing_pack.json  —— CLI prepare 产出的写作契约（证据/图/事实/约束）
  {ref}.prompt.md          —— 给会话模型的人类可读写作指令
  {ref}.article.md         —— 会话模型创作的正文（prepare 阶段先写占位）
  {ref}.draft_meta.json    —— 出处元数据（generator/model/citedSourcePaths/coveredFacts）

generator 只有 'agent' 能进入交付面；'template'（脚本拼接）与 'pending'（未创作）被门禁拒绝。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from _common.io import read_json, write_json
from _common.paths import batch_command_root

GENERATOR_AGENT = "agent"
GENERATOR_TEMPLATE = "template"
GENERATOR_PENDING = "pending"

PLACEHOLDER_MARKER = "<!-- QWQ_AWAITING_AGENT_DRAFT -->"


def drafts_dir(task_id: str, batch_id: str) -> Path:
    return batch_command_root(task_id, batch_id, "produce") / "drafts"


def writing_pack_path(task_id: str, batch_id: str, ref: str) -> Path:
    return drafts_dir(task_id, batch_id) / f"{ref}.writing_pack.json"


def prompt_path(task_id: str, batch_id: str, ref: str) -> Path:
    return drafts_dir(task_id, batch_id) / f"{ref}.prompt.md"


def draft_article_path(task_id: str, batch_id: str, ref: str) -> Path:
    return drafts_dir(task_id, batch_id) / f"{ref}.article.md"


def draft_meta_path(task_id: str, batch_id: str, ref: str) -> Path:
    return drafts_dir(task_id, batch_id) / f"{ref}.draft_meta.json"


def write_writing_pack(task_id: str, batch_id: str, ref: str, pack: dict[str, Any]) -> Path:
    path = writing_pack_path(task_id, batch_id, ref)
    write_json(path, pack)
    return path


def read_writing_pack(task_id: str, batch_id: str, ref: str) -> dict[str, Any] | None:
    path = writing_pack_path(task_id, batch_id, ref)
    return read_json(path) if path.exists() else None


def write_prompt(task_id: str, batch_id: str, ref: str, prompt_md: str) -> Path:
    path = prompt_path(task_id, batch_id, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt_md, encoding="utf-8")
    return path


def write_placeholder_draft(task_id: str, batch_id: str, ref: str) -> None:
    """prepare 阶段写占位正文 + pending meta，待会话模型覆盖。"""
    article = draft_article_path(task_id, batch_id, ref)
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        f"{PLACEHOLDER_MARKER}\n# 待会话模型创作\n\n请阅读同目录 {ref}.prompt.md 与 {ref}.writing_pack.json 后创作正文并覆盖本文件。\n",
        encoding="utf-8",
    )
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {"ref": ref, "generator": GENERATOR_PENDING, "model": None, "citedSourcePaths": [], "coveredFacts": []},
    )


def read_draft_article(task_id: str, batch_id: str, ref: str) -> str | None:
    path = draft_article_path(task_id, batch_id, ref)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def is_placeholder(article: str | None) -> bool:
    return article is None or PLACEHOLDER_MARKER in article


def read_draft_meta(task_id: str, batch_id: str, ref: str) -> dict[str, Any] | None:
    path = draft_meta_path(task_id, batch_id, ref)
    return read_json(path) if path.exists() else None


def write_agent_draft(
    task_id: str,
    batch_id: str,
    ref: str,
    article_markdown: str,
    *,
    model: str,
    cited_source_paths: Sequence[str],
    covered_facts: Sequence[str],
    session_trace: str | None = None,
    extracted_entities: Sequence[dict[str, Any]] | None = None,
) -> None:
    """会话模型创作正文写回（SOP 与测试 fixture 共用）。generator 固定为 agent。

    extracted_entities: 正文中挖掘出的专有实体，形如 [{"name":"洛绒牛场","type":"自然景观","evidenceRef":"..."}]，
    供 produce review 生成实体 sidecar / 关联实体主页。
    """
    article = draft_article_path(task_id, batch_id, ref)
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(article_markdown, encoding="utf-8")
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {
            "ref": ref,
            "generator": GENERATOR_AGENT,
            "model": model,
            "sessionTrace": session_trace,
            "citedSourcePaths": list(cited_source_paths),
            "coveredFacts": list(covered_facts),
            "extractedEntities": list(extracted_entities or []),
        },
    )
