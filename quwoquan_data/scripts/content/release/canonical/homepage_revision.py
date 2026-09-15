"""显式单对象事实修正：新审核、新版本，保留旧包与逻辑身份。"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from content.release.canonical.aggregate_release_closure import object_locations
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.content_pool_record import latest_pool_record, pool_payload_digest
from content.release.canonical.object_transaction import build_entity_object_transaction_package
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError, _digest_bytes, _json_bytes, _read_json, _safe_rel,
    _tree_digest, _verify_package, canonical_transaction_id,
)
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.publish_object import _review_approved, _target_object
from core import paths
from core.schema import assert_valid


def _identity(root: Path, logical: str, version: int) -> dict:
    manifest = _read_json(root / "manifest.json")
    record = latest_pool_record(root, "homepage")
    if (manifest.get("entityRef") != "/entity/" + logical
            or manifest.get("version") != version or not manifest.get("entityId")
            or not record or record.get("objectId") != manifest["entityId"]
            or record.get("objectRef") != logical or record.get("contentVersion") != version):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision manifest/record binding")
    return manifest


def _before(publish: Path, logical: str, version: int, digest: str):
    matches = object_locations(publish, "entities").get(logical, [])
    if not matches or any(type(v) is not int or v < 1 for v, _ in matches):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision target absent/invalid")
    versions = [v for v, _ in matches]
    if len(set(versions)) != len(versions) or version not in versions:
        raise ObjectTransactionError("DATA.POOL.VERSION_CONFLICT: revision before version")
    old = next(root for v, root in matches if v == version)
    manifest = _identity(old, logical, version)
    if pool_payload_digest(old) != digest:
        raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT: revision before")
    for v, root in matches:
        if _identity(root, logical, v)["entityId"] != manifest["entityId"]:
            raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision history")
    return old, manifest, max(versions)


def _reviewed_target(execution_id: str, logical: str, old_manifest: dict):
    root = paths.execution_root(execution_id)
    run = _read_json(root / "execution_manifest.json")
    if run.get("retryOf") is not None or execution_id == old_manifest.get("executionId"):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision requires fresh execution")
    targets = _read_json(root / "0.plan/target_set.json")
    assert_valid(targets, "execution", "target_set")
    rows = [(ref, row) for ref, row in zip(targets["targetRefs"], targets["targets"], strict=True)
            if row.get("entityRef") == "/entity/" + logical]
    if targets.get("carrier") != "homepage" or len(rows) != 1:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision target ref mismatch")
    process_ref, row = rows[0]
    if row.get("entityId") != old_manifest["entityId"]:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision target ID mismatch")
    _, canonical, object_dir, target, carrier = _target_object(execution_id, process_ref)
    _review_approved(execution_id, object_dir, expected_object_ref=process_ref, target=target, carrier=carrier)
    return root, canonical, object_dir


def _input_digest(root: Path, object_dir: Path, request: dict) -> str:
    # 只绑定本次已封存输入与成品，排除会新增的事务 evidence，重放仍逐字核对来源和 receipt。
    return _digest_bytes(_json_bytes({**request, "executionManifest": _read_json(root / "execution_manifest.json"),
        "inputs": {name: _tree_digest(root / name) for name in ("0.plan", "sources", "_shared/receipts")},
        "object": _tree_digest(object_dir)}))


def _apply_revision(*, publish, output, package_root, transaction_id, old, old_digest, recheck):
    before = load_or_bootstrap_inventory(publish)["stats"]["merkleRoot"]
    audit = audit_object_transaction(publish_root=publish, output_root=output, package_root=package_root,
                                    transaction_id=transaction_id, expected_canonical_merkle=before)
    recheck()
    if _tree_digest(old) != old_digest:
        raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT: revision before apply")
    return apply_object_transaction(publish_root=publish, output_root=output, package_root=package_root,
        transaction_id=transaction_id, dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]))


def revise_homepage(*, execution_id: str, target_ref: str, expected_current_version: int,
                    expected_payload_digest: str, reason: str) -> dict:
    """调用前由宿主确认 exact 授权，本函数不签发授权或语义审核。"""
    relative = _safe_rel(target_ref, label="revision.targetRef")
    if (relative.as_posix() != target_ref or relative.parts[0] != "entities" or len(relative.parts) < 2
            or type(expected_current_version) is not int or expected_current_version < 1
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_payload_digest) or not reason.strip()):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision input")
    logical = relative.relative_to("entities").as_posix()
    publish, output = paths.PUBLISH_ROOT, paths.OUTPUT_ROOT
    with canonical_publish_lock(publish):
        old, old_manifest, latest = _before(publish, logical, expected_current_version, expected_payload_digest)
        old_digest = _tree_digest(old)
        root, canonical, object_dir = _reviewed_target(execution_id, logical, old_manifest)
        transaction_id = canonical_transaction_id(execution_id=execution_id, object_kind="entities", object_ref=canonical)
        package_root = root / "evidence/object-transactions" / transaction_id
        version = expected_current_version + 1
        for prior_version, prior_root in object_locations(publish, "entities").get(logical, []):
            if prior_version < version and _read_json(prior_root / "manifest.json").get("executionId") == execution_id:
                raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision execution already used")
        if latest != expected_current_version and not (latest == version and package_root.is_dir()):
            raise ObjectTransactionError("DATA.POOL.VERSION_CONFLICT: revision stale current")
        request = {"executionId": execution_id, "targetRef": target_ref, "expectedCurrentVersion": expected_current_version,
                   "expectedPayloadDigest": expected_payload_digest, "reason": reason}
        digest = _input_digest(root, object_dir, request)
        # 即使有旧包也从新 execution 重新投影，不能靠存在性或重算旧 v1 摘要冒充本次成品。
        package_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".revision-", dir=package_root.parent) as temporary:
            candidate = Path(temporary) / "package"
            package = build_entity_object_transaction_package(execution_root=root, object_ref="/entity/" + canonical,
                transaction_id=transaction_id, package_root=candidate, version=version,
                input_payload_digest=digest, publish_root=publish)
            verified = _verify_package(candidate, canonical_root=publish, require_target_absent=False)
            new_manifest = _identity(candidate / "object", logical, version)
            if new_manifest["entityId"] != old_manifest["entityId"] or new_manifest["executionId"] != execution_id:
                raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: revision package identity")
            if package_root.exists():
                if _tree_digest(package_root) != _tree_digest(candidate):
                    raise ObjectTransactionError("DATA.POOL.VERSION_CONFLICT: revision input/package drift")
            else:
                candidate.rename(package_root)
        destination = publish / verified["objectPath"]
        idempotent = destination.exists()
        def recheck():
            _, _, current = _before(publish, logical, expected_current_version, expected_payload_digest)
            if current != expected_current_version or _input_digest(root, object_dir, request) != digest:
                raise ObjectTransactionError("DATA.POOL.VERSION_CONFLICT: revision pre-apply drift")
            _reviewed_target(execution_id, logical, old_manifest)
        if idempotent:
            if latest != version or _tree_digest(destination) != _tree_digest(package_root / "object"):
                raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT: revision replay")
            _identity(destination, logical, version)
        else:
            _apply_revision(publish=publish, output=output, package_root=package_root, transaction_id=transaction_id,
                            old=old, old_digest=old_digest, recheck=recheck)
        if _tree_digest(destination) != _tree_digest(package_root / "object"):
            raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT: revision readback")
        return {"transactionId": transaction_id, "executionId": execution_id, "canonicalObjectRef": target_ref,
                "canonicalObjectPath": package["target"]["objectPath"], "contentVersion": version,
                "objectClosureDigest": package["objectClosureDigest"], "payloadDigest": pool_payload_digest(destination),
                "status": "published", "idempotent": idempotent}


def handle_revise_homepage(args) -> None:
    try:
        result = revise_homepage(execution_id=args.execution_id, target_ref=args.target_ref,
            expected_current_version=args.expected_current_version,
            expected_payload_digest=args.expected_payload_digest, reason=args.reason)
    except (ObjectTransactionError, OSError, ValueError, TypeError) as error:
        raise SystemExit(f"[release object-transaction revise-homepage] GATE_BLOCK {error}") from error
    print(json.dumps(result, ensure_ascii=False, indent=2))
