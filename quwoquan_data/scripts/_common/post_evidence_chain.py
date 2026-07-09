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
from _common.paths import RUNTIME_ROOT, batch_root, relative_batch_ref

SOURCE_REFS_SCHEMA = "quwoquan_data.source_refs/2"
SOURCE_REFS_SCHEMA_LEGACY = "quwoquan_data.source_refs"
FINALIZATION_REPORT_SCHEMA = "quwoquan_data.finalization_report"
# 单底稿零参考宪法：source_refs.json 仅登记唯一底稿来源单元，禁止内联原文镜像。
SOURCE_REFS_MAX_BYTES = 10 * 1024

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.S)
_TEXT_SOURCE_SUFFIXES = {".md", ".markdown", ".txt"}


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
    # 顶层批次目录名 = {intentLabel}-{taskHash}__{batch_id}（取自真实 batch 根，含任务消歧哈希）。
    batch_dir = batch_root(task_id, batch_id).name
    batch_prefix = f"batches/{batch_dir}/"
    if text.startswith(batch_prefix):
        return text[len(batch_prefix) :]
    normalized = text.replace("\\", "/")
    marker = f"/batches/{batch_dir}/"
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


def _is_text_source_file(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_SOURCE_SUFFIXES


def _build_base_source_entry(
    task_id: str,
    batch_id: str,
    *,
    raw_ref: str,
    normalized_ref: str,
) -> dict[str, Any]:
    """单底稿来源条目（slim）：只留回查入口 + sha256，禁止内联原文镜像。"""
    resolved = _resolve_source_path(task_id, batch_id, raw_ref)
    if resolved is None:
        raise FileNotFoundError(f"source ref missing: {raw_ref}")
    unit_dir = resolved.parent
    meta_path = unit_dir / "meta.json"
    clean_path = unit_dir / "source.clean.md"
    source_unit_ref = _normalized_ref(task_id, batch_id, str(unit_dir), unit_dir.resolve())
    entry: dict[str, Any] = {
        "sourceRef": normalized_ref,
        "sourceUnitRef": source_unit_ref,
        "role": "base",
        "sourceFileSha256": sha256_file(resolved),
        "metaRef": _relative_ref_or_none(task_id, batch_id, meta_path),
    }
    if clean_path.is_file() and _is_text_source_file(clean_path):
        entry["cleanSourceRef"] = _relative_ref_or_none(task_id, batch_id, clean_path)
        entry["sourceCleanMarkdownSha256"] = sha256_text(clean_path.read_text(encoding="utf-8"))
    return entry


def build_source_refs_snapshot(
    task_id: str,
    batch_id: str,
    *,
    base_source_ref: str,
) -> dict[str, Any]:
    """构造 post 对象 `1.download/source_refs.json`（单底稿零参考宪法 v2）。

    宪法约束：
    - 每个内容对象只有一个底稿来源单元（`sources` 长度恒为 1，`role == base`）。
    - 不再携带 `citedSourceRefs` / `sourcePaths` 等第二来源或全量索引。
    - 不内联 `sourceMarkdown` 原文镜像，只留 sha256，正文回查 source unit 文件。
    """
    resolved = _resolve_source_path(task_id, batch_id, base_source_ref)
    normalized_base = _normalized_ref(task_id, batch_id, base_source_ref, resolved)
    if not normalized_base:
        raise FileNotFoundError(
            f"source_refs requires a single baseSourceRef, got: {base_source_ref!r}"
        )
    entry = _build_base_source_entry(
        task_id,
        batch_id,
        raw_ref=base_source_ref,
        normalized_ref=normalized_base,
    )
    return {
        "schemaVersion": SOURCE_REFS_SCHEMA,
        "baseSourceRef": normalized_base,
        "sources": [entry],
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
    "SOURCE_REFS_SCHEMA_LEGACY",
    "SOURCE_REFS_MAX_BYTES",
    "build_finalization_report",
    "build_source_refs_snapshot",
]
