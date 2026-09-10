"""显式全池 cutover：新 staging 预验、单次 OS exchange、离线原字节审计。

不转换旧输入、不授予资格；dry-run 不写池。激活与精确旧树清理分别需要授权。
"""
from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn

from content.execution.receipt_chain import validate_publish_review_chain
from content.release.canonical.content_pool_record import (
    is_pool_record_admitted, latest_pool_record, pool_payload_digest,
)
from content.release.canonical.object_transaction_audit import validate_publish_invariants
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError, _digest_bytes, _digest_file, _json_bytes, _read_json,
    _tree_digest, _verify_package,
)
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.pool_query import query_pool
from content.release.canonical.review_rights_binding import validate_review_authority
from core.schema import assert_valid, load_schema, validate_strict


class PoolCutoverError(ObjectTransactionError):
    """不掩盖下层诊断的 cutover typed blocker。"""

    def __init__(self, code: str, detail: object) -> None:
        self.code = f"DATA.CUTOVER.{code}"
        super().__init__(f"{self.code}: {detail}")


def _fail(code: str, detail: object) -> NoReturn:
    raise PoolCutoverError(code, detail)


def _absolute(value: str | Path, *, kind: str) -> Path:
    text = str(value)
    path = Path(text)
    if not path.is_absolute() or text != path.as_posix() or ".." in path.parts or "\x00" in text or text.startswith("//"):
        _fail("PATH_INVALID", text)
    for ancestor in (*reversed(path.parents), path):
        if ancestor.is_symlink():
            _fail("SYMLINK_FORBIDDEN", ancestor)
    if kind == "new_file":
        if path.exists() or not path.parent.is_dir():
            _fail("EVIDENCE_DESTINATION_INVALID", path)
    elif not path.exists() or not (path.is_file() if kind == "file" else path.is_dir()):
        _fail("PATH_INVALID", path)
    return path


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or path.as_posix() != value or ".." in path.parts or "\\" in value or "\x00" in value:
        _fail("REF_INVALID", value)
    return value


def _separate(left: Path, right: Path) -> None:
    if left == right or left in right.parents or right in left.parents:
        _fail("PATH_OVERLAP", f"{left} <> {right}")


def _regular_tree(root: Path) -> list[Path]:
    files: list[Path] = []
    device = root.stat().st_dev
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("SYMLINK_FORBIDDEN", path)
        if metadata.st_dev != device:
            _fail("CROSS_DEVICE", path)
        if stat.S_ISREG(metadata.st_mode):
            files.append(path)
        elif not stat.S_ISDIR(metadata.st_mode):
            _fail("SPECIAL_FILE_FORBIDDEN", path)
    return files


def _binding(row: Mapping[str, Any]) -> Path:
    path = _absolute(row["ref"], kind=row.get("kind", "file"))
    if row.get("kind") == "tree":
        _regular_tree(path)
        digest = _tree_digest(path)
    else:
        digest = _digest_file(path)
    if digest != row["digest"]:
        _fail("EVIDENCE_DIGEST_DRIFT", path)
    return path


def _schema(document: Any, *, definition: str | None = None) -> None:
    schema = load_schema("release", "pool_cutover")
    target = schema if definition is None else schema["$defs"][definition]
    issues = validate_strict(document, target, _root_schema=schema)
    if issues:
        _fail("SCHEMA_INVALID", issues[:10])


def _dependencies(root: Path, document: Mapping[str, Any]) -> list[str]:
    refs = set()
    for value in document.get("entityRefs") or []:
        if not isinstance(value, str) or not value.startswith("/entity/"):
            _fail("DEPENDENCY_INVALID", value)
        refs.add("entities/" + _relative(value.removeprefix("/entity/")))
    if root.parent.name != "creators":
        creator = document.get("creatorProfileId")
        if creator:
            refs.add("creators/" + _relative(str(creator)))
        sidecar = root / "creator.refs.json"
        if sidecar.is_file():
            refs.update("creators/" + _relative(value) for value in _read_json(sidecar).get("creatorRefs", []))
    return sorted(refs)


def _source_digest(document: Mapping[str, Any]) -> str:
    # 只比较原始身份/来源事实；结构别名仅在离线 cutover 快照归一，不授予资格。
    from content.release.canonical.post_transaction_assets import source_binding_refs
    attribution = dict(document.get("sourceAttribution") or {})
    attribution.pop("publicationAdmission", None)
    if attribution.get("riskAcceptanceId") is None:
        attribution.pop("riskAcceptanceId", None)
    asset_keys = ("assetId", "sha256", "sourceUrl", "collectionPageUrl", "originalAssetUrl", "sourceAssetId", "creator", "license", "termsUrl", "authorizationProof")
    return _digest_bytes(_json_bytes({
        "sourceUrls": document.get("sourceUrls"),
        "avatarAsset": document.get("avatarAsset"),
        "attribution": attribution,
        "assets": [{**{key: asset.get(key) for key in asset_keys}, "sourceAssetRefs": source_binding_refs(asset)}
                   for asset in document.get("assets", [])],
    }))


def _object_snapshot(pool: Path, ref: str) -> dict[str, Any]:
    root = pool / ref
    author = ref.startswith("creators/")
    primary = root / ("profile.json" if author else "manifest.json")
    document = _read_json(primary) if primary.is_file() else {}
    id_key = "authorId" if author else "entityId" if ref.startswith("entities/") else "contentId"
    records = []
    for path in sorted((root / "_pool/versions").glob("*.json")):
        raw = _read_json(path)
        records.append({key: raw.get(key) for key in ("objectId", "contentVersion", "objectRef", "recordSequence")})
    return {
        "objectRef": ref, "treeDigest": _tree_digest(root),
        "identity": {"objectId": document.get(id_key), "contentVersion": document.get("version")},
        "recordIdentities": records, "dependencyRefs": _dependencies(root, document),
        "sourceDigest": _source_digest(document),
    }


def _occupied_ref(relative: Path) -> str | None:
    prefix = relative.parts[0]
    if prefix not in {"creators", "entities", "posts", "tags"}:
        _fail("POOL_LAYOUT_INVALID", relative)
    if prefix == "creators" and len(relative.parts) >= 3:
        return PurePosixPath(*relative.parts[:2]).as_posix()
    if prefix not in {"entities", "posts"}:
        return None
    if "_pool" in relative.parts:
        return PurePosixPath(*relative.parts[:relative.parts.index("_pool")]).as_posix()
    return relative.parent.as_posix() if relative.name in {"manifest.json", "_entity.json"} else None


def snapshot_pool(publish_root: Path) -> dict[str, Any]:
    """只盘点原字节和占位身份；本结果不声明旧对象可迁移或 admitted。"""
    pool = _absolute(publish_root, kind="tree")
    files = _regular_tree(pool)
    refs = {ref for path in files if (ref := _occupied_ref(path.relative_to(pool)))}
    refs.update(path.parent.relative_to(pool).as_posix() for path in pool.rglob("_pool") if path.is_dir())
    roots = {pool / _relative(ref) for ref in refs}
    for root in roots:
        if roots.intersection(root.parents):
            _fail("PATH_OVERLAP", root)
    for path in files:
        relative = path.relative_to(pool)
        if relative.parts[0] != "tags" and not roots.intersection(path.parents):
            _fail("UNOWNED_POOL_BYTES", relative)
    return {"treeDigest": _tree_digest(pool), "objects": [_object_snapshot(pool, ref) for ref in sorted(refs)]}


def _inputs(plan_path: Path, expected_plan_digest: str, authorization: Mapping[str, str], operation: str) -> tuple[dict, Path, Path]:
    plan_file = _binding({"ref": str(plan_path), "digest": expected_plan_digest})
    plan = _read_json(plan_file)
    _schema(plan)
    _schema(dict(authorization), definition="binding")
    authority = _binding(authorization)
    granted = _read_json(authority)
    _schema(granted, definition="authorization")
    deletes = sorted(row["before"]["objectRef"] for row in plan["objects"] if row["action"] == "delete")
    if granted["planDigest"] != expected_plan_digest or operation not in granted["operations"] or sorted(granted["deleteObjectRefs"]) != deletes:
        _fail("AUTHORIZATION_MISMATCH", operation)
    active = _absolute(plan["publishRoot"], kind="tree")
    stage = _absolute(plan["stagingRoot"], kind="tree")
    _separate(active, stage)
    from core.paths import PUBLISH_ROOT
    _separate(stage, PUBLISH_ROOT.resolve())
    if active.stat().st_dev != stage.stat().st_dev:
        _fail("CROSS_DEVICE", stage)
    active_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in _regular_tree(active)}
    if any((p.stat().st_dev, p.stat().st_ino) in active_inodes for p in _regular_tree(stage)):
        _fail("HARDLINK_ALIAS", "staging 不能共享活跃 metadata inode")
    # plan、授权、保护集与所有证据必须在两棵池树之外。
    for path in (plan_file, authority):
        _separate(path, active)
        _separate(path, stage)
    for row in [*plan["protected"], *(e for action in plan["objects"] for e in action["evidence"])]:
        path = _binding(row)
        _separate(path, active)
        _separate(path, stage)
    return plan, active, stage


def _coverage(plan: dict, before: dict, after: dict) -> None:
    current = {row["objectRef"]: row for row in before["objects"]}
    desired = {row["objectRef"]: row for row in after["objects"]}
    before_refs = [row["before"]["objectRef"] for row in plan["objects"]]
    after_refs = [row["after"]["objectRef"] for row in plan["objects"] if row["action"] == "migrate"]
    if len(set(before_refs)) != len(before_refs) or set(before_refs) != set(current):
        _fail("COVERAGE_MISMATCH", "每个 before 对象必须且只能裁决一次")
    if not after_refs:
        _fail("EMPTY_POOL_FORBIDDEN", "不接受整池清空")
    if len(set(after_refs)) != len(after_refs) or set(after_refs) != set(desired):
        _fail("COVERAGE_MISMATCH", "完整 after 只能包含已点名 migrate 终态")
    identities = {(ref.split("/", 1)[0], row["identity"]["objectId"]) for ref, row in desired.items()}
    if len(identities) != len(desired):
        _fail("DUPLICATE_IDENTITY", "after 逻辑身份只能有一个终态")
    for action in plan["objects"]:
        _action_coverage(action, current, desired)


def _action_coverage(action: dict, current: dict, desired: dict) -> None:
    old = action["before"]
    if old != current[old["objectRef"]]:
        _fail("BEFORE_OBJECT_DRIFT", old["objectRef"])
    if action["action"] == "delete":
        decision = _read_json(_role(action, "decision", "file"))
        if decision.get("decision") != "delete" or decision.get("objectRef") != old["objectRef"] or not str(decision.get("reason") or "").strip():
            _fail("DELETE_DECISION_MISMATCH", old["objectRef"])
        return
    new = action["after"]
    if new != desired.get(new["objectRef"]):
        _fail("AFTER_OBJECT_DRIFT", new["objectRef"])
    _identity_transition(old, new)
    if not set(new["dependencyRefs"]).issubset(desired):
        _fail("DEPENDENCY_MISSING", new["objectRef"])


def _identity_transition(old: dict, new: dict) -> None:
    old_identity, new_identity = old["identity"], new["identity"]
    version = old_identity["contentVersion"]
    if not old_identity["objectId"] or not isinstance(version, int):
        _fail("BEFORE_IDENTITY_UNPROVEN", old["objectRef"])
    if new_identity["objectId"] != old_identity["objectId"] or not isinstance(new_identity["contentVersion"], int) or new_identity["contentVersion"] <= version:
        _fail("IDENTITY_VERSION_DRIFT", old["objectRef"])
    old_ref, new_ref = PurePosixPath(old["objectRef"]), PurePosixPath(new["objectRef"])
    lineage_old = old_ref.parent if old_ref.parts[0] == "posts" else old_ref
    lineage_new = new_ref.parent if new_ref.parts[0] == "posts" else new_ref
    if lineage_old != lineage_new or old["sourceDigest"] != new["sourceDigest"]:
        _fail("SOURCE_IDENTITY_DRIFT", old["objectRef"])
    for record in old["recordIdentities"]:
        if record["objectId"] != old_identity["objectId"] or record["contentVersion"] != version:
            _fail("BEFORE_IDENTITY_UNPROVEN", old["objectRef"])


def _role(action: dict, name: str, kind: str) -> Path:
    rows = [row for row in action["evidence"] if row["role"] == name and row["kind"] == kind]
    if len(rows) != 1:
        _fail("EVIDENCE_ROLE_MISSING", f"{action['before']['objectRef']}:{name}")
    return _binding(rows[0])


def _verify_migration(action: dict, stage: Path) -> None:
    ref = action["after"]["objectRef"]
    root = stage / ref
    object_type = "author" if ref.startswith("creators/") else "homepage" if ref.startswith("entities/") else "content"
    record = latest_pool_record(root, object_type)
    if not is_pool_record_admitted(record):
        _fail("OBJECT_NOT_ADMITTED", ref)
    assert_valid(record, "release", "pool_object_record", label=ref)
    for record_path in (root / "_pool/versions").glob("*.json"):
        assert_valid(_read_json(record_path), "release", "pool_object_record", label=str(record_path))
    if record["objectId"] != action["after"]["identity"]["objectId"] or record["contentVersion"] != action["after"]["identity"]["contentVersion"]:
        _fail("RECORD_IDENTITY_DRIFT", ref)
    if object_type == "author":
        # canonical profile 是 creator_projection 产物，不是 control-plane creator_profile。
        profile = _read_json(root / "profile.json")
        admission_schema = load_schema("content", "pool_admission")
        issues = validate_strict(profile.get("admission"), admission_schema["$defs"]["authorAdmission"], _root_schema=admission_schema)
        if issues:
            _fail("AUTHOR_ADMISSION_SCHEMA_INVALID", issues)
        if record["payloadDigest"] != pool_payload_digest(root):
            _fail("AUTHOR_PAYLOAD_DRIFT", ref)
        authority = _role(action, "author_authority", "file")
        evidence = _read_json(authority)
        assert_valid(evidence, "content", "author_admission_evidence", label=ref)
        if _digest_file(authority) != record["evidenceDigest"] or record["objectId"] not in evidence["authorIds"]:
            _fail("AUTHOR_EVIDENCE_DRIFT", ref)
        return
    document = _read_json(root / "manifest.json")
    if object_type == "content":
        assert_valid(document, "content", "post_manifest", label=ref)
    else:
        assert_valid(_read_json(root / "_entity.json"), "publish", "entity", label=ref)
    _verify_content_evidence(action, stage)


def _verify_content_evidence(action: dict, stage: Path) -> None:
    ref = action["after"]["objectRef"]
    root = stage / ref
    execution = _role(action, "execution", "tree")
    package_root = _role(action, "package", "tree")
    package = _verify_package(package_root, canonical_root=stage, require_target_absent=False)
    if f"{package['objectKind']}/{package['objectRef']}" != ref or package["executionId"] != execution.name:
        _fail("PACKAGE_IDENTITY_DRIFT", ref)
    if pool_payload_digest(package["objectRoot"]) != pool_payload_digest(root):
        _fail("PACKAGE_PAYLOAD_DRIFT", ref)
    _chain, review = validate_publish_review_chain(execution_id=execution.name, execution_root=execution, target_ref=ref)
    canonical_review = root / "content_review.json"
    if canonical_review.read_bytes() != (execution / ref / "5.review/content_review.json").read_bytes():
        _fail("REVIEW_BINDING_DRIFT", ref)
    manifest = _read_json(root / "manifest.json")
    if manifest.get("sourceIdentity", {}).get("executionId") != execution.name:
        _fail("EXECUTION_IDENTITY_DRIFT", ref)
    draft = execution / ref / _relative(review["draft"]["ref"])
    if _digest_file(draft) != review["draft"]["digest"]:
        _fail("REVIEW_DRAFT_DRIFT", ref)
    if draft.suffix == ".md":
        final = root / _relative(str(manifest.get("finalContentRef") or ""))
        if final.read_bytes() != draft.read_bytes():
            _fail("REVIEWED_SURFACE_DRIFT", ref)
    else:
        _verify_json_surface(execution, ref, manifest)
    from content.release.canonical.entity_transaction_sources import source_assets_by_ref
    from content.release.canonical.post_transaction_assets import source_assets
    index = source_assets_by_ref(execution) if ref.startswith("entities/") else source_assets(execution)
    validate_review_authority(review_root=root, manifest=manifest, object_kind=package["objectKind"], execution_id=execution.name, object_ref=ref, source_assets=index)


def _verify_json_surface(execution: Path, ref: str, manifest: dict) -> None:
    """复演现有纯 projection，含实际 video probe/图片 pHash；不写 execution/媒体。"""
    import json
    from content.release.canonical import final_surface_projection as projection
    from content.release.canonical.post_transaction_assets import canonical_post_asset_row
    from content.release.canonical.post_asset_identity import freeze_canonical_video_poster_identities
    targets = _read_json(execution / "0.plan/target_set.json")
    matches = [target for target_ref, target in zip(targets["targetRefs"], targets["targets"], strict=True) if target_ref == ref]
    if len(matches) != 1:
        _fail("PROJECTION_TARGET_MISMATCH", ref)
    carrier = manifest["contentType"]
    if carrier not in {"image", "video"}:
        _fail("PROJECTION_CARRIER_INVALID", carrier)
    root = execution / ref
    rows = projection._source_rows(execution, root)
    prefixes = tuple(f"{row['sourceRef'].rsplit('/', 1)[0]}/assets/" for row in rows)
    index = {key: row for key, row in projection.source_assets(execution).items() if key.startswith(prefixes)}
    compose = projection._author_intent(object_dir=root, carrier=carrier, target=matches[0], source_rows=rows, asset_index=index)
    surface = projection._post_surface(execution_root=execution, object_dir=root, target_ref=ref, target=matches[0], carrier=carrier, compose=compose, source_rows=rows)
    projected = json.loads(surface[Path("manifest.json")])
    # 验证 execution 上已保存的 surface，不能只信任 package 与刷新后的摘要互证。
    if any(not projection._same_content(root / relative, expected) for relative, expected in surface.items()):
        _fail("REVIEWED_SURFACE_DRIFT", ref)
    assets = [canonical_post_asset_row(row, asset_source=surface[Path(row["fileName"])], mime_type=row["mimeType"],
                                       object_key=row["objectKey"], source_assets_by_ref=index) for row in projected["assets"]]
    freeze_canonical_video_poster_identities(assets)
    projected["assets"] = assets
    # 只有事务身份/版本由受治理切换改变；所有 author/source/媒体投影字段必须 exact。
    for key, value in projected.items():
        if key not in {"schema", "version"} and manifest.get(key) != value:
            _fail("REVIEWED_SURFACE_DRIFT", f"{ref}:{key}")


def _validate_staging(plan: dict, stage: Path) -> dict:
    for action in plan["objects"]:
        if action["action"] == "migrate":
            _verify_migration(action, stage)
    from content.release.canonical.canonical_inventory import canonical_inventory_path
    if canonical_inventory_path(stage).exists():
        _fail("STAGING_INVENTORY_UNVERIFIED", "预验不信任可失效的磁盘索引，也不删除 caller 缓存；请使用无 sidecar 的隔离 staging")
    candidates = [{"objectRef": row["after"]["objectRef"], "manifest": _read_json(stage / row["after"]["objectRef"] / "manifest.json")} for row in plan["objects"] if row["action"] == "migrate" and not row["after"]["objectRef"].startswith("creators/")]
    query = query_pool(stage, candidates=candidates)
    if query["excluded"]:
        _fail("STAGING_QUERY_INVALID", query["excluded"])
    conflicts = [row for row in query["preflight"] if row["imageConflicts"] or row["dependencyIssues"]]
    if conflicts:
        _fail("STAGING_PREFLIGHT_INVALID", conflicts)
    invariants = validate_publish_invariants(stage)
    if invariants["status"] != "passed":
        _fail("STAGING_CLOSURE_INVALID", invariants["issues"])
    return query


def _validate_locked(plan: dict, active: Path, stage: Path) -> dict:
    before, after = snapshot_pool(active), snapshot_pool(stage)
    if before["treeDigest"] != plan["beforeDigest"]:
        _fail("BEFORE_CAS_MISMATCH", active)
    if after["treeDigest"] != plan["afterDigest"]:
        _fail("STAGING_CAS_MISMATCH", stage)
    _coverage(plan, before, after)
    query = _validate_staging(plan, stage)
    if snapshot_pool(active) != before or snapshot_pool(stage) != after:
        _fail("VALIDATION_RACE", "验证期间池字节发生变化")
    for row in [*plan["protected"], *(e for action in plan["objects"] for e in action["evidence"])]:
        _binding(row)
    return {"before": before, "after": after, "stagingQuery": query}


def dry_run_pool_cutover(*, plan_path: Path, expected_plan_digest: str, authorization: Mapping[str, str], evidence_path: Path) -> dict[str, Any]:
    """完整验证后仅 create-once 写命名证据；不写 pool、inventory 或旧 receipt。"""
    plan, active, stage = _inputs(plan_path, expected_plan_digest, authorization, "dry_run")
    destination = _absolute(evidence_path, kind="new_file")
    from core import paths
    media_root = Path(os.environ.get("QWQ_LIBRARY_ROOT") or paths.LIBRARY_ROOT).expanduser().resolve()
    for protected_root in (media_root, paths.carried_media_root().resolve(), paths.RELEASE_ROOT.resolve(), paths.REFERENCE_RELEASES_ROOT.resolve(), paths.PUBLISH_ROOT.resolve()):
        _separate(destination, protected_root)
        _separate(stage, protected_root)
    guarded = [active, stage, plan_path, Path(authorization["ref"]), *(Path(row["ref"]) for row in plan["protected"]), *(Path(row["ref"]) for action in plan["objects"] for row in action["evidence"])]
    for root in guarded:
        _separate(destination, root)
    try:
        with canonical_publish_lock(active):
            result = _validate_locked(plan, active, stage)
            _binding({"ref": str(plan_path), "digest": expected_plan_digest})
            _binding(authorization)
            _absolute(destination, kind="new_file")
            report = {"schema": "quwoquan_data.pool_cutover_dry_run.v1", "status": "validated_not_activated", "cutoverId": plan["cutoverId"], "planDigest": expected_plan_digest, "authorization": dict(authorization), "protected": plan["protected"], "objects": plan["objects"], **result,
                      "protectedScope": "caller_declared_exact_bytes", "activationRequires": "explicit_authority_and_fresh_locked_validation"}
            # O_EXCL 保留任何同名旧证据，不覆盖。失败最多留下不可作为成功凭据的局部证据。
            with destination.open("xb") as handle:
                handle.write(_json_bytes(report))
                handle.flush()
                os.fsync(handle.fileno())
            return {"report": report, "evidence": {"ref": str(destination), "digest": _digest_file(destination)}}
    except PoolCutoverError:
        raise
    except (ObjectTransactionError, OSError, TypeError, ValueError) as exc:
        _fail("VALIDATION_FAILED", str(exc))


def activate_pool_cutover(*, plan_path: Path, expected_plan_digest: str, authorization: Mapping[str, str], dry_run_evidence: Mapping[str, str]) -> dict:
    """显式原子提交；提交点之后的异常必须 inspect，不自动回滚或重复交换。"""
    from content.release.canonical.pool_cutover_activation import activate
    return activate(plan_path=plan_path, expected_plan_digest=expected_plan_digest, authorization=authorization, dry_run_evidence=dry_run_evidence)


def inspect_pool_cutover(*, plan_path: Path, expected_plan_digest: str, intent: Mapping[str, str]) -> dict:
    from content.release.canonical.pool_cutover_activation import inspect
    return inspect(plan_path=plan_path, expected_plan_digest=expected_plan_digest, intent=intent)


def cleanup_pool_cutover(*, plan_path: Path, expected_plan_digest: str, intent: Mapping[str, str], authorization: Mapping[str, str]) -> dict:
    from content.release.canonical.pool_cutover_activation import cleanup
    return cleanup(plan_path=plan_path, expected_plan_digest=expected_plan_digest, intent=intent, authorization=authorization)


__all__ = ["PoolCutoverError", "snapshot_pool", "dry_run_pool_cutover", "activate_pool_cutover", "inspect_pool_cutover", "cleanup_pool_cutover"]
