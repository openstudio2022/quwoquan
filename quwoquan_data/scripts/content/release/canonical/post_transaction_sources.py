"""Source-unit resolution helpers for canonical post transactions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)


def https_source(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text.startswith("https://"):
            return text
    return ""


def source_meta_for_ref(
    execution_root: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    candidates: list[Path] = []
    for field in ("metaRef", "sourceUnitRef", "sourceRef", "sourceAssetRef"):
        raw = str(source.get(field) or "").strip()
        if not raw or raw.startswith(("http://", "https://")):
            continue
        path = execution_root / _safe_rel(raw, label=f"source_refs.{field}")
        if field == "metaRef":
            candidates.append(path)
        elif field == "sourceUnitRef":
            candidates.append(path / "meta.json")
        elif field == "sourceAssetRef":
            candidates.append(path.parent.parent / "meta.json")
        else:
            candidates.append(path.parent / "meta.json")
    existing = tuple(dict.fromkeys(path for path in candidates if path.is_file()))
    if len(existing) != 1:
        raise ObjectTransactionError(
            "post source ref 必须唯一解析到 source unit meta.json："
            f"candidates={[path.relative_to(execution_root).as_posix() for path in existing]}"
        )
    meta = _read_json(existing[0])
    if not isinstance(meta, dict):
        raise ObjectTransactionError("post source unit meta 必须为 object")
    return meta


def source_catalog(
    execution_root: Path,
    post_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source_refs = _read_json(post_root / "1.download/source_refs.json")
    sources = source_refs.get("sources") if isinstance(source_refs, dict) else None
    if not isinstance(sources, list) or not sources:
        raise ObjectTransactionError("post source catalog requires non-empty source_refs")
    manifest_urls = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in manifest.get("sourceUrls") or []
            if str(item).strip()
        )
    )
    if not manifest_urls:
        raise ObjectTransactionError("post source catalog has no sourceUrls")
    rows: list[dict[str, str]] = []
    mode_by_url: dict[str, str] = {}
    for index, raw in enumerate(sources):
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError(
                f"post source_refs.sources[{index}] 必须为 object"
            )
        meta = source_meta_for_ref(execution_root, raw)
        mode = str(meta.get("sourceUseMode") or "").strip()
        if mode not in {
            "licensed_adaptation",
            "factual_reference_only",
            "rights_audit_only",
        }:
            raise ObjectTransactionError(
                f"post source unit sourceUseMode 非法或缺失：{mode or '<missing>'}"
            )
        source_url = https_source(
            raw.get("sourceUrl"),
            meta.get("canonicalUrl"),
            meta.get("url"),
        )
        if not source_url:
            raise ObjectTransactionError("post source unit 缺 HTTPS sourceUrl")
        previous = mode_by_url.setdefault(source_url, mode)
        if previous != mode:
            raise ObjectTransactionError(
                f"post sourceUrl 对应冲突 sourceUseMode：{source_url}"
            )
        if not any(row["sourceUrl"] == source_url for row in rows):
            rows.append({"sourceUrl": source_url, "sourceUseMode": mode})
    if set(manifest_urls) != set(mode_by_url):
        raise ObjectTransactionError(
            "post manifest sourceUrls 与 source unit 真值不一致："
            f"manifest={sorted(manifest_urls)} sourceUnits={sorted(mode_by_url)}"
        )
    declared_mode = str(manifest.get("sourceUseMode") or "").strip()
    if declared_mode:
        source_modes = set(mode_by_url.values())
        if source_modes != {declared_mode}:
            raise ObjectTransactionError(
                "post manifest sourceUseMode 与 source unit 真值冲突："
                f"manifest={declared_mode} sourceUnits={sorted(source_modes)}"
            )
    return {
        "schema": "quwoquan_data.source_catalog",
        "sources": rows,
    }


def asset_source_use_mode(
    execution_root: Path,
    raw: Mapping[str, Any],
) -> str:
    refs = [str(raw.get("sourceAssetRef") or "").strip()]
    refs.extend(str(item).strip() for item in raw.get("sourceAssetRefs") or [])
    refs = [ref for ref in refs if ref]
    if not refs:
        raise ObjectTransactionError(
            "post asset 缺 sourceAssetRef，无法绑定 source unit sourceUseMode"
        )
    modes: set[str] = set()
    for ref in refs:
        meta = source_meta_for_ref(execution_root, {"sourceAssetRef": ref})
        mode = str(meta.get("sourceUseMode") or "").strip()
        if mode not in {
            "licensed_adaptation",
            "factual_reference_only",
            "rights_audit_only",
        }:
            raise ObjectTransactionError(
                f"post asset source unit sourceUseMode 非法或缺失：{mode or '<missing>'}"
            )
        modes.add(mode)
    if len(modes) != 1:
        raise ObjectTransactionError(
            "post asset 必须唯一绑定 source unit sourceUseMode："
            f"refs={refs} modes={sorted(modes)}"
        )
    return next(iter(modes))


__all__ = [
    "asset_source_use_mode",
    "https_source",
    "source_catalog",
    "source_meta_for_ref",
]
