"""Validate and audit canonical object transactions."""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Any
from core.tree_integrity import tree_integrity_stats
from core.schema import assert_valid
from content.release.canonical.object_transaction_contract import (
    DRY_RUN_SCHEMA, LAYOUT_SCHEMA, ALLOWED_CANONICAL_ROOTS,
    ObjectTransactionError, _json_bytes, _digest_bytes, _digest_file, _read_json,
    _write_json, _safe_id, _safe_rel, _files, _copy_tree, collect_canonical_tag_refs,
    refresh_canonical_tag_snapshots, _collect_object_keys, _verify_package,
)

def _transaction_root(output_root: Path, transaction_id: str) -> Path:
    return output_root / "data/local/workspace/object-transactions" / transaction_id


def _post_media_issues(payload: dict[str, Any], ref: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if str(payload.get("contentIdentity") or "").strip() != "work":
        issues.append({"code": "post_content_identity_invalid", "ref": ref})
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return issues
    by_id: dict[str, dict[str, Any]] = {}
    for raw in assets:
        if not isinstance(raw, dict):
            issues.append({"code": "invalid_post_asset", "ref": ref})
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        if not asset_id:
            issues.append({"code": "missing_post_asset_id", "ref": ref})
        elif asset_id in by_id:
            issues.append({"code": "duplicate_post_asset_id", "ref": f"{ref}:{asset_id}"})
        else:
            by_id[asset_id] = raw
        for field in ("cdnUrl", "thumbnailUrl", "coverUrl", "videoUrl"):
            if str(raw.get(field) or "").strip():
                issues.append(
                    {"code": "environment_media_url_in_canonical", "ref": f"{ref}:{asset_id}:{field}"}
                )
    if str(payload.get("contentType") or "").strip() != "video":
        return issues
    video_assets = [raw for raw in by_id.values() if str(raw.get("kind") or "") == "video"]
    if not video_assets:
        issues.append({"code": "video_asset_missing", "ref": ref})
    for video in video_assets:
        video_id = str(video.get("assetId") or "")
        poster_id = str(video.get("posterAssetId") or "").strip()
        poster = by_id.get(poster_id)
        if (
            not poster_id
            or poster is None
            or str(poster.get("kind") or "") != "image"
            or str(poster.get("role") or "") != "cover"
        ):
            issues.append({"code": "video_poster_closure_invalid", "ref": f"{ref}:{video_id}"})
    return issues

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
        if rel.startswith("entities/") and rel.endswith("/_entity.json"):
            creator_profile_id = str(payload.get("creatorProfileId") or "").strip()
            if creator_profile_id:
                creator_refs_path = path.parent / "creator.refs.json"
                creator_refs = (
                    _read_json(creator_refs_path).get("creatorRefs")
                    if creator_refs_path.is_file()
                    else None
                )
                if (
                    not isinstance(creator_refs, list)
                    or creator_profile_id not in creator_refs
                ):
                    issues.append(
                        {
                            "code": "entity_creator_closure_missing",
                            "ref": f"{rel}:{creator_profile_id}",
                        }
                    )
        if rel.startswith("posts/") and rel.endswith("/manifest.json"):
            issues.extend(_post_media_issues(payload, rel))

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
    for creator_id in sorted(referenced_creators):
        if not (creators_root / creator_id / "_creator.json").is_file():
            issues.append({"code": "dangling_creator_ref", "ref": creator_id})
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
    # Canonical publish is derived state. A fresh checkout or an intentional
    # empty-baseline reset therefore has no physical directory yet; initialize
    # the empty root before taking the Merkle snapshot and staging the atomic
    # transaction. Static inputs remain in the version-controlled control plane.
    if publish_root.exists() and not publish_root.is_dir():
        raise ObjectTransactionError(f"canonical publish root is not a directory: {publish_root}")
    publish_root.mkdir(parents=True, exist_ok=True)
    before = tree_integrity_stats(publish_root)
    if before["merkleRoot"] != expected_canonical_merkle:
        raise ObjectTransactionError(
            "current canonical Merkle 不匹配："
            f"expected={expected_canonical_merkle} actual={before['merkleRoot']}"
        )
    package = _verify_package(
        package_root,
        canonical_root=publish_root,
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
    for creator in package["creatorObjects"]:
        target_creator = staging / "creators" / creator["creatorRef"]
        if target_creator.is_dir():
            if tree_integrity_stats(target_creator)["merkleRoot"] != tree_integrity_stats(
                creator["objectRoot"]
            )["merkleRoot"]:
                raise ObjectTransactionError(
                    f"canonical creator projection drift：{creator['creatorRef']}"
                )
            continue
        _copy_tree(Path(creator["objectRoot"]), target_creator)
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
        "schema": DRY_RUN_SCHEMA,
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
