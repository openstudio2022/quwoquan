"""prod-sim local rehearsal User schema owner and Post safety materialization.

Gamma 仍独占 source allocator。prod-sim 由 postgres-init 创建空 namespace 后，
启动锁内消费封存的 source-init 制品写入 User schema，并签发不可提升的
local rehearsal Post safety 材料。不把 prod-hosted 或 alpha/beta/gamma 卷进来。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
from urllib.parse import urlsplit

import yaml

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.deployment_candidate_manifest.candidate_fs import (
    _read_candidate_bytes,
)
from quwoquan_ops.cli.lib.source_initializer_package import (
    digest,
    load_source_initializer,
    source_initializer_required,
)

PROD_SIM_ENVIRONMENT = "prod"
PROD_SIM_TARGET = "prod-sim"
USER_NAMESPACE = "quwoquan_user"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROD_SIM_PUBLIC_LOOPBACK_ROLES = (
    "api",
    "publicWeb",
    "productOps",
    "mediaImage",
    "mediaUpload",
)
_HUMAN_AUTHORITY_ISSUER = "quwoquan-prod-sim-rehearsal"
_HUMAN_AUTHORITY_PROVIDER_VERSION = "prod-sim-rehearsal"
_HUMAN_AUTHORITY_KEY_ID = "prod-sim-rehearsal-ed25519"
_HUMAN_AUTHORITY_ROLE_MAPPINGS = '{"ops-release":["release_owner"]}'
PROD_ROLLOUT_POLICY = (
    output_paths.ROOT
    / "quwoquan_ops"
    / "environments"
    / "prod"
    / "rollout"
    / "routing_policy.yaml"
)


class ProdSimRehearsalAuthorityError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProdSimRehearsalAuthorityError("duplicate JSON key")
        result[key] = value
    return result


def _required_port(name: str) -> int:
    raw = os.environ.get(name, "")
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ProdSimRehearsalAuthorityError(f"{name} is invalid")
    return int(raw)


def prod_sim_user_postgres_host_dsn() -> str:
    port = _required_port("LOCAL_GAMMA_POSTGRES_PORT")
    return (
        f"postgresql://quwoquan:quwoquan@127.0.0.1:{port}/"
        f"{USER_NAMESPACE}?sslmode=disable"
    )


def prod_sim_user_postgres_container_dsn() -> str:
    return (
        f"postgres://quwoquan:quwoquan@postgres:5432/"
        f"{USER_NAMESPACE}?sslmode=disable"
    )


def _active_prod_sim_candidate():
    snapshot = output_paths.active_deployment_candidate_snapshot(PROD_SIM_TARGET)
    if snapshot is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim User schema owner requires the current full candidate"
        )
    manifest = snapshot["manifest"]
    if (
        manifest.get("environment") != PROD_SIM_ENVIRONMENT
        or manifest.get("target") != PROD_SIM_TARGET
    ):
        raise ProdSimRehearsalAuthorityError("prod-sim candidate identity differs")
    return snapshot, Path(snapshot["candidateDir"]), manifest


def _load_packaged_initializer(candidate_root: Path):
    shared = json.loads(
        _read_candidate_bytes(
            candidate_root,
            "packages/runtime-shared/manifest.json",
            label="prod-sim runtime-shared manifest",
        ),
        object_pairs_hook=_unique,
    )
    if not source_initializer_required(PROD_SIM_ENVIRONMENT, PROD_SIM_TARGET):
        raise ProdSimRehearsalAuthorityError("prod-sim source initializer is not required")
    return load_source_initializer(
        candidate_root,
        shared.get("sourceInitializer"),
        PROD_SIM_ENVIRONMENT,
        PROD_SIM_TARGET,
    )


def _schema_readback(dsn: str):
    import psycopg

    with psycopg.connect(dsn) as connection:
        ledger, profiles, count = connection.execute(
            """
            SELECT
                to_regclass('public.service_schema_migrations')::text,
                to_regclass('public.user_profiles')::text,
                (SELECT count(*) FROM pg_tables WHERE schemaname = 'public')
            """
        ).fetchone()
    return ledger, profiles, int(count)


def ensure_prod_sim_user_schema_for_locked_up() -> dict[str, str]:
    """在已持有 prod-sim 锁且 postgres-init 完成后应用或复验 User schema。"""
    _, candidate_root, _ = _active_prod_sim_candidate()
    executable = _load_packaged_initializer(candidate_root)
    dsn = prod_sim_user_postgres_host_dsn()
    ledger, profiles, count = _schema_readback(dsn)
    if ledger is not None and profiles is not None:
        return {
            "status": "verified",
            "namespace": USER_NAMESPACE,
            "containerDsn": prod_sim_user_postgres_container_dsn(),
        }
    if count != 0:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim User PostgreSQL namespace is not empty without managed schema"
        )
    result = subprocess.run(
        [str(executable)],
        env={
            **os.environ,
            "QWQ_SOURCE_INIT_ENV": PROD_SIM_ENVIRONMENT,
            "QWQ_SOURCE_INIT_TARGET": PROD_SIM_TARGET,
            "QWQ_SOURCE_INIT_DSN": dsn,
        },
        cwd=executable.parent,
        capture_output=True,
        timeout=100,
    )
    if result.returncode:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim User managed initialization failed"
        )
    ledger, profiles, _ = _schema_readback(dsn)
    if ledger is None or profiles is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim User managed initialization readback differs"
        )
    return {
        "status": "applied",
        "namespace": USER_NAMESPACE,
        "containerDsn": prod_sim_user_postgres_container_dsn(),
    }


def _prod_sim_mongo_uri() -> str:
    return (
        f"mongodb://127.0.0.1:{_required_port('LOCAL_GAMMA_MONGO_PORT')}"
        "/?directConnection=true"
    )


def _prod_sim_content_mongo_binding(manifest: dict, candidate_root: Path):
    binding_ref = manifest["dataPlaneBinding"]
    raw = _read_candidate_bytes(
        candidate_root,
        binding_ref["ref"],
        label="prod-sim data-plane binding",
    )
    if digest(raw) != binding_ref["digest"]:
        raise ProdSimRehearsalAuthorityError("prod-sim data-plane bytes drift")
    payload = json.loads(raw, object_pairs_hook=_unique)
    rows = list(payload["bindings"].values())
    mongo = [
        row
        for row in rows
        if row["service"] == "content-service" and row["engine"] == "mongodb"
    ]
    if len(mongo) != 1:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim Post safety Content Mongo binding is ambiguous"
        )
    return mongo[0]


def _empty_digest() -> str:
    return digest(b"[]")


def _prod_sim_rehearsal_authority(startup, *, keyring_path):
    from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import (
        ContentAccountClosureRuntimeEvidence,
    )
    from quwoquan_ops.cli.lib.post_safety_runtime import (
        PostSafetyRuntimeError,
        ProductionRuntimeAuthority,
        post_safety_startup_material_root,
    )
    from quwoquan_ops.cli.lib.source_allocation_current import _material_bytes

    descriptor = startup.accountClosureAuthority

    def verifier():
        raw = _material_bytes(
            Path(descriptor.materialRoot.path),
            descriptor.accountClosureEvidence.ref,
        )
        return ContentAccountClosureRuntimeEvidence.model_validate_json(raw)

    class _RehearsalAuthority(ProductionRuntimeAuthority):
        def verify_evidence(self, requested):
            if requested == descriptor.accountClosureEvidence:
                raw = _material_bytes(
                    Path(descriptor.materialRoot.path), requested.ref
                )
                if digest(raw) != requested.digest:
                    raise PostSafetyRuntimeError(
                        "account closure evidence digest differs"
                    )
                return raw
            return super().verify_evidence(requested)

    return _RehearsalAuthority(
        authorization_root=post_safety_startup_material_root(PROD_SIM_TARGET),
        account_closure_evidence=descriptor.accountClosureEvidence,
        account_closure_verifier=verifier,
        keyring_path=keyring_path,
    )


def produce_prod_sim_rehearsal_startup_material(
    *,
    current,
    database,
    account_material_root: Path,
    deployment_owner,
    keyring_path=None,
    now=None,
):
    """prod-sim 唯一 local rehearsal Post safety producer；永不签发 prod-hosted。"""
    from quwoquan_ops.cli.lib.content_account_closure_runtime import (
        COLLECTIONS,
        _canonical as account_canonical,
        _collection_rows,
        _digest as account_digest,
    )
    from quwoquan_ops.cli.lib.evidence_signing import (
        DEFAULT_KEYRING_PATH,
        ENVIRONMENT_OPS_IDENTITY,
        ed25519_signer,
        key_root,
        load_keyring,
    )
    from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import (
        ContentAccountClosureRuntimeCollection,
        ContentAccountClosureRuntimeEvidence,
        ContentAccountClosureRuntimeEvidenceRef,
        ContentAccountClosureRuntimeSource,
        ContentAccountClosureRuntimeSourceCreation,
        ContentAccountClosureRuntimeSourcePartition,
    )
    from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
        PostSafetyAccountClosureAuthorityDescriptor,
        PostSafetyContentMongoAuthorityDescriptor,
        PostSafetyMaterialRootLocator,
        PostSafetyRuntimeAuthorization,
        PostSafetyRuntimeEvidence,
        PostSafetySecretRefDescriptor,
        PostSafetySourceAllocationCurrentDescriptor,
    )
    from quwoquan_ops.cli.lib.post_safety_runtime import (
        AUTHORIZATION_PAYLOAD_TYPE,
        FileDeploymentStartupMaterialOwner,
        PostSafetyRuntimeError,
        _canonical,
        _canonical_model,
        _write_once,
        produce_startup_material,
        post_safety_startup_material_root,
    )
    from quwoquan_ops.ci.environment_scheduler import dsse_pae

    if current.environment != PROD_SIM_ENVIRONMENT or current.target != PROD_SIM_TARGET:
        raise PostSafetyRuntimeError(
            "local Post safety rehearsal signer is prod-sim only; prod-hosted requires external authority"
        )
    if keyring_path is None:
        keyring_path = DEFAULT_KEYRING_PATH
    if not isinstance(deployment_owner, FileDeploymentStartupMaterialOwner):
        raise PostSafetyRuntimeError("prod-sim Post safety deployment owner differs")
    account_material_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if account_material_root.exists():
        raise PostSafetyRuntimeError(
            "account closure material already exists without startup material"
        )
    account_material_root.mkdir(mode=0o700, exist_ok=False)
    os.chmod(account_material_root, 0o700)
    subject_ref = "account-closure-subject.key"
    _write_once(account_material_root, subject_ref, secrets.token_bytes(32))
    specs = database.command(
        {"listCollections": 1, "nameOnly": True}
    ).get("cursor", {}).get("firstBatch", [])
    if any(row.get("name") in COLLECTIONS for row in specs):
        raise PostSafetyRuntimeError(
            "existing account closure collection cannot receive new-runtime evidence"
        )
    for name in COLLECTIONS:
        database.command({"create": name})
    rows = _collection_rows(database)
    if any(row["recordCount"] != 0 for row in rows):
        raise PostSafetyRuntimeError("new account closure collection is not empty")
    source_root = account_material_root / "source-allocation"
    source_root.mkdir(mode=0o700, exist_ok=False)
    os.chmod(source_root, 0o700)
    issued = now or datetime.now(timezone.utc)
    source_creation = ContentAccountClosureRuntimeSourceCreation(
        environment=current.environment,
        target=current.target,
        candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest,
        allocationAttemptId=current.allocation_attempt_id,
        producerResourceRef=current.resource_ref,
        producerNamespace=USER_NAMESPACE,
        producerManagedAllocationBindingId="sha256:" + "e" * 64,
        sourceResourceRef="primary-redis",
        sourceNamespace="db-user",
        sourceManagedAllocationBindingId="sha256:" + "f" * 64,
        producerBindingDigest=current.data_plane_binding_digest,
        producerRole="quwoquan",
        sourceAclUser="qwq_runtime",
        producerCredentialIdentity="sha256:" + "a" * 64,
        sourceCredentialIdentity="sha256:" + "b" * 64,
        rejectedProducerRole="qwq_source_old_probe",
        rejectedSourceAclUser="qwq_source_old_probe",
        allocatedAt=issued,
    )
    source_raw = account_canonical(source_creation.model_dump(mode="json"))
    _write_once(source_root, "source-creation.json", source_raw)
    source_evidence = ContentAccountClosureRuntimeEvidenceRef(
        ref="source-creation.json",
        digest=account_digest(source_raw),
    )
    subject_key = (account_material_root / subject_ref).read_bytes()
    key_identity = (
        "sha256:"
        + hashlib.sha256(
            hmac.digest(
                subject_key,
                b"quwoquan/content.account-closure/runtime/key-identity",
                "sha256",
            )
        ).hexdigest()
    )
    evidence = ContentAccountClosureRuntimeEvidence(
        environment=current.environment,
        target=current.target,
        candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest,
        resourceRef=current.resource_ref,
        namespace=current.namespace,
        allocationAttemptId=current.allocation_attempt_id,
        runtimeGeneration=current.runtime_generation,
        subjectHmacKeyIdentity=key_identity,
        source=ContentAccountClosureRuntimeSource(
            mode="new_source",
            resourceRef="primary-redis",
            namespace="db-user",
            managedAllocationBindingId="sha256:" + "f" * 64,
            stream="events.user.account",
            consumerGroup="content-service-user-account-closed",
            producerBindingDigest=current.data_plane_binding_digest,
            sourceCreation=source_evidence,
            recovery=None,
            partitions=[
                ContentAccountClosureRuntimeSourcePartition(
                    partition="events.user.account",
                    firstAvailablePosition="0-0",
                    frozenThrough="0-0",
                    deliveredThrough="0-0",
                    appliedThrough="0-0",
                    pendingCount=0,
                    entryCount=0,
                    canonicalDigest=_empty_digest(),
                )
            ],
        ),
        collections=[
            ContentAccountClosureRuntimeCollection.model_validate(row) for row in rows
        ],
        recordCount=0,
        canonicalDigest=account_digest(account_canonical(rows)),
        initializedAt=issued,
    )
    evidence_raw = account_canonical(evidence.model_dump(mode="json"))
    evidence_ref = _write_once(
        account_material_root, "content-account-closure-runtime.json", evidence_raw
    )
    secret = lambda ref: PostSafetySecretRefDescriptor(secretRef=ref)
    descriptor = PostSafetyAccountClosureAuthorityDescriptor(
        environment=current.environment,
        target=current.target,
        candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest,
        startupAttemptId=current.allocation_attempt_id,
        runtimeGeneration=current.runtime_generation,
        accountClosureEvidence=PostSafetyRuntimeEvidence.model_validate(
            evidence_ref.model_dump()
        ),
        materialRoot=PostSafetyMaterialRootLocator(path=str(account_material_root)),
        subjectHmacKey=secret(subject_ref),
        sourceAllocationCurrent=PostSafetySourceAllocationCurrentDescriptor(
            allocationAttemptId=source_root.name,
            materialRoot=PostSafetyMaterialRootLocator(path=str(source_root)),
            sourceCreation=PostSafetyRuntimeEvidence(
                ref="source-creation.json",
                digest=account_digest(source_raw),
            ),
        ),
        postgresAdminReadback=secret("QWQ_SOURCE_PG_ADMIN_DSN"),
        redisAdminReadback=secret("QWQ_SOURCE_REDIS_ADMIN_URL"),
        oldPostgresPrincipalProbe=secret("QWQ_SOURCE_OLD_PG_DSN"),
        oldRedisPrincipalProbe=secret("QWQ_SOURCE_OLD_REDIS_URL"),
        contentMongo=PostSafetyContentMongoAuthorityDescriptor(
            admin=secret("QWQ_CONTENT_MONGO_ADMIN_URI"),
            database=current.namespace,
            namespace=current.namespace,
        ),
    )
    keyring = load_keyring(keyring_path)
    signer = ed25519_signer(ENVIRONMENT_OPS_IDENTITY, root=key_root(), keyring=keyring)
    authorization = PostSafetyRuntimeAuthorization(
        environment=current.environment,
        target=current.target,
        candidateDigest=current.candidate_digest,
        dataPlaneBindingDigest=current.data_plane_binding_digest,
        startupAttemptId=current.allocation_attempt_id,
        runtimeGeneration=current.runtime_generation,
        action="initialize_post_safety_runtime",
        issuedAt=issued,
        authorityIdentity=ENVIRONMENT_OPS_IDENTITY,
        evidencePredecessor=descriptor.accountClosureEvidence,
        signature="pending",
    )
    payload = _canonical(authorization.model_dump(mode="json", exclude={"signature"}))
    authorization = authorization.model_copy(
        update={"signature": signer(dsse_pae(AUTHORIZATION_PAYLOAD_TYPE, payload))}
    )
    authorization_raw = _canonical_model(authorization.model_dump(mode="json"))
    authorization_root = post_safety_startup_material_root(current.target)
    authorization_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(authorization_root, 0o700)
    authorization_evidence = _write_once(
        authorization_root, "authorization.json", authorization_raw
    )
    startup = type("Startup", (), {"accountClosureAuthority": descriptor})()
    authority = _prod_sim_rehearsal_authority(startup, keyring_path=keyring_path)
    return produce_startup_material(
        current=current,
        authorization=authorization_evidence,
        account_closure_authority=descriptor,
        authority=authority,
        deployment_owner=deployment_owner,
    )


def _startup_package_binding_matches(startup, expected) -> bool:
    return (
        startup.environment == expected.environment
        and startup.target == expected.target
        and startup.candidateDigest == expected.candidate_digest
        and startup.dataPlaneBindingDigest == expected.data_plane_binding_digest
    )


def _archive_stale_prod_sim_post_safety_residue(*, attempt_id: str) -> None:
    """Archive leftover rehearsal Post safety files so a new attempt can create-once."""
    from quwoquan_ops.cli.lib.post_safety_runtime import (
        post_safety_startup_material_root,
    )

    archive = output_paths.deployment_target_path(
        PROD_SIM_TARGET, "archive", "rehearsal-post-safety", attempt_id
    )
    if archive.exists():
        raise ProdSimRehearsalAuthorityError(
            "prod-sim post safety residue archive already exists"
        )
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(archive.parent, 0o700)
    archive.mkdir(mode=0o700, exist_ok=False)
    os.chmod(archive, 0o700)
    sources = (
        post_safety_startup_material_root(PROD_SIM_TARGET),
        output_paths.deployment_target_path(PROD_SIM_TARGET, "secrets", "post-safety"),
        output_paths.deployment_target_path(
            PROD_SIM_TARGET, "secrets", "content-account-closure"
        ),
    )
    for index, source in enumerate(sources):
        if not source.exists():
            continue
        destination = archive / f"{index:02d}-{source.name}"
        source.rename(destination)


def _drop_stale_prod_sim_post_safety_collections(database) -> None:
    from quwoquan_ops.cli.lib.content_account_closure_runtime import COLLECTIONS

    specs = database.command({"listCollections": 1, "nameOnly": True}).get(
        "cursor", {}
    ).get("firstBatch", [])
    names = {row.get("name") for row in specs if isinstance(row, dict)}
    for name in ("post_safety_states", *COLLECTIONS):
        if name in names:
            database.command({"drop": name})


def ensure_prod_sim_post_safety_for_locked_up() -> dict[str, str]:
    """初始化或复验 prod-sim local rehearsal Post safety current。"""
    from quwoquan_ops.cli.commands.post_safety_runtime import _required, _runtime_dependencies
    from quwoquan_ops.cli.lib.evidence_signing import DEFAULT_KEYRING_PATH
    from quwoquan_ops.cli.lib.post_safety_runtime import (
        FileDeploymentStartupMaterialOwner,
        ManagedAuthorityConnectionFactory,
        PostSafetyTarget,
        create_new_runtime,
        verify_current,
    )

    snapshot, candidate_root, manifest = _active_prod_sim_candidate()
    mongo = _prod_sim_content_mongo_binding(manifest, candidate_root)
    startup_path = (
        output_paths.target_process_dir(PROD_SIM_TARGET) / "startup_attempt.json"
    )
    attempt = json.loads(_required(startup_path))
    attempt_id = str(attempt.get("attemptId") or "").strip()
    if not attempt_id:
        raise ProdSimRehearsalAuthorityError("prod-sim startup attempt missing")
    expected = PostSafetyTarget(
        PROD_SIM_ENVIRONMENT,
        PROD_SIM_TARGET,
        manifest["packageDigest"],
        manifest["dataPlaneBinding"]["bindingDigest"],
        mongo["resource"],
        mongo["namespace"],
        attempt_id,
        attempt_id,
    )
    dependencies = _runtime_dependencies()
    owner = FileDeploymentStartupMaterialOwner(PROD_SIM_TARGET)
    factory = ManagedAuthorityConnectionFactory(
        {"QWQ_CONTENT_MONGO_ADMIN_URI": _prod_sim_mongo_uri()}
    )
    client, database = factory.mongo("QWQ_CONTENT_MONGO_ADMIN_URI", expected.namespace)
    try:
        if owner.path.exists():
            leftover_raw = owner.read()
            leftover = dependencies[
                "PostSafetyDeploymentStartupMaterial"
            ].model_validate_json(leftover_raw)
            if not _startup_package_binding_matches(leftover, expected):
                _archive_stale_prod_sim_post_safety_residue(attempt_id=attempt_id)
                _drop_stale_prod_sim_post_safety_collections(database)
        if not owner.path.exists():
            account_root = output_paths.deployment_target_path(
                PROD_SIM_TARGET, "secrets", "content-account-closure", attempt_id
            )
            produce_prod_sim_rehearsal_startup_material(
                current=expected,
                database=database,
                account_material_root=account_root,
                deployment_owner=owner,
            )
        startup_raw = owner.read()
        startup = dependencies[
            "PostSafetyDeploymentStartupMaterial"
        ].model_validate_json(startup_raw)
        bound = replace(
            expected,
            runtime_generation=startup.runtimeGeneration,
            allocation_attempt_id=startup.startupAttemptId,
        )
        authority = _prod_sim_rehearsal_authority(
            startup, keyring_path=DEFAULT_KEYRING_PATH
        )
        material_root = Path(
            output_paths.deployment_target_path(
                PROD_SIM_TARGET, "secrets", "post-safety", startup.runtimeGeneration
            )
        )
        if startup.postSafetyCurrent is None:
            material_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(material_root.parent, 0o700)
            material_root.mkdir(mode=0o700, exist_ok=False)
            os.chmod(material_root, 0o700)
            startup = create_new_runtime(
                startup_material_raw=startup_raw,
                current=bound,
                database=database,
                material_root=material_root,
                authority=authority,
                deployment_owner=owner,
            )
        else:
            verify_current(
                startup_material_raw=startup_raw,
                expected=bound,
                database=database,
                material_root=material_root,
                authority=authority,
            )
        if startup.postSafetyCurrent is None:
            raise ProdSimRehearsalAuthorityError(
                "prod-sim post safety current remained null"
            )
        current = dependencies["PostSafetyRuntimeCurrentBinding"].model_validate_json(
            dependencies["read_once"](material_root, startup.postSafetyCurrent)
        )
        account_root = Path(startup.accountClosureAuthority.materialRoot.path)
        subject_secret = factory.relative_secret(
            account_root, startup.accountClosureAuthority.subjectHmacKey.secretRef
        ).hex()
        return {
            "hostMaterialRoot": str(material_root),
            "accountSubjectHmacSecret": subject_secret,
            "containerMaterialRoot": "/run/quwoquan/post-safety",
            "hmacSecretRef": "post-safety.key",
            "recoveryEvidenceRef": current.fact.ref,
            "currentBindingRef": startup.postSafetyCurrent.ref,
            "runtimeGeneration": startup.runtimeGeneration,
        }
    finally:
        client.close()


def _sha256_bytes(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _dump_yaml(payload: object) -> bytes:
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    ).encode("utf-8")


def _write_bytes(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(encoded)
    if path.read_bytes() != encoded:
        raise ProdSimRehearsalAuthorityError(f"{path.name} copy drifted")


def prod_sim_public_loopback_hosts() -> tuple[str, ...]:
    from quwoquan_ops.cli.lib.environment_topology import (
        get_target,
        load_environment_topology,
    )

    bases = get_target(load_environment_topology(), PROD_SIM_TARGET)["publicBases"]
    hosts: list[str] = []
    seen: set[str] = set()
    for role in _PROD_SIM_PUBLIC_LOOPBACK_ROLES:
        host = str(urlsplit(str(bases[role])).hostname or "").strip()
        if not host:
            raise ProdSimRehearsalAuthorityError(
                f"prod-sim public host for {role} is missing"
            )
        if host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return tuple(hosts)


def _resolved_addresses(host: str) -> set[str]:
    return {item[4][0] for item in socket.getaddrinfo(host, None)}


def ensure_prod_sim_public_loopback_resolution() -> dict[str, str]:
    """本机公开入口必须解析到 loopback，才能走与 Gamma 相同的 host 侧 HTTPS 探针。"""
    hosts = prod_sim_public_loopback_hosts()
    failed: list[str] = []
    for host in hosts:
        try:
            resolved = sorted(_resolved_addresses(host))
        except OSError as error:
            failed.append(f"{host} -> unresolved ({error})")
            continue
        if not any(address.startswith("127.") or address == "::1" for address in resolved):
            failed.append(f"{host} -> {', '.join(resolved)}")
    if failed:
        line = "127.0.0.1 " + " ".join(hosts)
        raise ProdSimRehearsalAuthorityError(
            "prod-sim public hosts must resolve to loopback; add to /etc/hosts: "
            + line
            + "; unresolved: "
            + "; ".join(failed)
        )
    return {"status": "verified", "hosts": ",".join(hosts)}


def _ensure_prod_sim_human_authority_material() -> dict[str, str]:
    root = output_paths.deployment_target_path(
        PROD_SIM_TARGET, "secrets", "platform-ops-human-authority"
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    seed_path = root / "signing.seed"
    webhook_path = root / "github-webhook.secret"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    if not seed_path.exists():
        descriptor = os.open(seed_path, flags, 0o600)
        try:
            os.write(descriptor, secrets.token_bytes(32))
        finally:
            os.close(descriptor)
        os.chmod(seed_path, 0o600)
    if seed_path.is_symlink() or not seed_path.is_file():
        raise ProdSimRehearsalAuthorityError(
            "prod-sim human authority signing seed is unsafe"
        )
    seed = seed_path.read_bytes()
    if len(seed) != 32:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim human authority signing seed is invalid"
        )
    if not webhook_path.exists():
        descriptor = os.open(webhook_path, flags, 0o600)
        try:
            os.write(descriptor, secrets.token_hex(16).encode("ascii"))
        finally:
            os.close(descriptor)
        os.chmod(webhook_path, 0o600)
    if webhook_path.is_symlink() or not webhook_path.is_file():
        raise ProdSimRehearsalAuthorityError(
            "prod-sim human authority webhook secret is unsafe"
        )
    webhook = webhook_path.read_text(encoding="ascii").strip()
    if len(webhook) < 16:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim human authority webhook secret is too short"
        )
    return {
        "signingPrivateKeyBase64": base64.b64encode(seed).decode("ascii"),
        "webhookSecret": webhook,
        "providerCommit": _sha256_bytes(seed),
    }


def bind_prod_sim_platform_ops_rehearsal_runtime(
    *,
    candidate_digest: str,
) -> dict[str, str]:
    """把当前 package digest 与不可提升的 human-authority rehearsal 材料绑到 platform-ops。"""
    if _DIGEST.fullmatch(candidate_digest) is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim release manifest digest is invalid"
        )
    material = _ensure_prod_sim_human_authority_material()
    return {
        "RELEASE_MANIFEST_DIGEST": candidate_digest,
        "PLATFORM_OPS_HUMAN_AUTHORITY_ISSUER": _HUMAN_AUTHORITY_ISSUER,
        "PLATFORM_OPS_HUMAN_AUTHORITY_PROVIDER_VERSION": (
            _HUMAN_AUTHORITY_PROVIDER_VERSION
        ),
        "PLATFORM_OPS_HUMAN_AUTHORITY_PROVIDER_COMMIT": material["providerCommit"],
        "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_KEY_ID": _HUMAN_AUTHORITY_KEY_ID,
        "PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_BASE64": material[
            "signingPrivateKeyBase64"
        ],
        "PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_WEBHOOK_SECRET": material["webhookSecret"],
        "PLATFORM_OPS_HUMAN_AUTHORITY_ROLE_MAPPINGS": _HUMAN_AUTHORITY_ROLE_MAPPINGS,
    }


def _ensure_prod_sim_rollout_allocation_key() -> str:
    root = output_paths.deployment_target_path(
        PROD_SIM_TARGET, "secrets", "api-edge-rollout"
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    path = root / "allocation.key"
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ProdSimRehearsalAuthorityError(
                "prod-sim rollout allocation key is unsafe"
            )
        value = path.read_text(encoding="ascii").strip()
        if len(value.encode("ascii")) < 32:
            raise ProdSimRehearsalAuthorityError(
                "prod-sim rollout allocation key is too short"
            )
        return value
    value = secrets.token_hex(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, value.encode("ascii"))
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    return value


def bind_prod_sim_api_edge_rehearsal_runtime(
    *,
    config_root: Path,
    candidate_digest: str,
    source_policy: Path | None = None,
) -> dict[str, str]:
    """把 IaC 灰度策略绑到当前 package，并覆盖本地 compose 的 admission Redis。

    不改 packaged config.version：CONFIG_VERSION 仍钉住 package 身份。
    policy_sha256 随绑定后的策略字节重算，供 api-edge 运行时核验。
    """
    if _DIGEST.fullmatch(candidate_digest) is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim rollout candidate digest is invalid"
        )
    policy_path = source_policy or PROD_ROLLOUT_POLICY
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim rollout routing policy is unavailable"
        ) from error
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict) or policy.get("enabled") is not True:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim rollout routing policy must be enabled"
        )
    policy["candidateDigest"] = candidate_digest
    # 本地 rehearsal 没有 candidate 面；保持 enabled 以满足 prod 配置校验，
    # 但把 campaign 标为 complete，避免 assignment GET 走 Redis 热路径。
    policy["status"] = "complete"
    encoded = _dump_yaml(payload)
    policy_digest = _sha256_bytes(encoded)
    for destination in (
        config_root / "rollout" / "routing_policy.yaml",
        config_root / "gray-routing" / "policy.yaml",
    ):
        _write_bytes(destination, encoded)

    edge_path = config_root / "api-edge.yaml"
    try:
        edge = yaml.safe_load(edge_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim api-edge runtime config is unavailable"
        ) from error
    if not isinstance(edge, dict):
        raise ProdSimRehearsalAuthorityError("prod-sim api-edge runtime config is invalid")
    graph = edge.get("graphql_read")
    rollout = edge.get("rollout")
    version = ((edge.get("config") or {}).get("version") if isinstance(edge.get("config"), dict) else "")
    if not isinstance(graph, dict) or graph.get("candidate_digest") != candidate_digest:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim GraphQL registry candidate digest must match the package"
        )
    if not isinstance(rollout, dict) or rollout.get("enabled") is not True:
        raise ProdSimRehearsalAuthorityError("prod-sim api-edge rollout must stay enabled")
    if _DIGEST.fullmatch(str(version or "")) is None:
        raise ProdSimRehearsalAuthorityError("prod-sim api-edge config version is invalid")
    rollout["policy_file"] = "rollout/routing_policy.yaml"
    rollout["policy_sha256"] = policy_digest
    admission = ((edge.get("redis") or {}).get("admission") if isinstance(edge.get("redis"), dict) else None)
    if not isinstance(admission, dict):
        raise ProdSimRehearsalAuthorityError(
            "prod-sim api-edge admission Redis config is unavailable"
        )
    admission["mode"] = "standalone"
    admission["addr"] = "redis:6379"
    admission["tls"] = False
    admission.pop("addrs", None)
    _write_bytes(edge_path, _dump_yaml(edge))
    rebound = yaml.safe_load(edge_path.read_text(encoding="utf-8"))
    if rebound["config"]["version"] != version:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim api-edge config version drifted during rehearsal bind"
        )
    if rebound["rollout"]["policy_sha256"] != policy_digest:
        raise ProdSimRehearsalAuthorityError("prod-sim rollout policy digest bind drifted")
    _bind_prod_sim_assistant_skill_asset_root(config_root)
    _bind_prod_sim_product_ops_local_redis(config_root)
    return {
        "policyDigest": policy_digest,
        "allocationKey": _ensure_prod_sim_rollout_allocation_key(),
        "candidateDigest": candidate_digest,
    }


def _bind_prod_sim_assistant_skill_asset_root(config_root: Path) -> None:
    asset_root = "/etc/qwq-config/skill-packages/official"
    host_root = config_root / "skill-packages" / "official"
    releases = host_root / "releases"
    if not releases.is_dir() or releases.is_symlink():
        raise ProdSimRehearsalAuthorityError(
            "prod-sim packaged official Skill publication is not mounted in config-root"
        )
    publications = [
        path
        for path in releases.iterdir()
        if path.is_dir() and not path.is_symlink() and (path / "publication.json").is_file()
    ]
    if len(publications) != 1:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim official Skill bootstrap requires exactly one publication"
        )
    assistant_path = config_root / "assistant-service.yaml"
    try:
        assistant = yaml.safe_load(assistant_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant-service runtime config is unavailable"
        ) from error
    if not isinstance(assistant, dict):
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant-service runtime config is invalid"
        )
    skill = assistant.get("skill_package")
    version = (
        (assistant.get("config") or {}).get("version")
        if isinstance(assistant.get("config"), dict)
        else ""
    )
    if not isinstance(skill, dict):
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant-service skill_package config is unavailable"
        )
    if _DIGEST.fullmatch(str(version or "")) is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant-service config version is invalid"
        )
    skill["asset_root"] = asset_root
    _write_bytes(assistant_path, _dump_yaml(assistant))
    rebound = yaml.safe_load(assistant_path.read_text(encoding="utf-8"))
    if rebound["config"]["version"] != version:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant-service config version drifted during rehearsal bind"
        )
    if rebound["skill_package"]["asset_root"] != asset_root:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim assistant Skill asset_root bind drifted"
        )


def _bind_prod_sim_product_ops_local_redis(config_root: Path) -> None:
    path = config_root / "product-ops-service.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops-service runtime config is unavailable"
        ) from error
    if not isinstance(payload, dict):
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops-service runtime config is invalid"
        )
    redis = payload.get("redis")
    version = (
        (payload.get("config") or {}).get("version")
        if isinstance(payload.get("config"), dict)
        else ""
    )
    if not isinstance(redis, dict):
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops Redis config is unavailable"
        )
    if _DIGEST.fullmatch(str(version or "")) is None:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops-service config version is invalid"
        )
    for scene_name in ("general", "rec"):
        scene = redis.get(scene_name)
        if not isinstance(scene, dict):
            raise ProdSimRehearsalAuthorityError(
                f"prod-sim product-ops Redis {scene_name} config is unavailable"
            )
        scene["mode"] = "standalone"
        scene["addr"] = "redis:6379"
        scene["tls"] = False
        scene["addrs"] = []
    _write_bytes(path, _dump_yaml(payload))
    rebound = yaml.safe_load(path.read_text(encoding="utf-8"))
    if rebound["config"]["version"] != version:
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops-service config version drifted during rehearsal bind"
        )
    if rebound["redis"]["general"]["mode"] != "standalone":
        raise ProdSimRehearsalAuthorityError(
            "prod-sim product-ops Redis standalone bind drifted"
        )


def ensure_prod_sim_rehearsal_authorities_for_locked_up() -> dict[str, str]:
    """schema 先落地，再签发/复验 Post safety；供 service-core 启动前投影。"""
    ensure_prod_sim_user_schema_for_locked_up()
    return ensure_prod_sim_post_safety_for_locked_up()
