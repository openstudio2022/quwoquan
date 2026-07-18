"""Merkle 前置校验下的稳定单对象发布事务。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.tree_integrity import tree_integrity_stats
from core.schema import assert_valid
from core.release_layout import attestation_root, payload_digest, payload_file, payload_root
from core.media_asset_url import build_release_media_manifest
from content.release.canonical.object_transaction_contract import (
    PACKAGE_SCHEMA,
    DRY_RUN_SCHEMA,
    APPLY_SCHEMA,
    ROLLBACK_SCHEMA,
    LAYOUT_SCHEMA,
    RELEASE_SCHEMA,
    REQUIRED_SOURCE_POLICY,
    ALLOWED_OBJECT_KINDS,
    ALLOWED_CANONICAL_ROOTS,
    EXPECTED_OBJECT_SCHEMAS,
    ObjectTransactionError,
    assert_environment_neutral,
    _now,
    _json_bytes,
    _digest_bytes,
    _digest_file,
    _execution_id,
    _read_json,
    _write_json,
    _safe_id,
    _safe_rel,
    _files,
    _copy_tree,
    _tree_digest,
    _tag_exists,
    collect_canonical_tag_refs,
    refresh_canonical_tag_snapshots,
    _collect_object_keys,
    _object_json_keys,
    _review_binding,
    _rights_binding,
    _closure_digest,
    _verify_package,
)

def _release_entity_tag_refs(*, publish_root: Path, entity_refs: set[str]) -> list[str]:
    refs: set[str] = set()
    for ref in sorted(entity_refs):
        path = publish_root / "entities" / _safe_rel(ref, label="entityRef") / "tag.refs.json"
        if not path.is_file():
            raise ObjectTransactionError(f"canonical entity 缺 tag.refs.json：{ref}")
        payload = _read_json(path)
        raw_refs = payload.get("tagRefs")
        if not isinstance(raw_refs, list):
            raise ObjectTransactionError(f"canonical entity tagRefs 必须为 array：{ref}")
        refs.update(item.strip() for item in raw_refs if isinstance(item, str) and item.strip())
    return sorted(refs)












































def _image_dimensions(path: Path) -> tuple[int, int, str]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
            mime = str(Image.MIME.get(image.format or "") or "")
    except Exception as exc:  # noqa: BLE001
        raise ObjectTransactionError(f"发布图片不可解析：{path}: {exc}") from exc
    if width <= 0 or height <= 0 or not mime.startswith("image/"):
        raise ObjectTransactionError(f"发布图片缺有效尺寸或 MIME：{path}")
    return width, height, mime


def _safe_asset_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ObjectTransactionError("manifest asset 缺 assetId")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def build_entity_object_transaction_package(
    *,
    execution_root: Path,
    object_ref: str,
    transaction_id: str,
    package_root: Path,
) -> dict[str, Any]:
    """Build one production transaction package from an approved execution entity.

    The execution work package remains the only process-evidence root.  This builder
    projects one approved entity into a content-addressed, rights-bound transaction
    input without copying runtime stages into canonical content.release.canonical.
    """
    manifest_path = execution_root / "execution_manifest.json"
    execution_manifest = _read_json(manifest_path)
    execution_id = _execution_id(str(execution_manifest.get("executionId") or ""))
    if execution_root.name != execution_id:
        raise ObjectTransactionError("execution root 与 executionId 不一致")
    rel = _safe_rel(object_ref.removeprefix("/entity/"), label="objectRef")
    if len(rel.parts) < 3:
        raise ObjectTransactionError("entity objectRef 必须包含 domain/type/name")
    object_source = execution_root / "entities" / rel
    for required in ("_entity.json", "manifest.json", "page.md"):
        if not (object_source / required).is_file():
            raise ObjectTransactionError(f"execution entity 缺 {required}: {object_source}")
    source_manifest = _read_json(object_source / "manifest.json")
    entity = _read_json(object_source / "_entity.json")
    canonical_ref = rel.as_posix()
    if str(entity.get("entityRef") or "").removeprefix("/entity/") != canonical_ref:
        raise ObjectTransactionError("entityRef 与对象路径不一致")
    attestation_source = object_source / "5.review/attestation.json"
    evidence_index_source = object_source / "5.review/evidence_index.json"
    attestation = _read_json(attestation_source)
    if attestation.get("decision") != "approved":
        raise ObjectTransactionError("对象未 review-approved")
    for key in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        if str((attestation.get(key) or {}).get("status") or "") != "passed":
            raise ObjectTransactionError(f"review 前置未通过：{key}")

    expected_transaction_id = (
        f"{execution_id}--entity-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    transaction_id = _safe_id(transaction_id, label="transactionId")
    if transaction_id != expected_transaction_id:
        raise ObjectTransactionError(
            "transactionId 必须由 executionId 与 objectRef 稳定派生："
            f"expected={expected_transaction_id}"
        )
    if package_root.exists():
        existing = _read_json(package_root / "object_transaction_package.json")
        if (
            existing.get("transactionId") == transaction_id
            and existing.get("executionId") == execution_id
        ):
            return existing
        raise ObjectTransactionError(f"对象事务包已存在且输入不一致：{package_root}")

    package_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{package_root.name}.", dir=package_root.parent))
    try:
        object_root = staging / "object"
        (object_root / "rights_snapshots").mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_source / "_entity.json", object_root / "_entity.json")
        shutil.copy2(object_source / "page.md", object_root / "page.md")
        source_catalog_ref = Path("source_catalog.json")
        source_catalog_source = object_source / "evidence/source_catalog.json"
        if not source_catalog_source.is_file():
            raise ObjectTransactionError("entity 缺 source catalog")
        shutil.copy2(source_catalog_source, object_root / source_catalog_ref)
        shutil.copy2(attestation_source, object_root / "attestation.json")
        shutil.copy2(evidence_index_source, object_root / "evidence_index.json")

        source_assets: dict[str, dict[str, Any]] = {}
        for index_path in sorted((execution_root / "sources").glob("*/assets/index.json")):
            for row in (_read_json(index_path).get("assets") or []):
                if isinstance(row, dict) and str(row.get("sourceAssetId") or ""):
                    source_assets[str(row["sourceAssetId"])] = row

        cas_rows: list[dict[str, Any]] = []
        asset_refs: list[dict[str, Any]] = []
        rights_rows: list[dict[str, Any]] = []
        canonical_assets: list[dict[str, Any]] = []
        for raw in source_manifest.get("assets") or []:
            if not isinstance(raw, dict):
                raise ObjectTransactionError("manifest.assets item 必须为 object")
            file_name = str(raw.get("fileName") or "").strip()
            asset_source = object_source / "assets" / file_name
            if not file_name or not asset_source.is_file():
                raise ObjectTransactionError(f"manifest asset 不存在：{file_name or '<empty>'}")
            digest = _digest_file(asset_source)
            hex_digest = digest.removeprefix("sha256:")
            suffix = asset_source.suffix.lower().lstrip(".") or "bin"
            object_key = f"media/objects/sha256/{hex_digest[:2]}/{hex_digest[2:4]}/{hex_digest}.{suffix}"
            cas_ref = Path("cas") / f"{hex_digest}.{suffix}"
            cas_target = staging / cas_ref
            cas_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_source, cas_target)
            width, height, mime = _image_dimensions(asset_source)
            asset_id = str(raw.get("assetId") or "").strip()
            source_asset = source_assets.get(str(raw.get("sourceAssetId") or "")) or {}
            canonical_file_page = str(
                raw.get("authorizationProof") or source_asset.get("authorizationProof") or ""
            ).strip()
            license_url = str(raw.get("termsUrl") or source_asset.get("termsUrl") or "").strip()
            if license_url.startswith("http://"):
                license_url = "https://" + license_url.removeprefix("http://")
            if not canonical_file_page.startswith("https://") or not license_url.startswith("https://"):
                raise ObjectTransactionError(f"asset {asset_id} 缺 HTTPS 权利证明")
            snapshot_payload = {
                "schema": "quwoquan_data.asset_rights_snapshot",
                "executionId": execution_id,
                "assetId": asset_id,
                "sourceAsset": source_asset,
                "manifestAsset": raw,
            }
            snapshot_ref = Path("object/rights_snapshots") / f"{_safe_asset_id(asset_id)}.json"
            _write_json(staging / snapshot_ref, snapshot_payload)
            snapshot_path = staging / snapshot_ref
            fetched_at = str(
                source_asset.get("fetchedAt")
                or (entity.get("primarySource") or {}).get("fetchedAt")
                or execution_manifest.get("createdAt")
                or ""
            )
            author = str(raw.get("credit") or source_asset.get("credit") or source_asset.get("creator") or "").strip()
            license_name = str(raw.get("license") or source_asset.get("license") or "").strip()
            if not author or not license_name or not fetched_at:
                raise ObjectTransactionError(f"asset {asset_id} 权利字段不完整")
            attribution = f"{str(raw.get('caption') or asset_id)}，作者：{author}，{license_name}"
            rights_rows.append(
                {
                    "assetId": asset_id,
                    "sourceKind": str((entity.get("primarySource") or {}).get("sourceKind") or "wikipedia"),
                    "sourceUseMode": "licensed_adaptation",
                    "canonicalFilePage": canonical_file_page,
                    "snapshotUrl": canonical_file_page,
                    "pageRevision": _digest_file(snapshot_path),
                    "originalAssetUrl": str(source_asset.get("url") or canonical_file_page),
                    "author": author,
                    "source": str(source_asset.get("collectionPageUrl") or canonical_file_page),
                    "licenseName": license_name,
                    "licenseShortName": license_name,
                    "licenseUrl": license_url,
                    "usageScope": "app_publish",
                    "attribution": attribution,
                    "caption": str(raw.get("caption") or ""),
                    "captionSource": "captured source asset metadata",
                    "modifications": "homepage materialization resize/crop when applicable",
                    "fetchedAt": fetched_at,
                    "snapshot": {
                        "ref": snapshot_ref.as_posix(),
                        "sha256": _digest_file(snapshot_path),
                        "bytes": snapshot_path.stat().st_size,
                    },
                    "asset": {
                        "ref": cas_ref.as_posix(),
                        "sha256": digest,
                        "bytes": asset_source.stat().st_size,
                        "mimeType": mime,
                        "width": width,
                        "height": height,
                    },
                    "authorizationProof": canonical_file_page,
                    "modelReleaseStatus": "not_required",
                }
            )
            cas_rows.append(
                {
                    "sourceRef": cas_ref.as_posix(),
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )
            asset_refs.append(
                {
                    "assetId": asset_id,
                    "objectKey": object_key,
                    "sha256": digest,
                    "bytes": asset_source.stat().st_size,
                }
            )
            canonical_assets.append({**raw, "objectKey": object_key})

        if not cas_rows:
            raise ObjectTransactionError("entity 事务至少需要一个已授权发布资产")
        tag_refs = sorted({str(item) for item in entity.get("tagRefs") or [] if str(item)})
        _write_json(object_root / "creator.refs.json", {"creatorRefs": []})
        _write_json(object_root / "tag.refs.json", {"tagRefs": tag_refs})
        _write_json(object_root / "asset.refs.json", {"assets": asset_refs})
        rights_ref = Path("rights.json")
        _write_json(
            object_root / rights_ref,
            {"schema": "quwoquan_data.asset_rights_closure", "assets": rights_rows},
        )
        _write_json(
            object_root / "manifest.json",
            {
                "schema": "quwoquan_data.entity_object",
                "entityRef": str(entity.get("entityRef") or ""),
                "executionId": execution_id,
                "finalContentRef": "page.md",
                "sourceCatalogRef": source_catalog_ref.as_posix(),
                "rightsRef": rights_ref.as_posix(),
                "creatorRefsRef": "creator.refs.json",
                "tagRefsRef": "tag.refs.json",
                "assetRefsRef": "asset.refs.json",
                "assets": canonical_assets,
            },
        )
        closure = {
            "creatorRefs": [],
            "tagRefs": tag_refs,
            "sourceCatalogRef": source_catalog_ref.as_posix(),
            "rightsRef": rights_ref.as_posix(),
            "casRefs": cas_rows,
        }
        review = {
            "attestationRef": "attestation.json",
            "evidenceIndexRef": "evidence_index.json",
        }
        review_binding = _review_binding(object_root, {"review": review})
        closure_digest = _closure_digest(
            object_root=object_root,
            object_kind="entities",
            object_ref=canonical_ref,
            target_schema="quwoquan_data.entity_object",
            source_policy_revision=REQUIRED_SOURCE_POLICY,
            closure=closure,
            cas_rows=cas_rows,
            review=review_binding,
        )
        package = {
            "schema": PACKAGE_SCHEMA,
            "transactionId": transaction_id,
            "executionId": execution_id,
            "sourcePolicyRevision": REQUIRED_SOURCE_POLICY,
            "target": {
                "layoutSchema": LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": canonical_ref,
                "objectSchema": "quwoquan_data.entity_object",
                "packageObjectRef": "object",
            },
            "closure": closure,
            "review": review,
            "objectClosureDigest": closure_digest,
        }
        _write_json(staging / "object_transaction_package.json", package)
        staging.replace(package_root)
        return package
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
