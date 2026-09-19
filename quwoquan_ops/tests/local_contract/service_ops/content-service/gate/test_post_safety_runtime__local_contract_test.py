# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
"""Post safety 环境 owner 生产与 authority 必须由真实读回闭合。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

class Binary(bytes):
    subtype = 4

class Timestamp:
    def __init__(self, time, inc): self.time, self.inc = time, inc
    def __eq__(self, other): return isinstance(other, Timestamp) and (self.time, self.inc) == (other.time, other.inc)

import pytest

from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
    PostSafetyAccountClosureAuthorityDescriptor, PostSafetyContentMongoAuthorityDescriptor,
    PostSafetyDeploymentStartupMaterial, PostSafetyMaterialRootLocator, PostSafetyRuntimeClosure,
    PostSafetyRuntimeEvidence, PostSafetySecretRefDescriptor, PostSafetySourceAllocationCurrentDescriptor,
)
from quwoquan_ops.cli.lib.post_safety_runtime import PostSafetyRuntimeError, PostSafetyTarget, create_new_runtime, verify_current


class Mongo:
    name = "quwoquan_content"
    def __init__(self):
        self.created = False
        self.uuid = Binary(UUID("018f65ec-2b31-7d87-a490-91f80f67c53a").bytes)
        self.rows = []
        self.watermark = Timestamp(42, 7)

    def command(self, command):
        if "listCollections" in command:
            rows = [] if not self.created else [{"name": "post_safety_states", "info": {"uuid": self.uuid}}]
            return {"cursor": {"firstBatch": rows}}
        if command.get("create") == "post_safety_states":
            if self.created: raise RuntimeError("already exists")
            self.created = True
            return {"ok": 1}
        if command.get("aggregate") == "post_safety_states":
            assert command["readConcern"]["level"] == "majority"
            if "afterClusterTime" in command["readConcern"]:
                assert command["readConcern"]["afterClusterTime"] == self.watermark
            return {"cursor": {"firstBatch": list(self.rows)}, "operationTime": self.watermark}
        raise AssertionError(command)


class Authority:
    def __init__(self):
        self.bytes = {
            "new.json": b'{"decision":"approved","owner":"environment-ops"}',
            "closure.json": b'{"count":0,"watermark":"account-source:0-0"}',
        }

    def evidence(self, ref):
        return PostSafetyRuntimeEvidence(ref=ref, digest="sha256:" + hashlib.sha256(self.bytes[ref]).hexdigest())

    def verify_authorization(self, target, evidence):
        if target.environment not in {"alpha", "beta", "gamma"}: raise PostSafetyRuntimeError("production denied")
        if evidence != self.evidence("new.json"): raise PostSafetyRuntimeError("authorization owner evidence differs")
        return self.verify_evidence(evidence)

    def account_closure(self, target, evidence):
        if evidence != self.evidence("closure.json"): raise PostSafetyRuntimeError("account closure owner evidence differs")
        return PostSafetyRuntimeClosure(kind="account_closure", recordCount=0, canonicalDigest="sha256:" + hashlib.sha256(b"[]").hexdigest(), watermark="account-source:0-0", ownerEvidence=evidence)

    def verify_evidence(self, evidence):
        raw = self.bytes.get(evidence.ref)
        if raw is None or "sha256:" + hashlib.sha256(raw).hexdigest() != evidence.digest:
            raise PostSafetyRuntimeError("authority evidence unavailable")
        return raw


def target(environment="gamma"):
    return PostSafetyTarget(environment, environment + "-local", "sha256:" + "a" * 64, "sha256:" + "b" * 64, "primary-mongodb", "quwoquan_content", "generation-7", "startup-attempt-9")


def canonical(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()

def account_descriptor(authority):
    secret = lambda ref: PostSafetySecretRefDescriptor(secretRef=ref)
    return PostSafetyAccountClosureAuthorityDescriptor(
        environment="gamma", target="gamma-local", candidateDigest="sha256:" + "a" * 64,
        dataPlaneBindingDigest="sha256:" + "b" * 64, startupAttemptId="startup-attempt-9",
        runtimeGeneration="generation-7",
        accountClosureEvidence=authority.evidence("closure.json"),
        materialRoot=PostSafetyMaterialRootLocator(path="/canonical/account-closure"),
        subjectHmacKey=secret("subject.key"),
        sourceAllocationCurrent=PostSafetySourceAllocationCurrentDescriptor(
            allocationAttemptId="source-attempt-1",
            materialRoot=PostSafetyMaterialRootLocator(path="/canonical/source/source-attempt-1"),
            sourceCreation=PostSafetyRuntimeEvidence(ref="source-creation.json", digest="sha256:" + "5" * 64),
        ),
        postgresAdminReadback=secret("QWQ_SOURCE_PG_ADMIN_DSN"),
        redisAdminReadback=secret("QWQ_SOURCE_REDIS_ADMIN_URL"),
        oldPostgresPrincipalProbe=secret("QWQ_SOURCE_OLD_PG_DSN"),
        oldRedisPrincipalProbe=secret("QWQ_SOURCE_OLD_REDIS_URL"),
        contentMongo=PostSafetyContentMongoAuthorityDescriptor(
            admin=secret("QWQ_CONTENT_MONGO_ADMIN_URI"), database="quwoquan_content", namespace="quwoquan_content"),
    )


def startup_material(authority, **updates):
    value = PostSafetyDeploymentStartupMaterial(
        environment="gamma", target="gamma-local",
        candidateDigest="sha256:" + "a" * 64,
        dataPlaneBindingDigest="sha256:" + "b" * 64,
        startupAttemptId="startup-attempt-9", runtimeGeneration="generation-7",
        authorization=authority.evidence("new.json"),
        accountClosureAuthority=account_descriptor(authority),
        postSafetyCurrent=None,
    ).model_copy(update=updates)
    return canonical(value.model_dump(mode="json"))

class DeploymentOwner:
    def __init__(self, current): self.current, self.calls = current, []
    def compare_and_swap(self, expected, replacement):
        self.calls.append((expected, replacement))
        if self.current != expected: raise PostSafetyRuntimeError("startup material CAS differs")
        self.current = replacement

def apply(root, mongo, authority, *, raw=None, owner=None):
    initial = raw or startup_material(authority)
    deployment = owner or DeploymentOwner(initial)
    result = create_new_runtime(startup_material_raw=initial, current=target(), database=mongo, material_root=root, authority=authority, deployment_owner=deployment)
    return result, deployment


def test_generated_dto_canonical_bytes_match_go_struct_field_order():
    authority = Authority()
    raw = startup_material(authority)
    assert raw.startswith(b'{"environment":"gamma","target":"gamma-local","candidateDigest":')
    assert b'"authorization":' in raw
    assert raw.index(b'"authorization":') < raw.index(b'"accountClosureAuthority":')
    assert raw.index(b'"accountClosureAuthority":') < raw.index(b'"postSafetyCurrent":')


def test_real_owner_producer_and_strict_current_readback(tmp_path):
    root = (tmp_path / "runtime").absolute(); root.mkdir(mode=0o700)
    mongo, authority = Mongo(), Authority()
    current, deployment = apply(root, mongo, authority)
    fact = verify_current(startup_material_raw=deployment.current, expected=target(), database=mongo, material_root=root, authority=authority)
    assert current.postSafetyCurrent is not None
    bound = PostSafetyDeploymentStartupMaterial.model_validate_json(deployment.current)
    current_binding = json.loads((root / bound.postSafetyCurrent.ref).read_text())
    assert current_binding["binding"]["physicalInstanceId"] == "mongodb-collection-uuid:018f65ec2b317d87a49091f80f67c53a"
    assert fact.closures[1].watermark == "mongodb-timestamp:42:7"
    assert current_binding["binding"]["hmacKeyIdentity"].startswith("sha256:")
    assert [row.kind for row in fact.closures] == ["account_closure", "post_safety"]
    assert fact.closures[1].recordCount == 0
    assert {path.name for path in root.iterdir()} == {
        "post-safety.key", "creation.json", "fact.json", "current.json",
        "startup.json", "new.json", "closure.json",
    }
    assert (root / "startup.json").read_bytes() == deployment.current
    assert (root / "new.json").read_bytes() == authority.bytes["new.json"]
    assert (root / "closure.json").read_bytes() == authority.bytes["closure.json"]
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in root.iterdir())

    mongo.uuid = Binary(UUID("018f65ec-2b31-7d87-a490-91f80f67ffff").bytes)
    with pytest.raises(PostSafetyRuntimeError, match="binding differs"):
        verify_current(startup_material_raw=deployment.current, expected=target(), database=mongo, material_root=root, authority=authority)



def test_verify_current_accepts_advanced_majority_watermark_but_rejects_regression(tmp_path):
    root = (tmp_path / "watermark-advance").absolute(); root.mkdir(mode=0o700)
    mongo, authority = Mongo(), Authority()
    _, deployment = apply(root, mongo, authority)
    mongo.watermark = Timestamp(43, 0)
    fact = verify_current(startup_material_raw=deployment.current, expected=target(), database=mongo, material_root=root, authority=authority)
    assert fact.closures[1].watermark == "mongodb-timestamp:42:7"
    mongo.watermark = Timestamp(41, 9)
    with pytest.raises(PostSafetyRuntimeError, match="watermark regressed"):
        verify_current(startup_material_raw=deployment.current, expected=target(), database=mongo, material_root=root, authority=authority)

def test_fail_closed_for_prod_existing_storage_and_drift(tmp_path):
    for environment in ("prod",):
        root = (tmp_path / environment).absolute(); root.mkdir(mode=0o700)
        with pytest.raises(PostSafetyRuntimeError, match="nonproduction"):
            create_new_runtime(startup_material_raw=startup_material(Authority(), environment="prod", target="prod-hosted", startupAttemptId="a", runtimeGeneration="g"), current=PostSafetyTarget(environment, "prod-hosted", "sha256:" + "a" * 64, "sha256:" + "b" * 64, "mongo", "quwoquan_content", "g", "a"), database=Mongo(), material_root=root, authority=Authority(), deployment_owner=DeploymentOwner(startup_material(Authority(), environment="prod", target="prod-hosted", startupAttemptId="a", runtimeGeneration="g")))

    root = (tmp_path / "existing").absolute(); root.mkdir(mode=0o700)
    mongo = Mongo(); mongo.created = True
    with pytest.raises(PostSafetyRuntimeError, match="existing"):
        apply(root, mongo, Authority())[0]
    assert not list(root.iterdir())

    root = (tmp_path / "drift").absolute(); root.mkdir(mode=0o700)
    mongo = Mongo(); authority = Authority()
    _, deployment = apply(root, mongo, authority)
    original = json.loads((root / "current.json").read_text())
    original["binding"]["candidateDigest"] = "sha256:" + "c" * 64
    (root / "current.json").write_text(json.dumps(original, separators=(",", ":")))
    (root / "current.json").chmod(0o600)
    with pytest.raises(PostSafetyRuntimeError):
        verify_current(startup_material_raw=deployment.current, expected=target(), database=mongo, material_root=root, authority=authority)


def test_authority_is_typed_and_exact_not_boolean(tmp_path):
    root = (tmp_path / "authority").absolute(); root.mkdir(mode=0o700)
    authority = Authority()
    material = startup_material(authority)
    authority.bytes["new.json"] += b" "
    mongo = Mongo()
    with pytest.raises(PostSafetyRuntimeError, match="authorization owner evidence differs"):
        apply(root, mongo, authority, raw=material)[0]
    assert not mongo.created


def test_uuid_uuid_form_timestamp_missing_and_path_replacement_fail_closed(tmp_path, monkeypatch):
    root = (tmp_path / "bson").absolute(); root.mkdir(mode=0o700)
    mongo, authority = Mongo(), Authority()
    mongo.uuid = UUID("018f65ec-2b31-7d87-a490-91f80f67c53a")
    _, deployment = apply(root, mongo, authority)
    evidence = deployment.current
    assert verify_current(startup_material_raw=evidence, expected=target(), database=mongo, material_root=root, authority=authority).binding.physicalInstanceId.endswith("018f65ec2b317d87a49091f80f67c53a")

    mongo.watermark = None
    with pytest.raises(PostSafetyRuntimeError, match="operationTime"):
        verify_current(startup_material_raw=evidence, expected=target(), database=mongo, material_root=root, authority=authority)
    mongo.watermark = Timestamp(42, 7)

    import os
    real_open = os.open
    replaced = False
    def replacing_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == "current.json" and kwargs.get("dir_fd") is not None and not replaced:
            replaced = True
            old = root / "current.old"
            (root / "current.json").rename(old)
            (root / "current.json").write_bytes(old.read_bytes())
            (root / "current.json").chmod(0o600)
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", replacing_open)
    with pytest.raises(PostSafetyRuntimeError, match="root changed|digest differs"):
        verify_current(startup_material_raw=evidence, expected=target(), database=mongo, material_root=root, authority=authority)


def test_startup_material_requires_null_then_create_once_cas(tmp_path):
    root = (tmp_path / "deployment").absolute(); root.mkdir(mode=0o700)
    mongo, authority = Mongo(), Authority()
    initial = startup_material(authority)
    current, deployment = apply(root, mongo, authority, raw=initial)
    assert len(deployment.calls) == 1
    assert PostSafetyDeploymentStartupMaterial.model_validate_json(deployment.current).postSafetyCurrent.ref == "current.json"
    with pytest.raises(PostSafetyRuntimeError, match="must be null"):
        create_new_runtime(startup_material_raw=deployment.current, current=target(), database=mongo, material_root=root, authority=authority, deployment_owner=deployment)


@pytest.mark.parametrize("field", ["candidateDigest", "startupAttemptId", "runtimeGeneration"])
def test_startup_material_identity_drift_is_rejected(tmp_path, field):
    root = (tmp_path / field).absolute(); root.mkdir(mode=0o700)
    authority = Authority()
    value = {"candidateDigest": "sha256:" + "c" * 64, "startupAttemptId": "other-attempt", "runtimeGeneration": "other-generation"}[field]
    with pytest.raises(PostSafetyRuntimeError, match="startup material binding differs"):
        apply(root, Mongo(), authority, raw=startup_material(authority, **{field: value}))


def test_arbitrary_caller_evidence_refs_are_rejected(tmp_path):
    root = (tmp_path / "caller").absolute(); root.mkdir(mode=0o700)
    authority = Authority()
    arbitrary = PostSafetyRuntimeEvidence(ref="caller/chosen.json", digest="sha256:" + "f" * 64)
    with pytest.raises(PostSafetyRuntimeError, match="authorization owner evidence differs"):
        apply(root, Mongo(), authority, raw=startup_material(authority, authorization=arbitrary))
    assert not list(root.iterdir())


def test_missing_startup_material_field_is_rejected(tmp_path):
    root = (tmp_path / "missing").absolute(); root.mkdir(mode=0o700)
    authority = Authority()
    value = json.loads(startup_material(authority)); del value["accountClosureAuthority"]
    with pytest.raises(PostSafetyRuntimeError, match="startup material is invalid"):
        apply(root, Mongo(), authority, raw=canonical(value))


def test_account_closure_caller_ref_is_rejected_before_mutation(tmp_path):
    root = (tmp_path / "account-caller").absolute(); root.mkdir(mode=0o700)
    authority = Authority()
    arbitrary = PostSafetyRuntimeEvidence(ref="caller/account.json", digest="sha256:" + "e" * 64)
    mongo = Mongo()
    with pytest.raises(PostSafetyRuntimeError, match="account closure owner evidence differs"):
        apply(root, mongo, authority, raw=startup_material(authority, accountClosureAuthority=account_descriptor(authority).model_copy(update={"accountClosureEvidence": arbitrary})))
    assert not mongo.created
    assert not list(root.iterdir())


def test_startup_material_cas_failure_does_not_publish_pointer(tmp_path):
    root = (tmp_path / "cas").absolute(); root.mkdir(mode=0o700)
    authority = Authority(); initial = startup_material(authority)
    owner = DeploymentOwner(startup_material(authority, runtimeGeneration="competing-generation"))
    with pytest.raises(PostSafetyRuntimeError, match="CAS differs"):
        apply(root, Mongo(), authority, raw=initial, owner=owner)
    assert PostSafetyDeploymentStartupMaterial.model_validate_json(owner.current).postSafetyCurrent is None

def test_signed_authorization_binds_action_identity_predecessor_and_target(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from quwoquan_ops.cli.lib.generated.post_safety_runtime import PostSafetyRuntimeAuthorization
    import quwoquan_ops.cli.lib.post_safety_runtime as runtime
    authority = Authority(); predecessor = authority.evidence("closure.json")
    value = PostSafetyRuntimeAuthorization(environment="gamma", target="gamma-local", candidateDigest="sha256:"+"a"*64,
        dataPlaneBindingDigest="sha256:"+"b"*64, startupAttemptId="startup-attempt-9", runtimeGeneration="generation-7",
        action="initialize_post_safety_runtime", issuedAt=datetime.now(timezone.utc), authorityIdentity="quwoquan-environment-ops-local",
        evidencePredecessor=predecessor, signature="ed25519:"+"A"*88)
    raw = canonical(value.model_dump(mode="json")); evidence = PostSafetyRuntimeEvidence(ref="authorization.json", digest="sha256:"+hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(runtime, "load_keyring", lambda path: object())
    monkeypatch.setattr(runtime, "ed25519_environment_verifier", lambda keyring, identities: lambda identity,payload,signature: True)
    assert runtime.verify_runtime_authorization(raw=raw,evidence=evidence,target=target(),expected_predecessor=predecessor).action == "initialize_post_safety_runtime"
    for field, changed in (("candidateDigest","sha256:"+"c"*64),("startupAttemptId","other"),("runtimeGeneration","other")):
        drift=value.model_copy(update={field:changed}); drift_raw=canonical(drift.model_dump(mode="json")); drift_ref=PostSafetyRuntimeEvidence(ref="authorization.json",digest="sha256:"+hashlib.sha256(drift_raw).hexdigest())
        with pytest.raises(PostSafetyRuntimeError, match="target/action"):
            runtime.verify_runtime_authorization(raw=drift_raw,evidence=drift_ref,target=target(),expected_predecessor=predecessor)


def test_startup_material_producer_uses_canonical_create_once_path(tmp_path, monkeypatch):
    import quwoquan_ops.cli.lib.output_paths as paths
    import quwoquan_ops.cli.lib.post_safety_runtime as runtime
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path/"deploy"))
    authority=Authority(); owner=runtime.FileDeploymentStartupMaterialOwner("gamma-local")
    material=runtime.produce_startup_material(current=target(),authorization=authority.evidence("new.json"),account_closure_authority=account_descriptor(authority),authority=authority,deployment_owner=owner)
    assert material.postSafetyCurrent is None
    assert owner.path == paths.post_safety_startup_material_path("gamma-local")
    assert owner.read() == canonical(material.model_dump(mode="json"))
    with pytest.raises(FileExistsError):
        runtime.produce_startup_material(current=target(),authorization=authority.evidence("new.json"),account_closure_authority=account_descriptor(authority),authority=authority,deployment_owner=owner)


def test_production_account_closure_adapter_binds_descriptor_and_calls_owner_verifier(monkeypatch):
    import quwoquan_ops.cli.lib.content_account_closure_runtime as closure
    import quwoquan_ops.cli.lib.post_safety_runtime as runtime
    descriptor = account_descriptor(Authority())
    calls = []
    verified = type("Verified", (), {"recordCount": 3, "canonicalDigest": "sha256:" + "9" * 64})()
    monkeypatch.setattr(closure, "verify_content_account_closure_current", lambda **kwargs: calls.append(kwargs) or verified)
    class Connections:
        def mongo(self, ref, database): return Mongo(), Mongo()
        def postgres(self, ref): return object()
        def redis(self, ref): return object()
        def text(self, ref): return "managed-old-pg"
    adapter = runtime.ProductionAccountClosureAuthority(target=target(), descriptor=descriptor,
        authorization_root=Path("/unused"), source_expected=object(), source_binding={}, connection_factory=Connections())
    closure_value = adapter.account_closure(target(), descriptor.accountClosureEvidence)
    assert closure_value.recordCount == 3 and len(calls) == 1
    assert calls[0]["evidence"].ref == "closure.json"
    assert calls[0]["subject_key_ref"] == "subject.key"
    assert calls[0]["source_material_root"] == Path("/canonical/source/source-attempt-1")

    drift = descriptor.model_copy(update={"runtimeGeneration": "other"})
    with pytest.raises(PostSafetyRuntimeError, match="deployment binding differs"):
        runtime.ProductionAccountClosureAuthority(target=target(), descriptor=drift, authorization_root=Path("/unused"),
            source_expected=object(), source_binding={}, connection_factory=Connections())


def test_gamma_local_producer_uses_real_local_signer_and_prod_or_missing_source_fail_closed(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import os
    from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing
    from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import ContentAccountClosureRuntimeEvidenceRef
    import quwoquan_ops.cli.lib.content_account_closure_runtime as closure
    import quwoquan_ops.cli.lib.post_safety_runtime as runtime

    signing = create_temporary_signing(tmp_path / "signing", identities=(runtime.ENVIRONMENT_OPS_IDENTITY,))
    monkeypatch.setenv("QWQ_EVIDENCE_SIGNING_KEY_ROOT", str(signing.key_root))
    source_root = (tmp_path / "source" / "attempt-source").absolute(); source_root.mkdir(parents=True)
    source = PostSafetySourceAllocationCurrentDescriptor(
        allocationAttemptId=source_root.name, materialRoot=PostSafetyMaterialRootLocator(path=str(source_root)),
        sourceCreation=PostSafetyRuntimeEvidence(ref="source-creation.json", digest="sha256:" + "5" * 64))
    account_raw = b'{"verified":"real-owner-seam"}'
    captured = {}
    def create_account(**kwargs):
        path = kwargs["material_root"] / "content-account-closure-runtime.json"
        path.write_bytes(account_raw); path.chmod(0o600)
        return ContentAccountClosureRuntimeEvidenceRef(ref=path.name, digest="sha256:" + hashlib.sha256(account_raw).hexdigest())
    monkeypatch.setattr(closure, "create_content_account_closure_runtime", create_account)
    def consume(**kwargs):
        captured.update(kwargs)
        raw = kwargs["deployment_owner"].read() if kwargs["deployment_owner"].path.exists() else None
        assert raw is None
        authorization_raw = runtime._read_once(runtime.post_safety_startup_material_root("gamma-local"), kwargs["authorization"])
        runtime.verify_runtime_authorization(raw=authorization_raw, evidence=kwargs["authorization"], target=target(),
            expected_predecessor=kwargs["account_closure_authority"].accountClosureEvidence, keyring_path=signing.keyring_path)
        return object()
    monkeypatch.setattr(runtime, "produce_startup_material", consume)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str((tmp_path / "deploy").absolute()))
    runtime.produce_gamma_local_startup_material(current=target(), source_current=source, source_expected=object(),
        source_binding={}, database=Mongo(), account_material_root=(tmp_path / "account").absolute(),
        connection_factory=object(), deployment_owner=runtime.FileDeploymentStartupMaterialOwner("gamma-local"),
        keyring_path=signing.keyring_path, now=datetime(2026, 9, 14, tzinfo=timezone.utc))
    authorization_raw = runtime._read_once(runtime.post_safety_startup_material_root("gamma-local"), captured["authorization"])
    tampered = json.loads(authorization_raw); tampered["runtimeGeneration"] = "tampered"
    tampered_raw = canonical(tampered); tampered_ref = PostSafetyRuntimeEvidence(ref="authorization.json", digest="sha256:" + hashlib.sha256(tampered_raw).hexdigest())
    with pytest.raises(PostSafetyRuntimeError):
        runtime.verify_runtime_authorization(raw=tampered_raw, evidence=tampered_ref, target=target(),
            expected_predecessor=captured["account_closure_authority"].accountClosureEvidence, keyring_path=signing.keyring_path)

    with pytest.raises(PostSafetyRuntimeError, match="does not support"):
        runtime.produce_gamma_local_startup_material(current=PostSafetyTarget("prod", "prod-hosted", "sha256:"+"a"*64,
            "sha256:"+"b"*64, "mongo", "quwoquan_content", "generation", "attempt"), source_current=source,
            source_expected=object(), source_binding={}, database=Mongo(), account_material_root=(tmp_path/"prod-account").absolute(),
            connection_factory=object(), deployment_owner=runtime.FileDeploymentStartupMaterialOwner("prod-hosted"), keyring_path=signing.keyring_path)
    missing = source.model_copy(update={"sourceCreation": source.sourceCreation.model_copy(update={"ref": "missing.json"})})
    with pytest.raises(PostSafetyRuntimeError, match="source allocation current"):
        runtime.produce_gamma_local_startup_material(current=target(), source_current=missing, source_expected=object(),
            source_binding={}, database=Mongo(), account_material_root=(tmp_path/"missing-account").absolute(),
            connection_factory=object(), deployment_owner=runtime.FileDeploymentStartupMaterialOwner("gamma-local"), keyring_path=signing.keyring_path)
