# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-008
"""plan/apply入口隔离验证：真实initializer/PG/Redis，无allocator替身。"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shutil
from unittest import mock

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import source_allocation as entry
from quwoquan_ops.cli.lib import output_paths, deployment_candidate_manifest as candidate
from quwoquan_ops.cli.lib.local_runtime_reservation import local_stack_operation_lock
from quwoquan_ops.cli.lib.source_initializer_package import build_source_initializer, digest, load_source_initializer
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import DeploymentCandidateManifestContractBase

ROOT=Path(__file__).resolve().parents[5]
# 复用已存在真实隔离PG/Redis fixture，不调用生产资源。
spec=importlib.util.spec_from_file_location("source_resources",Path(__file__).with_name("test_source_allocation__api_integration_test.py"))
fixtures=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
resources=fixtures.resources


@pytest.fixture
def packaged(tmp_path,monkeypatch):
    DeploymentCandidateManifestContractBase.setUpClass()
    fixture=DeploymentCandidateManifestContractBase()
    fixture.setUp()
    try:
        descriptor=build_source_initializer(fixture.shared,ROOT,"alpha","alpha-local")
        shared=json.loads((fixture.shared/"manifest.json").read_text())
        shared["sourceInitializer"]=descriptor
        (fixture.shared/"manifest.json").write_text(json.dumps(shared))
        candidate.write_candidate_manifest("alpha","alpha-local",package_snapshot=fixture.snapshot,release_attestation=str(fixture.release),rollback_release_attestation=str(fixture.rollback))
        monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT",str(tmp_path/"deploy"))
        targetroot=output_paths.deployment_work_root("alpha-local")
        final=output_paths.deployment_candidate_dir("alpha-local",fixture.snapshot["baselineId"])
        final.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(fixture.candidate,final)
        # 只改路径seam；保留load_candidate_manifest完整解析验证。
        fixture.patches.enter_context(mock.patch.object(candidate,"deployment_candidate_dir",return_value=final))
        descriptor_pointer={"schema":output_paths.ACTIVE_CANDIDATE_SCHEMA,"candidateType":"runtime-full","target":"alpha-local","baselineId":fixture.snapshot["baselineId"],"candidateDir":str(final)}
        output_paths.active_candidate_manifest_path("alpha-local").write_text(json.dumps(descriptor_pointer))
        monkeypatch.setenv("QWQ_OUTPUT_ROOT",str(tmp_path/"output"))
        # canonical同target锁的既有隔离路径seam，不mock锁内逻辑。
        monkeypatch.setattr(entry,"local_stack_operation_lock",lambda target:local_stack_operation_lock(target,lock_path=tmp_path/"operation.lock"))
        yield final
    finally:
        fixture.doCleanups()


def args(action,**values):
    result=argparse.Namespace(action=action,target="alpha-local",plan_ref="",confirm_source_allocation=False,report_dir="",command="source-allocation")
    for key,value in values.items(): setattr(result,key,value)
    return result


def bind_connections(resources,monkeypatch):
    pg,rd,olddsn,old=resources
    monkeypatch.setenv("QWQ_SOURCE_PG_ADMIN_DSN",fixtures._pg_credentials(pg,"postgres","postgres",pg.info.password))
    from urllib.parse import quote
    def redis_url(client):
        v=client.connection_pool.connection_kwargs
        return f"redis://{quote(v['username'])}:{quote(v['password'])}@{v['host']}:{v['port']}/0"
    monkeypatch.setenv("QWQ_SOURCE_REDIS_ADMIN_URL",redis_url(rd))
    monkeypatch.setenv("QWQ_SOURCE_OLD_PG_DSN",olddsn)
    monkeypatch.setenv("QWQ_SOURCE_OLD_REDIS_URL",redis_url(old))


def test_plan_apply_real_allocator(packaged,resources,tmp_path,monkeypatch):
    pg,rd,_,_=resources
    bind_connections(resources,monkeypatch)
    before=pg.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()
    report=output_paths.output_root()/"env/alpha/runs/source-test"
    parsed=stackctl.build_parser().parse_args(["source-allocation","plan","--target","alpha-local","--report-dir",str(report)])
    planned=stackctl.stackctl_dispatch.dispatch(parsed,vars(stackctl))
    assert planned["exitCode"]==0,planned
    assert pg.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()==before
    assert not rd.exists("events.user.account")
    missing=entry.command_source_allocation(args("apply",plan_ref=planned["planRef"]))
    assert missing["exitCode"]==2
    apply_args=stackctl.build_parser().parse_args(["source-allocation","apply","--target","alpha-local","--plan-ref",planned["planRef"],"--confirm-source-allocation"])
    applied=stackctl.stackctl_dispatch.dispatch(apply_args,vars(stackctl))
    assert applied["exitCode"]==0,applied
    assert Path(applied["receiptRef"]).is_file()
    assert entry.command_source_allocation(args("apply",plan_ref=planned["planRef"],confirm_source_allocation=True))["exitCode"]==2


def test_initializer_drift_and_invalid_plan_zero_creation(packaged,resources,tmp_path,monkeypatch):
    pg,rd,_,_=resources
    bind_connections(resources,monkeypatch)
    report=output_paths.output_root()/"env/alpha/runs/source-negative"
    planned=entry.command_source_allocation(args("plan",report_dir=str(report)))
    assert planned["exitCode"]==0,planned
    before=pg.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()
    plan_path=Path(planned["planRef"].rsplit("=",1)[0])
    original_plan=plan_path.read_bytes()
    for changed in ({**json.loads(original_plan),"target":"gamma-local"}, {**json.loads(original_plan),"expiresAt":"2000-01-01T00:00:00+00:00"}):
        plan_path.write_text(json.dumps(changed))
        assert entry.command_source_allocation(args("apply",plan_ref=f"{plan_path}={digest(plan_path.read_bytes())}",confirm_source_allocation=True))["exitCode"]==2
    plan_path.write_bytes(original_plan)
    connection=os.environ["QWQ_SOURCE_OLD_REDIS_URL"]
    monkeypatch.setenv("QWQ_SOURCE_OLD_REDIS_URL",connection+"?socket_timeout=1")
    assert entry.command_source_allocation(args("apply",plan_ref=planned["planRef"],confirm_source_allocation=True))["exitCode"]==2
    monkeypatch.setenv("QWQ_SOURCE_OLD_REDIS_URL",connection)
    # 拒绝发生于持锁阶段，现役executor fence按失败语义保留；测试仅清理自己隔离的锁fixture。
    fence=tmp_path/"operation.executor.json"
    if fence.exists(): fence.unlink()
    candidate_path=packaged/"manifest.json"
    original_candidate=candidate_path.read_bytes()
    changed=json.loads(original_candidate); changed["workspaceDigest"]="sha256:"+"9"*64
    candidate_path.write_text(json.dumps(changed))
    assert entry.command_source_allocation(args("apply",plan_ref=planned["planRef"],confirm_source_allocation=True))["exitCode"]==2
    candidate_path.write_bytes(original_candidate)
    if fence.exists(): fence.unlink()
    from quwoquan_ops.cli.lib.startup_attempt_receipt import startup_attempt_path
    startup_path=startup_attempt_path("alpha-local")
    startup_path.parent.mkdir(parents=True,exist_ok=True)
    startup_path.write_text('{"invalidStartup":true}')
    assert entry.command_source_allocation(args("apply",plan_ref=planned["planRef"],confirm_source_allocation=True))["exitCode"]==2
    startup_path.unlink()
    if fence.exists(): fence.unlink()
    manifest=json.loads((packaged/"packages/runtime-shared/manifest.json").read_text())
    executable=load_source_initializer(packaged,manifest["sourceInitializer"],"alpha","alpha-local")
    with executable.open("ab") as output: output.write(b"drift")
    rejected=entry.command_source_allocation(args("apply",plan_ref=planned["planRef"],confirm_source_allocation=True))
    assert rejected["exitCode"]==2
    assert pg.execute("SELECT datname FROM pg_database ORDER BY datname").fetchall()==before
    assert not rd.exists("events.user.account")
    assert entry.command_source_allocation(args("apply",target="prod-hosted",plan_ref=planned["planRef"],confirm_source_allocation=True))["exitCode"]==2
    with pytest.raises(SystemExit):
        stackctl.build_parser().parse_args(["source-allocation","apply","--target","alpha-local","--initializer","/usr/bin/true"])


def test_gamma_startup_derives_managed_connections_ignoring_caller_env(monkeypatch,tmp_path):
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT",str((tmp_path/"deploy").absolute()))
    monkeypatch.setenv("LOCAL_GAMMA_POSTGRES_PORT","19400")
    monkeypatch.setenv("LOCAL_GAMMA_REDIS_PORT","19420")
    monkeypatch.setenv("LOCAL_GAMMA_MONGO_PORT","19410")
    for name in entry.contract()["credentials"].values(): monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv("QWQ_SOURCE_PG_ADMIN_DSN","postgresql://evil.invalid/evil")
    captured={}
    monkeypatch.setattr(entry,"_gamma_local_managed_connections",lambda **kwargs:{
        "pg_admin":"postgresql://quwoquan:quwoquan@127.0.0.1:19400/quwoquan?sslmode=disable",
        "redis_admin":"redis://managed-admin@127.0.0.1:19420/0",
        "old_pg":"postgresql://managed-probe@127.0.0.1:19400/quwoquan?sslmode=disable",
        "old_redis":"redis://managed-probe@127.0.0.1:19420/0"})
    selected=type("Selected",(),{"candidate_digest":"sha256:"+"a"*64})(); binding={}
    monkeypatch.setattr(entry,"_current",lambda target,**kwargs:(captured.update(kwargs) or ({"managementConnections":entry._connection_identity(kwargs["management_connections"])},selected,binding,tmp_path/"init")))
    path=tmp_path/"missing-current.json"; monkeypatch.setattr(entry,"_source_current_path",lambda target:path)
    monkeypatch.setattr(entry.output_paths,"deployment_target_path",lambda *parts:(tmp_path/"material").absolute())
    monkeypatch.setattr(entry,"_apply_connections",lambda *args,**kwargs:(captured.update(kwargs) or object()))
    monkeypatch.setattr(entry,"_gamma_local_source_password",lambda:"managed-source-secret")
    monkeypatch.setattr(entry,"_publish_source_current",lambda *args:("descriptor"))
    descriptor, actual, actual_binding, connections=entry.ensure_source_allocation_for_locked_up("gamma-local")
    assert descriptor=="descriptor" and actual is selected and actual_binding is binding
    assert connections["pg_admin"].startswith("postgresql://quwoquan:quwoquan@127.0.0.1:")
    assert "evil.invalid" not in repr(connections)
    assert captured["management_connections"]==connections
    with pytest.raises(ValueError,match="forbidden"):
        entry.ensure_source_allocation_for_locked_up("gamma-local",management_connections=connections)
    with pytest.raises(ValueError,match="gamma-local only"):
        entry.ensure_source_allocation_for_locked_up("prod-hosted")


def test_public_source_allocation_still_requires_explicit_environment_connections(packaged,monkeypatch):
    for reference in entry.contract()["credentials"].values(): monkeypatch.delenv(reference,raising=False)
    result=entry.command_source_allocation(args("plan",report_dir=str(output_paths.output_root()/"env/alpha/runs/no-connections")))
    assert result["exitCode"]==2
