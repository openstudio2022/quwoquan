"""Source-unit resolution helpers for canonical post transactions."""

from __future__ import annotations

import shutil
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


def project_object_sources(
    *, execution_root: Path, source_object: Path, object_root: Path,
    manifest: Mapping[str, Any], source_assets: Mapping[str, dict[str, Any]],
    canonical_assets: list[dict[str, Any]], rights_rows: list[dict[str, Any]],
) -> list[str]:
    """只拷贝采用来源的实际证据；生成元数据不冒充原页或许可证明。"""
    from content.release.canonical.object_transaction_contract import _digest_file, _write_json
    from core.schema import assert_valid

    selected: dict[str, dict[str, Any]] = {}
    refs_doc = _read_json(source_object / "1.download/source_refs.json")
    for raw in refs_doc.get("sources") or []:
        ref = str(raw.get("metaRef") or raw.get("sourceRef") or raw.get("sourceAssetRef") or "")
        rel = _safe_rel(ref, label="source unit ref")
        if len(rel.parts) < 3 or rel.parts[0] != "sources":
            raise ObjectTransactionError("DATA.PUBLISH.SOURCE_REF_INVALID")
        selected.setdefault(rel.parts[1], dict(raw))
    for asset in canonical_assets:
        for ref in asset.get("sourceAssetRefs") or []:
            rel = _safe_rel(str(ref), label="sourceAssetRef")
            selected.setdefault(rel.parts[1], {})
    if not selected:
        raise ObjectTransactionError("DATA.PUBLISH.SOURCE_EVIDENCE_MISSING")
    rights_by_id = {str(row["assetId"]): row for row in rights_rows}
    refs: list[str] = []
    for unit, selected_row in sorted(selected.items()):
        unit_root = execution_root / "sources" / unit
        meta = _read_json(unit_root / "meta.json")
        url = https_source(selected_row.get("sourceUrl"), meta.get("canonicalUrl"), meta.get("url"))
        if not url:
            raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_URL_MISSING: {unit}")
        source_ref = f"sources/{unit}/source.json"
        target = object_root / "sources" / unit
        evidence: list[dict[str, Any]] = []
        originals = [path for path in sorted(unit_root.glob("snapshot.*")) if path.is_file()]
        excerpt = unit_root / "source.md"
        if excerpt.is_file():
            originals.append(excerpt)
        if not originals:
            raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_EVIDENCE_MISSING: {unit}")
        for index, original in enumerate(originals):
            if original.is_symlink() or original.stat().st_size < 1:
                raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_EVIDENCE_INVALID: {original}")
            digest = _digest_file(original)
            expected = meta.get("cleanSha256" if original.name == "source.md" else "rawSha256")
            if expected and digest != expected:
                raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_EVIDENCE_DRIFT: {original}")
            filename = f"evidence{'-' + str(index + 1) if index else ''}{original.suffix}"
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target / filename)
            evidence.append({"path": filename, "sha256": digest, "bytes": original.stat().st_size,
                             "kind": "source_excerpt" if original.name == "source.md" else "source_snapshot"})
        adopted: list[dict[str, Any]] = []
        for asset in canonical_assets:
            matching = [ref for ref in asset.get("sourceAssetRefs") or [] if str(ref).startswith(f"sources/{unit}/")]
            if not matching:
                continue
            asset.setdefault("sourceRefs", []).append(source_ref)
            rights = rights_by_id[str(asset["assetId"])]
            facts = {key: value for key, value in rights.items() if key not in {"snapshot", "asset", "pageRevision", "snapshotUrl"}}
            facts.update(sha256=asset["sha256"], bytes=asset["bytes"], mimeType=asset["mimeType"])
            for ref in matching:
                adopted.append({**facts, "sourceAssetRef": ref, "sourceAsset": dict(source_assets[ref])})
        fetched_at = str(meta.get("fetchedAt") or next((row.get("fetchedAt") for row in adopted if row.get("fetchedAt")), ""))
        document = {"schema": "quwoquan_data.publish_source", "sourceId": unit, "sourceUrl": url,
                    "sourceUseMode": meta.get("sourceUseMode"), "fetchedAt": fetched_at,
                    "metadata": dict(meta), "assets": adopted, "evidence": evidence}
        if isinstance(meta.get("sourceAttribution"), Mapping):
            document["sourceAttribution"] = dict(meta["sourceAttribution"])
        assert_valid(document, "publish", "source")
        _write_json(target / "source.json", document)
        refs.append(source_ref)
    return refs


def read_object_sources(object_root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """发布态只读唯一新 schema，并验证真正随体证据。"""
    from content.release.canonical.object_transaction_contract import _digest_file
    from core.schema import assert_valid

    refs = manifest.get("sourceRefs")
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
        raise ObjectTransactionError("DATA.PUBLISH.SOURCE_REF_INVALID")
    result = []
    for ref in refs:
        rel = _safe_rel(str(ref), label="manifest.sourceRefs")
        if len(rel.parts) != 3 or rel.parts[0] != "sources" or rel.name != "source.json":
            raise ObjectTransactionError("DATA.PUBLISH.SOURCE_REF_INVALID")
        source = object_root / rel
        if source.is_symlink() or any(p.is_symlink() for p in (source.parent, source.parent.parent)):
            raise ObjectTransactionError("DATA.PUBLISH.SOURCE_EVIDENCE_INVALID")
        document = _read_json(source)
        assert_valid(document, "publish", "source")
        for row in document["evidence"]:
            path = source.parent / _safe_rel(row["path"], label="source.evidence.path")
            if not path.is_file() or path.is_symlink():
                raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_EVIDENCE_MISSING: {ref}")
            if _digest_file(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
                raise ObjectTransactionError(f"DATA.PUBLISH.SOURCE_EVIDENCE_DRIFT: {ref}")
        result.append({**document, "ref": ref})
    for asset in manifest.get("assets") or []:
        if not asset.get("sourceRefs") or not set(asset["sourceRefs"]).issubset(refs):
            raise ObjectTransactionError("DATA.PUBLISH.ASSET_SOURCE_REF_INVALID")
    return result


__all__ = [
    "asset_source_use_mode",
    "https_source",
    "source_catalog",
    "source_meta_for_ref",
]
