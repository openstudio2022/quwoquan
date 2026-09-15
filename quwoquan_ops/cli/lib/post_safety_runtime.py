"""Content Post safety runtime 的环境 owner 创建、发布与严格读回。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Protocol
from uuid import UUID

from quwoquan_ops.ci.environment_scheduler import dsse_pae
from quwoquan_ops.cli.lib.evidence_signing import (
    DEFAULT_KEYRING_PATH, ENVIRONMENT_OPS_IDENTITY, ed25519_environment_verifier,
    ed25519_signer, key_root, load_keyring,
)
from quwoquan_ops.cli.lib.output_paths import (
    post_safety_startup_material_path, post_safety_startup_material_root,
)


AUTHORIZATION_PAYLOAD_TYPE = "application/vnd.quwoquan.post-safety-runtime-authorization.v1+json"
from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
    PostSafetyAccountClosureAuthorityDescriptor,
    PostSafetyDeploymentStartupMaterial,
    PostSafetyRuntimeAuthorization,
    PostSafetyRuntimeBinding,
    PostSafetyContentMongoAuthorityDescriptor,
    PostSafetyMaterialRootLocator,
    PostSafetySecretRefDescriptor,
    PostSafetySourceAllocationCurrentDescriptor,
    PostSafetyRuntimeClosure,
    PostSafetyRuntimeCreationReceipt,
    PostSafetyRuntimeCurrentBinding,
    PostSafetyRuntimeEvidence,
    PostSafetyRuntimeFact,
)


class PostSafetyRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PostSafetyTarget:
    environment: str
    target: str
    candidate_digest: str
    data_plane_binding_digest: str
    resource_ref: str
    namespace: str
    runtime_generation: str
    allocation_attempt_id: str


class MongoOwner(Protocol):
    """由受管连接实现；command 必须到达目标 MongoDB。"""
    @property
    def name(self) -> str: ...
    def command(self, command: dict) -> dict: ...


class RuntimeAuthority(Protocol):
    """环境控制面 authority；只核验 startup material 点名的 owner exact evidence。"""
    def verify_authorization(self, target: PostSafetyTarget, evidence: PostSafetyRuntimeEvidence) -> bytes: ...
    def account_closure(self, target: PostSafetyTarget, evidence: PostSafetyRuntimeEvidence) -> PostSafetyRuntimeClosure: ...
    def verify_evidence(self, evidence: PostSafetyRuntimeEvidence) -> bytes: ...


class DeploymentStartupMaterialOwner(Protocol):
    """既有 deployment/startup material 的 exact-bytes CAS port。"""
    def compare_and_swap(self, expected: bytes, replacement: bytes) -> None: ...


class FileDeploymentStartupMaterialOwner:
    """Canonical startup path 的 create-once/CAS production adapter。"""
    def __init__(self, target: str):
        self.target = target
        self.path = post_safety_startup_material_path(target)

    def create_once(self, raw: bytes) -> None:
        root = post_safety_startup_material_root(self.target)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        if root != self.path.parent:
            raise PostSafetyRuntimeError("startup material canonical root differs")
        _write_once(root, self.path.name, raw)

    def read(self) -> bytes:
        return _read_once(self.path.parent, ref=self.path.name)

    def compare_and_swap(self, expected: bytes, replacement: bytes) -> None:
        current = self.read()
        if current != expected:
            raise PostSafetyRuntimeError("startup material CAS differs")
        directory, _ = _open_root(self.path.parent)
        temporary = ".startup.json.cas"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as handle:
                handle.write(replacement); handle.flush(); os.fsync(handle.fileno())
            if self.read() != expected:
                raise PostSafetyRuntimeError("startup material CAS differs")
            os.replace(temporary, self.path.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try: os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError: pass
            os.close(directory)


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _canonical_model(value) -> bytes:
    """按 generated DTO 声明顺序编码，与 Go json.Marshal 对齐。"""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def verify_runtime_authorization(*, raw: bytes, evidence: PostSafetyRuntimeEvidence,
    target: PostSafetyTarget, expected_predecessor: PostSafetyRuntimeEvidence,
    keyring_path: Path = DEFAULT_KEYRING_PATH) -> PostSafetyRuntimeAuthorization:
    if _digest(raw) != evidence.digest:
        raise PostSafetyRuntimeError("authorization evidence digest differs")
    try:
        authorization = PostSafetyRuntimeAuthorization.model_validate_json(raw)
    except Exception as error:
        raise PostSafetyRuntimeError("authorization evidence is invalid") from error
    payload = authorization.model_dump(mode="json", exclude={"signature"})
    if raw != _canonical_model(authorization.model_dump(mode="json")):
        raise PostSafetyRuntimeError("authorization evidence is not canonical exact bytes")
    pairs = ((authorization.environment, target.environment), (authorization.target, target.target),
        (authorization.candidateDigest, target.candidate_digest),
        (authorization.dataPlaneBindingDigest, target.data_plane_binding_digest),
        (authorization.startupAttemptId, target.allocation_attempt_id),
        (authorization.runtimeGeneration, target.runtime_generation))
    if any(a != b for a, b in pairs) or authorization.action != "initialize_post_safety_runtime":
        raise PostSafetyRuntimeError("authorization target/action differs")
    if authorization.authorityIdentity != ENVIRONMENT_OPS_IDENTITY or authorization.evidencePredecessor != expected_predecessor:
        raise PostSafetyRuntimeError("authorization authority/predecessor differs")
    verifier = ed25519_environment_verifier(load_keyring(keyring_path), [ENVIRONMENT_OPS_IDENTITY])
    if not verifier(authorization.authorityIdentity, dsse_pae(AUTHORIZATION_PAYLOAD_TYPE, _canonical(payload)), authorization.signature):
        raise PostSafetyRuntimeError("authorization signature invalid")
    return authorization


class ProductionRuntimeAuthority:
    """既有 keyring + owner current verifier 的生产 authority adapter；不含签发能力。"""
    def __init__(self, *, authorization_root: Path, account_closure_evidence: PostSafetyRuntimeEvidence,
        account_closure_verifier, keyring_path: Path = DEFAULT_KEYRING_PATH):
        self.authorization_root = authorization_root
        self.account_closure_evidence = account_closure_evidence
        self.account_closure_verifier = account_closure_verifier
        self.keyring_path = keyring_path

    def verify_evidence(self, evidence: PostSafetyRuntimeEvidence) -> bytes:
        return _read_once(self.authorization_root, evidence)

    def verify_authorization(self, target: PostSafetyTarget, evidence: PostSafetyRuntimeEvidence) -> bytes:
        raw = self.verify_evidence(evidence)
        verify_runtime_authorization(raw=raw, evidence=evidence, target=target,
            expected_predecessor=self.account_closure_evidence, keyring_path=self.keyring_path)
        return raw

    def account_closure(self, target: PostSafetyTarget, evidence: PostSafetyRuntimeEvidence) -> PostSafetyRuntimeClosure:
        if evidence != self.account_closure_evidence:
            raise PostSafetyRuntimeError("account closure owner evidence differs")
        verified = self.account_closure_verifier()
        return PostSafetyRuntimeClosure(kind="account_closure", recordCount=verified.recordCount,
            canonicalDigest=verified.canonicalDigest, watermark=evidence.digest, ownerEvidence=evidence)


class ManagedAuthorityConnectionFactory:
    """按 descriptor secretRef 解析受管连接；startup可传内存映射且不记录原文。"""
    def __init__(self, managed_connections: dict[str, str] | None = None):
        self.managed_connections = dict(managed_connections or {})

    def _environment_secret(self, reference: str) -> str:
        if not reference or not reference.replace("_", "A").isalnum() or reference.upper() != reference:
            raise PostSafetyRuntimeError("managed connection secretRef is invalid")
        value = self.managed_connections.get(reference, "") or os.environ.get(reference, "")
        if not value:
            raise PostSafetyRuntimeError("managed connection secret is unavailable")
        return value

    def relative_secret(self, root: Path, reference: str) -> bytes:
        return _read_once(root, ref=reference)

    def mongo(self, reference: str, database: str):
        try:
            from pymongo import MongoClient
            client = MongoClient(self._environment_secret(reference))
            return client, client[database]
        except PostSafetyRuntimeError:
            raise
        except Exception as error:
            raise PostSafetyRuntimeError("managed Mongo connection unavailable") from error

    def postgres(self, reference: str):
        try:
            import psycopg
            return psycopg.connect(self._environment_secret(reference), autocommit=True)
        except PostSafetyRuntimeError:
            raise
        except Exception as error:
            raise PostSafetyRuntimeError("managed Postgres connection unavailable") from error

    def redis(self, reference: str):
        try:
            import redis
            return redis.Redis.from_url(self._environment_secret(reference), decode_responses=True)
        except PostSafetyRuntimeError:
            raise
        except Exception as error:
            raise PostSafetyRuntimeError("managed Redis connection unavailable") from error

    def text(self, reference: str) -> str:
        return self._environment_secret(reference)


class ProductionAccountClosureAuthority(ProductionRuntimeAuthority):
    """accountClosureAuthority descriptor 到 owner current verifier 的生产组合 adapter。"""
    def __init__(self, *, target: PostSafetyTarget, descriptor: PostSafetyAccountClosureAuthorityDescriptor,
        authorization_root: Path, source_expected, source_binding: dict,
        connection_factory: ManagedAuthorityConnectionFactory | None = None,
        keyring_path: Path = DEFAULT_KEYRING_PATH):
        from quwoquan_ops.cli.lib.content_account_closure_runtime import (
            ContentAccountClosureTarget, verify_content_account_closure_current,
        )
        from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import ContentAccountClosureRuntimeEvidenceRef
        from quwoquan_ops.cli.lib.source_allocation_current import _material_bytes, verify_source_current
        identity = (descriptor.environment, descriptor.target, descriptor.candidateDigest,
            descriptor.dataPlaneBindingDigest, descriptor.startupAttemptId, descriptor.runtimeGeneration)
        expected_identity = (target.environment, target.target, target.candidate_digest,
            target.data_plane_binding_digest, target.allocation_attempt_id, target.runtime_generation)
        if identity != expected_identity:
            raise PostSafetyRuntimeError("account closure authority deployment binding differs")
        if descriptor.contentMongo.database != descriptor.contentMongo.namespace or descriptor.contentMongo.namespace != target.namespace:
            raise PostSafetyRuntimeError("account closure Content Mongo binding differs")
        self.descriptor = descriptor
        self.target = target
        self.source_expected = source_expected
        self.source_binding = source_binding
        self.connections = connection_factory or ManagedAuthorityConnectionFactory()
        self.account_target = ContentAccountClosureTarget(
            target.environment, target.target, target.candidate_digest, target.data_plane_binding_digest,
            target.resource_ref, target.namespace, target.allocation_attempt_id, target.runtime_generation,
        )
        evidence = ContentAccountClosureRuntimeEvidenceRef.model_validate(descriptor.accountClosureEvidence.model_dump())

        def verifier():
            account_root = Path(descriptor.materialRoot.path)
            source_root = Path(descriptor.sourceAllocationCurrent.materialRoot.path)
            source_evidence = descriptor.sourceAllocationCurrent.sourceCreation
            if source_evidence.ref != "source-creation.json":
                raise PostSafetyRuntimeError("source allocation current ref differs")
            def source_verifier(**kwargs):
                if kwargs.get("receipt_digest") != source_evidence.digest:
                    raise PostSafetyRuntimeError("source allocation current digest differs")
                return verify_source_current(**kwargs)
            client = pg = redis_admin = old_redis = None
            try:
                client, database = self.connections.mongo(descriptor.contentMongo.admin.secretRef, descriptor.contentMongo.database)
                pg = self.connections.postgres(descriptor.postgresAdminReadback.secretRef)
                redis_admin = self.connections.redis(descriptor.redisAdminReadback.secretRef)
                old_redis = self.connections.redis(descriptor.oldRedisPrincipalProbe.secretRef)
                return verify_content_account_closure_current(
                    expected=self.account_target, evidence=evidence, material_root=account_root, database=database,
                    subject_key_ref=descriptor.subjectHmacKey.secretRef, source_expected=self.source_expected,
                    source_binding=self.source_binding, source_material_root=source_root, pg_admin=pg,
                    redis_admin=redis_admin, old_pg_dsn=self.connections.text(descriptor.oldPostgresPrincipalProbe.secretRef),
                    old_redis=old_redis, source_verifier=source_verifier,
                )
            except PostSafetyRuntimeError:
                raise
            except Exception as error:
                raise PostSafetyRuntimeError("account closure current verification failed") from error
            finally:
                for value in (old_redis, redis_admin, pg, client):
                    if value is not None:
                        try: value.close()
                        except Exception: pass

        super().__init__(authorization_root=authorization_root,
            account_closure_evidence=descriptor.accountClosureEvidence, account_closure_verifier=verifier,
            keyring_path=keyring_path)

    def verify_evidence(self, evidence: PostSafetyRuntimeEvidence) -> bytes:
        if evidence == self.descriptor.accountClosureEvidence:
            from quwoquan_ops.cli.lib.source_allocation_current import _material_bytes
            raw = _material_bytes(Path(self.descriptor.materialRoot.path), evidence.ref)
            if _digest(raw) != evidence.digest:
                raise PostSafetyRuntimeError("account closure evidence digest differs")
            return raw
        return super().verify_evidence(evidence)

    def account_closure(self, target: PostSafetyTarget, evidence: PostSafetyRuntimeEvidence) -> PostSafetyRuntimeClosure:
        if target != self.target:
            raise PostSafetyRuntimeError("account closure target differs")
        return super().account_closure(target, evidence)


def _validate_account_closure_authority(descriptor: PostSafetyAccountClosureAuthorityDescriptor, target: PostSafetyTarget) -> None:
    actual = (descriptor.environment, descriptor.target, descriptor.candidateDigest, descriptor.dataPlaneBindingDigest,
        descriptor.startupAttemptId, descriptor.runtimeGeneration, descriptor.contentMongo.namespace)
    expected = (target.environment, target.target, target.candidate_digest, target.data_plane_binding_digest,
        target.allocation_attempt_id, target.runtime_generation, target.namespace)
    if actual != expected or descriptor.contentMongo.database != target.namespace:
        raise PostSafetyRuntimeError("account closure authority deployment binding differs")


def produce_startup_material(*, current: PostSafetyTarget, authorization: PostSafetyRuntimeEvidence,
    account_closure_authority: PostSafetyAccountClosureAuthorityDescriptor, authority: RuntimeAuthority,
    deployment_owner: FileDeploymentStartupMaterialOwner) -> PostSafetyDeploymentStartupMaterial:
    """消费 deployment owner 显式 descriptor，在 canonical path create-once 写入 null material。"""
    _validate_account_closure_authority(account_closure_authority, current)
    account_evidence = account_closure_authority.accountClosureEvidence
    authority.verify_authorization(current, authorization)
    authority.account_closure(current, account_evidence)
    material = PostSafetyDeploymentStartupMaterial(environment=current.environment, target=current.target,
        candidateDigest=current.candidate_digest, dataPlaneBindingDigest=current.data_plane_binding_digest,
        startupAttemptId=current.allocation_attempt_id, runtimeGeneration=current.runtime_generation,
        authorization=authorization, accountClosureAuthority=account_closure_authority, postSafetyCurrent=None)
    deployment_owner.create_once(_canonical_model(material.model_dump(mode="json")))
    return material



def produce_gamma_local_startup_material(*, current: PostSafetyTarget, source_current: PostSafetySourceAllocationCurrentDescriptor,
    source_expected, source_binding: dict, database: MongoOwner, account_material_root: Path,
    connection_factory: ManagedAuthorityConnectionFactory, deployment_owner: FileDeploymentStartupMaterialOwner,
    keyring_path: Path = DEFAULT_KEYRING_PATH, now=None) -> PostSafetyDeploymentStartupMaterial:
    """gamma-local 唯一 target-owned producer；真实创建/读回 owner 前驱后本地签发。"""
    if current.environment != "gamma" or current.target != "gamma-local":
        raise PostSafetyRuntimeError("local Post safety signer is gamma-local only; prod requires external authority")
    if source_current.sourceCreation.ref != "source-creation.json" or source_current.allocationAttemptId != Path(source_current.materialRoot.path).name:
        raise PostSafetyRuntimeError("source allocation current is unavailable")
    from quwoquan_ops.cli.lib.content_account_closure_runtime import (
        COLLECTIONS, ContentAccountClosureTarget, create_content_account_closure_runtime,
    )
    account_material_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if account_material_root.exists():
        raise PostSafetyRuntimeError("account closure material already exists without startup material")
    account_material_root.mkdir(mode=0o700, exist_ok=False)
    subject_ref = "account-closure-subject.key"
    _write_once(account_material_root, subject_ref, secrets.token_bytes(32))
    account_target = ContentAccountClosureTarget(
        current.environment, current.target, current.candidate_digest, current.data_plane_binding_digest,
        current.resource_ref, current.namespace, current.allocation_attempt_id, current.runtime_generation,
    )
    evidence = create_content_account_closure_runtime(
        expected=account_target, database=database, material_root=account_material_root,
        subject_key_ref=subject_ref, source_expected=source_expected, source_binding=source_binding,
        source_current=source_current, connection_factory=connection_factory, now=now,
    )
    secret = lambda ref: PostSafetySecretRefDescriptor(secretRef=ref)
    descriptor = PostSafetyAccountClosureAuthorityDescriptor(
        environment=current.environment, target=current.target, candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest, startupAttemptId=current.allocation_attempt_id,
        runtimeGeneration=current.runtime_generation, accountClosureEvidence=PostSafetyRuntimeEvidence.model_validate(evidence.model_dump()),
        materialRoot=PostSafetyMaterialRootLocator(path=str(account_material_root)), subjectHmacKey=secret(subject_ref),
        sourceAllocationCurrent=source_current, postgresAdminReadback=secret("QWQ_SOURCE_PG_ADMIN_DSN"),
        redisAdminReadback=secret("QWQ_SOURCE_REDIS_ADMIN_URL"), oldPostgresPrincipalProbe=secret("QWQ_SOURCE_OLD_PG_DSN"),
        oldRedisPrincipalProbe=secret("QWQ_SOURCE_OLD_REDIS_URL"),
        contentMongo=PostSafetyContentMongoAuthorityDescriptor(admin=secret("QWQ_CONTENT_MONGO_ADMIN_URI"), database=current.namespace, namespace=current.namespace),
    )
    keyring = load_keyring(keyring_path)
    signer = ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=key_root(), keyring=keyring)
    issued = now or datetime.now(timezone.utc)
    authorization = PostSafetyRuntimeAuthorization(
        environment=current.environment, target=current.target, candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest, startupAttemptId=current.allocation_attempt_id,
        runtimeGeneration=current.runtime_generation, action="initialize_post_safety_runtime", issuedAt=issued,
        authorityIdentity=ENVIRONMENT_OPS_IDENTITY, evidencePredecessor=descriptor.accountClosureEvidence, signature="pending",
    )
    payload = _canonical(authorization.model_dump(mode="json", exclude={"signature"}))
    authorization = authorization.model_copy(update={"signature": signer(dsse_pae(AUTHORIZATION_PAYLOAD_TYPE, payload))})
    authorization_raw = _canonical_model(authorization.model_dump(mode="json"))
    authorization_root = post_safety_startup_material_root(current.target)
    authorization_root.mkdir(mode=0o700, parents=True, exist_ok=True); os.chmod(authorization_root, 0o700)
    authorization_evidence = _write_once(authorization_root, "authorization.json", authorization_raw)
    authority = ProductionAccountClosureAuthority(
        target=current, descriptor=descriptor, authorization_root=authorization_root,
        source_expected=source_expected, source_binding=source_binding, connection_factory=connection_factory, keyring_path=keyring_path,
    )
    return produce_startup_material(current=current, authorization=authorization_evidence,
        account_closure_authority=descriptor, authority=authority, deployment_owner=deployment_owner)

def _validate_target(approved: PostSafetyTarget, current: PostSafetyTarget) -> None:
    if approved != current:
        raise PostSafetyRuntimeError("approved/current Post safety target differs")
    if current.environment not in {"alpha", "beta", "gamma"} or current.target != current.environment + "-local":
        raise PostSafetyRuntimeError("managed nonproduction target required")
    if current.namespace.strip() == "" or current.resource_ref.strip() == "" or current.runtime_generation.strip() == "":
        raise PostSafetyRuntimeError("runtime binding is incomplete")
    for value in (current.candidate_digest, current.data_plane_binding_digest):
        if len(value) != 71 or not value.startswith("sha256:") or any(c not in "0123456789abcdef" for c in value[7:]):
            raise PostSafetyRuntimeError("runtime digest is invalid")


def _open_root(root: Path) -> tuple[int, os.stat_result]:
    if not root.is_absolute() or Path(os.path.normpath(root)) != root:
        raise PostSafetyRuntimeError("unsafe runtime material root")
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
    except OSError as error:
        raise PostSafetyRuntimeError("runtime material root unavailable") from error
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise PostSafetyRuntimeError("runtime material root is not owner-exclusive")
    return fd, info


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_mode, left.st_nlink, left.st_uid, left.st_gid) == (right.st_dev, right.st_ino, right.st_mode, right.st_nlink, right.st_uid, right.st_gid)


def _write_once(root: Path, name: str, raw: bytes) -> PostSafetyRuntimeEvidence:
    directory, _ = _open_root(root)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    return PostSafetyRuntimeEvidence(ref=name, digest=_digest(raw))


def _read_once(root: Path, evidence: PostSafetyRuntimeEvidence | None = None, *, ref: str | None = None) -> bytes:
    reference = evidence.ref if evidence is not None else ref
    if reference is None or Path(reference).name != reference:
        raise PostSafetyRuntimeError("nested or escaping evidence ref rejected")
    directory, root_before = _open_root(root)
    try:
        fd = os.open(reference, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > 1 << 20:
            raise PostSafetyRuntimeError("runtime evidence permissions differ")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read((1 << 20) + 1)
        after = os.fstat(fd)
        os.close(fd)
        if len(raw) != before.st_size or not _same_file(before, after) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns:
            raise PostSafetyRuntimeError("runtime evidence changed during secure read")
        if evidence is not None and _digest(raw) != evidence.digest:
            raise PostSafetyRuntimeError("runtime evidence digest differs")
        root_after = os.fstat(directory)
        if not _same_file(root_before, root_after):
            raise PostSafetyRuntimeError("runtime material root changed during read")
        return raw
    except OSError as error:
        raise PostSafetyRuntimeError("runtime evidence unavailable") from error
    finally:
        os.close(directory)

def _uuid_bytes(value) -> bytes:
    if isinstance(value, UUID):
        raw = value.bytes
    elif isinstance(value, (bytes, bytearray, memoryview)) and hasattr(value, "subtype"):
        raw = bytes(value)
    else:
        raise PostSafetyRuntimeError("MongoDB collection UUID type unavailable")
    if len(raw) != 16:
        raise PostSafetyRuntimeError("MongoDB collection UUID length differs")
    return raw


def _physical_identity(database: MongoOwner) -> str:
    reply = database.command({"listCollections": 1, "filter": {"name": "post_safety_states"}, "nameOnly": False})
    rows = reply.get("cursor", {}).get("firstBatch", [])
    if len(rows) != 1 or rows[0].get("name") != "post_safety_states":
        raise PostSafetyRuntimeError("Post safety collection identity unavailable")
    # 与 Go hex.EncodeToString(spec.UUID.Data) 逐字一致：16 raw bytes、无连字符、小写。
    return "mongodb-collection-uuid:" + _uuid_bytes(rows[0].get("info", {}).get("uuid")).hex()


def _timestamp(value):
    if isinstance(value, bool) or not isinstance(getattr(value, "time", None), int) or not isinstance(getattr(value, "inc", None), int) or value.time < 0 or value.inc < 0:
        raise PostSafetyRuntimeError("MongoDB majority operationTime unavailable")
    return value


def _watermark(value) -> str:
    return f"mongodb-timestamp:{value.time}:{value.inc}"

def _watermark_parts(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "mongodb-timestamp" or not all(part.isdigit() for part in parts[1:]):
        raise PostSafetyRuntimeError("Post safety recorded watermark differs")
    return int(parts[1]), int(parts[2])


def _safety_rows(database: MongoOwner, after=None) -> tuple[list, object]:
    read_concern = {"level": "majority"}
    if after is not None:
        read_concern["afterClusterTime"] = after
    reply = database.command({"aggregate": "post_safety_states", "pipeline": [{"$sort": {"_id": 1}}, {"$project": {"_id": 0, "postId": 1, "state": 1, "revision": 1, "terminatedAt": 1}}], "cursor": {}, "readConcern": read_concern})
    rows = reply.get("cursor", {}).get("firstBatch")
    if not isinstance(rows, list):
        raise PostSafetyRuntimeError("Post safety full readback unavailable")
    operation_time = _timestamp(reply.get("operationTime"))
    return rows, operation_time


def _safety_closure(database: MongoOwner, owner_evidence: PostSafetyRuntimeEvidence) -> PostSafetyRuntimeClosure:
    first, first_time = _safety_rows(database)
    second, second_time = _safety_rows(database, first_time)
    first_bytes, second_bytes = _canonical(first), _canonical(second)
    if first_bytes != second_bytes or (second_time.time, second_time.inc) < (first_time.time, first_time.inc):
        raise PostSafetyRuntimeError("Post safety consistency readback differs")
    return PostSafetyRuntimeClosure(kind="post_safety", recordCount=len(second), canonicalDigest=_digest(second_bytes), watermark=_watermark(second_time), ownerEvidence=owner_evidence)

def _target_from_startup_material(
    material: PostSafetyDeploymentStartupMaterial,
    current: PostSafetyTarget,
) -> None:
    pairs = (
        (material.environment, current.environment),
        (material.target, current.target),
        (material.candidateDigest, current.candidate_digest),
        (material.dataPlaneBindingDigest, current.data_plane_binding_digest),
        (material.startupAttemptId, current.allocation_attempt_id),
        (material.runtimeGeneration, current.runtime_generation),
    )
    if any(actual != wanted for actual, wanted in pairs):
        raise PostSafetyRuntimeError("deployment startup material binding differs")


def create_new_runtime(
    *,
    startup_material_raw: bytes,
    current: PostSafetyTarget,
    database: MongoOwner,
    material_root: Path,
    authority: RuntimeAuthority,
    deployment_owner: DeploymentStartupMaterialOwner,
) -> PostSafetyDeploymentStartupMaterial:
    """在 deployment owner 锁内，从 null pointer 创建并 CAS 发布 current。"""
    try:
        startup = PostSafetyDeploymentStartupMaterial.model_validate_json(startup_material_raw)
    except Exception as error:
        raise PostSafetyRuntimeError("deployment startup material is invalid") from error
    if startup_material_raw != _canonical_model(startup.model_dump(mode="json")):
        raise PostSafetyRuntimeError("deployment startup material is not canonical exact bytes")
    _validate_target(current, current)
    _target_from_startup_material(startup, current)
    _validate_account_closure_authority(startup.accountClosureAuthority, current)
    if startup.postSafetyCurrent is not None:
        raise PostSafetyRuntimeError("postSafetyCurrent must be null before apply")
    if database.name != current.namespace:
        raise PostSafetyRuntimeError("MongoDB namespace differs")
    authorization_raw = authority.verify_authorization(current, startup.authorization)
    account = authority.account_closure(current, startup.accountClosureAuthority.accountClosureEvidence)
    if account.kind != "account_closure" or account.ownerEvidence != startup.accountClosureAuthority.accountClosureEvidence:
        raise PostSafetyRuntimeError("account closure deployment evidence differs")
    account_closure_raw = authority.verify_evidence(startup.accountClosureAuthority.accountClosureEvidence)
    existing = database.command({"listCollections": 1, "filter": {"name": "post_safety_states"}, "nameOnly": True}).get("cursor", {}).get("firstBatch", [])
    if existing:
        raise PostSafetyRuntimeError("existing Post safety collection cannot receive new-runtime authority")
    # Content 只消费一个只读挂载 authority 根；创建 provider 状态前，按 typed ref
    # 保存 deployment owner 已核验的 exact bytes。
    _write_once(material_root, startup.authorization.ref, authorization_raw)
    _write_once(material_root, startup.accountClosureAuthority.accountClosureEvidence.ref, account_closure_raw)
    database.command({"create": "post_safety_states"})
    key = secrets.token_bytes(32)
    _write_once(material_root, "post-safety.key", key)
    key_identity = "sha256:" + hashlib.sha256(hmac.digest(key, b"quwoquan/content.post/post-safety-runtime/key-identity", "sha256")).hexdigest()
    physical = _physical_identity(database)
    binding = PostSafetyRuntimeBinding(environment=current.environment, target=current.target, candidateDigest=current.candidate_digest, dataPlaneBindingDigest=current.data_plane_binding_digest, resourceRef=current.resource_ref, namespace=current.namespace, physicalInstanceId=physical, runtimeGeneration=current.runtime_generation, hmacKeyIdentity=key_identity)
    safety_seed = PostSafetyRuntimeEvidence(ref="creation.json", digest="sha256:" + "0" * 64)
    safety = _safety_closure(database, safety_seed)
    if safety.recordCount != 0:
        raise PostSafetyRuntimeError("new Post safety collection is not empty")
    creation = PostSafetyRuntimeCreationReceipt(binding=binding, allocationAttemptId=current.allocation_attempt_id, physicalAllocationId=physical, namespaceReadback=database.name, initialSafetyRecordCount=0, initialSafetyCanonicalDigest=safety.canonicalDigest, allocatedAt=datetime.now(timezone.utc))
    creation_evidence = _write_once(material_root, "creation.json", _canonical_model(creation.model_dump(mode="json")))
    safety = safety.model_copy(update={"ownerEvidence": creation_evidence})
    fact = PostSafetyRuntimeFact(mode="new_runtime", binding=binding, authorization=startup.authorization, creation=creation_evidence, previousBinding=None, recovery=None, closures=[account, safety], recordedAt=datetime.now(timezone.utc))
    fact_evidence = _write_once(material_root, "fact.json", _canonical_model(fact.model_dump(mode="json")))
    current_binding = PostSafetyRuntimeCurrentBinding(binding=binding, fact=fact_evidence)
    current_evidence = _write_once(material_root, "current.json", _canonical_model(current_binding.model_dump(mode="json")))
    replacement = startup.model_copy(update={"postSafetyCurrent": current_evidence})
    replacement_raw = _canonical_model(replacement.model_dump(mode="json"))
    deployment_owner.compare_and_swap(startup_material_raw, replacement_raw)
    _write_once(material_root, "startup.json", replacement_raw)
    verify_current(startup_material_raw=replacement_raw, expected=current, database=database, material_root=material_root, authority=authority)
    return replacement


def verify_current(
    *,
    startup_material_raw: bytes,
    expected: PostSafetyTarget,
    database: MongoOwner,
    material_root: Path,
    authority: RuntimeAuthority,
) -> PostSafetyRuntimeFact:
    """只从 deployment-owned startup material 取得 current exact pointer。"""
    try:
        startup = PostSafetyDeploymentStartupMaterial.model_validate_json(startup_material_raw)
    except Exception as error:
        raise PostSafetyRuntimeError("deployment startup material is invalid") from error
    if startup_material_raw != _canonical_model(startup.model_dump(mode="json")):
        raise PostSafetyRuntimeError("deployment startup material is not canonical exact bytes")
    _validate_target(expected, expected)
    _target_from_startup_material(startup, expected)
    _validate_account_closure_authority(startup.accountClosureAuthority, expected)
    current_evidence = startup.postSafetyCurrent
    if current_evidence is None:
        raise PostSafetyRuntimeError("deployment postSafetyCurrent is null")
    if current_evidence.ref != "current.json":
        raise PostSafetyRuntimeError("deployment current evidence ref differs")
    current_raw = _read_once(material_root, current_evidence)
    current = PostSafetyRuntimeCurrentBinding.model_validate_json(current_raw)
    fact_raw = _read_once(material_root, current.fact)
    fact = PostSafetyRuntimeFact.model_validate_json(fact_raw)
    binding = fact.binding
    pairs = ((binding.environment, expected.environment), (binding.target, expected.target), (binding.candidateDigest, expected.candidate_digest), (binding.dataPlaneBindingDigest, expected.data_plane_binding_digest), (binding.resourceRef, expected.resource_ref), (binding.namespace, expected.namespace), (binding.runtimeGeneration, expected.runtime_generation))
    if current.binding != binding or any(actual != wanted for actual, wanted in pairs) or database.name != expected.namespace or _physical_identity(database) != binding.physicalInstanceId:
        raise PostSafetyRuntimeError("current Post safety binding differs")
    key = _read_once(material_root, ref="post-safety.key")
    identity = "sha256:" + hashlib.sha256(hmac.digest(key, b"quwoquan/content.post/post-safety-runtime/key-identity", "sha256")).hexdigest()
    if identity != binding.hmacKeyIdentity or fact.mode != "new_runtime" or fact.previousBinding is not None or fact.recovery is not None:
        raise PostSafetyRuntimeError("Post safety key or mode differs")
    if fact.authorization != startup.authorization:
        raise PostSafetyRuntimeError("authorization deployment evidence differs")
    authority.verify_authorization(expected, startup.authorization)
    if [item.kind for item in fact.closures] != ["account_closure", "post_safety"]:
        raise PostSafetyRuntimeError("runtime closure order differs")
    account = authority.account_closure(expected, startup.accountClosureAuthority.accountClosureEvidence)
    if account.ownerEvidence != startup.accountClosureAuthority.accountClosureEvidence:
        raise PostSafetyRuntimeError("account closure deployment evidence differs")
    authority.verify_evidence(startup.accountClosureAuthority.accountClosureEvidence)
    safety = _safety_closure(database, fact.creation)
    recorded_safety = fact.closures[1]
    if _watermark_parts(recorded_safety.watermark) > _watermark_parts(safety.watermark):
        raise PostSafetyRuntimeError("runtime owner closure watermark regressed")
    # Mongo operationTime is a majority lower-bound and advances on unrelated
    # commands. Preserve the recorded owner watermark while requiring the live
    # readback to dominate it; all content fields remain exact.
    normalized_safety = safety.model_copy(update={"watermark": recorded_safety.watermark})
    if fact.closures != [account, normalized_safety]:
        raise PostSafetyRuntimeError("runtime owner closure readback differs")
    creation = PostSafetyRuntimeCreationReceipt.model_validate_json(_read_once(material_root, fact.creation))
    if creation.binding != binding or creation.allocationAttemptId != startup.startupAttemptId or creation.physicalAllocationId != binding.physicalInstanceId or creation.namespaceReadback != database.name or creation.initialSafetyRecordCount != 0 or creation.initialSafetyCanonicalDigest != safety.canonicalDigest:
        raise PostSafetyRuntimeError("runtime creation readback differs")
    if current_raw != _read_once(material_root, current_evidence):
        raise PostSafetyRuntimeError("current binding changed during verification")
    return fact
