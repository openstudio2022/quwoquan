"""显式一次性 cutover 提交、只读判定与单独授权清理；没有自动恢复循环。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical import pool_cutover as contract
from content.release.canonical import pool_cutover_storage as storage
from content.release.canonical.canonical_inventory import canonical_inventory_path
from content.release.canonical.object_transaction_contract import _digest_bytes, _digest_file, _json_bytes, _read_json, _tree_digest
from content.release.canonical.object_transaction_lock import canonical_publish_lock


@contextmanager
def _locks(active: Path, stage: Path):
    # 统一路径排序避免相反 cutover 的双锁死锁；普通事务继续使用同一个 canonical 锁。
    first, second = sorted((active, stage))
    with canonical_publish_lock(first), canonical_publish_lock(second):
        yield


def _checkpoint(_name: str) -> None:
    """测试存储边界故障；运行时不执行策略或后继动作。"""


def _protected_roots() -> tuple[Path, ...]:
    from core import paths
    media = Path(os.environ.get("QWQ_LIBRARY_ROOT") or paths.LIBRARY_ROOT).expanduser().resolve()
    return media, paths.carried_media_root().resolve(), paths.RELEASE_ROOT.resolve(), paths.REFERENCE_RELEASES_ROOT.resolve(), paths.PUBLISH_ROOT.resolve()


def _context(plan: dict, active: Path, stage: Path, *, fresh: bool) -> Path:
    if "activation" not in plan:
        contract._fail("PROTECTION_AUTHORITY_REQUIRED", "需显式 auditRoot 与保护闭包 authority")
    audit = contract._absolute(plan["activation"]["auditRoot"], kind="tree")
    from core.paths import OUTPUT_ROOT
    contract._separate(audit, OUTPUT_ROOT.resolve())
    for root in (active, stage, *_protected_roots()):
        contract._separate(audit, root)
    for root in _protected_roots():
        contract._separate(stage, root)
    for root in _protected_roots()[:-1]:
        contract._separate(active, root)
    if audit.stat().st_dev != active.stat().st_dev:
        contract._fail("CROSS_DEVICE", audit)
    contract._separate(active, stage)
    for row in plan["protected"]:
        contract._separate(audit, Path(row["ref"]))
        contract._separate(active, Path(row["ref"]))
        contract._separate(stage, Path(row["ref"]))
    contract._regular_tree(audit)
    if fresh and any(audit.iterdir()):
        contract._fail("AUDIT_ROOT_NOT_EMPTY", audit)
    authority = contract._binding(plan["activation"]["protectionAuthority"])
    for root in (audit, active, stage):
        contract._separate(root, authority)
    document = _read_json(authority)
    contract._schema(document, definition="protectionAuthority")
    expected = {"cutoverId": plan["cutoverId"], "beforeDigest": plan["beforeDigest"], "afterDigest": plan["afterDigest"], "protectedDigest": _digest_bytes(_json_bytes(plan["protected"]))}
    if any(document[key] != value for key, value in expected.items()):
        contract._fail("PROTECTION_AUTHORITY_DRIFT", authority)
    _protection_coverage(plan)
    return audit


def _protection_coverage(plan: dict) -> None:
    categories = {row["category"] for row in plan["protected"]}
    if categories != {"media_library", "golden_media", "release", "receipt", "rollback", "environment_binding"}:
        contract._fail("PROTECTION_CLOSURE_INCOMPLETE", sorted(categories))
    # 媒体/历史 release 的现有根必须作为完整树声明；不从一个样本推断全保护。
    trees = {Path(row["ref"]) for row in plan["protected"] if row["kind"] == "tree"}
    for root in _protected_roots()[:-1]:
        if root.exists() and root not in trees:
            contract._fail("PROTECTION_CLOSURE_INCOMPLETE", root)


def _sidecar_paths(plan: dict, active: Path, stage: Path, audit: Path) -> None:
    from core.paths import publish_lock_path
    guarded = (active, stage, audit, *_protected_roots(), *(Path(row["ref"]) for row in plan["protected"]))
    for pool in (active, stage):
        for path in (canonical_inventory_path(pool), publish_lock_path(pool)):
            for root in guarded:
                contract._separate(path, root)
            for ancestor in (*reversed(path.parents), path):
                if ancestor.is_symlink():
                    contract._fail("SYMLINK_FORBIDDEN", ancestor)


def _recheck_evidence(plan: dict, plan_path: Path, digest: str, authorization: Mapping[str, str]) -> None:
    contract._binding({"ref": str(plan_path), "digest": digest})
    contract._binding(authorization)
    contract._binding(plan["activation"]["protectionAuthority"])
    for row in [*plan["protected"], *(e for action in plan["objects"] for e in action["evidence"])]:
        contract._binding(row)


def _invalidate_inventory(active: Path, plan: dict) -> None:
    """交换前 durable invalidation；crash 后任何新 writer 只能 bootstrap 当前完整树。"""
    cache = canonical_inventory_path(active)
    if not cache.parent.exists():
        return
    contract._absolute(cache.parent, kind="tree")
    for row in plan["protected"]:
        contract._separate(cache.parent, Path(row["ref"]))
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = cache.with_name(cache.name + suffix)
        if path.exists() or path.is_symlink():
            contract._absolute(path, kind="file")
            path.unlink()
    storage.sync_directory(cache.parent)


def _prepare(plan: dict, active: Path, stage: Path, audit: Path, digest: str, authorization: Mapping[str, str], dry_run: Mapping[str, str]) -> dict:
    storage.sync_tree(active)
    archive = storage.archive_before(active, audit / "before.tar", plan["beforeDigest"])
    storage.sync_tree(stage)
    storage.sync_directory(active.parent)
    storage.sync_directory(stage.parent)
    intent = {"schema": "quwoquan_data.pool_cutover_intent.v1", "planDigest": digest,
              "publishRoot": str(active), "stagingRoot": str(stage), "auditRoot": str(audit),
              "beforeDigest": plan["beforeDigest"], "afterDigest": plan["afterDigest"],
              "beforeIdentity": storage.identity(active), "afterIdentity": storage.identity(stage),
              "archive": archive, "authorization": dict(authorization), "dryRunEvidence": dict(dry_run)}
    contract._schema(intent, definition="intent")
    return {"document": intent, "binding": storage.write_once(audit / "intent.json", intent)}


def activate(*, plan_path: Path, expected_plan_digest: str, authorization: Mapping[str, str], dry_run_evidence: Mapping[str, str]) -> dict[str, Any]:
    plan, active, stage = contract._inputs(plan_path, expected_plan_digest, authorization, "activate")
    audit = _context(plan, active, stage, fresh=True)
    _sidecar_paths(plan, active, stage, audit)
    for path in (plan_path, Path(authorization["ref"]), Path(dry_run_evidence["ref"]), *(Path(row["ref"]) for row in plan["protected"]), *(Path(e["ref"]) for row in plan["objects"] for e in row["evidence"])):
        contract._separate(audit, path)
    contract._schema(dict(dry_run_evidence), definition="binding")
    report = _read_json(contract._binding(dry_run_evidence))
    if report.get("planDigest") != expected_plan_digest or report.get("status") != "validated_not_activated" or report.get("objects") != plan["objects"]:
        contract._fail("DRY_RUN_EVIDENCE_MISMATCH", expected_plan_digest)
    storage._rename_function()  # unsupported 平台在任何审计写入之前停止。
    with _locks(active, stage):
        result = contract._validate_locked(plan, active, stage)
        if report.get("before") != result["before"] or report.get("after") != result["after"]:
            contract._fail("DRY_RUN_EVIDENCE_MISMATCH", "snapshot")
        prepared = _prepare(plan, active, stage, audit, expected_plan_digest, authorization, dry_run_evidence)
        intent = prepared["document"]
        _checkpoint("after_intent")
        _invalidate_inventory(active, plan)
        _checkpoint("before_exchange")
        # 在不可逆提交点前最后重验完整树与全部外部证据；不读取 disposable 缓存。
        contract._validate_locked(plan, active, stage)
        _recheck_evidence(plan, plan_path, expected_plan_digest, authorization)
        contract._binding(prepared["binding"])
        contract._binding(intent["archive"])
        contract._binding(dry_run_evidence)
        if storage.identity(stage) != intent["afterIdentity"]:
            contract._fail("DIRECTORY_IDENTITY_DRIFT", stage)
        storage.rename_exact(active, stage, exchange=True, expected=intent["beforeIdentity"], destination_identity=intent["afterIdentity"])
        # 交换是唯一提交点。此后失败禁止交换回去：会覆盖并发业务或掩盖 crash outcome。
        try:
            _checkpoint("after_exchange")
            storage.sync_directory(active.parent)
            storage.sync_directory(stage.parent)
            _recheck_evidence(plan, plan_path, expected_plan_digest, authorization)
            if _tree_digest(active) != plan["afterDigest"] or _tree_digest(stage) != plan["beforeDigest"]:
                contract._fail("POST_EXCHANGE_DRIFT", active)
            storage.rename_exact(stage, audit / "retired", exchange=False, expected=intent["beforeIdentity"])
            storage.sync_directory(stage.parent)
            storage.sync_directory(audit)
            _checkpoint("after_retire")
            receipt = {"schema": "quwoquan_data.pool_cutover_activation.v1", "status": "activated", "planDigest": expected_plan_digest, "intent": prepared["binding"], "archive": intent["archive"], "beforeDigest": plan["beforeDigest"], "afterDigest": plan["afterDigest"]}
            evidence = storage.write_once(audit / "activated.json", receipt)
            return {"report": receipt, "evidence": evidence}
        except Exception as exc:
            contract._fail("COMMIT_OUTCOME_REQUIRES_INSPECTION", f"{audit / 'intent.json'}: {exc}")


def _inspection_inputs(plan_path: Path, expected_plan_digest: str, intent_binding: Mapping[str, str]) -> tuple[dict, dict, Path, Path]:
    plan = _read_json(contract._binding({"ref": str(plan_path), "digest": expected_plan_digest}))
    contract._schema(plan)
    contract._schema(dict(intent_binding), definition="binding")
    intent_file = contract._binding(intent_binding)
    intent = _read_json(intent_file)
    contract._schema(intent, definition="intent")
    active = contract._absolute(plan["publishRoot"], kind="tree")
    audit = contract._absolute(plan["activation"]["auditRoot"], kind="tree")
    if intent_file != audit / "intent.json" or intent.get("schema") != "quwoquan_data.pool_cutover_intent.v1":
        contract._fail("INTENT_MISMATCH", intent_file)
    for key, value in {"planDigest": expected_plan_digest, "publishRoot": str(active), "stagingRoot": plan["stagingRoot"], "auditRoot": str(audit), "beforeDigest": plan["beforeDigest"], "afterDigest": plan["afterDigest"]}.items():
        if intent.get(key) != value:
            contract._fail("INTENT_MISMATCH", key)
    if intent["archive"]["ref"] != str(audit / "before.tar"):
        contract._fail("INTENT_MISMATCH", "archive path")
    archive = contract._binding(intent["archive"])
    storage.verify_archive(archive, plan["beforeDigest"])
    return plan, intent, active, audit


def _tree_matches(path: Path, expected_identity: list[int], digest: str) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    contract._absolute(path, kind="tree")
    contract._regular_tree(path)
    return storage.identity(path) == expected_identity and _tree_digest(path) == digest


def _retired_paths(staged: Path, audit: Path, plan: dict, document: dict, state: str) -> tuple[list[str], list[str]]:
    exact, unverified = [], []
    for path in (staged, audit / "retired"):
        if _tree_matches(path, document["beforeIdentity"], plan["beforeDigest"]):
            exact.append(str(path))
        elif state == "activated" and path.exists():
            unverified.append(str(path))
    return exact, unverified


def inspect(*, plan_path: Path, expected_plan_digest: str, intent: Mapping[str, str]) -> dict:
    """严格只读：无锁文件创建、无缓存重建、无自动 swap/repair；不签发成功 receipt。"""
    plan, document, active, audit = _inspection_inputs(plan_path, expected_plan_digest, intent)
    contract._regular_tree(active)
    digest, inode = _tree_digest(active), storage.identity(active)
    state = "conflict"
    if (digest, inode) == (plan["beforeDigest"], document["beforeIdentity"]):
        state = "not_activated"
    elif (digest, inode) == (plan["afterDigest"], document["afterIdentity"]):
        state = "activated"
    staged = Path(plan["stagingRoot"])
    if state == "not_activated" and not _tree_matches(staged, document["afterIdentity"], plan["afterDigest"]):
        state = "conflict"
    retired, retired_unverified = _retired_paths(staged, audit, plan, document, state)
    protection_issues = []
    for row in plan["protected"]:
        try:
            contract._binding(row)
        except (OSError, contract.PoolCutoverError) as exc:
            protection_issues.append(str(exc))
    if digest != _tree_digest(active) or inode != storage.identity(active):
        state = "conflict"
    return {"status": state, "retiredPaths": retired, "unverifiedRetiredPaths": retired_unverified, "archive": document["archive"], "protectionIssues": protection_issues, "durability": "not_inferred_from_readonly_inspection"}


def cleanup(*, plan_path: Path, expected_plan_digest: str, intent: Mapping[str, str], authorization: Mapping[str, str]) -> dict:
    plan, document, active, audit = _inspection_inputs(plan_path, expected_plan_digest, intent)
    granted = _read_json(contract._binding(authorization))
    contract._schema(granted, definition="cleanupAuthorization")
    required = {"planDigest": expected_plan_digest, "intentDigest": intent["digest"], "archiveDigest": document["archive"]["digest"], "beforeDigest": plan["beforeDigest"]}
    if any(granted[key] != value for key, value in required.items()):
        contract._fail("CLEANUP_AUTHORIZATION_MISMATCH", audit)
    _context(plan, active, Path(plan["stagingRoot"]), fresh=False)
    _sidecar_paths(plan, active, Path(plan["stagingRoot"]), audit)
    with _locks(active, Path(plan["stagingRoot"])):
        state = inspect(plan_path=plan_path, expected_plan_digest=expected_plan_digest, intent=intent)
        if state["status"] != "activated" or state["protectionIssues"] or state["unverifiedRetiredPaths"] or len(state["retiredPaths"]) != 1:
            contract._fail("CLEANUP_STATE_CONFLICT", state)
        retired = Path(state["retiredPaths"][0])
        for root in (active, *_protected_roots(), *(Path(row["ref"]) for row in plan["protected"])):
            contract._separate(retired, root)
        contract._separate(retired, Path(authorization["ref"]))
        contract._binding(authorization)
        contract._absolute(audit / "cleanup.json", kind="new_file")
        contract._absolute(audit / ".cleanup.json.writing", kind="new_file")
        storage.remove_exact_tree(retired, plan["beforeDigest"], document["beforeIdentity"])
        result = {"schema": "quwoquan_data.pool_cutover_cleanup_result.v1", "planDigest": expected_plan_digest, "removedTree": str(retired), "archive": document["archive"], "authorization": dict(authorization)}
        return {"report": result, "evidence": storage.write_once(audit / "cleanup.json", result)}
