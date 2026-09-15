"""源分配current只读核验：expected由部署调用层独立提供，不从receipt反填。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import ContentAccountClosureRuntimeSourceCreation
from quwoquan_ops.cli.lib.output_paths import _read_secure_bytes
from quwoquan_ops.cli.lib.source_allocation import (
    SourceAllocationError, _digest, _identity, _pg_credentials, _redis_credentials,
    managed_binding_ids, readback, validate_target,
)


def _material_bytes(root: Path, name: str) -> bytes:
    if not root.is_absolute() or root.resolve() != root or Path(name).name != name:
        raise SourceAllocationError("unsafe source material path")
    for directory in (root, *root.parents):
        info = directory.stat(follow_symlinks=False)
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}:
            raise SourceAllocationError("untrusted source material ancestor")
        if mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise SourceAllocationError("writable source material ancestor")
    before = (root/name).stat(follow_symlinks=False)
    root_info = root.stat(follow_symlinks=False)
    if root_info.st_uid != os.geteuid() or stat.S_IMODE(root_info.st_mode) != 0o700 or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > 1 << 20:
        raise SourceAllocationError("source material permission/link mismatch")
    raw = _read_secure_bytes(root/name, label="source material")
    after = (root/name).stat(follow_symlinks=False)
    identity = lambda value: (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_uid,value.st_gid,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
    if raw is None or identity(before) != identity(after) or root_info != root.stat(follow_symlinks=False):
        raise SourceAllocationError("source material changed during read")
    return raw


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceAllocationError("duplicate source material JSON key")
        result[key] = value
    return result


def verify_source_current(*, expected, binding, material_root, receipt_digest, pg_admin, redis_admin, old_pg_dsn, old_redis):
    """读回create-once receipt/key及现役权限；正常源增长不重验初始空集合。

    receipt_digest必须由现役部署current pin提供；本函数没有写入或补材料分支。
    """
    canonical = validate_target(expected, expected, binding)
    raw = _material_bytes(material_root,"source-creation.json")
    if "sha256:"+hashlib.sha256(raw).hexdigest() != receipt_digest:
        raise SourceAllocationError("current source receipt digest differs")
    json.loads(raw, object_pairs_hook=_unique_object)
    receipt = ContentAccountClosureRuntimeSourceCreation.model_validate_json(raw)
    pairs = ((receipt.environment,expected.environment),(receipt.target,expected.target),(receipt.candidateDigest,expected.candidate_digest),(receipt.dataPlaneBindingDigest,expected.data_plane_digest),(receipt.producerResourceRef,expected.producer_resource),(receipt.producerNamespace,expected.database),(receipt.sourceResourceRef,expected.source_resource),(receipt.sourceNamespace,expected.source_namespace),(receipt.producerRole,expected.role),(receipt.sourceAclUser,expected.acl_user),(receipt.allocationAttemptId,material_root.name))
    if any(actual != wanted for actual,wanted in pairs) or receipt.producerBindingDigest != _digest(canonical["bindings"]):
        raise SourceAllocationError("current source deployment binding differs")
    pg_key = _material_bytes(material_root,"postgres.key").decode("ascii")
    redis_key = _material_bytes(material_root,"redis.key").decode("ascii")
    if len(pg_key) < 64 or len(redis_key) < 64 or pg_key == redis_key:
        raise SourceAllocationError("source credentials not independent")
    pg_identity = _identity(pg_key,"quwoquan/source-allocation/postgres")
    redis_identity = _identity(redis_key,"quwoquan/source-allocation/redis")
    ids = managed_binding_ids(expected,pg_identity,redis_identity,canonical)
    if (receipt.producerCredentialIdentity,receipt.sourceCredentialIdentity) != (pg_identity,redis_identity) or (receipt.producerManagedAllocationBindingId,receipt.sourceManagedAllocationBindingId) != ids:
        raise SourceAllocationError("current source credential/binding identity differs")
    dsn = _pg_credentials(pg_admin,expected.database,expected.role,pg_key)
    source = _redis_credentials(redis_admin,expected.acl_user,redis_key)
    try:
        state = readback(expected,pg_admin,redis_admin,dsn,source,old_pg_dsn,old_redis,initial=False)
    finally:
        source.close()
    old_user = str(old_redis.connection_pool.connection_kwargs.get("username") or "default")
    if receipt.rejectedProducerRole != state["rejectedProducerRole"] or receipt.rejectedSourceAclUser != old_user:
        raise SourceAllocationError("source rejected principal binding differs")
    if raw != _material_bytes(material_root,"source-creation.json") or pg_key.encode() != _material_bytes(material_root,"postgres.key") or redis_key.encode() != _material_bytes(material_root,"redis.key"):
        raise SourceAllocationError("source current changed during verification")
    return receipt
