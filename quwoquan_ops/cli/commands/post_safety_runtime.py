"""stackctl post-safety-runtime：canonical plan/apply/verify。"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.deployment_candidate_manifest.candidate_fs import _read_candidate_bytes
from quwoquan_ops.cli.lib.local_runtime_reservation import local_stack_operation_lock
from quwoquan_ops.cli.lib.startup_attempt_receipt import _write_transaction_journal_exclusive

PLAN_SCHEMA = "stackctl-post-safety-runtime-plan"
PLAN_FILENAME = "post-safety-runtime-plan.json"
PLAN_TTL = timedelta(minutes=15)
DEPENDENCY_BLOCKER = "post_safety_runtime_dependency_unavailable"
DEPENDENCY_INSTALL = "run `make prepare-test-python` and execute stackctl with the managed Python interpreter"


def _runtime_dependencies():
    """只在实际 plan/apply/verify 执行时加载 Pydantic/PyMongo 运行链。"""
    try:
        import pymongo  # noqa: F401 - managed runtime dependency preflight
        from quwoquan_ops.cli.lib.data_plane_binding import validate_canonical_data_plane_binding
        from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
            PostSafetyDeploymentStartupMaterial, PostSafetyRuntimeCurrentBinding,
        )
        from quwoquan_ops.cli.lib.post_safety_runtime import (
            FileDeploymentStartupMaterialOwner, ManagedAuthorityConnectionFactory, PostSafetyTarget,
            ProductionAccountClosureAuthority, _read_once, create_new_runtime,
            produce_gamma_local_startup_material, verify_current,
        )
        from quwoquan_ops.cli.lib.source_allocation import SourceTarget
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(DEPENDENCY_BLOCKER) from error
    return {
        "FileDeploymentStartupMaterialOwner": FileDeploymentStartupMaterialOwner,
        "ManagedAuthorityConnectionFactory": ManagedAuthorityConnectionFactory,
        "PostSafetyDeploymentStartupMaterial": PostSafetyDeploymentStartupMaterial,
        "PostSafetyRuntimeCurrentBinding": PostSafetyRuntimeCurrentBinding,
        "PostSafetyTarget": PostSafetyTarget,
        "ProductionAccountClosureAuthority": ProductionAccountClosureAuthority,
        "SourceTarget": SourceTarget,
        "create_new_runtime": create_new_runtime,
        "produce_gamma_local_startup_material": produce_gamma_local_startup_material,
        "read_once": _read_once,
        "validate_canonical_data_plane_binding": validate_canonical_data_plane_binding,
        "verify_current": verify_current,
    }


def register_parser(subparsers):
    parser = subparsers.add_parser("post-safety-runtime", help="plan/apply/verify Content Post safety runtime")
    parser.add_argument("action", choices=("plan", "apply", "verify"))
    parser.add_argument("--target", required=True, choices=("alpha-local", "beta-local", "gamma-local"))
    parser.add_argument("--plan-ref", default="", help="exact PATH=sha256:DIGEST from planning")
    parser.add_argument("--confirm-post-safety-runtime", action="store_true")
    parser.add_argument("--report-dir", default="")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _canonical_model(value) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(raw: bytes) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate post safety plan key")
        result[key] = value
    return result


def _required(path: Path) -> bytes:
    raw = output_paths._read_secure_bytes(path, label="post safety input")
    if raw is None or len(raw) > 4 * 1024 * 1024 or path.stat(follow_symlinks=False).st_nlink != 1:
        raise ValueError("post safety input missing, oversized or linked")
    return raw


def _candidate_context(target: str, dependencies):
    snapshot = output_paths.active_deployment_candidate_snapshot(target)
    if snapshot is None:
        raise ValueError("post safety runtime requires current full candidate")
    root = Path(snapshot["candidateDir"])
    manifest = snapshot["manifest"]
    environment = target.removesuffix("-local")
    if manifest["environment"] != environment or manifest["target"] != target:
        raise ValueError("post safety candidate target differs")
    binding_ref = manifest["dataPlaneBinding"]
    binding_raw = _read_candidate_bytes(root, binding_ref["ref"], label="post safety data-plane binding")
    if _digest(binding_raw) != binding_ref["digest"]:
        raise ValueError("post safety data-plane bytes drift")
    binding = dependencies["validate_canonical_data_plane_binding"](json.loads(binding_raw, object_pairs_hook=_unique))
    rows = list(binding["bindings"].values())

    def owning(service, engine):
        found = [row for row in rows if row["service"] == service and row["engine"] == engine]
        if len(found) != 1:
            raise ValueError("post safety data-plane binding ambiguous")
        return found[0]

    mongo = owning("content-service", "mongodb")
    pg, redis = owning("user-service", "postgres"), owning("user-service", "redis")
    startup_owner = dependencies["FileDeploymentStartupMaterialOwner"](target)
    startup_raw = startup_owner.read()
    startup = dependencies["PostSafetyDeploymentStartupMaterial"].model_validate_json(startup_raw)
    if startup_raw != _canonical_model(startup.model_dump(mode="json")):
        raise ValueError("post safety startup material is not canonical exact bytes")
    expected = dependencies["PostSafetyTarget"](environment, target, manifest["packageDigest"], binding_ref["bindingDigest"],
        mongo["resource"], mongo["namespace"], startup.runtimeGeneration, startup.startupAttemptId)
    suffix = manifest["packageDigest"].removeprefix("sha256:")[:24]
    source = dependencies["SourceTarget"](environment, target, manifest["packageDigest"], binding_ref["bindingDigest"],
        pg["resource"], pg["namespace"], redis["resource"], redis["namespace"],
        "qwq_source_" + suffix, "qwq_source_" + suffix, "content-service-user-account-closed")
    if (startup.environment, startup.target, startup.candidateDigest, startup.dataPlaneBindingDigest) != (
        environment, target, manifest["packageDigest"], binding_ref["bindingDigest"]):
        raise ValueError("post safety startup/candidate binding differs")
    descriptor = startup.accountClosureAuthority
    if descriptor.contentMongo.database != mongo["namespace"] or descriptor.contentMongo.namespace != mongo["namespace"]:
        raise ValueError("post safety Content Mongo descriptor differs")
    if descriptor.sourceAllocationCurrent.allocationAttemptId != Path(descriptor.sourceAllocationCurrent.materialRoot.path).name:
        raise ValueError("source allocation attempt/material root differs")
    context = {"candidate": snapshot, "candidateBytesDigest": _digest(_read_candidate_bytes(root, "manifest.json", label="post safety candidate manifest")),
        "startupMaterialDigest": _digest(startup_raw), "targetBinding": asdict(expected),
        "sourceBinding": asdict(source), "postSafetyMaterialRoot": str(output_paths.deployment_target_path(target, "secrets", "post-safety", startup.runtimeGeneration))}
    output_paths.assert_active_deployment_candidate_snapshot(snapshot)
    if startup_owner.read() != startup_raw:
        raise ValueError("post safety startup material changed during read")
    return context, expected, source, binding, startup, startup_raw, startup_owner


def _plan_path(path: Path, target: str) -> Path:
    path = path.absolute()
    allowed = output_paths.output_root() / "env" / target.removesuffix("-local") / "runs"
    if path.name != PLAN_FILENAME or not path.is_relative_to(allowed):
        raise ValueError("post safety plan must be canonical target run evidence")
    return path


def _create_plan(args, context):
    import quwoquan_ops.cli.stackctl as stackctl
    report = stackctl.resolve_report_dir(args, args.target.removesuffix("-local"), args.target)
    report.mkdir(parents=True, exist_ok=True)
    path = _plan_path(report / PLAN_FILENAME, args.target)
    now = datetime.now(timezone.utc)
    plan = {"schema": PLAN_SCHEMA, "target": args.target, "context": context,
        "createdAt": now.isoformat(), "expiresAt": (now + PLAN_TTL).isoformat()}
    raw = _canonical(plan)
    _write_transaction_journal_exclusive(path, raw)
    return f"{path}={_digest(raw)}"


def _load_plan(args):
    if not args.confirm_post_safety_runtime or not args.plan_ref:
        raise ValueError("post safety apply requires exact plan and explicit confirmation")
    name, expected = args.plan_ref.rsplit("=", 1)
    path = _plan_path(Path(name), args.target)
    raw = _required(path)
    if _digest(raw) != expected:
        raise ValueError("post safety plan digest differs")
    plan = json.loads(raw, object_pairs_hook=_unique)
    if set(plan) != {"schema", "target", "context", "createdAt", "expiresAt"} or plan["schema"] != PLAN_SCHEMA or plan["target"] != args.target:
        raise ValueError("post safety plan identity differs")
    now = datetime.now(timezone.utc)
    start, end = datetime.fromisoformat(plan["createdAt"]), datetime.fromisoformat(plan["expiresAt"])
    if start > now or end <= now or end - start != PLAN_TTL:
        raise ValueError("post safety plan expired or invalid clock")
    return path, raw, plan


def _gamma_local_managed_connection_values(target=""):
    from quwoquan_ops.cli.commands.source_allocation import (
        _gamma_local_managed_connections, gamma_local_mongo_uri,
    )
    source = _gamma_local_managed_connections(create=False, target=target)
    return {
        "QWQ_SOURCE_PG_ADMIN_DSN": source["pg_admin"],
        "QWQ_SOURCE_REDIS_ADMIN_URL": source["redis_admin"],
        "QWQ_SOURCE_OLD_PG_DSN": source["old_pg"],
        "QWQ_SOURCE_OLD_REDIS_URL": source["old_redis"],
        "QWQ_CONTENT_MONGO_ADMIN_URI": gamma_local_mongo_uri(),
    }


def _connection_factory(target, dependencies, managed_connections=None):
    if managed_connections is not None:
        raise ValueError("caller managed connections are forbidden")
    values = _gamma_local_managed_connection_values(target) if target in {"alpha-local", "beta-local", "gamma-local"} else None
    return dependencies["ManagedAuthorityConnectionFactory"](values)


def _composition(expected, source, binding, startup, dependencies, connection_factory):
    descriptor = startup.accountClosureAuthority
    return dependencies["ProductionAccountClosureAuthority"](target=expected, descriptor=descriptor,
        authorization_root=output_paths.post_safety_startup_material_root(expected.target),
        source_expected=source, source_binding=binding, connection_factory=connection_factory)


def _database(startup, connection_factory):
    descriptor = startup.accountClosureAuthority.contentMongo
    return connection_factory.mongo(descriptor.admin.secretRef, descriptor.database)



def _gamma_local_startup_prerequisites(target: str, dependencies):
    if target not in {"alpha-local", "beta-local", "gamma-local"}:
        raise ValueError(f"local startup material producer does not support {target}")
    from quwoquan_ops.cli.commands.source_allocation import ensure_source_allocation_for_locked_up
    source_current, source, binding, connections = ensure_source_allocation_for_locked_up(target)
    snapshot = output_paths.active_deployment_candidate_snapshot(target)
    if snapshot is None: raise ValueError("post safety runtime requires current full candidate")
    manifest = snapshot["manifest"]; rows = list(binding["bindings"].values())
    mongo = [row for row in rows if row["service"] == "content-service" and row["engine"] == "mongodb"]
    if len(mongo) != 1: raise ValueError("post safety Content Mongo binding ambiguous")
    startup = output_paths.target_process_dir(target) / "startup_attempt.json"
    attempt = json.loads(_required(startup))
    attempt_id = str(attempt.get("attemptId") or "").strip()
    if not attempt_id: raise ValueError("post safety startup attempt missing")
    environment = target.removesuffix("-local")
    expected = dependencies["PostSafetyTarget"](environment, target, manifest["packageDigest"],
        manifest["dataPlaneBinding"]["bindingDigest"], mongo[0]["resource"], mongo[0]["namespace"], attempt_id, attempt_id)
    from quwoquan_ops.cli.commands.source_allocation import gamma_local_mongo_uri
    managed = {
        "QWQ_SOURCE_PG_ADMIN_DSN": connections["pg_admin"],
        "QWQ_SOURCE_REDIS_ADMIN_URL": connections["redis_admin"],
        "QWQ_SOURCE_OLD_PG_DSN": connections["old_pg"],
        "QWQ_SOURCE_OLD_REDIS_URL": connections["old_redis"],
        "QWQ_CONTENT_MONGO_ADMIN_URI": gamma_local_mongo_uri(),
    }
    factory = dependencies["ManagedAuthorityConnectionFactory"](managed)
    client, database = factory.mongo("QWQ_CONTENT_MONGO_ADMIN_URI", expected.namespace)
    account_root = output_paths.deployment_target_path(target, "secrets", "content-account-closure", attempt_id)
    try:
        dependencies["produce_gamma_local_startup_material"](current=expected, source_current=source_current,
            source_expected=source, source_binding=binding, database=database, account_material_root=account_root,
            connection_factory=factory, deployment_owner=dependencies["FileDeploymentStartupMaterialOwner"](target))
    finally:
        client.close()

def ensure_post_safety_runtime_for_locked_up(target: str) -> dict[str, str]:
    """在 stackctl up 已持有 target 锁时初始化或复验唯一 current。

    该内部入口不签发 startup material，也不接受 caller ref；它只消费 canonical
    deployment-owned startup.json。null current 只能在其签名 authorization 与全部
    account-closure/source 前驱读回成功后创建。普通重复 up 只 verify，不轮换 key。
    """
    dependencies = _runtime_dependencies()
    owner_type = dependencies.get("FileDeploymentStartupMaterialOwner")
    if owner_type is not None:
        owner = owner_type(target)
        if not owner.path.exists():
            _gamma_local_startup_prerequisites(target, dependencies)
    context, expected, source, binding, startup, startup_raw, owner = _candidate_context(
        target, dependencies
    )
    factory = _connection_factory(target, dependencies)
    authority = _composition(expected, source, binding, startup, dependencies, factory)
    material_root = Path(context["postSafetyMaterialRoot"])
    client, database = _database(startup, factory)
    try:
        if startup.postSafetyCurrent is None:
            # up 的外层 local_stack_operation_lock 是本次显式 startup mutation
            # fence；这里不能再次取同一非重入锁。所有前驱必须先完成只读核验。
            authority.verify_authorization(expected, startup.authorization)
            authority.account_closure(
                expected, startup.accountClosureAuthority.accountClosureEvidence
            )
            material_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            material_root.mkdir(mode=0o700, exist_ok=False)
            startup = dependencies["create_new_runtime"](
                startup_material_raw=startup_raw,
                current=expected,
                database=database,
                material_root=material_root,
                authority=authority,
                deployment_owner=owner,
            )
        else:
            dependencies["verify_current"](
                startup_material_raw=startup_raw,
                expected=expected,
                database=database,
                material_root=material_root,
                authority=authority,
            )
    finally:
        client.close()
    if startup.postSafetyCurrent is None:
        raise RuntimeError("post safety current remained null after startup preparation")
    current = dependencies["PostSafetyRuntimeCurrentBinding"].model_validate_json(
        dependencies["read_once"](material_root, startup.postSafetyCurrent)
    )
    account_descriptor = startup.accountClosureAuthority
    account_root = Path(account_descriptor.materialRoot.path)
    subject_secret = factory.relative_secret(
        account_root, account_descriptor.subjectHmacKey.secretRef
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


def command_post_safety_runtime(args):
    try:
        dependencies = _runtime_dependencies()
        if args.action == "plan":
            if args.plan_ref or args.confirm_post_safety_runtime:
                raise ValueError("post safety plan cannot consume approval")
            context, _, _, _, startup, _, _ = _candidate_context(args.target, dependencies)
            if startup.postSafetyCurrent is not None:
                raise ValueError("post safety current already exists")
            return {"exitCode": 0, "status": "planned", "planRef": _create_plan(args, context),
                "resourceMutation": False, "summary": "post safety runtime planned; explicit confirmation required"}
        if args.action == "verify":
            if args.plan_ref or args.confirm_post_safety_runtime:
                raise ValueError("post safety verify does not consume a plan")
            _, expected, source, binding, startup, raw, _ = _candidate_context(args.target, dependencies)
            factory = _connection_factory(args.target, dependencies)
            authority = _composition(expected, source, binding, startup, dependencies, factory)
            client, database = _database(startup, factory)
            try:
                dependencies["verify_current"](startup_material_raw=raw, expected=expected, database=database,
                    material_root=output_paths.deployment_target_path(args.target, "secrets", "post-safety", startup.runtimeGeneration),
                    authority=authority)
            finally:
                client.close()
            return {"exitCode": 0, "status": "verified", "summary": "post safety runtime current verified"}
        path, raw, plan = _load_plan(args)
        with local_stack_operation_lock(args.target):
            locked_path, locked_raw, locked_plan = _load_plan(args)
            if (locked_path, locked_raw, locked_plan) != (path, raw, plan):
                raise ValueError("post safety plan changed while acquiring lock")
            context, expected, source, binding, startup, startup_raw, owner = _candidate_context(args.target, dependencies)
            if context != plan["context"] or _required(path) != raw:
                raise ValueError("post safety candidate/startup/plan changed")
            material_root = Path(context["postSafetyMaterialRoot"])
            factory = _connection_factory(args.target, dependencies)
            authority = _composition(expected, source, binding, startup, dependencies, factory)
            # 所有前驱与现役owner闭包先只读核验，随后才创建runtime材料根和Mongo集合。
            authority.verify_authorization(expected, startup.authorization)
            authority.account_closure(expected, startup.accountClosureAuthority.accountClosureEvidence)
            material_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            material_root.mkdir(mode=0o700, exist_ok=False)
            client, database = _database(startup, factory)
            try:
                result = dependencies["create_new_runtime"](startup_material_raw=startup_raw, current=expected, database=database,
                    material_root=material_root, authority=authority, deployment_owner=owner)
            finally:
                client.close()
        return {"exitCode": 0, "status": "applied", "current": result.postSafetyCurrent.model_dump(mode="json"),
            "summary": "post safety runtime created and current verified"}
    except RuntimeError as error:
        if str(error) == DEPENDENCY_BLOCKER:
            return {"exitCode": 2, "status": "gate_block", "blockerKind": DEPENDENCY_BLOCKER,
                "summary": f"post safety runtime GATE_BLOCK: managed dependencies unavailable; {DEPENDENCY_INSTALL}"}
        return {"exitCode": 2, "status": "gate_block", "blockerKind": "post_safety_runtime_rejected",
            "summary": "post safety runtime GATE_BLOCK: check exact deployment material, signed predecessor, managed connections and current readback"}
    except Exception:
        return {"exitCode": 2, "status": "gate_block", "blockerKind": "post_safety_runtime_rejected",
            "summary": "post safety runtime GATE_BLOCK: check exact deployment material, signed predecessor, managed connections and current readback"}
