"""Content account-closure runtime current 的生产只读验证器。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import (
    ContentAccountClosureRuntimeCollection,
    ContentAccountClosureRuntimeEvidence,
    ContentAccountClosureRuntimeEvidenceRef,
    ContentAccountClosureRuntimeSource,
    ContentAccountClosureRuntimeSourcePartition,
)
from quwoquan_ops.cli.lib.source_allocation_current import _material_bytes, verify_source_current

COLLECTIONS = tuple(sorted((
    "user_account_closed_inbox", "user_account_closed_failures",
    "user_account_closed_search_work", "user_account_closed_media_artifact_work",
    "closed_account_subjects", "closed_account_subject_tombstones",
    "content_user_account_restrictions", "content_user_account_restriction_inbox",
    "content_user_account_restriction_watermarks",
)))

class ContentAccountClosureRuntimeError(RuntimeError):
    pass

@dataclass(frozen=True)
class ContentAccountClosureTarget:
    environment: str
    target: str
    candidate_digest: str
    data_plane_binding_digest: str
    resource_ref: str
    namespace: str
    startup_attempt_id: str
    runtime_generation: str

class MongoReadback(Protocol):
    @property
    def name(self) -> str: ...
    def command(self, command: dict) -> dict: ...

class SourceCurrentVerifier(Protocol):
    def __call__(self, **kwargs): ...


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _uuid(value) -> str:
    raw = bytes(value) if isinstance(value, (bytes, bytearray, memoryview)) else b""
    if len(raw) != 16:
        raise ContentAccountClosureRuntimeError("account closure collection UUID unavailable")
    return "mongodb-collection-uuid:" + raw.hex()


def _operation_time(value):
    if isinstance(value, bool) or not isinstance(getattr(value, "time", None), int) or not isinstance(getattr(value, "inc", None), int):
        raise ContentAccountClosureRuntimeError("account closure majority watermark unavailable")
    return value


def _bson_rows(rows: list) -> bytes:
    try:
        from bson.json_util import CANONICAL_JSON_OPTIONS, dumps
        return dumps(rows, json_options=CANONICAL_JSON_OPTIONS, sort_keys=True, separators=(",", ":")).encode()
    except ImportError:
        return _canonical(rows)


def _collection_rows(database: MongoReadback) -> list[dict]:
    specs = database.command({"listCollections": 1, "nameOnly": False}).get("cursor", {}).get("firstBatch", [])
    identities = {row.get("name"): _uuid(row.get("info", {}).get("uuid")) for row in specs if row.get("name") in COLLECTIONS}
    if tuple(sorted(identities)) != COLLECTIONS:
        raise ContentAccountClosureRuntimeError("account closure nine-collection identity differs")
    result = []
    for name in COLLECTIONS:
        reply = database.command({"aggregate": name, "pipeline": [{"$sort": {"_id": 1}}], "cursor": {}, "readConcern": {"level": "majority"}})
        rows = reply.get("cursor", {}).get("firstBatch")
        if not isinstance(rows, list):
            raise ContentAccountClosureRuntimeError("account closure full readback unavailable")
        watermark = _operation_time(reply.get("operationTime"))
        second = database.command({"aggregate": name, "pipeline": [{"$sort": {"_id": 1}}], "cursor": {}, "readConcern": {"level": "majority", "afterClusterTime": watermark}})
        second_rows = second.get("cursor", {}).get("firstBatch")
        second_watermark = _operation_time(second.get("operationTime"))
        raw = _bson_rows(rows)
        if raw != _bson_rows(second_rows) or (second_watermark.time, second_watermark.inc) < (watermark.time, watermark.inc):
            raise ContentAccountClosureRuntimeError("account closure collection watermark/readback differs")
        result.append({"collection": name, "physicalInstanceId": identities[name], "recordCount": len(rows), "canonicalDigest": _digest(raw)})
    return result



def create_content_account_closure_runtime(*, expected: ContentAccountClosureTarget, database: MongoReadback,
    material_root: Path, subject_key_ref: str, source_expected, source_binding: dict, source_current,
    connection_factory, now=None) -> ContentAccountClosureRuntimeEvidenceRef:
    """独占创建九集合并以真实 UUID/majority readback形成 canonical owner evidence。"""
    source_root = Path(source_current.materialRoot.path)
    source_evidence = source_current.sourceCreation
    pg = redis_admin = old_redis = None
    try:
        pg = connection_factory.postgres("QWQ_SOURCE_PG_ADMIN_DSN")
        redis_admin = connection_factory.redis("QWQ_SOURCE_REDIS_ADMIN_URL")
        old_redis = connection_factory.redis("QWQ_SOURCE_OLD_REDIS_URL")
        receipt = verify_source_current(expected=source_expected, binding=source_binding, material_root=source_root,
            receipt_digest=source_evidence.digest, pg_admin=pg, redis_admin=redis_admin,
            old_pg_dsn=connection_factory.text("QWQ_SOURCE_OLD_PG_DSN"), old_redis=old_redis)
    finally:
        for value in (old_redis, redis_admin, pg):
            if value is not None:
                try: value.close()
                except Exception: pass
    specs = database.command({"listCollections": 1, "nameOnly": True}).get("cursor", {}).get("firstBatch", [])
    if any(row.get("name") in COLLECTIONS for row in specs):
        raise ContentAccountClosureRuntimeError("existing account closure collection cannot receive new-runtime evidence")
    for name in COLLECTIONS:
        database.command({"create": name})
    rows = _collection_rows(database)
    if any(row["recordCount"] != 0 for row in rows):
        raise ContentAccountClosureRuntimeError("new account closure collection is not empty")
    key = _material_bytes(material_root, subject_key_ref)
    key_identity = "sha256:" + hashlib.sha256(hmac.digest(key, b"quwoquan/content.account-closure/runtime/key-identity", "sha256")).hexdigest()
    source = ContentAccountClosureRuntimeSource(
        mode="new_source", resourceRef=receipt.sourceResourceRef, namespace=receipt.sourceNamespace,
        managedAllocationBindingId=receipt.sourceManagedAllocationBindingId, stream="events.user.account",
        consumerGroup=source_expected.consumer_group, producerBindingDigest=receipt.producerBindingDigest,
        sourceCreation=ContentAccountClosureRuntimeEvidenceRef.model_validate(source_evidence.model_dump()), recovery=None,
        partitions=[ContentAccountClosureRuntimeSourcePartition(partition="events.user.account", firstAvailablePosition="0-0",
            frozenThrough="0-0", deliveredThrough="0-0", appliedThrough="0-0", pendingCount=0, entryCount=0, canonicalDigest=_digest(b"[]"))],
    )
    value = ContentAccountClosureRuntimeEvidence(
        environment=expected.environment, target=expected.target, candidateDigest=expected.candidate_digest,
        dataPlaneBindingDigest=expected.data_plane_binding_digest, resourceRef=expected.resource_ref, namespace=expected.namespace,
        allocationAttemptId=expected.startup_attempt_id, runtimeGeneration=expected.runtime_generation,
        subjectHmacKeyIdentity=key_identity, source=source,
        collections=[ContentAccountClosureRuntimeCollection.model_validate(row) for row in rows],
        recordCount=0, canonicalDigest=_digest(_canonical(rows)), initializedAt=now or datetime.now(timezone.utc),
    )
    raw = _canonical(value.model_dump(mode="json")); path = material_root / "content-account-closure-runtime.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    return ContentAccountClosureRuntimeEvidenceRef(ref=path.name, digest=_digest(raw))

def verify_content_account_closure_current(*, expected: ContentAccountClosureTarget,
    evidence: ContentAccountClosureRuntimeEvidenceRef, material_root: Path,
    database: MongoReadback, subject_key_ref: str, source_expected, source_binding: dict,
    source_material_root: Path, pg_admin, redis_admin, old_pg_dsn: str, old_redis,
    source_verifier: SourceCurrentVerifier = verify_source_current) -> ContentAccountClosureRuntimeEvidence:
    """核对 exact evidence、九集合全量闭包、subject key 与 source current。"""
    if evidence.ref != "content-account-closure-runtime.json":
        raise ContentAccountClosureRuntimeError("account closure canonical evidence ref differs")
    raw = _material_bytes(material_root, evidence.ref)
    if _digest(raw) != evidence.digest:
        raise ContentAccountClosureRuntimeError("account closure evidence digest differs")
    try:
        current = ContentAccountClosureRuntimeEvidence.model_validate_json(raw)
    except Exception as error:
        raise ContentAccountClosureRuntimeError("account closure evidence is invalid") from error
    if raw != _canonical(current.model_dump(mode="json")):
        raise ContentAccountClosureRuntimeError("account closure evidence is not canonical exact bytes")
    pairs = ((current.environment, expected.environment), (current.target, expected.target),
        (current.candidateDigest, expected.candidate_digest), (current.dataPlaneBindingDigest, expected.data_plane_binding_digest),
        (current.resourceRef, expected.resource_ref), (current.namespace, expected.namespace),
        (current.allocationAttemptId, expected.startup_attempt_id), (current.runtimeGeneration, expected.runtime_generation))
    if any(a != b for a, b in pairs) or database.name != expected.namespace:
        raise ContentAccountClosureRuntimeError("account closure deployment binding differs")
    key = _material_bytes(material_root, subject_key_ref)
    if len(key) < 32:
        raise ContentAccountClosureRuntimeError("account closure subject key unavailable")
    key_identity = "sha256:" + hashlib.sha256(hmac.digest(key, b"quwoquan/content.account-closure/runtime/key-identity", "sha256")).hexdigest()
    if current.subjectHmacKeyIdentity != key_identity:
        raise ContentAccountClosureRuntimeError("account closure subject key identity differs")
    actual_collections = _collection_rows(database)
    if [row.model_dump(mode="json") for row in current.collections] != actual_collections:
        raise ContentAccountClosureRuntimeError("account closure collection readback differs")
    if current.recordCount != sum(row["recordCount"] for row in actual_collections) or current.canonicalDigest != _digest(_canonical(actual_collections)):
        raise ContentAccountClosureRuntimeError("account closure root closure differs")
    source = current.source
    if source.mode != "new_source" or source.sourceCreation is None or source.recovery is not None:
        raise ContentAccountClosureRuntimeError("account closure source recovery is not verifiable")
    try:
        source_receipt = source_verifier(expected=source_expected, binding=source_binding,
            material_root=source_material_root, receipt_digest=source.sourceCreation.digest,
            pg_admin=pg_admin, redis_admin=redis_admin, old_pg_dsn=old_pg_dsn, old_redis=old_redis)
    except Exception as error:
        raise ContentAccountClosureRuntimeError("account closure source current verification failed") from error
    if source.sourceCreation.ref != "source-creation.json" or (
        source.resourceRef, source.namespace, source.managedAllocationBindingId, source.producerBindingDigest
    ) != (source_receipt.sourceResourceRef, source_receipt.sourceNamespace,
         source_receipt.sourceManagedAllocationBindingId, source_receipt.producerBindingDigest):
        raise ContentAccountClosureRuntimeError("account closure source current binding differs")
    if len(source.partitions) != 1:
        raise ContentAccountClosureRuntimeError("account closure source partition differs")
    partition = source.partitions[0]
    if (partition.partition, partition.firstAvailablePosition, partition.frozenThrough,
        partition.deliveredThrough, partition.appliedThrough, partition.pendingCount,
        partition.entryCount, partition.canonicalDigest) != ("events.user.account", "0-0", "0-0", "0-0", "0-0", 0, 0, _digest(b"[]")):
        raise ContentAccountClosureRuntimeError("account closure new source closure differs")
    if raw != _material_bytes(material_root, evidence.ref) or key != _material_bytes(material_root, subject_key_ref):
        raise ContentAccountClosureRuntimeError("account closure current changed during verification")
    return current
