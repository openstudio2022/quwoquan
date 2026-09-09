"""Verification implementation behind the canonical transaction contract facade."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_bindings import (
    verify_entity_manifest_asset_binding,
)
from content.release.canonical.object_transaction_contract import (
    ALLOWED_OBJECT_KINDS,
    EXPECTED_OBJECT_SCHEMAS,
    EXPECTED_SOURCE_POLICIES,
    LAYOUT_SCHEMA,
    PACKAGE_SCHEMA,
    ObjectTransactionError,
    _closure_digest,
    _digest_file,
    _execution_id,
    _object_json_keys,
    _read_json,
    _review_binding,
    _rights_binding,
    _safe_id,
    _safe_rel,
    _tag_exists,
    _tree_digest,
)
from core.schema import assert_valid


def verify_package(
    package_root: Path,
    *,
    canonical_root: Path,
    require_target_absent: bool,
) -> dict[str, Any]:
    package_path = package_root / "object_transaction_package.json"
    package = _read_json(package_path)
    if package.get("schema") != PACKAGE_SCHEMA:
        raise ObjectTransactionError("object transaction package schema 不匹配")
    try:
        assert_valid(
            package,
            "release",
            "object_transaction_package",
            label="object_transaction_package",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    transaction_id = _safe_id(
        str(package.get("transactionId") or ""),
        label="transactionId",
    )
    execution_id = _execution_id(str(package.get("executionId") or ""))
    source_policy_revision = str(package.get("sourcePolicyRevision") or "")
    target = package.get("target")
    if not isinstance(target, dict) or target.get("layoutSchema") != LAYOUT_SCHEMA:
        raise ObjectTransactionError("target layout schema 不匹配")
    object_kind = str(target.get("objectKind") or "")
    if object_kind not in ALLOWED_OBJECT_KINDS:
        raise ObjectTransactionError(f"objectKind 不支持：{object_kind}")
    expected_source_policy = EXPECTED_SOURCE_POLICIES[object_kind].value
    if source_policy_revision != expected_source_policy:
        raise ObjectTransactionError(
            "sourcePolicyRevision 不匹配："
            f"expected={expected_source_policy} actual={source_policy_revision}"
        )
    target_schema = str(target.get("objectSchema") or "")
    if target_schema != EXPECTED_OBJECT_SCHEMAS[object_kind]:
        raise ObjectTransactionError("target object schema 不匹配")
    object_ref = _safe_rel(
        str(target.get("objectRef") or ""),
        label="objectRef",
    ).as_posix()
    from core.publish_layout import logical_object_ref
    from core.publish_repository import require_publish_repository
    require_publish_repository(canonical_root)
    object_path = _safe_rel(str(target.get("objectPath") or ""), label="objectPath")
    if object_path.parts[0] != object_kind:
        raise ObjectTransactionError("DATA.PUBLISH.OBJECT_PATH_INVALID")
    target_root = canonical_root / object_path
    if require_target_absent and target_root.exists():
        raise ObjectTransactionError(f"对象事务只能 create-once，目标已存在：{target_root}")
    object_package_ref = _safe_rel(
        str(target.get("packageObjectRef") or "object"),
        label="packageObjectRef",
    )
    object_root = package_root / object_package_ref
    required_anchor = "_creator.json" if object_kind == "creators" else "manifest.json"
    if not (object_root / required_anchor).is_file():
        raise ObjectTransactionError(f"对象缺 {required_anchor}")
    for retired in ("_entity.json", "source_catalog.json", "rights.json", "rights_snapshots", "_pool", "asset.refs.json", "creator.refs.json", "tag.refs.json"):
        if (object_root / retired).exists():
            raise ObjectTransactionError(f"DATA.PUBLISH.RETIRED_SIDECAR: {retired}")
    media_mode = str(package.get("publishMediaMode") or "")
    object_manifest = (
        _read_json(object_root / "manifest.json")
        if object_kind in {"entities", "posts"}
        else {}
    )
    if object_kind == "posts":
        manifest_mode = str(object_manifest.get("publishMediaMode") or "").strip()
        expected_mode = "text_only" if manifest_mode == "text_only" else "embedded_media"
        if media_mode != expected_mode:
            raise ObjectTransactionError(
                "publishMediaMode 与 packaged post manifest 漂移"
            )
    elif object_kind == "entities":
        manifest_mode = str(object_manifest.get("publishMediaMode") or "").strip()
        expected_mode = "text_only" if manifest_mode == "text_only" else "not_applicable"
        if media_mode != expected_mode:
            raise ObjectTransactionError("publishMediaMode 与 packaged entity manifest 漂移")
    elif media_mode != "not_applicable":
        raise ObjectTransactionError(
            "non-content object transaction publishMediaMode 必须为 not_applicable"
        )
    review = _review_binding(object_root, package)
    closure = package.get("closure")
    if not isinstance(closure, dict):
        raise ObjectTransactionError("对象包缺 closure")
    creator_refs = [str(item) for item in closure.get("creatorRefs") or []]
    tag_refs = [str(item) for item in closure.get("tagRefs") or []]
    creator_objects: dict[str, dict[str, Any]] = {}
    for raw in closure.get("creatorObjects") or []:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError("creatorObjects item 必须为 object")
        creator_ref = str(raw.get("creatorRef") or "").strip()
        package_ref = _safe_rel(
            str(raw.get("packageRef") or ""),
            label="creatorObjects.packageRef",
        )
        creator_root = package_root / package_ref
        if not creator_ref or creator_ref in creator_objects:
            raise ObjectTransactionError("creatorObjects creatorRef 为空或重复")
        if not (creator_root / "_creator.json").is_file():
            raise ObjectTransactionError(f"creatorObjects 缺 _creator.json：{creator_ref}")
        tree_digest = _tree_digest(creator_root)
        if tree_digest != str(raw.get("treeDigest") or ""):
            raise ObjectTransactionError(f"creatorObjects treeDigest 不匹配：{creator_ref}")
        creator_objects[creator_ref] = {
            "creatorRef": creator_ref,
            "packageRef": package_ref.as_posix(),
            "treeDigest": tree_digest,
            "objectRoot": creator_root,
        }
    for creator_ref in creator_refs:
        creator = canonical_root / "creators" / _safe_rel(
            creator_ref,
            label="creatorRef",
        )
        packaged = creator_objects.get(creator_ref)
        if not (creator / "_creator.json").is_file():
            raise ObjectTransactionError(
                f"DATA.POOL.AUTHOR_NOT_ADMITTED: creatorRef={creator_ref}"
            )
        from content.release.canonical.content_pool_record import (
            is_pool_record_admitted,
            latest_pool_record,
        )

        author_record = latest_pool_record(creator, "author")
        if not is_pool_record_admitted(author_record):
            raise ObjectTransactionError(
                f"DATA.POOL.AUTHOR_NOT_ADMITTED: creatorRef={creator_ref}"
            )
        if packaged is not None:
            packaged_profile = _read_json(packaged["objectRoot"] / "profile.json")
            if (
                    packaged_profile.get("version")
                    != author_record["contentVersion"]
                or str(packaged_profile.get("authorId") or "")
                != str(author_record["objectId"])
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.AUTHOR_VERSION_MISMATCH: "
                    f"creatorRef={creator_ref} expected={author_record['version']} "
                    f"actual={packaged_profile.get('version')}"
                )
    if not set(creator_objects).issubset(creator_refs):
        raise ObjectTransactionError("creatorObjects 不得包含 creatorRefs 之外的对象")
    for tag_ref in tag_refs:
        if not _tag_exists(tag_ref):
            raise ObjectTransactionError(f"tag closure 不可解析：{tag_ref}")
    if logical_object_ref(object_manifest, object_kind) != object_ref:
        raise ObjectTransactionError("DATA.PUBLISH.LOGICAL_REF_DRIFT")
    if closure.get("sourceRefs") != object_manifest.get("sourceRefs"):
        raise ObjectTransactionError("DATA.PUBLISH.SOURCE_REF_DRIFT")
    from content.release.canonical.post_transaction_sources import read_object_sources
    sources = read_object_sources(object_root, object_manifest)
    cas_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for raw in closure.get("casRefs") or []:
        if not isinstance(raw, dict):
            raise ObjectTransactionError("casRefs item 必须为 object")
        source_ref = _safe_rel(str(raw.get("sourceRef") or ""), label="cas.sourceRef")
        source = package_root / source_ref
        object_key = _safe_rel(
            str(raw.get("objectKey") or ""),
            label="cas.objectKey",
        ).as_posix()
        if not source.is_file() or source.is_symlink():
            raise ObjectTransactionError(f"CAS source 不存在或为 symlink：{source_ref}")
        if not object_key.startswith("media/objects/sha256/"):
            raise ObjectTransactionError(f"CAS objectKey 非 canonical：{object_key}")
        digest = _digest_file(source)
        if digest != str(raw.get("sha256") or ""):
            raise ObjectTransactionError(f"CAS digest mismatch：{object_key}")
        if int(raw.get("bytes") or -1) != source.stat().st_size:
            raise ObjectTransactionError(f"CAS bytes mismatch：{object_key}")
        if Path(object_key).stem != digest.removeprefix("sha256:"):
            raise ObjectTransactionError(f"CAS objectKey 未按内容寻址：{object_key}")
        if object_key in seen_keys:
            raise ObjectTransactionError(f"CAS objectKey 重复：{object_key}")
        seen_keys.add(object_key)
        cas_rows.append(
            {
                "sourceRef": source_ref.as_posix(),
                "objectKey": object_key,
                "sha256": digest,
                "bytes": source.stat().st_size,
            }
        )
    if (media_mode == "text_only") != (len(cas_rows) == 0):
        raise ObjectTransactionError(
            "text_only 与空 CAS closure 必须逐项一致"
        )
    rights = {"assets": []}
    for asset in object_manifest.get("assets") or []:
        path = _safe_rel(str(asset.get("path") or ""), label="asset.path")
        body = object_root / path
        if path.parts[0] != "media" or body.is_symlink() or not body.is_file() or _digest_file(body) != asset.get("sha256") or body.stat().st_size != asset.get("bytes"):
            raise ObjectTransactionError("DATA.PUBLISH.CARRIED_MEDIA_DRIFT")
        matches = [row for row in cas_rows if row["sourceRef"] == (object_package_ref / path).as_posix() and row["sha256"] == asset["sha256"] and row["bytes"] == asset["bytes"]]
        facts = [row for source in sources if source["ref"] in asset["sourceRefs"] for row in source["assets"] if row.get("assetId") == asset["assetId"]]
        if len(matches) != 1 or not facts:
            raise ObjectTransactionError("DATA.PUBLISH.ASSET_SOURCE_BINDING_MISSING")
        rights["assets"].append({"assetId": asset["assetId"], "assetSha256": asset["sha256"], "assetBytes": asset["bytes"], "assetRef": matches[0]["sourceRef"]})
    if object_kind == "entities":
        try:
            verify_entity_manifest_asset_binding(
                _read_json(object_root / "manifest.json"),
                rights,
            )
        except (TypeError, ValueError) as exc:
            raise ObjectTransactionError(str(exc)) from exc
    referenced_keys = _object_json_keys(object_root)
    if referenced_keys != seen_keys:
        raise ObjectTransactionError(
            "对象 asset closure 与事务包 CAS 不一致："
            f"object={sorted(referenced_keys)} package={sorted(seen_keys)}"
        )
    closure_digest = _closure_digest(
        object_root=object_root,
        object_kind=object_kind,
        object_ref=object_ref,
        target_schema=target_schema,
        source_policy_revision=source_policy_revision,
        closure=closure,
        cas_rows=cas_rows,
        review=review,
    )
    if closure_digest != str(package.get("objectClosureDigest") or ""):
        raise ObjectTransactionError(
            "object closure digest mismatch："
            f"expected={package.get('objectClosureDigest')} actual={closure_digest}"
        )
    return {
        "package": package,
        "packageSha256": _digest_file(package_path),
        "transactionId": transaction_id,
        "executionId": execution_id,
        "sourcePolicyRevision": source_policy_revision,
        "objectKind": object_kind,
        "objectRef": object_ref,
        "objectPath": object_path.as_posix(),
        "objectSchema": target_schema,
        "objectRoot": object_root,
        "objectClosureDigest": closure_digest,
        "creatorRefs": creator_refs,
        "creatorObjects": list(creator_objects.values()),
        "tagRefs": tag_refs,
        "casRows": cas_rows,
        "review": review,
        "rights": rights,
    }


__all__ = ["verify_package"]
