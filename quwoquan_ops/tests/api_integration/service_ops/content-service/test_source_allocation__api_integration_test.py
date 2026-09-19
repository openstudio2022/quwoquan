# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
"""只在本测试新建的PG/Redis容器中验证环境owner源分配。"""
from dataclasses import replace
from pathlib import Path
import os
import json
import secrets
import time

import docker
import psycopg
import pytest
import redis
import yaml

from quwoquan_ops.cli.lib.data_plane_binding import canonical_data_plane_binding
from quwoquan_ops.cli.lib.source_allocation import SourceTarget, SourceAllocationError, allocate_source, _pg_credentials, _redis_connection_descriptor, _redis_credentials, readback

ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def resources():
    client = docker.DockerClient(base_url=os.environ.get("DOCKER_HOST", "unix://" + str(Path.home() / ".colima/default/docker.sock")))
    password = secrets.token_hex(32)
    containers = []
    try:
        pgc = client.containers.run("postgres:16-alpine", detach=True, environment={"POSTGRES_PASSWORD": password}, ports={"5432/tcp": ("127.0.0.1", None)})
        containers.append(pgc)
        rc = client.containers.run("redis:7-alpine", detach=True, ports={"6379/tcp": ("127.0.0.1", None)})
        containers.append(rc)
        pgc.reload(); rc.reload()
        pgport = pgc.attrs["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
        rport = rc.attrs["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"]
        dsn = psycopg.conninfo.make_conninfo(host="127.0.0.1", port=pgport, user="postgres", password=password, dbname="postgres", connect_timeout=2)
        deadline = time.monotonic()+45
        while True:
            try:
                pg = psycopg.connect(dsn, autocommit=True)
                rd = redis.Redis(host="127.0.0.1", port=int(rport), decode_responses=True)
                rd.ping()
                break
            except (psycopg.OperationalError, redis.ConnectionError):
                if time.monotonic() > deadline: raise
                time.sleep(.2)
        pg.execute("CREATE ROLE old_business LOGIN PASSWORD 'isolated_old_password'")
        rd.execute_command("ACL", "SETUSER", "allocator", "on", ">"+password, "~*", "+@all")
        rd.execute_command("ACL", "SETUSER", "old_business", "on", ">isolated_old_password", "~old.*", "+@read", "+ping")
        admin = redis.Redis(host="127.0.0.1", port=int(rport), username="allocator", password=password, decode_responses=True)
        admin.execute_command("ACL", "SETUSER", "default", "off")
        oldredis = redis.Redis(host="127.0.0.1", port=int(rport), username="old_business", password="isolated_old_password", decode_responses=True)
        olddsn = _pg_credentials(pg, "postgres", "old_business", "isolated_old_password")
        yield pg, admin, olddsn, oldredis
        oldredis.close(); admin.close(); rd.close(); pg.close()
    finally:
        for container in containers:
            container.remove(force=True, v=True)
        client.close()


def inputs():
    doc = yaml.safe_load((ROOT / "quwoquan_ops/environments/gamma/runtime.yaml").read_text())
    def locate(value):
        if isinstance(value, dict):
            if "dataPlane" in value: return value["dataPlane"]
            for child in value.values():
                found = locate(child)
                if found is not None: return found
        return None
    plane = locate(doc)
    plane["bindings"]["user-service.redis"]["namespace"] = "isolated_source"
    plane["bindings"]["user-service.postgres"]["namespace"] = "isolated_user"
    binding = canonical_data_plane_binding({"dataPlane": plane}, target_name="gamma-local")
    target = SourceTarget("gamma", "gamma-local", "sha256:"+"a"*64, binding["bindingDigest"], "primary-postgres", "isolated_user", "primary-redis", "isolated_source", "isolated_owner", "isolated_source", "content-service-user-account-closed")
    return target, binding


def test_real_source_creation_permissions_and_drift(resources, tmp_path):
    pg, rd, olddsn, oldredis = resources
    target, binding = inputs()
    kwargs = dict(approved=target, current=target, binding=binding, material_root=tmp_path/"attempt", pg_admin=pg, redis_admin=rd, old_pg_dsn=olddsn, old_redis=oldredis, user_initializer=ROOT/".qwq_output/env/repo/local/source-allocation-a418/source-init", lock_path=tmp_path/"source.lock")
    with pytest.raises(SourceAllocationError):
        allocate_source(**{**kwargs, "current":replace(target, candidate_digest="sha256:"+"b"*64)})
    altered = {**binding, "bindingDigest":"sha256:"+"d"*64}
    with pytest.raises(ValueError):
        allocate_source(**{**kwargs,"binding":altered})
    receipt = allocate_source(**kwargs)
    assert receipt.producerRole == target.role
    assert receipt.rejectedProducerRole == "old_business"
    assert (tmp_path/"attempt/source-creation.json").is_file()
    with pytest.raises(FileExistsError): allocate_source(**kwargs)
    with pytest.raises(SourceAllocationError, match="existing"):
        allocate_source(**{**kwargs,"material_root":tmp_path/"another-attempt", "lock_path":tmp_path/"another.lock"})
    dsn = _pg_credentials(pg,target.database,target.role,(tmp_path/"attempt/postgres.key").read_text())
    runtime_role = target.role + "_runtime"
    runtime_dsn = _pg_credentials(pg,target.database,runtime_role,(tmp_path/"attempt/postgres-runtime.key").read_text())
    with psycopg.connect(runtime_dsn) as runtime:
        assert runtime.execute("SELECT current_user, to_regclass('public.user_profiles')::text").fetchone() == (runtime_role, "user_profiles")
        assert runtime.execute("SELECT has_table_privilege(current_user,'public.user_profiles','SELECT,INSERT,UPDATE,DELETE'), has_table_privilege(current_user,'public.user_profiles','TRUNCATE,REFERENCES,TRIGGER'), has_table_privilege(current_user,'public.service_schema_migrations','INSERT,UPDATE,DELETE')").fetchone() == (True, False, False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("CREATE TABLE forbidden_runtime_ddl(id integer)")
    source = _redis_credentials(rd,target.acl_user,(tmp_path/"attempt/redis.key").read_text())
    try:
        import hashlib
        from quwoquan_ops.cli.lib.source_allocation_current import verify_source_current
        digest = "sha256:"+hashlib.sha256((tmp_path/"attempt/source-creation.json").read_bytes()).hexdigest()
        current_args = dict(expected=target,binding=binding,material_root=tmp_path/"attempt",receipt_digest=digest,pg_admin=pg,redis_admin=rd,old_pg_dsn=olddsn,old_redis=oldredis)
        assert verify_source_current(**current_args) == receipt
        with pytest.raises(SourceAllocationError):
            verify_source_current(**{**current_args,"expected":replace(target,candidate_digest="sha256:"+"e"*64)})
        keypath = tmp_path/"attempt/redis.key"
        original_key = keypath.read_bytes()
        keypath.write_bytes(b"0"*64)
        with pytest.raises(SourceAllocationError): verify_source_current(**current_args)
        keypath.write_bytes(original_key)
        keypath.chmod(0o644)
        with pytest.raises(SourceAllocationError): verify_source_current(**current_args)
        keypath.chmod(0o600)
        os.link(keypath,tmp_path/"linked-key")
        with pytest.raises(SourceAllocationError): verify_source_current(**current_args)
        (tmp_path/"linked-key").unlink()
        wrong = _redis_credentials(rd,target.acl_user,"not-the-created-key")
        try:
            with pytest.raises(redis.AuthenticationError): wrong.ping()
        finally: wrong.close()
        wrongdsn = _pg_credentials(pg,target.database,target.role,"not-the-created-key")
        with pytest.raises(psycopg.OperationalError): psycopg.connect(wrongdsn)
        assert readback(target,pg,rd,dsn,source,olddsn,oldredis)["pendingCount"] == 0
        # 验证生产consumer reclaim/PEL/ACK与DLQ必要命令，仍禁止任意键及管理命令。
        assert target.consumer_group == "content-service-user-account-closed"
        source.xautoclaim("events.user.account",target.consumer_group,"isolated-consumer",0,"0-0")
        message_id=source.xadd("events.user.account", {"isolated_transport_probe":"not-a-business-event"})
        source.xreadgroup(target.consumer_group,"isolated-consumer",{"events.user.account":">"},count=1)
        assert source.xack("events.user.account",target.consumer_group,message_id)==1
        dlq="events.user.account.content-service.dlq"
        source.xadd(dlq,{"errorDigest":"isolated-non-pii-probe"})
        assert source.expire(dlq,60)
        with pytest.raises(redis.exceptions.NoPermissionError): source.expire("events.user.account",60)
        with pytest.raises(redis.exceptions.NoPermissionError): source.get("unrelated-key")
        with pytest.raises(redis.exceptions.NoPermissionError): source.execute_command("CONFIG","GET","*")
        assert verify_source_current(**current_args) == receipt
        # 新进程从材料和独立expected重新构造连接，不继承allocation内存状态。
        import json
        import subprocess
        import sys
        from dataclasses import asdict
        def subprocess_connection(client):
            descriptor = _redis_connection_descriptor(client)
            kwargs = client.connection_pool.connection_kwargs
            descriptor.update(username=kwargs.get("username"), password=kwargs.get("password"))
            return descriptor

        payload = dict(target=asdict(target),binding=binding,root=str(tmp_path/"attempt"),digest=digest,
                       pg_dsn=_pg_credentials(pg,"postgres","postgres",pg.info.password),
                       redis=subprocess_connection(rd),old_pg=olddsn,
                       old_redis=subprocess_connection(oldredis))
        program = """import json,os,pathlib,psycopg,redis
from quwoquan_ops.cli.lib.source_allocation import SourceTarget
from quwoquan_ops.cli.lib.source_allocation_current import verify_source_current
v=json.loads(os.environ['QWQ_ISOLATED_SOURCE_CURRENT'])
p=psycopg.connect(v['pg_dsn'],autocommit=True); r=redis.Redis(**v['redis']); old=redis.Redis(**v['old_redis'])
try:
 verify_source_current(expected=SourceTarget(**v['target']),binding=v['binding'],material_root=pathlib.Path(v['root']),receipt_digest=v['digest'],pg_admin=p,redis_admin=r,old_pg_dsn=v['old_pg'],old_redis=old)
finally:
 p.close(); r.close(); old.close()
"""
        child = subprocess.run([sys.executable,"-c",program],env={**os.environ,"QWQ_ISOLATED_SOURCE_CURRENT":json.dumps(payload)},capture_output=True,timeout=20)
        assert child.returncode == 0, "cross-process source current verification failed"
        with pytest.raises(SourceAllocationError,match="boundary"):
            readback(target,pg,rd,dsn,source,olddsn,oldredis)
        rd.execute_command("ACL","SETUSER",target.acl_user,"~*")
        with pytest.raises(SourceAllocationError,match="ACL drift"):
            readback(target,pg,rd,dsn,source,olddsn,oldredis)
    finally: source.close()


def test_partial_initialization_never_writes_receipt(resources, tmp_path):
    pg, rd, olddsn, oldredis = resources
    target,binding = inputs()
    with pytest.raises(SourceAllocationError,match="initialization failed"):
        allocate_source(approved=target,current=target,binding=binding,material_root=tmp_path/"partial",pg_admin=pg,redis_admin=rd,old_pg_dsn=olddsn,old_redis=oldredis,user_initializer=Path("/usr/bin/false"),lock_path=tmp_path/"partial.lock")
    assert not (tmp_path/"partial/source-creation.json").exists()
    assert pg.execute("SELECT 1 FROM pg_database WHERE datname=%s",(target.database,)).fetchone()



@pytest.mark.parametrize("stop_after", ("role", "runtime_role", "database", "database_acl", "initializer", "runtime_acl", "stream_group"))
def test_journal_resumes_only_same_owner_after_each_step(resources, tmp_path, stop_after):
    pg, rd, olddsn, oldredis = resources; target, binding = inputs()
    root = tmp_path / ("resume-" + stop_after)
    kwargs = dict(approved=target, current=target, binding=binding, material_root=root, pg_admin=pg,
        redis_admin=rd, old_pg_dsn=olddsn, old_redis=oldredis,
        user_initializer=ROOT/".qwq_output/env/repo/local/source-allocation-a418/source-init",
        lock_path=tmp_path/(stop_after+".lock"))
    def interrupt(step):
        if step == stop_after: raise RuntimeError("simulated interruption")
    with pytest.raises(RuntimeError, match="simulated interruption"):
        allocate_source(**kwargs, failpoint=interrupt)
    journal = json.loads((root/"allocation-journal.json").read_text())
    assert journal["completed"][-1] == stop_after
    (tmp_path/(stop_after+".executor.json")).unlink()
    receipt = allocate_source(**kwargs)
    assert receipt.candidateDigest == target.candidate_digest
    with pytest.raises((SourceAllocationError, FileExistsError)):
        allocate_source(**{**kwargs, "current": replace(target, candidate_digest="sha256:"+"c"*64)})


def test_unknown_preexisting_resource_without_journal_is_never_adopted(resources, tmp_path):
    pg, rd, olddsn, oldredis = resources; target, binding = inputs()
    pg.execute(f"CREATE ROLE \"{target.role}\" LOGIN PASSWORD 'unknown-password'")
    root = tmp_path/"unknown"
    kwargs = dict(approved=target, current=target, binding=binding, material_root=root, pg_admin=pg, redis_admin=rd,
        old_pg_dsn=olddsn, old_redis=oldredis, user_initializer=ROOT/".qwq_output/env/repo/local/source-allocation-a418/source-init", lock_path=tmp_path/"unknown.lock")
    with pytest.raises(SourceAllocationError, match="existing producer resource"):
        allocate_source(**kwargs)

def test_gamma_managed_acl_survives_real_redis_restart(tmp_path, monkeypatch):
    import hashlib
    from quwoquan_ops.cli.commands import source_allocation as entry

    import shutil
    target, _ = inputs()
    root = (ROOT / ".qwq_output/env/repo/local/tests" / ("source-acl-" + secrets.token_hex(8))).absolute()
    monkeypatch.setattr(entry, "_gamma_local_connection_root", lambda *args, **kwargs: root)
    monkeypatch.setattr(entry, "_gamma_local_prepared_source_target", lambda *args, **kwargs: target)
    prepared = entry.prepare_gamma_local_redis_acl(); acl_path = Path(prepared["aclFile"])
    assert acl_path.stat().st_mode & 0o777 == 0o600
    client = docker.DockerClient(base_url=os.environ.get("DOCKER_HOST", "unix://" + str(Path.home() / ".colima/default/docker.sock")))
    container = None
    try:
        container = client.containers.run("redis:7-alpine", detach=True,
            command=["redis-server", "--appendonly", "yes", "--aclfile", "/run/qwq/users.acl"],
            volumes={str(acl_path): {"bind": "/run/qwq/users.acl", "mode": "ro"}},
            ports={"6379/tcp": ("127.0.0.1", None)})
        container.reload(); port = int(container.attrs["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"])
        values = {name: entry._gamma_local_read_secret(root, name) for name in (
            "redis-runtime.key", "redis-admin.key", "redis-probe.key", "redis-source.key")}
        def clients():
            make = lambda user, key: redis.Redis(host="127.0.0.1", port=port, username=user, password=key, decode_responses=True)
            return make("qwq_runtime", values["redis-runtime.key"]), make("qwq_source_admin", values["redis-admin.key"]), make("qwq_source_old_probe", values["redis-probe.key"]), make(target.acl_user, values["redis-source.key"])
        deadline = time.monotonic() + 30
        while True:
            try: runtime, admin, probe, source = clients(); admin.ping(); break
            except redis.ConnectionError:
                if time.monotonic() > deadline: raise AssertionError(container.logs().decode())
                time.sleep(.2)
        for current in (runtime, admin, probe, source): current.ping()
        pubsub = runtime.pubsub()
        pubsub.subscribe("rt:account:security-relay")
        subscribed = pubsub.get_message(timeout=2)
        assert subscribed is not None and subscribed["type"] == "subscribe"
        runtime.publish("rt:account:security-relay", "credential-probe")
        delivered = pubsub.get_message(timeout=2)
        assert delivered is not None and delivered["data"] == "credential-probe"
        pubsub.close()
        with pytest.raises(redis.exceptions.NoPermissionError): probe.xrange("events.user.account")
        with pytest.raises(redis.exceptions.AuthenticationError): redis.Redis(host="127.0.0.1", port=port).ping()
        source.xgroup_create("events.user.account", target.consumer_group, id="0-0", mkstream=True)
        container.restart(timeout=10)
        container.reload()
        port = int(container.attrs["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"])
        deadline = time.monotonic() + 30
        while True:
            try: runtime, admin, probe, source = clients(); admin.ping(); break
            except redis.ConnectionError:
                if time.monotonic() > deadline: raise AssertionError(container.logs().decode())
                time.sleep(.2)
        assert "off" in admin.acl_getuser("default")["flags"]
        assert admin.acl_getuser(target.acl_user)["passwords"] == [hashlib.sha256(values["redis-source.key"].encode()).hexdigest()]
        runtime.ping(); source.xinfo_stream("events.user.account")
        runtime_pubsub = runtime.pubsub()
        runtime_pubsub.subscribe("rt:account:security-relay")
        subscribed = runtime_pubsub.get_message(timeout=2)
        assert subscribed is not None and subscribed["type"] == "subscribe"
        runtime_pubsub.close()
        with pytest.raises(redis.exceptions.NoPermissionError): probe.xrange("events.user.account")
    finally:
        if container is not None: container.remove(force=True, v=True)
        client.close()
        shutil.rmtree(root, ignore_errors=True)
