"""环境owner的非生产源分配；不由Content服务创建User业务schema。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
from dataclasses import dataclass

from quwoquan_ops.cli.lib.data_plane_binding import validate_canonical_data_plane_binding
from quwoquan_ops.cli.lib.local_runtime_reservation import local_stack_operation_lock


class SourceAllocationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceTarget:
    environment: str
    target: str
    candidate_digest: str
    data_plane_digest: str
    producer_resource: str
    database: str
    source_resource: str
    source_namespace: str
    role: str
    acl_user: str
    consumer_group: str


def _digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _identity(password, domain):
    return "sha256:" + hashlib.sha256(hmac.digest(password.encode(), domain.encode(), "sha256")).hexdigest()


def managed_binding_ids(target, producer_identity, source_identity, binding):
    # 必须先实测readback验证这些权限值；摘要不是权限检查的替代。
    common = {"candidate": target.candidate_digest, "dataPlane": binding["bindingDigest"], "publisherToSource": binding["bindings"], "target": target.target}
    producer = {**common, "resource": target.producer_resource, "namespace": target.database, "role": target.role, "credential": producer_identity, "superuser": False, "createdb": False, "createrole": False, "replication": False, "otherNonAdminConnectRoles": []}
    source = {**common, "resource": target.source_resource, "namespace": target.source_namespace, "user": target.acl_user, "credential": source_identity, "keys": ["events.user.account"], "commands": sorted(["ping", "xadd", "xinfo", "xrange", "xpending", "xgroup", "xreadgroup", "xack", "xautoclaim"]), "consumerGroup": target.consumer_group, "defaultEnabled": False, "otherNonAdminWriters": [], "selectors": [{"keys": ["events.user.account.content-service.dlq"], "commands": ["expire", "xadd"]}]}
    return _digest(producer), _digest(source)


def validate_target(approved, current, binding):
    if approved != current or current.environment not in {"alpha", "beta", "gamma"} or current.target != current.environment + "-local":
        raise SourceAllocationError("target/candidate authorization differs")
    if len(current.candidate_digest) != 71 or not current.candidate_digest.startswith("sha256:"):
        raise SourceAllocationError("candidate digest missing")
    canonical = validate_canonical_data_plane_binding(binding)
    if canonical["bindingDigest"] != current.data_plane_digest:
        raise SourceAllocationError("approved data-plane digest differs")
    rows = list(canonical["bindings"].values())
    for service, engine, resource, namespace in (("user-service", "postgres", current.producer_resource, current.database), ("user-service", "redis", current.source_resource, current.source_namespace)):
        if not any(r["service"] == service and r["engine"] == engine and r["resource"] == resource and r["namespace"] == namespace for r in rows):
            raise SourceAllocationError("producer/source binding differs")
    return canonical


def _write_once(root, name, raw):
    import stat
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise SourceAllocationError("material permissions differ")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)


def _pg_credentials(admin, database, user, password):
    import psycopg
    values = {key: value for key, value in admin.info.get_parameters().items() if key in {"host", "port", "sslmode"}}
    values.update(dbname=database, user=user, password=password, connect_timeout=3)
    return psycopg.conninfo.make_conninfo(**values)


def _redis_connection_descriptor(client):
    """返回可序列化且不含凭据的 Redis 公开连接描述。"""
    import inspect
    import json
    import redis

    pool = client.connection_pool
    connection_kwargs = dict(pool.connection_kwargs)
    supported = inspect.signature(redis.Redis.__init__).parameters
    descriptor = {}
    for key, value in connection_kwargs.items():
        if key not in supported or key in {"username", "password", "credential_provider"}:
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        descriptor[key] = value

    connection_class = pool.connection_class
    if issubclass(connection_class, redis.SSLConnection):
        descriptor["ssl"] = True
    elif issubclass(connection_class, redis.UnixDomainSocketConnection):
        descriptor["unix_socket_path"] = connection_kwargs["path"]
    return descriptor


def _redis_credentials(admin, user, password):
    import redis

    values = _redis_connection_descriptor(admin)
    values.update(username=user, password=password, decode_responses=True)
    return redis.Redis(**values)


def allocate_source(*, approved: SourceTarget, current: SourceTarget, binding: dict, material_root: Path, pg_admin, redis_admin, old_pg_dsn: str, old_redis, user_initializer: Path, lock_path: Path | None = None, prepared_redis_password: str | None = None, failpoint=None):
    """独占创建PG/ACL/源，失败保留partial且不写完成材料。

    approved由受管调用层独立取得，current来自现役candidate；本函数比较并验证
    data-plane，实际取得canonical target锁。lock_path仅现有隔离测试seam。
    """
    canonical = validate_target(approved, current, binding)
    if not material_root.is_absolute() or material_root.resolve() != material_root:
        raise SourceAllocationError("unsafe material root")
    with local_stack_operation_lock(current.target, lock_path=lock_path):
        if material_root.exists():
            info = material_root.stat(follow_symlinks=False)
            if not material_root.is_dir() or (info.st_mode & 0o777) != 0o700:
                raise SourceAllocationError("partial unknown: recovery material root is not secure")
        else:
            material_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        return _allocate(current, canonical, material_root, pg_admin, redis_admin, old_pg_dsn, old_redis, user_initializer, prepared_redis_password=prepared_redis_password, failpoint=failpoint)



_ALLOCATION_STEPS = ("role", "runtime_role", "database", "database_acl", "initializer", "runtime_acl", "stream_group")

def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def _journal_path(root):
    return root / "allocation-journal.json"

def _write_journal(root, value):
    path = _journal_path(root); raw = _canonical_bytes(value)
    temporary = root / ".allocation-journal.json.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass

def _load_journal(root, expected):
    path = _journal_path(root)
    if not path.exists():
        if any(root.iterdir()):
            raise SourceAllocationError("partial unknown: source material exists without owner journal")
        return None
    info = path.stat(follow_symlinks=False)
    if info.st_nlink != 1 or (info.st_mode & 0o777) != 0o600:
        raise SourceAllocationError("source allocation journal permissions differ")
    try: value = json.loads(path.read_bytes())
    except Exception as error: raise SourceAllocationError("source allocation journal invalid") from error
    if value.get("identity") != expected or value.get("completed") not in [list(_ALLOCATION_STEPS[:i]) for i in range(len(_ALLOCATION_STEPS)+1)]:
        raise SourceAllocationError("source allocation journal identity or steps differ")
    return value

def _journal_identity(target, binding, root, pg_password, redis_password):
    return {
        "target": target.target, "environment": target.environment, "candidateDigest": target.candidate_digest,
        "dataPlaneBindingDigest": binding["bindingDigest"], "allocationAttemptId": root.name,
        "database": target.database, "producerRole": target.role, "sourceResource": target.source_resource,
        "sourceNamespace": target.source_namespace, "sourceAclUser": target.acl_user,
        "stream": "events.user.account", "consumerGroup": target.consumer_group,
        "postgresSecretDigest": _identity(pg_password, "quwoquan/source-allocation/journal/postgres"),
        "redisSecretDigest": _identity(redis_password, "quwoquan/source-allocation/journal/redis"),
    }

def _complete_step(root, journal, step, readback):
    expected = _ALLOCATION_STEPS[len(journal["completed"])]
    if step != expected: raise SourceAllocationError("source allocation journal step order differs")
    journal = {**journal, "completed": [*journal["completed"], step], "readbacks": {**journal["readbacks"], step: _digest(readback)}}
    _write_journal(root, journal)
    return journal

def _allocate(target, binding, root, pg, redis, old_pg_dsn, old_redis, initializer, *, initializer_cwd=None, prepared_redis_password=None, failpoint=None):
    import psycopg
    from psycopg import sql
    default = redis.acl_getuser("default")
    if default and "on" in default["flags"]: raise SourceAllocationError("default Redis access must be disabled")
    existing_files = {path.name for path in root.iterdir()}
    if "source-creation.json" in existing_files:
        raise FileExistsError(root / "source-creation.json")
    allowed = {"postgres.key", "postgres-runtime.key", "redis.key", "allocation-journal.json", "source-creation.json"}
    if existing_files - allowed:
        raise SourceAllocationError("partial unknown: source material contains unbound files")
    credential_files = {"postgres.key", "postgres-runtime.key", "redis.key"}
    if existing_files & credential_files:
        if not credential_files.issubset(existing_files): raise SourceAllocationError("partial unknown: source credential material incomplete")
        pg_password = (root / "postgres.key").read_text()
        runtime_pg_password = (root / "postgres-runtime.key").read_text()
        redis_password = (root / "redis.key").read_text()
        if prepared_redis_password is not None and redis_password != prepared_redis_password:
            raise SourceAllocationError("prepared source credential differs")
    else:
        pg_password = secrets.token_hex(32)
        runtime_pg_password = secrets.token_hex(32)
        redis_password = prepared_redis_password or secrets.token_hex(32)
        _write_once(root, "postgres.key", pg_password.encode())
        _write_once(root, "postgres-runtime.key", runtime_pg_password.encode())
        _write_once(root, "redis.key", redis_password.encode())
    identity = _journal_identity(target, binding, root, pg_password, redis_password)
    identity["runtimeRole"] = target.role + "_runtime"
    identity["runtimePostgresSecretDigest"] = _identity(runtime_pg_password, "quwoquan/source-allocation/journal/postgres-runtime")
    journal_path = _journal_path(root)
    if not journal_path.exists() and existing_files:
        raise SourceAllocationError("partial unknown: source material exists without owner journal")
    journal = _load_journal(root, identity) if journal_path.exists() else None
    if journal is None:
        journal = {"schema": "qwq.source-allocation-journal.v1", "identity": identity, "completed": [], "readbacks": {}}
        _write_journal(root, journal)
    completed = set(journal["completed"])
    role = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (target.role,)).fetchone()
    if "role" not in completed:
        if role is None:
            pg.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(sql.Identifier(target.role), sql.Literal(pg_password)))
        role = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (target.role,)).fetchone()
        try:
            probe = psycopg.connect(_pg_credentials(pg, "postgres", target.role, pg_password)); probe.close()
        except psycopg.OperationalError as error: raise SourceAllocationError("existing producer resource: credential differs from this journal") from error
        if role != (False, False, False, False): raise SourceAllocationError("partial unknown: producer role attributes differ")
        journal = _complete_step(root, journal, "role", {"attributes": role})
        if failpoint: failpoint("role")
    elif role != (False, False, False, False): raise SourceAllocationError("producer role drift")
    runtime_role = target.role + "_runtime"
    runtime_attributes = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (runtime_role,)).fetchone()
    if "runtime_role" not in completed:
        if runtime_attributes is None:
            pg.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(sql.Identifier(runtime_role), sql.Literal(runtime_pg_password)))
        runtime_attributes = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (runtime_role,)).fetchone()
        if runtime_attributes != (False, False, False, False): raise SourceAllocationError("runtime role attributes differ")
        journal = _complete_step(root, journal, "runtime_role", {"attributes": runtime_attributes, "role": runtime_role})
        if failpoint: failpoint("runtime_role")
    elif runtime_attributes != (False, False, False, False): raise SourceAllocationError("runtime role drift")
    owner = pg.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (target.database,)).fetchone()
    if "database" not in completed:
        if owner is None: pg.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(target.database), sql.Identifier(target.role)))
        owner = pg.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (target.database,)).fetchone()
        if owner != (target.role,): raise SourceAllocationError("partial unknown: producer database owner differs")
        journal = _complete_step(root, journal, "database", {"owner": owner[0]})
        if failpoint: failpoint("database")
    elif owner != (target.role,): raise SourceAllocationError("database owner drift")
    if "database_acl" not in completed:
        pg.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(target.database)))
        public = pg.execute("SELECT has_database_privilege('public',%s,'CONNECT')", (target.database,)).fetchone()
        if public != (False,): raise SourceAllocationError("producer database PUBLIC ACL differs")
        journal = _complete_step(root, journal, "database_acl", {"publicConnect": False})
        if failpoint: failpoint("database_acl")
    dsn = _pg_credentials(pg, target.database, target.role, pg_password)
    if "initializer" not in completed:
        result = subprocess.run([str(initializer)], env={**os.environ, "QWQ_SOURCE_INIT_ENV": target.environment, "QWQ_SOURCE_INIT_DSN": dsn}, cwd=initializer_cwd, capture_output=True, timeout=100)
        if result.returncode: raise SourceAllocationError("User managed initialization failed")
        with psycopg.connect(dsn) as producer:
            tables = producer.execute("SELECT to_regclass('public.user_account_outbox')::text").fetchone()
        if tables != ("user_account_outbox",): raise SourceAllocationError("User managed initialization readback differs")
        journal = _complete_step(root, journal, "initializer", {"outbox": tables[0]})
        if failpoint: failpoint("initializer")
    runtime_dsn = _pg_credentials(pg, target.database, runtime_role, runtime_pg_password)
    if "runtime_acl" not in completed:
        with psycopg.connect(dsn, autocommit=True) as producer:
            producer.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(target.database), sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE ON service_schema_migrations FROM {}").format(sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(sql.Identifier(target.role), sql.Identifier(runtime_role)))
            producer.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(sql.Identifier(target.role), sql.Identifier(runtime_role)))
        journal = _complete_step(root, journal, "runtime_acl", {"role": runtime_role, "privileges": "runtime-dml-v1"})
        if failpoint: failpoint("runtime_acl")
    _verify_runtime_postgres_access(pg, target, runtime_role, runtime_dsn)
    existing_acl = redis.acl_getuser(target.acl_user)
    if prepared_redis_password is not None and existing_acl is None: raise SourceAllocationError("prepared source ACL authority differs")
    if prepared_redis_password is None and existing_acl is not None and "stream_group" not in completed: raise SourceAllocationError("existing source resource: ACL lacks completed journal step")
    commands = ["+ping", "+xadd", "+xinfo", "+xrange", "+xpending", "+xgroup", "+xreadgroup", "+xack", "+xautoclaim"]
    if prepared_redis_password is None and existing_acl is None:
        redis.execute_command("ACL", "SETUSER", target.acl_user, "reset", "on", ">" + redis_password, "~events.user.account", *commands, "(~events.user.account.content-service.dlq +xadd +expire)")
    source = _redis_credentials(redis, target.acl_user, redis_password)
    try:
        groups = source.xinfo_groups("events.user.account") if redis.exists("events.user.account") else []
        if "stream_group" not in completed:
            if not groups: source.xgroup_create("events.user.account", target.consumer_group, id="0-0", mkstream=True)
            groups = source.xinfo_groups("events.user.account")
            if len(groups) != 1 or groups[0]["name"] != target.consumer_group: raise SourceAllocationError("partial unknown: source group differs")
            journal = _complete_step(root, journal, "stream_group", {"stream": "events.user.account", "group": target.consumer_group})
        if failpoint: failpoint("stream_group")
        state = readback(target, pg, redis, dsn, source, old_pg_dsn, old_redis, initial=True)
    finally: source.close()
    from datetime import datetime, timezone
    from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import ContentAccountClosureRuntimeSourceCreation
    producer_identity = _identity(pg_password, "quwoquan/source-allocation/postgres"); source_identity = _identity(redis_password, "quwoquan/source-allocation/redis")
    producer_binding, source_binding = managed_binding_ids(target, producer_identity, source_identity, binding)
    receipt = ContentAccountClosureRuntimeSourceCreation(environment=target.environment, target=target.target, candidateDigest=target.candidate_digest, dataPlaneBindingDigest=binding["bindingDigest"], allocationAttemptId=root.name, producerResourceRef=target.producer_resource, producerNamespace=target.database, producerManagedAllocationBindingId=producer_binding, sourceResourceRef=target.source_resource, sourceNamespace=target.source_namespace, sourceManagedAllocationBindingId=source_binding, producerBindingDigest=_digest(binding["bindings"]), producerRole=target.role, sourceAclUser=target.acl_user, producerCredentialIdentity=producer_identity, sourceCredentialIdentity=source_identity, rejectedProducerRole=state["rejectedProducerRole"], rejectedSourceAclUser=str(old_redis.connection_pool.connection_kwargs.get("username") or "default"), allocatedAt=datetime.now(timezone.utc))
    _write_once(root, "source-creation.json", receipt.model_dump_json().encode())
    return receipt



def _verify_runtime_postgres_access(pg, target, runtime_role, runtime_dsn):
    import psycopg
    attributes = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (runtime_role,)).fetchone()
    if attributes != (False, False, False, False):
        raise SourceAllocationError("runtime role drift")
    checks = pg.execute("SELECT has_database_privilege(%s,%s,'CONNECT')", (runtime_role, target.database)).fetchone()
    if checks != (True,):
        raise SourceAllocationError("runtime database CONNECT grant differs")
    with psycopg.connect(runtime_dsn) as runtime:
        privileges = runtime.execute("""SELECT
            has_schema_privilege(current_user, 'public', 'USAGE'),
            has_table_privilege(current_user, 'public.user_profiles', 'SELECT,INSERT,UPDATE,DELETE'),
            has_table_privilege(current_user, 'public.service_schema_migrations', 'SELECT'),
            has_table_privilege(current_user, 'public.service_schema_migrations', 'INSERT,UPDATE,DELETE'),
            has_table_privilege(current_user, 'public.user_profiles', 'TRUNCATE,REFERENCES,TRIGGER')""").fetchone()
        if privileges != (True, True, True, False, False):
            raise SourceAllocationError("runtime schema privileges differ")
        if runtime.execute("SELECT to_regclass('public.user_profiles')::text").fetchone() != ("user_profiles",):
            raise SourceAllocationError("runtime schema readback differs")

def readback(target, pg, redis, dsn, source, old_pg_dsn, old_redis, *, initial=True):
    import psycopg
    from redis.exceptions import AuthenticationError, NoPermissionError
    role = pg.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s", (target.role,)).fetchone()
    if role != (False, False, False, False):
        raise SourceAllocationError("producer role drift")
    owner = pg.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (target.database,)).fetchone()
    if owner != (target.role,):
        raise SourceAllocationError("database owner drift")
    runtime_role = target.role + "_runtime"
    others = pg.execute("SELECT rolname FROM pg_roles WHERE NOT rolsuper AND rolname NOT IN (%s,%s) AND has_database_privilege(oid,%s,'CONNECT')", (target.role,runtime_role,target.database)).fetchall()
    if others:
        raise SourceAllocationError("unexpected database CONNECT grant")
    with psycopg.connect(dsn) as producer:
        if initial and producer.execute("SELECT count(*) FROM user_account_outbox").fetchone()[0] != 0:
            raise SourceAllocationError("source outbox not initially empty")
    old = psycopg.conninfo.conninfo_to_dict(old_pg_dsn)
    with psycopg.connect(old_pg_dsn) as prior:
        old_role = prior.execute("SELECT current_user").fetchone()[0]
    if old_role == target.role or pg.execute("SELECT rolsuper FROM pg_roles WHERE rolname=%s", (old_role,)).fetchone() != (False,):
        raise SourceAllocationError("old producer probe is not a distinct business role")
    old["dbname"] = target.database
    try:
        connection = psycopg.connect(**old)
    except psycopg.OperationalError:
        denied = pg.execute("SELECT has_database_privilege(%s,%s,'CONNECT')", (old_role,target.database)).fetchone()
        if denied != (False,):
            raise SourceAllocationError("old producer rejection is not permission evidence") from None
    else:
        connection.close()
        raise SourceAllocationError("old producer can connect")
    # 先证明旧凭据真实有效，不能把错误密码/连接失败当权限隔离证据。
    old_redis.ping()
    try:
        old_redis.xrange("events.user.account")
    except (AuthenticationError, NoPermissionError):
        pass
    else:
        raise SourceAllocationError("old source credential can read")
    acl = redis.acl_getuser(target.acl_user)
    expected_commands = {"-@all", "+ping", "+xadd", "+xinfo", "+xrange", "+xpending", "+xgroup", "+xreadgroup", "+xack", "+xautoclaim"}
    password = source.connection_pool.connection_kwargs.get("password", "")
    if acl is None or acl["keys"] != ["~events.user.account"] or set(acl["commands"]) != expected_commands - {"-@all"} or set(acl["categories"]) != {"-@all"} or "on" not in acl["flags"] or "nopass" in acl["flags"] or acl["passwords"] != [hashlib.sha256(password.encode()).hexdigest()]:
        raise SourceAllocationError("source ACL drift")
    selectors = acl.get("selectors", [])
    if len(selectors) != 1 or not isinstance(selectors[0], list) or len(selectors[0]) != 6:
        raise SourceAllocationError("source DLQ selector shape drift")
    selector = dict(zip(selectors[0][::2], selectors[0][1::2]))
    if selector.get("keys") != "~events.user.account.content-service.dlq" or set(selector.get("commands", "").split()) != {"-@all", "+xadd", "+expire"} or selector.get("channels") != "":
        raise SourceAllocationError("source DLQ selector drift")
    default = redis.acl_getuser("default")
    if default and "on" in default["flags"]:
        raise SourceAllocationError("default ACL drift")
    managed_non_source_users = {"qwq_runtime", "qwq_source_old_probe"}
    for user in redis.acl_users():
        if user in {target.acl_user, "default", redis.connection_pool.connection_kwargs.get("username"), *managed_non_source_users}: continue
        rules = redis.acl_getuser(user)
        if rules and "on" in rules["flags"]:
            from redis.exceptions import ResponseError
            try:
                allowed = redis.execute_command("ACL", "DRYRUN", user, "XADD", "events.user.account", "*", "allocation_probe", "no_write")
            except ResponseError as error:
                if "no permissions" not in str(error): raise
                allowed = None
            if allowed == "OK":
                raise SourceAllocationError("another source writer has access")
    # 持续验证保留凭据认证与订阅存在性，不把普通事件增长与初始空摘要比较。
    if not initial:
        source.ping()
        source.xinfo_stream("events.user.account")
        groups = source.xinfo_groups("events.user.account")
        matching_groups = [group for group in groups if group.get("name") == target.consumer_group]
        if len(matching_groups) != 1:
            raise SourceAllocationError("source subscription drift")
        return {"producerRole": target.role, "sourceAclUser": target.acl_user, "rejectedProducerRole": old_role}
    info = source.xinfo_stream("events.user.account")
    pending = source.xpending("events.user.account", target.consumer_group)
    entries = source.xrange("events.user.account")
    groups = source.xinfo_groups("events.user.account")
    if info["length"] != 0 or info["last-generated-id"] != "0-0" or info["entries-added"] != 0 or entries or pending["pending"] != 0 or len(groups) != 1 or groups[0]["name"] != target.consumer_group or groups[0]["last-delivered-id"] != "0-0":
        raise SourceAllocationError("source initialization boundary differs")
    return {"producerRole": target.role, "sourceAclUser": target.acl_user, "rejectedProducerRole": old_role, "firstAvailablePosition": "0-0", "frozenThrough": "0-0", "deliveredThrough": "0-0", "appliedThrough": "0-0", "pendingCount": 0, "entryCount": 0}
