"""Asset admission and exclusive-claim helpers for content planning."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.controller.content_plan_prep import (
    _assess_content_plan_publish_image,
)
from content.execution.support import ExecutionContext, read_json, relative_execution_ref


def asset_rows(source_dir: Path) -> list[dict[str, Any]]:
    index_path = source_dir / "assets" / "index.json"
    if not index_path.is_file():
        return []
    try:
        rows = read_json(index_path).get("assets") or []
    except (OSError, ValueError, TypeError):
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def asset_ref(
    ctx: ExecutionContext,
    source_dir: Path,
    row: Mapping[str, Any],
) -> str:
    file_name = str(row.get("fileName") or "").strip()
    if not file_name:
        return ""
    return relative_execution_ref(
        source_dir / "assets" / file_name,
        ctx.execution_id,
    )


def asset_sha(row: Mapping[str, Any]) -> str:
    return str(row.get("sha256") or "").removeprefix("sha256:").strip().lower()


def source_ref(ctx: ExecutionContext, source_dir: Path) -> str:
    return relative_execution_ref(source_dir / "source.md", ctx.execution_id)


def image_claims(candidate: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    return (
        [str(candidate.get("assetRef") or "").strip()],
        [str(candidate.get("assetSha") or "").strip()],
        [str(candidate.get("collectionId") or "").strip()],
    )


def article_asset_claims(
    ctx: ExecutionContext,
    root: Path,
    candidate: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Reserve every publishable image bound to one article source unit."""
    source_dir = candidate.get("sourceDir")
    if not isinstance(source_dir, Path):
        return [], [], [], []
    refs: list[str] = []
    shas: list[str] = []
    collection_ids: list[str] = []
    for row in candidate.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        ref = asset_ref(ctx, source_dir, row)
        sha = asset_sha(row)
        collection_id = str(row.get("sourceCollectionId") or "").strip()
        if not ref:
            continue
        asset_path = root / ref
        if not asset_path.is_file():
            continue
        verdict = _assess_content_plan_publish_image(asset_path, ctx)
        if verdict.blocks_image_publish:
            continue
        refs.append(ref)
        if sha:
            shas.append(sha)
        if collection_id:
            collection_ids.append(collection_id)
    if len(refs) < 2:
        return [], [], [], []
    return refs, shas, collection_ids, refs


def claims_conflict(
    refs: list[str],
    shas: list[str],
    collections: list[str],
    *,
    claimed_refs: set[str],
    claimed_shas: set[str],
    claimed_collections: set[str],
) -> bool:
    return (
        any(ref in claimed_refs for ref in refs if ref)
        or any(sha in claimed_shas for sha in shas if sha)
        or any(cid in claimed_collections for cid in collections if cid)
    )


def claim(
    refs: list[str],
    shas: list[str],
    collections: list[str],
    *,
    claimed_refs: set[str],
    claimed_shas: set[str],
    claimed_collections: set[str],
) -> None:
    claimed_refs.update(ref for ref in refs if ref)
    claimed_shas.update(sha for sha in shas if sha)
    claimed_collections.update(cid for cid in collections if cid)
