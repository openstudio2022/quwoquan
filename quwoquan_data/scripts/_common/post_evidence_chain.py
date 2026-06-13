"""内容对象证据链 helper：`1.download/source_refs.json` + `5.review/finalization_report.json`。

目标：
- 让 post 对象自持「底稿/引证来源」索引与必要原文镜像，避免只在实体对象里有 source unit。
- 明确 `article.md` 是如何从 `4.draft/draft.article.md` 物化到最终成品的。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from _common.article_package import compute_document_sha256, sha256_file, sha256_text
from _common.io import read_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, batch_root, relative_batch_ref

SOURCE_REFS_SCHEMA = "quwoquan_data.source_refs"
FINALIZATION_REPORT_SCHEMA = "quwoquan_data.finalization_report"

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.S)


def _normalize_text(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _normalized_body(text: str) -> str:
    return _normalize_text(text).strip() + "\n"


def _split_frontmatter(markdown: str) -> tuple[str, str]:
    text = _normalize_text(markdown)
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return text[: match.end()], text[match.end() :]


def _stable_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalized_ref(task_id: str, batch_id: str, raw: str, resolved: Path | None = None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    batch_prefix = f"batches/{batch_id}/"
    if text.startswith(batch_prefix):
        return text[len(batch_prefix) :]
    normalized = text.replace("\\", "/")
    marker = f"/batches/{batch_id}/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    if resolved is not None:
        try:
            resolved.relative_to(batch_root(task_id, batch_id).resolve())
        except ValueError:
            return normalized
        return relative_batch_ref(resolved, task_id, batch_id)
    return normalized.lstrip("./")


def _resolve_source_path(task_id: str, batch_id: str, raw: str) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidate = Path(text)
    candidates: list[Path] = []
    if candidate.is_absolute():
        candidates.append(candidate)
    else:
        normalized = text.lstrip("./")
        candidates.append(batch_root(task_id, batch_id) / normalized)
        if normalized.startswith("quwoquan_data/runtime/"):
            candidates.append(DATA_ROOT.parent / normalized)
        candidates.append(RUNTIME_ROOT / normalized)
    for path in candidates:
        try:
            if path.is_file():
                return path.resolve()
        except OSError:
            continue
    return None


def _relative_ref_or_none(task_id: str, batch_id: str, path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return _normalized_ref(task_id, batch_id, str(path), path.resolve())


def _object_ref_from_source_ref(source_ref: str, source_unit_ref: str) -> str | None:
    for value in (source_ref, source_unit_ref):
        marker = "/1.download/sources/"
        if marker in value:
            return value.split(marker, 1)[0]
    return None


def _source_roles(
    source_ref: str,
    *,
    base_source_ref: str,
    cited_source_refs: set[str],
    source_paths: set[str],
) -> list[str]:
    roles: list[str] = []
    if source_ref == base_source_ref:
        roles.append("base")
    if source_ref in cited_source_refs:
        roles.append("cited")
    if source_ref in source_paths:
        roles.append("evidence")
    return roles or ["evidence"]


def _read_json_or_none(path: Path | None) -> Any | None:
    if path is None or not path.is_file():
        return None
    return read_json(path)


def _build_source_entry(
    task_id: str,
    batch_id: str,
    *,
    raw_ref: str,
    normalized_ref: str,
    roles: list[str],
) -> dict[str, Any]:
    resolved = _resolve_source_path(task_id, batch_id, raw_ref)
    if resolved is None:
        raise FileNotFoundError(f"source ref missing: {raw_ref}")
    unit_dir = resolved.parent
    meta_path = unit_dir / "meta.json"
    quality_path = unit_dir / "source.quality.json"
    clean_path = unit_dir / "source.clean.md"
    source_unit_ref = _normalized_ref(task_id, batch_id, str(unit_dir), unit_dir.resolve())
    source_markdown = resolved.read_text(encoding="utf-8")
    meta = _read_json_or_none(meta_path)
    quality = _read_json_or_none(quality_path)
    entry: dict[str, Any] = {
        "sourceRef": normalized_ref,
        "sourceUnitRef": source_unit_ref,
        "objectRef": _object_ref_from_source_ref(normalized_ref, source_unit_ref),
        "metaRef": _relative_ref_or_none(task_id, batch_id, meta_path),
        "qualityRef": _relative_ref_or_none(task_id, batch_id, quality_path),
        "cleanSourceRef": _relative_ref_or_none(task_id, batch_id, clean_path),
        "roles": roles,
        "sourceMarkdownSha256": sha256_text(source_markdown),
        "sourceMarkdown": source_markdown,
    }
    if clean_path.is_file():
        clean_markdown = clean_path.read_text(encoding="utf-8")
        entry["sourceCleanMarkdownSha256"] = sha256_text(clean_markdown)
        entry["sourceCleanMarkdown"] = clean_markdown
    if isinstance(meta, dict):
        entry["sourceMeta"] = meta
        entry["sourceKind"] = str(meta.get("sourceKind") or meta.get("platform") or unit_dir.name)
        entry["platform"] = str(meta.get("platform") or "")
        entry["title"] = str(meta.get("title") or "")
        entry["url"] = str(meta.get("url") or "")
    else:
        entry["sourceKind"] = unit_dir.name
        entry["platform"] = ""
        entry["title"] = ""
        entry["url"] = ""
    if isinstance(quality, dict):
        entry["sourceQuality"] = quality
    return entry


def build_source_refs_snapshot(
    task_id: str,
    batch_id: str,
    *,
    base_source_ref: str,
    cited_source_refs: Iterable[str],
    source_paths: Iterable[str],
) -> dict[str, Any]:
    """构造 post 对象 `1.download/source_refs.json`。

    兼顾两类诉求：
    - 索引：base/cited/sourcePaths 的相对路径与对应 source unit 回查入口。
    - 镜像：保留原始 `source.md`（以及可选 `source.clean.md`）与 digest，便于 draft/final 对比追责。
    """
    ordered_raw_refs: list[str] = []
    normalized_to_raw: dict[str, str] = {}
    normalized_to_resolved: dict[str, Path | None] = {}

    def normalize_from_raw(raw: str) -> str:
        resolved = _resolve_source_path(task_id, batch_id, raw)
        return _normalized_ref(task_id, batch_id, raw, resolved)

    def add_ref(raw: str) -> None:
        resolved = _resolve_source_path(task_id, batch_id, raw)
        normalized = _normalized_ref(task_id, batch_id, raw, resolved)
        if not normalized or normalized in normalized_to_raw:
            return
        ordered_raw_refs.append(normalized)
        normalized_to_raw[normalized] = str(raw or "")
        normalized_to_resolved[normalized] = resolved

    add_ref(base_source_ref)
    for raw in cited_source_refs:
        add_ref(str(raw))
    for raw in source_paths:
        add_ref(str(raw))

    normalized_base = normalize_from_raw(base_source_ref)
    normalized_cited = _stable_unique(
        normalize_from_raw(str(raw))
        for raw in cited_source_refs
    )
    normalized_source_paths = _stable_unique(
        normalize_from_raw(str(raw))
        for raw in source_paths
    )
    cited_set = set(normalized_cited)
    source_path_set = set(normalized_source_paths)

    sources: list[dict[str, Any]] = []
    for normalized_ref in ordered_raw_refs:
        sources.append(
            _build_source_entry(
                task_id,
                batch_id,
                raw_ref=normalized_to_raw[normalized_ref],
                normalized_ref=normalized_ref,
                roles=_source_roles(
                    normalized_ref,
                    base_source_ref=normalized_base,
                    cited_source_refs=cited_set,
                    source_paths=source_path_set,
                ),
            )
        )
    return {
        "schemaVersion": SOURCE_REFS_SCHEMA,
        "baseSourceRef": normalized_base or None,
        "citedSourceRefs": normalized_cited,
        "sourcePaths": normalized_source_paths,
        "sources": sources,
    }


def build_finalization_report(
    ref: str,
    *,
    draft_markdown: str,
    final_markdown: str,
    normalization_actions: Iterable[str],
    article_source: str,
    compose_snapshot_markdown: str | None = None,
    draft_ref: str = "4.draft/draft.article.md",
    final_ref: str = "article.md",
    compose_snapshot_ref: str | None = "5.review/compose.json",
) -> dict[str, Any]:
    draft_frontmatter, draft_body = _split_frontmatter(draft_markdown)
    final_frontmatter, final_body = _split_frontmatter(final_markdown)
    draft_frontmatter_normalized = _normalize_text(draft_frontmatter).strip()
    final_frontmatter_normalized = _normalize_text(final_frontmatter).strip()
    if not draft_frontmatter_normalized and final_frontmatter_normalized:
        # 仅 final 注入 frontmatter 时，正文比较应忽略这层包裹，避免误判 bodyChanged。
        draft_body_normalized = _normalized_body(draft_markdown)
    else:
        draft_body_normalized = _normalized_body(draft_body)
    final_body_normalized = _normalized_body(final_body)
    body_changed = draft_body_normalized != final_body_normalized
    frontmatter_changed = draft_frontmatter_normalized != final_frontmatter_normalized
    actions = _stable_unique(normalization_actions)
    compose_digest = compute_document_sha256(compose_snapshot_markdown) if compose_snapshot_markdown else None
    return {
        "schemaVersion": FINALIZATION_REPORT_SCHEMA,
        "ref": ref,
        "articleSource": article_source,
        "draftArticleRef": draft_ref,
        "finalArticleRef": final_ref,
        "composeSnapshotRef": compose_snapshot_ref if compose_snapshot_markdown is not None else None,
        "draftSha256": compute_document_sha256(draft_markdown),
        "finalSha256": compute_document_sha256(final_markdown),
        "draftBodySha256": sha256_text(draft_body_normalized),
        "finalBodySha256": sha256_text(final_body_normalized),
        "composeSnapshotSha256": compose_digest,
        "composeSnapshotMatchesDraft": (
            compose_digest == compute_document_sha256(draft_markdown) if compose_digest is not None else None
        ),
        "frontmatterInjected": not draft_frontmatter_normalized and bool(final_frontmatter_normalized),
        "frontmatterChanged": frontmatter_changed,
        "bodyChanged": body_changed,
        "frontmatterOnlyChange": frontmatter_changed and not body_changed,
        "normalizationActions": actions,
    }


__all__ = [
    "FINALIZATION_REPORT_SCHEMA",
    "SOURCE_REFS_SCHEMA",
    "build_finalization_report",
    "build_source_refs_snapshot",
]
