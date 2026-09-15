"""stackctl source-allocation：exact plan、显式确认与锁内现役candidate复验。"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.deployment_candidate_manifest.candidate_fs import _read_candidate_bytes
from quwoquan_ops.cli.lib.source_initializer_package import contract, digest, load_source_initializer
from quwoquan_ops.cli.lib.source_allocation import SourceTarget, SourceAllocationError, _allocate, validate_target
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt, _write_transaction_journal_exclusive
from quwoquan_ops.cli.lib.local_runtime_reservation import local_stack_operation_lock


def register_parser(subparsers):
    parser=subparsers.add_parser("source-allocation",help="plan/apply a new managed nonproduction User event source")
    parser.add_argument("action",choices=("plan","apply"))
    parser.add_argument("--target",required=True,choices=contract()["targets"])
    parser.add_argument("--plan-ref",default="",help="exact PATH=sha256:DIGEST from planning")
    parser.add_argument("--confirm-source-allocation",action="store_true")
    parser.add_argument("--report-dir",default="")


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError("duplicate source plan key")
        result[key]=value
    return result


def _required(path):
    raw=output_paths._read_secure_bytes(path,label="source allocation input")
    if raw is None or len(raw)>4*1024*1024: raise ValueError("source allocation input missing or oversized")
    if path.stat(follow_symlinks=False).st_nlink!=1: raise ValueError("source input hardlink rejected")
    return raw


def _startup_digest(target):
    from quwoquan_ops.cli.lib.startup_attempt_receipt import startup_attempt_path
    raw=output_paths._read_secure_bytes(startup_attempt_path(target),label="source startup exact bytes")
    return digest(raw) if raw is not None else None


def _connection_values():
    refs=contract()["credentials"]
    values={role:os.environ.get(reference,"") for role,reference in refs.items()}
    if not all(values.values()): raise ValueError("source management connection reference missing")
    return values

def _connection_identity(values=None):
    refs=contract()["credentials"]
    selected = _connection_values() if values is None else values
    if set(selected) != set(refs) or not all(isinstance(value,str) and value for value in selected.values()):
        raise ValueError("source management connection reference missing")
    return {role:{"envRef":refs[role],"digest":digest(selected[role].encode())} for role in refs}


def _current(target, *, allow_active_startup=False, management_connections=None):
    """不接受caller snapshot；每次由canonical active loader独立取得当前包。"""
    snapshot=output_paths.active_deployment_candidate_snapshot(target)
    if snapshot is None: raise ValueError("source allocation requires current full candidate")
    root=Path(snapshot["candidateDir"])
    manifest=snapshot["manifest"]
    env=target.removesuffix("-local")
    if manifest["environment"]!=env or manifest["target"]!=target: raise ValueError("candidate target differs")
    binding_ref=manifest["dataPlaneBinding"]
    binding_bytes=_read_candidate_bytes(root,binding_ref["ref"],label="source data-plane binding")
    if digest(binding_bytes)!=binding_ref["digest"]: raise ValueError("data-plane bytes drift")
    binding=json.loads(binding_bytes,object_pairs_hook=_unique)
    shared_bytes=_read_candidate_bytes(root,"packages/runtime-shared/manifest.json",label="source runtime-shared manifest")
    shared=json.loads(shared_bytes,object_pairs_hook=_unique)
    initializer=load_source_initializer(root,shared.get("sourceInitializer"),env,target)
    rows=list(binding["bindings"].values())
    def owning(engine):
        found=[row for row in rows if row["service"]=="user-service" and row["engine"]==engine]
        if len(found)!=1: raise ValueError("User source resource binding ambiguous")
        return found[0]
    pg,redis=owning("postgres"),owning("redis")
    # 角色与ACL名由exact candidate唯一派生，用户不能传任意命令/资源参数。
    suffix=manifest["packageDigest"].removeprefix("sha256:")[:24]
    selected=SourceTarget(env,target,manifest["packageDigest"],binding_ref["bindingDigest"],pg["resource"],pg["namespace"],redis["resource"],redis["namespace"],"qwq_source_"+suffix,"qwq_source_"+suffix,"content-service-user-account-closed")
    validate_target(selected,selected,binding)
    startup=load_startup_attempt(target)
    if not allow_active_startup and startup is not None and startup.get("status") not in {"stopped","failed"}:
        raise ValueError("source allocation requires stopped startup execution")
    context={"candidate":snapshot,"sharedDigest":digest(shared_bytes),"candidateBytesDigest":digest(_read_candidate_bytes(root,"manifest.json",label="source candidate manifest")),"startup":startup,"startupBytesDigest":_startup_digest(target),"source":asdict(selected),"initializer":shared["sourceInitializer"],"contractDigest":digest((output_paths.ROOT/"quwoquan_ops/policies/source_allocation.yaml").read_bytes()),"managementConnections":_connection_identity(management_connections)}
    output_paths.assert_active_deployment_candidate_snapshot(snapshot)
    if load_startup_attempt(target)!=startup:
        raise ValueError("startup changed during source plan read")
    return context,selected,binding,initializer


def _plan_path(path,target):
    path=path.absolute()
    allowed=output_paths.output_root()/"env"/target.removesuffix("-local")/"runs"
    if path.name!=contract()["plan_filename"] or not path.is_relative_to(allowed):
        raise ValueError("source plan must be exact canonical target run evidence")
    fd,_=output_paths._open_directory_chain(path.parent,label="source plan parent")
    os.close(fd)
    return path


def _create_plan(args,context):
    import quwoquan_ops.cli.stackctl as stackctl
    env=args.target.removesuffix("-local")
    report=stackctl.resolve_report_dir(args,env,args.target)
    allowed=output_paths.output_root()/"env"/env/"runs"
    if not report.absolute().is_relative_to(allowed) or report.absolute().resolve()!=report.absolute():
        raise ValueError("source plan report outside canonical runs")
    report.mkdir(parents=True,exist_ok=True)
    path=_plan_path(report/contract()["plan_filename"],args.target)
    now=datetime.now(timezone.utc)
    root=output_paths.deployment_target_path(args.target,"secrets","source-allocation",digest(json.dumps(context,sort_keys=True).encode()).removeprefix("sha256:"))
    plan={"schema":contract()["plan_schema"],"target":args.target,"context":context,"materialRoot":str(root),"createdAt":now.isoformat(),"expiresAt":(now+timedelta(seconds=contract()["plan_ttl_seconds"])).isoformat()}
    raw=json.dumps(plan,sort_keys=True,separators=(",", ":")).encode()
    _write_transaction_journal_exclusive(path,raw)
    return f"{path}={digest(raw)}"


def _load_plan(args):
    if not args.confirm_source_allocation or not args.plan_ref:
        raise ValueError("source apply requires exact plan and explicit confirmation")
    name,expected=args.plan_ref.rsplit("=",1)
    path=_plan_path(Path(name),args.target)
    raw=_required(path)
    if digest(raw)!=expected: raise ValueError("source plan digest differs")
    plan=json.loads(raw,object_pairs_hook=_unique)
    if not isinstance(plan,dict) or set(plan)!=set(contract()["plan_fields"]) or plan["schema"]!=contract()["plan_schema"] or plan["target"]!=args.target:
        raise ValueError("source plan identity differs")
    if not isinstance(plan["context"],dict) or set(plan["context"])!=set(contract()["context_fields"]):
        raise ValueError("source plan context fields differ")
    now=datetime.now(timezone.utc)
    start=datetime.fromisoformat(plan["createdAt"]); end=datetime.fromisoformat(plan["expiresAt"])
    if start>now or end<=now or end-start!=timedelta(seconds=contract()["plan_ttl_seconds"]): raise ValueError("source plan expired or invalid clock")
    return path,raw,plan


def _apply_connections(selected,binding,root,initializer,connection_identity, *, management_connections=None, create_root=True, prepared_redis_password_value=None):
    import psycopg
    import redis
    refs=contract()["credentials"]
    values=_connection_values() if management_connections is None else management_connections
    if set(values)!=set(refs) or not all(values.values()) or _connection_identity(values)!=connection_identity:
        raise ValueError("source management connection references changed")
    with psycopg.connect(values["pg_admin"],autocommit=True) as pg:
        admin=redis.Redis.from_url(values["redis_admin"],decode_responses=True)
        old=redis.Redis.from_url(values["old_redis"],decode_responses=True)
        try:
            if create_root:
                root.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                if not root.exists(): root.mkdir(mode=0o700,exist_ok=False)
                elif not root.is_dir() or (root.stat(follow_symlinks=False).st_mode & 0o777) != 0o700:
                    raise ValueError("partial unknown source material root")
            return _allocate(selected,binding,root,pg,admin,values["old_pg"],old,initializer,initializer_cwd=initializer.parent, prepared_redis_password=(prepared_redis_password_value))
        finally:
            admin.close(); old.close()




def _gamma_local_port(name):
    if name not in {"LOCAL_GAMMA_POSTGRES_PORT","LOCAL_GAMMA_REDIS_PORT","LOCAL_GAMMA_MONGO_PORT"}:
        raise ValueError("unknown gamma local topology port")
    raw=os.environ.get(name,"")
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError("gamma local topology port is invalid")
    return int(raw)

def gamma_local_mongo_uri():
    return f"mongodb://127.0.0.1:{_gamma_local_port('LOCAL_GAMMA_MONGO_PORT')}/?directConnection=true"

def _gamma_local_connection_root():
    return output_paths.deployment_target_path("gamma-local","secrets","source-allocation-management")

def _gamma_local_write_secret(root,name,value):
    root.mkdir(mode=0o700,parents=True,exist_ok=True); os.chmod(root,0o700)
    path=root/name
    try: fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        if _required(path).decode()!=value: raise ValueError("gamma local managed connection create-once differs")
        return
    with os.fdopen(fd,"w") as handle: handle.write(value); handle.flush(); os.fsync(handle.fileno())

def _gamma_local_read_secret(root,name):
    return _required(root/name).decode()


def _gamma_local_prepared_source_target():
    context, selected, _, _ = _current(
        "gamma-local", allow_active_startup=True,
        management_connections={
            "pg_admin": "prepared", "redis_admin": "prepared",
            "old_pg": "prepared", "old_redis": "prepared",
        },
    )
    return selected


def _gamma_local_replace_acl_exact(path, expected, replacement):
    if _required(path).decode() != expected:
        raise ValueError("gamma local Redis managed ACL differs")
    temporary = path.with_name(".users.acl.recovery")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(replacement); handle.flush(); os.fsync(handle.fileno())
        if _required(path).decode() != expected:
            raise ValueError("gamma local Redis managed ACL changed during recovery")
        os.replace(temporary, path)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass


def prepare_gamma_local_redis_acl():
    """启动前生成candidate-bound ACL；只恢复可精确识别的本attempt旧布局。"""
    root = _gamma_local_connection_root()
    selected = _gamma_local_prepared_source_target()
    base_names = ("redis-admin.key", "redis-probe.key", "redis-runtime.key")
    existing_base = [name for name in base_names if (root / name).exists()]
    if existing_base and len(existing_base) != len(base_names):
        raise ValueError("gamma local Redis managed material is partial")
    if not existing_base:
        for name in base_names:
            _gamma_local_write_secret(root, name, secrets.token_hex(32))
    values = {name: _gamma_local_read_secret(root, name) for name in base_names}
    legacy = (
        "user default off\n"
        f"user qwq_runtime reset on >{values['redis-runtime.key']} ~* +@all\n"
        f"user qwq_source_admin reset on >{values['redis-admin.key']} ~* +@all\n"
        f"user qwq_source_old_probe reset on >{values['redis-probe.key']} ~qwq.source.probe -@all +ping\n"
    )
    source_path = root / "redis-source.key"
    acl = root / "users.acl"
    if not source_path.exists():
        if acl.exists() and _required(acl).decode() != legacy:
            raise ValueError("gamma local Redis partial ACL is not recoverable")
        _gamma_local_write_secret(root, source_path.name, secrets.token_hex(32))
    values[source_path.name] = _gamma_local_read_secret(root, source_path.name)
    runtime_key_acl = (
        "user default reset off\n"
        f"user qwq_runtime reset on >{values['redis-runtime.key']} ~* +@all\n"
        f"user qwq_source_admin reset on >{values['redis-admin.key']} ~* +@all\n"
        f"user qwq_source_old_probe reset on >{values['redis-probe.key']} ~qwq.source.probe -@all +ping\n"
        f"user {selected.acl_user} reset on >{values['redis-source.key']} ~events.user.account -@all +ping +xadd +xinfo +xrange +xpending +xgroup +xreadgroup +xack +xautoclaim (~events.user.account.content-service.dlq -@all +xadd +expire)\n"
    )
    # Redis 7 将 key pattern（~）与 Pub/Sub channel pattern（&）分开。
    # runtime principal 既消费 durable streams，也承载 realtime relay，必须显式
    # 拥有 channel；+@all 本身不会隐式补出 &*。
    raw = runtime_key_acl.replace(" ~* +@all\n", " ~* &* +@all\n", 1)
    existing_acl = _required(acl).decode() if acl.exists() else ""
    managed_source_acl = re.compile(
        r"user default reset off\n"
        + re.escape(f"user qwq_runtime reset on >{values['redis-runtime.key']} ~* &* +@all\n")
        + re.escape(f"user qwq_source_admin reset on >{values['redis-admin.key']} ~* +@all\n")
        + re.escape(f"user qwq_source_old_probe reset on >{values['redis-probe.key']} ~qwq.source.probe -@all +ping\n")
        + r"user qwq_source_[0-9a-f]{24} reset on >"
        + re.escape(values["redis-source.key"])
        + r" ~events\.user\.account -@all \+ping \+xadd \+xinfo \+xrange \+xpending \+xgroup \+xreadgroup \+xack \+xautoclaim \(~events\.user\.account\.content-service\.dlq -@all \+xadd \+expire\)\n"
    )
    if not acl.exists():
        _gamma_local_write_secret(root, acl.name, raw)
    elif existing_acl in {legacy, runtime_key_acl} or managed_source_acl.fullmatch(existing_acl):
        _gamma_local_replace_acl_exact(acl, existing_acl, raw)
    elif existing_acl != raw:
        raise ValueError("gamma local Redis managed ACL differs")
    return {"aclFile": str(acl), "runtimePassword": values["redis-runtime.key"], "sourceTarget": selected}

def _gamma_local_managed_connections(*, create):
    """只从 canonical gamma local topology派生；caller env URL不参与。"""
    import psycopg, redis
    root=_gamma_local_connection_root()
    pg_port=_gamma_local_port("LOCAL_GAMMA_POSTGRES_PORT"); redis_port=_gamma_local_port("LOCAL_GAMMA_REDIS_PORT")
    admin_seed=psycopg.conninfo.make_conninfo(host="127.0.0.1", port=pg_port, dbname="quwoquan", user="quwoquan", password="quwoquan", sslmode="disable")
    redis_material = prepare_gamma_local_redis_acl() if create else None
    names=("pg-probe.key","redis-admin.key","redis-probe.key","redis-runtime.key","redis-source.key","users.acl")
    if create and not (root / "pg-probe.key").exists():
        pg_key = secrets.token_hex(32)
        redis_admin_key = _gamma_local_read_secret(root, "redis-admin.key")
        redis_probe_key = _gamma_local_read_secret(root, "redis-probe.key")
        with psycopg.connect(admin_seed,autocommit=True) as pg:
            from psycopg import sql
            role="qwq_source_old_probe"
            if pg.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,)).fetchone():
                raise ValueError("gamma local old Postgres probe already exists without managed material")
            pg.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(sql.Identifier(role),sql.Literal(pg_key)))
        # 先 create-once 保留恢复材料，再执行 provider mutation；失败不删除材料。
        _gamma_local_write_secret(root,"pg-probe.key",pg_key)
        admin = redis.Redis(host="127.0.0.1", port=redis_port, username="qwq_source_admin", password=redis_admin_key, decode_responses=True)
        try:
            selected = redis_material["sourceTarget"]
            required_users = ("qwq_runtime", "qwq_source_admin", "qwq_source_old_probe", selected.acl_user)
            if any(not admin.acl_getuser(user) for user in required_users):
                raise ValueError("gamma local Redis managed ACL was not loaded")
            default = admin.acl_getuser("default")
            if default is None or "off" not in default["flags"]:
                raise ValueError("gamma local Redis default ACL differs")
        finally: admin.close()
    if not all((root/name).exists() for name in names):
        raise ValueError("gamma local managed connection material missing")
    pg_key=_gamma_local_read_secret(root,"pg-probe.key")
    redis_admin_key=_gamma_local_read_secret(root,"redis-admin.key")
    redis_probe_key=_gamma_local_read_secret(root,"redis-probe.key")
    redis_url=lambda user,key:f"redis://{quote(user)}:{quote(key)}@127.0.0.1:{redis_port}/0"
    return {"pg_admin":admin_seed,"redis_admin":redis_url("qwq_source_admin",redis_admin_key),
        "old_pg":f"postgresql://qwq_source_old_probe:{quote(pg_key)}@127.0.0.1:{pg_port}/quwoquan?sslmode=disable",
        "old_redis":redis_url("qwq_source_old_probe",redis_probe_key)}

def _gamma_local_source_password():
    return _gamma_local_read_secret(_gamma_local_connection_root(), "redis-source.key")

def gamma_local_user_runtime_postgres_dsn():
    """返回 allocator 创建的 User runtime DSN；仅供锁内 startup Compose 投影。"""
    path = _source_current_path("gamma-local")
    if not path.exists():
        ensure_source_allocation_for_locked_up("gamma-local")
    if not path.exists():
        raise ValueError("gamma local source current missing after managed initialization")
    from quwoquan_ops.cli.lib.generated.post_safety_runtime import PostSafetySourceAllocationCurrentDescriptor
    descriptor = PostSafetySourceAllocationCurrentDescriptor.model_validate_json(_required(path))
    root = Path(descriptor.materialRoot.path)
    source = json.loads(_required(root / descriptor.sourceCreation.ref))
    role = str(source.get("producerRole") or "").strip() + "_runtime"
    namespace = str(source.get("producerNamespace") or "").strip()
    if role == "_runtime" or not namespace:
        raise ValueError("gamma local source PostgreSQL identity differs")
    runtime_credential = _gamma_local_read_secret(root, "postgres-runtime.key")
    import psycopg
    admin = psycopg.conninfo.conninfo_to_dict(_gamma_local_managed_connections(create=False)["pg_admin"])
    host_dsn = psycopg.conninfo.make_conninfo(
        host=admin["host"], port=admin["port"], dbname=namespace,
        user=role, password=runtime_credential, sslmode="disable", connect_timeout=3,
    )
    with psycopg.connect(host_dsn) as runtime:
        actual = runtime.execute("SELECT current_user, current_database(), to_regclass('public.user_profiles')::text").fetchone()
    if actual != (role, namespace, "user_profiles"):
        raise ValueError("gamma local User runtime PostgreSQL readback differs")
    return psycopg.conninfo.make_conninfo(
        host="postgres", port=5432, dbname=namespace,
        user=role, password=runtime_credential, sslmode="disable",
    )


def _source_current_path(target):
    return output_paths.deployment_target_path(target, "startup-material", "content-service", "account-closure", "source-current.json")

def _publish_source_current(target, selected, binding, root, receipt):
    from quwoquan_ops.cli.lib.generated.post_safety_runtime import (
        PostSafetyMaterialRootLocator, PostSafetyRuntimeEvidence, PostSafetySourceAllocationCurrentDescriptor,
    )
    raw = (root / "source-creation.json").read_bytes()
    descriptor = PostSafetySourceAllocationCurrentDescriptor(
        allocationAttemptId=root.name, materialRoot=PostSafetyMaterialRootLocator(path=str(root)),
        sourceCreation=PostSafetyRuntimeEvidence(ref="source-creation.json", digest=digest(raw)),
    )
    path = _source_current_path(target); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); os.chmod(path.parent, 0o700)
    encoded = json.dumps(descriptor.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    try:
        _write_transaction_journal_exclusive(path, encoded)
    except FileExistsError:
        if _required(path) != encoded: raise ValueError("source allocation current create-once differs")
    return descriptor

def ensure_source_allocation_for_locked_up(target, management_connections=None):
    """gamma-local startup 锁内 ensure；已有只核验，新建复用正式 source allocation。"""
    if target != "gamma-local": raise ValueError("startup source allocation producer is gamma-local only")
    if management_connections is not None: raise ValueError("caller managed connections are forbidden")
    path = _source_current_path(target)
    connections = _gamma_local_managed_connections(create=not path.exists())
    context, selected, binding, initializer = _current(target, allow_active_startup=True, management_connections=connections)
    if path.exists():
        from quwoquan_ops.cli.lib.generated.post_safety_runtime import PostSafetySourceAllocationCurrentDescriptor
        from quwoquan_ops.cli.lib.source_allocation_current import verify_source_current
        descriptor = PostSafetySourceAllocationCurrentDescriptor.model_validate_json(_required(path))
        root = Path(descriptor.materialRoot.path)
        if descriptor.allocationAttemptId != root.name or descriptor.sourceCreation.ref != "source-creation.json":
            raise ValueError("source allocation current binding differs")
        import psycopg, redis
        with psycopg.connect(connections["pg_admin"], autocommit=True) as pg:
            admin = redis.Redis.from_url(connections["redis_admin"], decode_responses=True)
            old = redis.Redis.from_url(connections["old_redis"], decode_responses=True)
            try:
                verify_source_current(expected=selected, binding=binding, material_root=root,
                    receipt_digest=descriptor.sourceCreation.digest, pg_admin=pg, redis_admin=admin,
                    old_pg_dsn=connections["old_pg"], old_redis=old)
            finally:
                admin.close(); old.close()
        return descriptor, selected, binding, connections
    root = output_paths.deployment_target_path(target, "secrets", "source-allocation", selected.candidate_digest.removeprefix("sha256:")[:24])
    receipt = _apply_connections(selected, binding, root, initializer, context["managementConnections"],
        management_connections=connections, prepared_redis_password_value=_gamma_local_source_password())
    return _publish_source_current(target, selected, binding, root, receipt), selected, binding, connections

def command_source_allocation(args):
    policy=contract()
    try:
        if args.target not in policy["targets"]: raise ValueError("managed nonproduction target required")
        if args.action=="plan":
            if args.plan_ref or args.confirm_source_allocation: raise ValueError("plan cannot consume approval")
            context,_,_,_=_current(args.target)
            reference=_create_plan(args,context)
            return {"exitCode":0,"status":"planned","planRef":reference,"resourceMutation":False,"summary":"source allocation planned; explicit confirmation required"}
        path,raw,plan=_load_plan(args)
        with local_stack_operation_lock(args.target):
            # 等锁期间计划也可能过期，必须在锁内再验完整exact plan。
            locked_path,locked_raw,locked_plan=_load_plan(args)
            if locked_path!=path or locked_raw!=raw or locked_plan!=plan:
                raise ValueError("source plan changed while acquiring lock")
            context,selected,binding,initializer=_current(args.target)
            expected_root=output_paths.deployment_target_path(args.target,"secrets","source-allocation",digest(json.dumps(context,sort_keys=True).encode()).removeprefix("sha256:"))
            if context!=plan["context"] or str(expected_root)!=plan["materialRoot"] or _required(path)!=raw:
                raise ValueError("source candidate/startup/plan changed")
            # _allocate为既有锁内实现；不再次取得同target锁。
            receipt=_apply_connections(selected,binding,expected_root,initializer,context["managementConnections"])
            _publish_source_current(args.target,selected,binding,expected_root,receipt)
        return {"exitCode":0,"status":"applied","receiptRef":str(expected_root/"source-creation.json"),"summary":"source allocation created; Content bootstrap not opened"}
    except Exception:
        # 底层驱动错误可能包含凭据/DSN，不传播其原始消息到CLI日志。
        return {"exitCode":2,"status":"gate_block","blockerKind":"source_allocation_rejected","summary":"source allocation GATE_BLOCK: check exact plan, current candidate, initializer and management references"}
