"""Draft IO 规范：创作 agent 创作正文的落盘契约（对象优先，规格 §2.4/§15.1）。

produce 过程产物挂在内容对象目录下（经 `_common.content_object` 路由解析）：
  3.compose/writing_pack.json —— CLI prepare 产出的最小写作契约（证据/图/事实/约束）
  4.draft/prompt.md           —— 给创作 agent 的人类可读写作指令
  4.draft/draft.article.md    —— 文章/主页类创作 agent 创作的正文（prepare 阶段先写占位）
  4.draft/draft_meta.json     —— 出处元数据（generator/model/citedSourcePaths/coveredFacts）
  4.draft/assets/             —— 草稿可引用资产包（只放必要物理文件）

图片作品是结构化 sourceCollection/assets/title/caption 证据包，不生成 draft.article.md。

generator 只有 'agent' 能进入文章/主页交付面；图片作品使用 'image_evidence_pack'。
'template'（脚本拼接）与 'pending'（未创作）被门禁拒绝。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from _common.article_package import compute_document_sha256, sha256_file, sha256_text
from _common.creator_assignment import creator_from_payload
from _common.io import read_json, write_json
from _common.paths import STAGE_COMPOSE, STAGE_DRAFT, batch_root

GENERATOR_AGENT = "agent"
GENERATOR_TEMPLATE = "template"
GENERATOR_PENDING = "pending"
GENERATOR_IMAGE_EVIDENCE = "image_evidence_pack"

PLACEHOLDER_MARKER = "<!-- QWQ_AWAITING_AGENT_DRAFT -->"
DRAFT_ARTICLE_FILE = "draft.article.md"
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_iso(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _file_mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _object_stage_dir(task_id: str, batch_id: str, ref: str, stage: str) -> Path | None:
    from _common.content_object import content_coords, content_object_stage_dir

    if content_coords(task_id, batch_id, ref):
        return content_object_stage_dir(task_id, batch_id, ref, stage)
    return None


def draft_package_dir(task_id: str, batch_id: str, ref: str) -> Path:
    """草稿包（prompt/draft.article/draft_meta/assets）目录：对象 4.draft。"""
    obj = _object_stage_dir(task_id, batch_id, ref, STAGE_DRAFT)
    if obj is None:
        raise KeyError(f"draft package not registered for ref={ref!r} (task={task_id} batch={batch_id})")
    return obj


def brief_package_dir(task_id: str, batch_id: str, ref: str) -> Path:
    """创作契约（writing_pack）目录：对象 3.compose。"""
    obj = _object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE)
    if obj is None:
        raise KeyError(f"brief package not registered for ref={ref!r} (task={task_id} batch={batch_id})")
    return obj


def draft_assets_dir(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "assets"


def writing_pack_path(task_id: str, batch_id: str, ref: str) -> Path:
    return brief_package_dir(task_id, batch_id, ref) / "writing_pack.json"


def prompt_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "prompt.md"


def draft_article_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / DRAFT_ARTICLE_FILE


def draft_meta_path(task_id: str, batch_id: str, ref: str) -> Path:
    return draft_package_dir(task_id, batch_id, ref) / "draft_meta.json"


def iter_draft_articles(task_id: str, batch_id: str) -> list[tuple[str, Path]]:
    """(ref, draft.article.md) 列表：仅枚举已登记的对象布局。"""
    from _common.content_object import iter_content_refs

    refs = iter_content_refs(task_id, batch_id)
    out: list[tuple[str, Path]] = []
    for ref in refs:
        path = draft_article_path(task_id, batch_id, ref)
        if path.exists():
            out.append((ref, path))
    return out


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


def write_placeholder_draft(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    allow_agent_downgrade: bool = False,
    downgrade_reason: str = "",
) -> None:
    """prepare 阶段写占位正文 + pending meta，待创作 agent 覆盖。

    A completed agent draft is production evidence.  It may only be reset by an
    explicit upstream retry/rebuild path, never by an incidental prepare rerun.
    """
    article = draft_article_path(task_id, batch_id, ref)
    existing_meta = read_draft_meta(task_id, batch_id, ref) or {}
    existing_article = article.read_text(encoding="utf-8") if article.exists() else None
    if (
        str(existing_meta.get("generator") or "") == GENERATOR_AGENT
        and existing_article
        and not is_placeholder(existing_article)
        and not allow_agent_downgrade
    ):
        raise RuntimeError(
            f"{ref}: refusing to downgrade completed agent draft to pending without explicit upstream retry"
        )
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(
        f"{PLACEHOLDER_MARKER}\n# 待创作 agent 创作\n\n请阅读同目录 prompt.md 与 3.compose/writing_pack.json 后创作正文并覆盖 draft.article.md。\n",
        encoding="utf-8",
    )
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {
            "ref": ref,
            "generator": GENERATOR_PENDING,
            "model": None,
            "citedSourcePaths": [],
            "coveredFacts": [],
            **({"downgradedFrom": "agent", "downgradeReason": downgrade_reason} if allow_agent_downgrade else {}),
        },
    )


def write_image_evidence_draft(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    selected_asset_ids: Sequence[str] | None = None,
    cited_source_paths: Sequence[str] | None = None,
) -> None:
    """图片作品的结构化草稿元数据；主动删除旧正文草稿，避免载体混用。"""

    article = draft_article_path(task_id, batch_id, ref)
    article.parent.mkdir(parents=True, exist_ok=True)
    if article.exists():
        article.unlink()
    existing_meta = read_draft_meta(task_id, batch_id, ref) or {}
    created_at = _normalized_iso(existing_meta.get("createdAt")) or _now_iso()
    now_iso = _now_iso()
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {
            "ref": ref,
            "generator": GENERATOR_IMAGE_EVIDENCE,
            "model": None,
            "citedSourcePaths": list(cited_source_paths or []),
            "coveredFacts": [],
            "selectedAssetIds": list(selected_asset_ids or []),
            "articleContract": "structured_image_only",
            "createdAt": created_at,
            "updatedAt": now_iso,
        },
    )


def read_draft_article(task_id: str, batch_id: str, ref: str) -> str | None:
    path = draft_article_path(task_id, batch_id, ref)
    return path.read_text(encoding="utf-8") if path.exists() else None


def is_placeholder(article: str | None) -> bool:
    return article is None or PLACEHOLDER_MARKER in article


def draft_asset_reference_issues(article: str | None, pack: dict[str, Any] | None) -> list[str]:
    if not article:
        return []
    if str((pack or {}).get("publishMediaMode") or "").strip() == "text_only":
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


def _source_bundle_sha256(cited_source_paths: Sequence[str], *, base_dir: Path | None = None) -> str | None:
    if not cited_source_paths:
        return None
    bundle = []
    for raw in cited_source_paths:
        path = Path(str(raw))
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        if not path.is_file():
            continue
        bundle.append({"path": str(raw), "sha256": sha256_file(path)})
    if not bundle:
        return None
    return sha256_text(
        __import__("json").dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def compute_draft_provenance_facts(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    article_markdown: str,
    cited_source_paths: Sequence[str],
) -> dict[str, str | None]:
    prompt_digest = sha256_file(prompt_path(task_id, batch_id, ref)) if prompt_path(task_id, batch_id, ref).is_file() else None
    writing_pack_digest = (
        sha256_file(writing_pack_path(task_id, batch_id, ref)) if writing_pack_path(task_id, batch_id, ref).is_file() else None
    )
    return {
        "promptSha256": prompt_digest,
        "writingPackSha256": writing_pack_digest,
        "sourceBundleSha256": _source_bundle_sha256(cited_source_paths, base_dir=batch_root(task_id, batch_id)),
        "draftSha256": compute_document_sha256(article_markdown),
    }


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
    agent_run_id: str | None = None,
    agent_id: str | None = None,
    extracted_entities: Sequence[dict[str, Any]] | None = None,
    extracted_tags: Sequence[dict[str, Any]] | None = None,
    style_family: str | None = None,
    opening_strategy: str | None = None,
    creative_plan: dict[str, Any] | None = None,
    self_critique: dict[str, Any] | None = None,
) -> None:
    """创作 agent 创作正文写回（SOP 与测试 fixture 共用）。generator 固定为 agent。

    extracted_entities: 正文中挖掘出的专有实体，形如 [{"name":"洛绒牛场","type":"自然景观","evidenceRef":"..."}]，
    供 produce review 生成实体 sidecar / 关联实体主页。
    extracted_tags: 正文中命中的标签，形如 [{"label":"晨雾","dimensionId":"摄影"}]，供 review 生成 tag
    semantic mention（已发布标签→published 可点击；未发布→pending_review 进治理），与实体同链路回填 manifest。
    style_family / opening_strategy: agent 按原文体裁+证据自选的最终文风族与开篇策略 id，
    供 review 开篇门按所选 styleFamily 的 allowedOpenings markers 语义化校验，避免千篇一律开头。
    """
    article = draft_article_path(task_id, batch_id, ref)
    existing_meta = read_draft_meta(task_id, batch_id, ref) or {}
    existing_article = article.read_text(encoding="utf-8") if article.exists() else None
    created_at = _normalized_iso(existing_meta.get("createdAt"))
    if created_at is None and existing_article and not is_placeholder(existing_article):
        created_at = _file_mtime_iso(article)
    now_iso = _now_iso()
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(article_markdown, encoding="utf-8")
    facts = compute_draft_provenance_facts(
        task_id,
        batch_id,
        ref,
        article_markdown=article_markdown,
        cited_source_paths=cited_source_paths,
    )
    pack = read_writing_pack(task_id, batch_id, ref) or {}
    creator_assignment = creator_from_payload(pack)
    creative = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), dict) else {}
    reader_promise = str(creative.get("readerPromise") or "兑现写作任务承诺").strip()
    title_match = re.search(r"(?m)^#\s+(.+)$", article_markdown or "")
    selected_title = title_match.group(1).strip() if title_match else str(pack.get("title") or ref)
    if creative_plan is None:
        from _common.creative_brief import default_creative_plan_meta

        creative_plan = default_creative_plan_meta(
            reader_promise=reader_promise,
            selected_title=selected_title,
            style_family=style_family,
            opening_strategy=opening_strategy,
        )
    if self_critique is None:
        from _common.creative_brief import default_self_critique

        self_critique = default_self_critique(reader_promise)
    write_json(
        draft_meta_path(task_id, batch_id, ref),
        {
            "ref": ref,
            "generator": GENERATOR_AGENT,
            "model": model,
            "sessionTrace": session_trace,
            "agentRunId": agent_run_id or existing_meta.get("agentRunId"),
            "agentId": agent_id or existing_meta.get("agentId"),
            "styleFamily": style_family,
            "openingStrategy": opening_strategy,
            "citedSourcePaths": list(cited_source_paths),
            "coveredFacts": list(covered_facts),
            "extractedEntities": list(extracted_entities or []),
            "extractedTags": list(extracted_tags or []),
            **creator_assignment,
            "creativePlan": creative_plan,
            "selfCritique": self_critique,
            "promptSha256": facts.get("promptSha256"),
            "writingPackSha256": facts.get("writingPackSha256"),
            "sourceBundleSha256": facts.get("sourceBundleSha256"),
            "draftSha256": facts.get("draftSha256"),
            "createdAt": created_at or now_iso,
            "updatedAt": now_iso,
        },
    )
