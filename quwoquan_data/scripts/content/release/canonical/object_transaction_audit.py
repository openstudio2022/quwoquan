"""Validate and audit canonical object transactions.

canonical publish 的 closure 分两层，两层共用同一批文档级规则：

- `validate_publish_delta` 是 per-object 热路径，成本 O(Δ)，只看本次事务触及的路径与
  它们引用的 CAS，候选字节直接读不可变 delta blob（此时还没落到 publish 树）。
- `validate_publish_invariants` 是全量扫描，负责只有看全树才能判定的 orphan 不变量，
  只在 release 聚合边界与 verify 门运行。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from content.release.canonical.canonical_inventory import (
    load_or_bootstrap_inventory,
)
from content.release.canonical.object_transaction_contract import (
    ALLOWED_CANONICAL_ROOTS,
    DRY_RUN_SCHEMA,
    LAYOUT_SCHEMA,
    ObjectTransactionError,
    _collect_object_keys,
    _digest_bytes,
    _files,
    _json_bytes,
    _read_json,
    _safe_id,
    _safe_rel,
    _verify_package,
    _write_json,
    collect_canonical_tag_refs,
)
from content.release.canonical.object_transaction_delta import (
    build_transaction_delta,
    load_transaction_delta,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT
from core.schema import assert_valid


def _system_creator_seed_closure() -> tuple[set[str], set[str]]:
    """Return system-builtin creator ids and avatar CAS keys allowed as publish seed.

    Avatar CAS must exist in publish before the first post transaction projects the
    creator. Until consumer objects reference them, closure must not treat those
    seed creators / avatar bytes as orphans.
    """
    profiles = (
        CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles" / "system_builtin"
    )
    creator_ids: set[str] = set()
    avatar_keys: set[str] = set()
    if not profiles.is_dir():
        return creator_ids, avatar_keys
    for path in sorted(profiles.glob("*.creator.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(payload, dict) or payload.get("isSystemBuiltin") is not True:
            continue
        creator_id = str(payload.get("creatorProfileId") or "").strip()
        avatar = payload.get("avatarAsset")
        if not creator_id or not isinstance(avatar, dict):
            continue
        object_key = str(avatar.get("objectKey") or "").strip()
        if not object_key.startswith("media/objects/sha256/"):
            continue
        creator_ids.add(creator_id)
        avatar_keys.add(object_key)
    return creator_ids, avatar_keys

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

def _document_closure_issues(
    *,
    rel: str,
    payload: dict[str, Any],
    cas_resolved: Callable[[str], bool],
    creator_refs_of: Callable[[str], Any],
) -> tuple[list[dict[str, str]], set[str], set[str]]:
    """Canonical closure rules for one document, shared by both closure layers."""
    issues: list[dict[str, str]] = []
    referenced_media: set[str] = set()
    referenced_creators: set[str] = set()
    for object_key in _collect_object_keys(payload):
        referenced_media.add(object_key)
        try:
            _safe_rel(object_key, label="objectKey")
        except ObjectTransactionError:
            issues.append({"code": "asset_ref_path_escape", "ref": f"{rel}:{object_key}"})
            continue
        if not object_key.startswith("media/objects/sha256/"):
            issues.append({"code": "non_cas_asset_ref", "ref": f"{rel}:{object_key}"})
        elif not cas_resolved(object_key):
            issues.append({"code": "dangling_asset_ref", "ref": f"{rel}:{object_key}"})
    if not rel.startswith("creators/"):
        referenced_creators.update(_collect_creator_ids(payload))
    if rel.startswith("entities/") and rel.endswith("/_entity.json"):
        creator_profile_id = str(payload.get("creatorProfileId") or "").strip()
        if creator_profile_id:
            creator_refs = creator_refs_of(rel)
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
    return issues, referenced_media, referenced_creators


def validate_publish_delta(
    *,
    publish_root: Path,
    run_root: Path,
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate one frozen transaction delta in O(Δ) before it reaches publish.

    Candidate bytes still live in the immutable delta blob store, so references
    close against `publish ∪ delta`.  Global orphan invariants are deliberately
    out of scope: they need the whole tree and belong to the release boundary.
    """
    issues: list[dict[str, str]] = []
    candidates: dict[str, Path] = {}
    deleted: set[str] = set()
    for raw in entries:
        destination = str(raw.get("destination") or "")
        try:
            relative = _safe_rel(destination, label="delta.destination")
        except ObjectTransactionError as exc:
            issues.append({"code": "delta_ref_path_escape", "ref": f"{destination}: {exc}"})
            continue
        if relative.parts[0] not in ALLOWED_CANONICAL_ROOTS:
            issues.append({"code": "noncanonical_root", "ref": relative.parts[0]})
            continue
        if raw.get("operation") == "delete":
            deleted.add(relative.as_posix())
            continue
        try:
            blob_ref = _safe_rel(str(raw.get("blobRef") or ""), label="delta.blobRef")
        except ObjectTransactionError as exc:
            issues.append({"code": "delta_ref_path_escape", "ref": f"{destination}: {exc}"})
            continue
        blob = run_root / blob_ref
        if not blob.is_file():
            issues.append({"code": "delta_blob_missing", "ref": relative.as_posix()})
            continue
        candidates[relative.as_posix()] = blob

    def cas_resolved(object_key: str) -> bool:
        if object_key in candidates:
            return True
        try:
            return (publish_root / _safe_rel(object_key, label="objectKey")).is_file()
        except ObjectTransactionError:
            return False

    def creator_refs_of(rel: str) -> Any:
        sibling = (Path(rel).parent / "creator.refs.json").as_posix()
        blob = candidates.get(sibling)
        if blob is None and sibling not in deleted:
            path = publish_root / sibling
            blob = path if path.is_file() else None
        if blob is None:
            return None
        try:
            return _read_json(blob).get("creatorRefs")
        except ObjectTransactionError:
            return None

    referenced_creators: set[str] = set()
    for rel, blob in sorted(candidates.items()):
        if not rel.endswith(".json"):
            continue
        try:
            payload = _read_json(blob)
        except ObjectTransactionError as exc:
            issues.append({"code": "invalid_json", "ref": rel, "message": str(exc)})
            continue
        if rel.startswith("tags/") and rel.endswith("/_definition.json"):
            try:
                assert_valid(
                    payload,
                    "governance",
                    "_definition",
                    label=f"publish tag {rel}",
                )
            except (ValueError, FileNotFoundError) as exc:
                issues.append({"code": "invalid_tag_snapshot", "ref": f"{rel}: {exc}"})
        document_issues, _media, creators = _document_closure_issues(
            rel=rel,
            payload=payload,
            cas_resolved=cas_resolved,
            creator_refs_of=creator_refs_of,
        )
        issues.extend(document_issues)
        referenced_creators.update(creators)

    for creator_id in sorted(referenced_creators):
        manifest = f"creators/{creator_id}/_creator.json"
        try:
            resolved = manifest in candidates or (
                publish_root / _safe_rel(manifest, label="creatorRef")
            ).is_file()
        except ObjectTransactionError:
            resolved = False
        if not resolved:
            issues.append({"code": "dangling_creator_ref", "ref": creator_id})

    return {
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "validationScope": "delta",
        "deltaFileCount": len(entries),
    }


def validate_publish_invariants(root: Path) -> dict[str, Any]:
    """Full-tree canonical closure, including the orphan invariants.

    O(N) by construction; only the release aggregation boundary and the verify
    gates may pay it.  The per-object hot path uses `validate_publish_delta`.
    """
    issues: list[dict[str, str]] = []
    referenced_media: set[str] = set()
    referenced_creators: set[str] = set()
    referenced_tags: set[str] = set()
    if root.is_dir():
        for child in root.iterdir():
            if child.name not in ALLOWED_CANONICAL_ROOTS:
                issues.append({"code": "noncanonical_root", "ref": child.name})

    def cas_resolved(object_key: str) -> bool:
        return (root / _safe_rel(object_key, label="objectKey")).is_file()

    def creator_refs_of(rel: str) -> Any:
        path = root / rel
        creator_refs_path = path.parent / "creator.refs.json"
        if not creator_refs_path.is_file():
            return None
        return _read_json(creator_refs_path).get("creatorRefs")

    for path in _files(root):
        if path.suffix != ".json":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            payload = _read_json(path)
        except ObjectTransactionError as exc:
            issues.append({"code": "invalid_json", "ref": rel, "message": str(exc)})
            continue
        document_issues, media, creators = _document_closure_issues(
            rel=rel,
            payload=payload,
            cas_resolved=cas_resolved,
            creator_refs_of=creator_refs_of,
        )
        issues.extend(document_issues)
        referenced_media.update(media)
        referenced_creators.update(creators)

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

    seed_creators, seed_avatar_keys = _system_creator_seed_closure()
    referenced_media.update(seed_avatar_keys)

    media_root = root / "media" / "objects"
    for asset in _files(media_root):
        # Ignore directory placeholders (e.g. .gitkeep); they are not CAS objects.
        if asset.name.startswith("."):
            continue
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
            if (
                creator_id not in referenced_creators
                and creator_id not in seed_creators
            ):
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

@canonical_publish_serialized
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
    before_inventory = load_or_bootstrap_inventory(publish_root)
    before = before_inventory["stats"]
    if before["merkleRoot"] != expected_canonical_merkle:
        raise ObjectTransactionError(
            "current canonical Merkle 不匹配："
            f"expected={expected_canonical_merkle} actual={before['merkleRoot']}"
        )
    package = _verify_package(
        package_root,
        canonical_root=publish_root,
        require_target_absent=False,
    )
    if package["transactionId"] != transaction_id:
        raise ObjectTransactionError("package transactionId 不匹配")
    run_root = _transaction_root(output_root, transaction_id)
    report_path = run_root / "audit_report.json"
    if report_path.is_file():
        persisted = _read_json(report_path)
        _verify_attestation(
            persisted,
            str(persisted.get("dryRunAttestationSha256") or ""),
        )
        if (
            persisted.get("beforeCanonical", {}).get("merkleRoot")
            == before["merkleRoot"]
            and persisted.get("beforeInventoryDigest")
            == before_inventory["inventoryDigest"]
            and persisted.get("objectClosureDigest")
            == package["objectClosureDigest"]
            and persisted.get("packageSha256") == package["packageSha256"]
        ):
            delta = load_transaction_delta(
                run_root=run_root,
                expected_digest=str(persisted.get("deltaManifestDigest") or ""),
            )
            if (
                delta.get("afterMerkle")
                != persisted.get("afterCanonical", {}).get("merkleRoot")
                or delta.get("afterInventoryDigest")
                != persisted.get("afterInventoryDigest")
            ):
                raise ObjectTransactionError("persisted transaction delta after Merkle drift")
            return {**persisted, "idempotent": True}
        raise ObjectTransactionError("已有 audit 与当前事务输入不一致")
    delta, after_inventory = build_transaction_delta(
        publish_root=publish_root,
        run_root=run_root,
        package_root=package_root,
        package=package,
        before_inventory=before_inventory,
    )
    after = after_inventory["stats"]
    closure = validate_publish_delta(
        publish_root=publish_root,
        run_root=run_root,
        entries=delta["entries"],
    )
    if closure["status"] != "passed":
        raise ObjectTransactionError(
            "canonical publish delta closure invalid："
            + "; ".join(
                f"{item['code']}:{item.get('ref', '')}"
                for item in closure["issues"][:5]
            )
        )
    fence_token = _digest_bytes(
        _json_bytes(
            {
                "transactionId": transaction_id,
                "beforeMerkle": before["merkleRoot"],
                "afterMerkle": after["merkleRoot"],
                "deltaDigest": delta["deltaDigest"],
            }
        )
    )
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
        "fenceToken": fence_token,
        "deltaManifestRef": (
            run_root / "delta/manifest.json"
        ).relative_to(output_root).as_posix(),
        "deltaManifestDigest": delta["deltaDigest"],
        "deltaFileCount": len(delta["entries"]),
        "deltaBytes": delta["deltaBytes"],
        "candidateValidationMode": "incremental_inventory_delta",
        "beforeInventoryDigest": before_inventory["inventoryDigest"],
        "afterInventoryDigest": after_inventory["inventoryDigest"],
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
            "validationScope": closure["validationScope"],
            "deltaFileCount": closure["deltaFileCount"],
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
