"""Draft IO 规范：创作 agent 创作正文的落盘契约（对象优先，规格 §2.4/§15.1）。

post 过程产物挂在内容对象目录下（经 `content.post.object_index` 路由解析）：
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

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from core.article_package import compute_document_sha256, sha256_file, sha256_text
from governance.creators.assignment import creator_from_payload
from core.io import read_json, write_json
from core.paths import STAGE_COMPOSE, STAGE_DRAFT, execution_root

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


def _object_stage_dir(execution_id: str, ref: str, stage: str) -> Path | None:
    from content.post.object_index import content_coords, content_object_stage_dir

    if content_coords(execution_id, ref):
        return content_object_stage_dir(execution_id, ref, stage)
    return None


def draft_package_dir(execution_id: str, ref: str) -> Path:
    """草稿包（prompt/draft.article/draft_meta/assets）目录：对象 4.draft。"""
    obj = _object_stage_dir(execution_id, ref, STAGE_DRAFT)
    if obj is None:
        raise KeyError(f"draft package not registered for ref={ref!r} (task={execution_id} batch={execution_id})")
    return obj


def brief_package_dir(execution_id: str, ref: str) -> Path:
    """创作契约（writing_pack）目录：对象 3.compose。"""
    obj = _object_stage_dir(execution_id, ref, STAGE_COMPOSE)
    if obj is None:
        raise KeyError(f"brief package not registered for ref={ref!r} (task={execution_id} batch={execution_id})")
    return obj


def draft_assets_dir(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / "assets"


def writing_pack_path(execution_id: str, ref: str) -> Path:
    return brief_package_dir(execution_id, ref) / "writing_pack.json"


def prompt_path(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / "prompt.md"


def prompt_snapshot_path(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / "prompt_snapshot.json"


def draft_article_path(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / DRAFT_ARTICLE_FILE


def draft_meta_path(execution_id: str, ref: str) -> Path:
    return draft_package_dir(execution_id, ref) / "draft_meta.json"


def iter_draft_articles(execution_id: str) -> list[tuple[str, Path]]:
    """(ref, draft.article.md) 列表：仅枚举已登记的对象布局。"""
    from content.post.object_index import iter_content_refs

    refs = iter_content_refs(execution_id)
    out: list[tuple[str, Path]] = []
    for ref in refs:
        path = draft_article_path(execution_id, ref)
        if path.exists():
            out.append((ref, path))
    return out


def write_writing_pack(execution_id: str, ref: str, pack: dict[str, Any]) -> Path:
    path = writing_pack_path(execution_id, ref)
    write_json(path, pack)
    return path


def read_writing_pack(execution_id: str, ref: str) -> dict[str, Any] | None:
    path = writing_pack_path(execution_id, ref)
    return read_json(path) if path.exists() else None


def write_prompt(
    execution_id: str,
    ref: str,
    prompt_md: str,
    *,
    template_family: str = "",
    variables: dict[str, Any] | None = None,
    output_refs: Sequence[str] = (),
) -> Path:
    from content.execution.runtime_contract import canonical_sha256, stage_execution_context
    from content.execution.prompt_snapshot import write_prompt_snapshot

    path = prompt_path(execution_id, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt_md, encoding="utf-8")
    pack = read_writing_pack(execution_id, ref)
    carrier = str(pack.get("carrier") or "").lower()
    resolved_family = template_family or (
        "image_curation" if carrier == "image" else "article_author"
    )
    resolved_outputs = list(output_refs) or (
        [
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ]
        if carrier == "image"
        else [
            "4.draft/draft.article.md",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ]
    )
    execution_id = stage_execution_context(execution_id)["executionId"]
    run_id = "author_" + canonical_sha256(
        {"executionId": execution_id, "objectRef": ref}
    ).removeprefix("sha256:")[:20]
    write_prompt_snapshot(
        prompt_snapshot_path(execution_id, ref),
        execution_id=execution_id,
        stage="4.draft",
        template_family=resolved_family,
        variables=variables or {"writingPack": pack},
        rendered_prompt=prompt_md,
        provider=os.environ.get("QWQ_AUTHOR_PROVIDER", "local_cursor_sdk"),
        model=os.environ.get("QWQ_AUTHOR_MODEL", "composer"),
        run_id=run_id,
        output_refs=resolved_outputs,
    )
    return path


def write_placeholder_draft(
    execution_id: str,
    ref: str,
    *,
    allow_agent_downgrade: bool = False,
    downgrade_reason: str = "",
) -> None:
    """prepare 阶段写占位正文 + pending meta，待创作 agent 覆盖。

    A completed agent draft is production evidence.  It may only be reset by an
    explicit upstream retry/rebuild path, never by an incidental prepare rerun.
    """
    article = draft_article_path(execution_id, ref)
    existing_meta = read_draft_meta(execution_id, ref) or {}
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
        draft_meta_path(execution_id, ref),
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
    execution_id: str,
    ref: str,
    *,
    selected_asset_ids: Sequence[str] | None = None,
    cited_source_paths: Sequence[str] | None = None,
) -> None:
    """图片作品的结构化草稿元数据；主动删除旧正文草稿，避免载体混用。"""

    article = draft_article_path(execution_id, ref)
    article.parent.mkdir(parents=True, exist_ok=True)
    if article.exists():
        article.unlink()
    existing_meta = read_draft_meta(execution_id, ref) or {}
    created_at = _normalized_iso(existing_meta.get("createdAt")) or _now_iso()
    now_iso = _now_iso()
    write_json(
        draft_meta_path(execution_id, ref),
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


def read_draft_article(execution_id: str, ref: str) -> str | None:
    path = draft_article_path(execution_id, ref)
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


def read_draft_meta(execution_id: str, ref: str) -> dict[str, Any] | None:
    path = draft_meta_path(execution_id, ref)
    return read_json(path) if path.exists() else None


def repair_creative_meta(execution_id: str, ref: str) -> dict[str, Any] | None:
    """Complete missing creativePlan/selfCritique on an authored agent draft.

    The structured creative-plan contract is a *metadata* artifact, not article
    body: it is completed deterministically from the locked creativeBrief so the
    review gate has a reliable structured input instead of hard-blocking drafts
    whose body already passes every body-level gate. Only authored agent drafts
    are touched (body + generator are never modified); image carriers and
    opted-out briefs are no-ops. Returns the effective (possibly repaired) meta.
    """
    from core.creative_brief import complete_creative_meta

    meta = read_draft_meta(execution_id, ref)
    if str((meta or {}).get("generator") or "") != GENERATOR_AGENT:
        return meta
    pack = read_writing_pack(execution_id, ref) or {}
    article = read_draft_article(execution_id, ref)
    if is_placeholder(article):
        return meta
    completed, changed = complete_creative_meta(meta, pack, body=str(article or ""))
    if not changed:
        return meta
    completed["updatedAt"] = _now_iso()
    write_json(draft_meta_path(execution_id, ref), completed)
    return completed


def _source_bundle_sha256(cited_source_paths: Sequence[str], *, base_dir: Path | None = None) -> str | None:
    if not cited_source_paths:
        return None
    bundle = []
    for raw in cited_source_paths:
        raw_text = str(raw)
        path = Path(raw_text)
        candidates = [path]
        if not path.is_absolute() and base_dir is not None:
            candidates.append(base_dir / path)
        resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
        if resolved is None:
            continue
        bundle.append({"path": raw_text, "sha256": sha256_file(resolved)})
    if not bundle:
        return None
    return sha256_text(
        __import__("json").dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def compute_draft_provenance_facts(
    execution_id: str,
    ref: str,
    *,
    article_markdown: str,
    cited_source_paths: Sequence[str],
) -> dict[str, str | None]:
    prompt_digest = sha256_file(prompt_path(execution_id, ref)) if prompt_path(execution_id, ref).is_file() else None
    writing_pack_digest = (
        sha256_file(writing_pack_path(execution_id, ref)) if writing_pack_path(execution_id, ref).is_file() else None
    )
    return {
        "promptSha256": prompt_digest,
        "writingPackSha256": writing_pack_digest,
        "sourceBundleSha256": _source_bundle_sha256(cited_source_paths, base_dir=execution_root(execution_id)),
        "draftSha256": compute_document_sha256(article_markdown),
    }


def write_agent_draft(
    execution_id: str,
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
    """创作 agent 创作正文写回（模板与测试 fixture 共用）。generator 固定为 agent。

    extracted_entities: 正文中挖掘出的专有实体，形如 [{"name":"洛绒牛场","type":"自然景观","evidenceRef":"..."}]，
    供 post review 生成实体 sidecar / 关联实体主页。
    extracted_tags: 正文中命中的标签，形如 [{"label":"晨雾","dimensionId":"摄影"}]，供 review 生成 tag
    semantic mention（已发布标签→published 可点击；未发布→pending_review 进治理），与实体同链路回填 manifest。
    style_family / opening_strategy: agent 按原文体裁+证据自选的最终文风族与开篇策略 id，
    供 review 开篇门按所选 styleFamily 的 allowedOpenings markers 语义化校验，避免千篇一律开头。
    """
    article = draft_article_path(execution_id, ref)
    existing_meta = read_draft_meta(execution_id, ref) or {}
    existing_article = article.read_text(encoding="utf-8") if article.exists() else None
    created_at = _normalized_iso(existing_meta.get("createdAt"))
    if created_at is None and existing_article and not is_placeholder(existing_article):
        created_at = _file_mtime_iso(article)
    now_iso = _now_iso()
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(article_markdown, encoding="utf-8")
    facts = compute_draft_provenance_facts(
        execution_id,
        ref,
        article_markdown=article_markdown,
        cited_source_paths=cited_source_paths,
    )
    pack = read_writing_pack(execution_id, ref) or {}
    creator_assignment = creator_from_payload(pack)
    creative = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), dict) else {}
    reader_promise = str(creative.get("readerPromise") or "兑现写作任务承诺").strip()
    title_match = re.search(r"(?m)^#\s+(.+)$", article_markdown or "")
    selected_title = title_match.group(1).strip() if title_match else str(pack.get("title") or ref)
    if creative_plan is None:
        from core.creative_brief import default_creative_plan_meta

        creative_plan = default_creative_plan_meta(
            reader_promise=reader_promise,
            selected_title=selected_title,
            style_family=style_family,
            opening_strategy=opening_strategy,
        )
    if self_critique is None:
        from core.creative_brief import default_self_critique

        self_critique = default_self_critique(reader_promise)
    write_json(
        draft_meta_path(execution_id, ref),
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
