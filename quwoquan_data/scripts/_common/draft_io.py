"""Draft IO 规范：会话模型创作正文的落盘契约。

produce 三段式中间产物全部放在 produce/drafts/<ref>/ 包目录下：
  writing_pack.json  —— CLI prepare 产出的最小写作契约（证据/图/事实/约束）
  prompt.md          —— 给会话模型的人类可读写作指令
  article.md         —— 会话模型创作的正文（prepare 阶段先写占位）
  draft_meta.json    —— 出处元数据（generator/model/citedSourcePaths/coveredFacts）
  assets/            —— 草稿可引用资产包（只放必要物理文件）

generator 只有 'agent' 能进入交付面；'template'（脚本拼接）与 'pending'（未创作）被门禁拒绝。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from _common.io import read_json, write_json
from _common.paths import batch_command_root

GENERATOR_AGENT = "agent"
GENERATOR_TEMPLATE = "template"
GENERATOR_PENDING = "pending"

PLACEHOLDER_MARKER = "<!-- QWQ_AWAITING_AGENT_DRAFT -->"
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")


def drafts_dir(task_id: str, batch_id: str) -> Path:
    return batch_command_root(task_id, batch_id, "produce") / "drafts"


def draft_package_dir(task_id: str, batch_id: str, ref: str) -> Path:
    return drafts_dir(task_id, batch_id) / ref


def draft_assets_dir(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "assets"


def writing_pack_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "writing_pack.json"


def prompt_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "prompt.md"


def draft_article_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "article.md"


def draft_meta_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "draft_meta.json"


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
        f"{PLACEHOLDER_MARKER}\n# 待会话模型创作\n\n请阅读同目录 prompt.md 与 writing_pack.json 后创作正文并覆盖 article.md。\n",
        encoding="utf-8",
    )
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {"ref": ref, "generator": GENERATOR_PENDING, "model": None, "citedSourcePaths": [], "coveredFacts": []},
    )


def read_draft_article(task_id: str, batch_id: str, ref: str) -> str | None:
    path = draft_article_path(task_id, batch_id, ref)
    return path.read_text(encoding="utf-8") if path.exists() else None


def is_placeholder(article: str | None) -> bool:
    return article is None or PLACEHOLDER_MARKER in article


def draft_asset_reference_issues(article: str | None, pack: dict[str, Any] | None) -> list[str]:
    if not article:
        return []
    refs = {raw.split("/")[-1] for raw in _ASSET_REF_RE.findall(article)}
    if not refs:
        return []
    assets = (pack or {}).get("assets") or []
    allowed_ids = {
        str(asset.get("assetId") or "").strip()
        for asset in assets
        if isinstance(asset, dict) and str(asset.get("assetId") or "").strip()
    }
    allowed_files = {
        str(asset.get("fileName") or "").strip()
        for asset in assets
        if isinstance(asset, dict) and str(asset.get("fileName") or "").strip()
    }
    allowed = allowed_ids | allowed_files
    dangling = sorted(ref for ref in refs if ref not in allowed)
    if not dangling:
        return []
    return [f"draft asset ref not in writing_pack.assets: {ref}" for ref in dangling]


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
    style_family: str | None = None,
    opening_strategy: str | None = None,
) -> None:
    """会话模型创作正文写回（SOP 与测试 fixture 共用）。generator 固定为 agent。

    extracted_entities: 正文中挖掘出的专有实体，形如 [{"name":"洛绒牛场","type":"自然景观","evidenceRef":"..."}]，
    供 produce review 生成实体 sidecar / 关联实体主页。
    style_family / opening_strategy: agent 按原文体裁+证据自选的最终文风族与开篇策略 id，
    供 review 开篇门按所选 styleFamily 的 allowedOpenings markers 语义化校验，避免千篇一律开头。
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
            "styleFamily": style_family,
            "openingStrategy": opening_strategy,
            "citedSourcePaths": list(cited_source_paths),
            "coveredFacts": list(covered_facts),
            "extractedEntities": list(extracted_entities or []),
        },
    )
