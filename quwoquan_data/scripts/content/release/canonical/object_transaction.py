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


CONTENT_RELEASE_KIND = "content"


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
                "schemaVersion": "quwoquan_data.asset_rights_snapshot/1",
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
            {"schemaVersion": "quwoquan_data.asset_rights_closure/1", "assets": rights_rows},
        )
        _write_json(
            object_root / "manifest.json",
            {
                "schemaVersion": "quwoquan_data.entity_object/1",
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
            target_schema="quwoquan_data.entity_object/1",
            source_policy_revision=REQUIRED_SOURCE_POLICY,
            closure=closure,
            cas_rows=cas_rows,
            review=review_binding,
        )
        package = {
            "schemaVersion": PACKAGE_SCHEMA,
            "transactionId": transaction_id,
            "executionId": execution_id,
            "sourcePolicyRevision": REQUIRED_SOURCE_POLICY,
            "target": {
                "layoutSchema": LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": canonical_ref,
                "objectSchema": "quwoquan_data.entity_object/1",
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


def build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_roots: list[Path],
    rollout_milestone: str,
) -> dict[str, Any]:
    """Create one immutable environment-neutral release from approved executions."""
    release_id = _safe_id(release_id, label="releaseId")
    rollout_milestone = str(rollout_milestone or "").strip()
    if rollout_milestone not in {"canary", "m1", "m2", "m3"}:
        raise ObjectTransactionError("rolloutMilestone must be canary, m1, m2, or m3")
    final_root = release_root / release_id
    execution_ids: list[str] = []
    entity_refs: set[str] = set()
    for root in execution_roots:
        manifest = _read_json(root / "execution_manifest.json")
        execution_id = _execution_id(str(manifest.get("executionId") or ""))
        if root.name != execution_id:
            raise ObjectTransactionError("aggregate execution root identity mismatch")
        execution_ids.append(execution_id)
        for attestation_path in sorted(root.glob("entities/*/*/*/5.review/attestation.json")):
            attestation = _read_json(attestation_path)
            if attestation.get("decision") != "approved" or str(
                (attestation.get("independentReviewer") or {}).get("status") or ""
            ) != "passed":
                continue
            ref = str(attestation.get("objectRef") or "").removeprefix("/entity/")
            if not ref:
                continue
            canonical = publish_root / "entities" / _safe_rel(ref, label="entityRef")
            if not (canonical / "manifest.json").is_file():
                raise ObjectTransactionError(f"approved execution object 未进入 canonical publish：{ref}")
            entity_refs.add(ref)
    if not entity_refs:
        raise ObjectTransactionError("aggregate release 没有 approved canonical entity")

    canonical_closure = validate_canonical_publish(publish_root)
    if canonical_closure["status"] != "passed":
        raise ObjectTransactionError(
            "aggregate release canonical closure invalid: "
            + "; ".join(
                f"{item['code']}:{item['ref']}" for item in canonical_closure["issues"][:5]
            )
        )
    tag_refs = _release_entity_tag_refs(publish_root=publish_root, entity_refs=entity_refs)

    if final_root.exists():
        header = _read_json(payload_file(final_root, "release.json"))
        desired = _read_json(payload_file(final_root, "desired_state.json"))
        existing_refs = sorted(
            str(item) for item in ((desired.get("desiredRefs") or {}).get("entities") or [])
        )
        existing_tag_refs = sorted(
            str(item) for item in ((desired.get("desiredRefs") or {}).get("tags") or [])
        )
        expected_execution_ids = sorted(set(execution_ids))
        current_merkle = tree_integrity_stats(publish_root)["merkleRoot"]
        if (
            header.get("releaseId") == release_id
            and sorted(header.get("executionIds") or []) == expected_execution_ids
            and existing_refs == sorted(entity_refs)
            and existing_tag_refs == tag_refs
            and header.get("canonicalMerkle") == current_merkle
            and header.get("releaseKind") == CONTENT_RELEASE_KIND
            and header.get("rolloutMilestone") == rollout_milestone
        ):
            return {
                "schemaVersion": "quwoquan_data.aggregate_release_result/1",
                "releaseId": release_id,
                "releaseRoot": str(final_root),
                "executionIds": expected_execution_ids,
                "entityCount": len(entity_refs),
                "canonicalMerkle": current_merkle,
                "rolloutMilestone": rollout_milestone,
                "idempotent": True,
            }
        raise ObjectTransactionError(f"aggregate release create-once conflict: {final_root}")

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        for ref in sorted(entity_refs):
            _copy_tree(
                publish_root / "entities" / ref,
                payload / "objects/entities" / ref,
            )
        for ref in tag_refs:
            _copy_tree(
                publish_root / "tags" / _safe_rel(ref, label="tagRef"),
                payload / "objects/tags" / ref,
            )
        desired = {
            "creators": [],
            "entities": sorted(entity_refs),
            "posts": [],
            "tags": tag_refs,
        }
        canonical = tree_integrity_stats(publish_root)
        _write_json(
            payload / "release.json",
            {
                "schemaVersion": RELEASE_SCHEMA,
                "releaseId": release_id,
                "releaseKind": CONTENT_RELEASE_KIND,
                "canonicalMerkle": canonical["merkleRoot"],
                "executionIds": sorted(set(execution_ids)),
                "rolloutMilestone": rollout_milestone,
            },
        )
        _write_json(
            payload / "desired_state.json",
            {
                "schemaVersion": "quwoquan_data.release_desired_state/1",
                "releaseId": release_id,
                "desiredRefs": desired,
            },
        )
        _write_json(
            payload / "index/objects.json",
            {"schemaVersion": "quwoquan_data.release_object_index/1", **desired},
        )
        _write_json(
            payload / "sample_bundle.json",
            {
                "schemaVersion": "quwoquan_data.release_sample_bundle/1",
                "entities": desired["entities"],
                "posts": desired["posts"],
                "tags": desired["tags"],
            },
        )
        media_manifest = build_release_media_manifest(
            release_id=release_id,
            post_refs=[],
            entity_refs=desired["entities"],
            publish_root=publish_root,
        )
        if media_manifest["issues"]:
            raise ObjectTransactionError(
                "aggregate release media closure invalid: "
                + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
            )
        _write_json(
            payload / "media_manifest.json",
            media_manifest,
        )
        aggregate_attestation = {
            "schemaVersion": "quwoquan_data.aggregate_release_attestation/2",
            "releaseId": release_id,
            "releaseKind": CONTENT_RELEASE_KIND,
            "executionIds": sorted(set(execution_ids)),
            "rolloutMilestone": rollout_milestone,
            "entityCount": len(entity_refs),
            "tagCount": len(tag_refs),
            "canonicalMerkle": canonical["merkleRoot"],
            "payloadSha256": payload_digest(staging),
            "recordedAt": _now(),
        }
        assert_valid(
            aggregate_attestation,
            "release",
            "aggregate_release_attestation",
            label=f"aggregate_release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "aggregate.json", aggregate_attestation)
        assert_environment_neutral(staging)
        staging.replace(final_root)
        return {
            "schemaVersion": "quwoquan_data.aggregate_release_result/1",
            "releaseId": release_id,
            "releaseRoot": str(final_root),
            "executionIds": sorted(set(execution_ids)),
            "entityCount": len(entity_refs),
            "canonicalMerkle": canonical["merkleRoot"],
            "rolloutMilestone": rollout_milestone,
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _transaction_root(output_root: Path, transaction_id: str) -> Path:
    return output_root / "data/local/workspace/object-transactions" / transaction_id


def validate_canonical_publish(root: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    referenced_media: set[str] = set()
    referenced_creators: set[str] = set()
    referenced_tags: set[str] = set()
    if root.is_dir():
        for child in root.iterdir():
            if child.name not in ALLOWED_CANONICAL_ROOTS:
                issues.append({"code": "noncanonical_root", "ref": child.name})
    for path in _files(root):
        if path.suffix != ".json":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            payload = _read_json(path)
        except ObjectTransactionError as exc:
            issues.append({"code": "invalid_json", "ref": rel, "message": str(exc)})
            continue
        for object_key in _collect_object_keys(payload):
            referenced_media.add(object_key)
            try:
                safe_key = _safe_rel(object_key, label="objectKey")
            except ObjectTransactionError:
                issues.append({"code": "asset_ref_path_escape", "ref": f"{rel}:{object_key}"})
                continue
            asset = root / safe_key
            if not object_key.startswith("media/objects/sha256/"):
                issues.append({"code": "non_cas_asset_ref", "ref": f"{rel}:{object_key}"})
            elif not asset.is_file():
                issues.append({"code": "dangling_asset_ref", "ref": f"{rel}:{object_key}"})
        if not rel.startswith("creators/"):
            referenced_creators.update(_collect_creator_ids(payload))

    try:
        referenced_tags = set(collect_canonical_tag_refs(root))
    except ObjectTransactionError as exc:
        issues.append({"code": "invalid_tag_ref_document", "ref": str(exc)})
    tag_root = root / "tags"
    expected_tag_files: set[str] = set()
    for tag_ref in sorted(referenced_tags):
        try:
            tag_path = _safe_rel(tag_ref, label="tagRef")
        except ObjectTransactionError:
            issues.append({"code": "tag_ref_path_escape", "ref": tag_ref})
            continue
        snapshot = tag_root / tag_path / "_definition.json"
        expected_tag_files.add(snapshot.relative_to(root).as_posix())
        if not snapshot.is_file():
            issues.append({"code": "dangling_tag_ref", "ref": tag_ref})
            continue
        try:
            assert_valid(_read_json(snapshot), "governance", "_definition", label=f"publish tag {tag_ref}")
        except (ObjectTransactionError, ValueError, FileNotFoundError) as exc:
            issues.append({"code": "invalid_tag_snapshot", "ref": f"{tag_ref}: {exc}"})
    for snapshot in _files(tag_root):
        rel = snapshot.relative_to(root).as_posix()
        if rel not in expected_tag_files:
            issues.append({"code": "orphan_tag_snapshot", "ref": rel})

    media_root = root / "media" / "objects"
    for asset in _files(media_root):
        object_key = asset.relative_to(root).as_posix()
        if object_key not in referenced_media:
            issues.append({"code": "orphan_media", "ref": object_key})

    creators_root = root / "creators"
    if creators_root.is_dir():
        for manifest in sorted(creators_root.glob("*/_creator.json")):
            creator_id = manifest.parent.name
            if creator_id not in referenced_creators:
                issues.append({"code": "orphan_creator", "ref": creator_id})
    return {
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "casObjectCount": len(list(_files(root / "media/objects"))),
        "tagSnapshotCount": len(expected_tag_files),
    }


def _collect_creator_ids(value: Any) -> set[str]:
    """Collect only consumer-side creator references from canonical object JSON."""
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"creatorId", "creatorProfileId"} and isinstance(child, str) and child:
                result.add(child)
            if key in {"creatorRef", "authorCreatorId"} and isinstance(child, str) and child:
                result.add(child)
            if key == "creatorRefs" and isinstance(child, list):
                result.update(item for item in child if isinstance(item, str) and item)
            result.update(_collect_creator_ids(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_collect_creator_ids(child))
    return result


def _verify_attestation(report: dict[str, Any], expected: str) -> None:
    embedded = str(report.pop("dryRunAttestationSha256", ""))
    actual = _digest_bytes(_json_bytes(report))
    report["dryRunAttestationSha256"] = embedded
    if expected != embedded or actual != embedded:
        raise ObjectTransactionError(
            "dry-run attestation mismatch："
            f"expected={expected} embedded={embedded} actual={actual}"
        )


def audit_object_transaction(
    *,
    publish_root: Path,
    output_root: Path,
    package_root: Path,
    transaction_id: str,
    expected_canonical_merkle: str,
) -> dict[str, Any]:
    transaction_id = _safe_id(transaction_id, label="transactionId")
    before = tree_integrity_stats(publish_root)
    if before["merkleRoot"] != expected_canonical_merkle:
        raise ObjectTransactionError(
            "current canonical Merkle 不匹配："
            f"expected={expected_canonical_merkle} actual={before['merkleRoot']}"
        )
    package = _verify_package(
        package_root,
        canonical_root=publish_root,
        required_source_policy_revision=REQUIRED_SOURCE_POLICY,
        require_target_absent=True,
    )
    if package["transactionId"] != transaction_id:
        raise ObjectTransactionError("package transactionId 不匹配")
    run_root = _transaction_root(output_root, transaction_id)
    report_path = run_root / "audit_report.json"
    staging = run_root / "staging/canonical"
    if report_path.is_file():
        persisted = _read_json(report_path)
        _verify_attestation(
            persisted,
            str(persisted.get("dryRunAttestationSha256") or ""),
        )
        if (
            persisted.get("beforeCanonical", {}).get("merkleRoot")
            == before["merkleRoot"]
            and persisted.get("objectClosureDigest")
            == package["objectClosureDigest"]
            and persisted.get("packageSha256") == package["packageSha256"]
            and staging.is_dir()
            and tree_integrity_stats(staging)["merkleRoot"]
            == persisted.get("afterCanonical", {}).get("merkleRoot")
        ):
            return {**persisted, "idempotent": True}
        raise ObjectTransactionError("已有 audit 与当前事务输入不一致")
    if staging.exists():
        raise ObjectTransactionError(f"stale staging 已存在：{staging}")
    _copy_tree(publish_root, staging)
    target = staging / package["objectKind"] / package["objectRef"]
    _copy_tree(Path(package["objectRoot"]), target)
    for row in package["casRows"]:
        source = package_root / row["sourceRef"]
        destination = staging / row["objectKey"]
        if destination.is_file():
            if _digest_file(destination) != row["sha256"]:
                raise ObjectTransactionError(f"canonical CAS collision：{row['objectKey']}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    refresh_canonical_tag_snapshots(staging)
    closure = validate_canonical_publish(staging)
    if closure["status"] != "passed":
        raise ObjectTransactionError(
            f"staging canonical closure 失败：{closure['issues'][:5]}"
        )
    after = tree_integrity_stats(staging)
    report: dict[str, Any] = {
        "schemaVersion": DRY_RUN_SCHEMA,
        "transactionId": transaction_id,
        "executionId": package["executionId"],
        "sourcePolicyRevision": package["sourcePolicyRevision"],
        "targetLayout": LAYOUT_SCHEMA,
        "targetObjectSchema": package["objectSchema"],
        "objectKind": package["objectKind"],
        "objectRef": package["objectRef"],
        "objectClosureDigest": package["objectClosureDigest"],
        "packageSha256": package["packageSha256"],
        "beforeCanonical": {
            key: before[key]
            for key in ("algorithm", "merkleRoot", "fileCount", "totalBytes", "inventoryHash")
        },
        "afterCanonical": {
            key: after[key]
            for key in ("algorithm", "merkleRoot", "fileCount", "totalBytes", "inventoryHash")
        },
        "review": package["review"],
        "closure": {
            "status": closure["status"],
            "creatorRefs": package["creatorRefs"],
            "tagRefs": package["tagRefs"],
            "casRefs": [
                {
                    key: row[key]
                    for key in ("objectKey", "sha256", "bytes")
                }
                for row in package["casRows"]
            ],
        },
        "idempotent": False,
    }
    report["dryRunAttestationSha256"] = _digest_bytes(_json_bytes(report))
    _write_json(report_path, report)
    return report
