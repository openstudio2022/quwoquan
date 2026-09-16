# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t12
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t13
"""真实 SQLite deployment/claim/token/task authority 链。"""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import pytest
from content.coordination import ROLE_NAMES
from content.coordination.fence import WriteFenceToken
from content.coordination.runtime import actor_key,governed_repackage_call
from content.coordination.store import CoordinationError,CoordinationStore
from content.coordination.cli import main
from local_contract.release.test_legacy_release_repackage__contract__local_contract_test import SOURCE, _legacy

def _install_authority_provider(tmp_path,monkeypatch,artifact):
    authority_digest="sha256:"+hashlib.sha256(artifact.read_bytes()).hexdigest()
    registry=tmp_path/"authority-registry.json"; registry.write_text(json.dumps({str(artifact.absolute()):authority_digest}))
    verifier=tmp_path/"authority-verifier.py"; verifier.write_text("""#!/usr/bin/env python3
import json,os,sys
r=json.loads(sys.stdin.read()); allowed=json.loads(open(os.environ['QWQ_TEST_AUTHORITY_REGISTRY']).read())
if allowed.get(r['ref']) != r['digest']: raise SystemExit(2)
print(json.dumps({**r,'state':'verified'}))
"""); verifier.chmod(0o755)
    monkeypatch.setenv("QWQ_TEST_AUTHORITY_REGISTRY",str(registry)); monkeypatch.setenv("QWQ_CONTENT_AUTHORITY_VERIFIER",str(verifier))
    return authority_digest

def _actor(role): return {"host":"cursor","sessionId":f"real-{role}","invocation":{"runId":f"run-{role}"}}
def test_gwt_062_t12_cli_task_to_real_fenced_repackage_without_batch_nonces(tmp_path,monkeypatch,capsys):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t12"""
    db=tmp_path/"coord.sqlite"; output=tmp_path/"output"; publish=tmp_path/"publish"; library=tmp_path/"library"; carried=tmp_path/"carried"
    for root in (output,publish,library,carried): root.mkdir()
    releases=output/"data/releases"; hd,cohort_digest=_legacy(releases)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module,"_validate_embedded_pool_rows",lambda **kwargs: [])
    (publish/".git").mkdir(); (publish/"repository.json").write_text(json.dumps({"schema":"quwoquan_data.publish_repository.v2","repositoryId":"repo","layoutVersion":2}))
    roles={role:[actor_key(_actor(role))] for role in ROLE_NAMES}; director=roles["director"][0]
    authorization=tmp_path/"authorization.json"; authorization.write_text(json.dumps({"schema":"test.signed_user_authorization","actor":"real-user","action":"repackage"}))
    confirmation=tmp_path/"confirmation.json"; confirmation.write_text('{"approved":true}')
    digest="sha256:"+hashlib.sha256(confirmation.read_bytes()).hexdigest()
    authorization_digest="sha256:"+hashlib.sha256(authorization.read_bytes()).hexdigest()
    registry=tmp_path/"authority-registry.json"; registry.write_text(json.dumps({str(authorization.absolute()):authorization_digest,str(confirmation.absolute()):digest}))
    _install_authority_provider(tmp_path,monkeypatch,authorization)
    registry.write_text(json.dumps({str(authorization.absolute()):authorization_digest,str(confirmation.absolute()):digest}))
    task=tmp_path/"task.json"
    assert main(["--db",str(db),"create-repackage-task","--output",str(task),"--authorization-ref",str(authorization),"--authorization-digest",authorization_digest,"--confirmation-ref",str(confirmation),"--confirmation-digest",digest,"--confirmed-by",director,"--roles",json.dumps(roles)])==0
    task_result=json.loads(capsys.readouterr().out); task_digest=task_result["taskDigest"]
    store=CoordinationStore(db); store.register_iteration("migration",str(authorization),authorization_digest); store.register_deployment("migration","deployment",roles,instance_id="instance",account_identity_ref="account",resource_reservation_ref="reservation")
    roots={"output":str(output.resolve()),"publish":str(publish.resolve()),"library":str(library.resolve()),"carried":str(carried.resolve())}
    store.bind_context("migration","deployment",task_ref=str(task),task_digest=task_digest,roots=roots,actor=director)
    store.register_shard("migration","s","migration","scope://migration",0,["entities/a"],authorized_team="migration-team")
    claim=store.claim("migration","migration-team","claim",shard_id="s",deployment_id="deployment")
    token=WriteFenceToken("migration","s","deployment","migration-team",claim["generation"],"entities/a")
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB",str(db)); monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE",json.dumps(token.__dict__ if hasattr(token,'__dict__') else {k:getattr(token,k) for k in token.__slots__}))
    monkeypatch.setenv("QWQ_CONTENT_ACTOR",json.dumps(_actor("director"))); monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST",task_digest); monkeypatch.setenv("QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT","deployment")
    monkeypatch.delenv("QWQ_CONTENT_BATCH_NONCES",raising=False)
    monkeypatch.setattr("content.coordination.runtime.actual_roots",lambda:roots)
    import content.coordination.store as store_module
    monkeypatch.setattr(store_module,"RELEASE_ROOT",output/"data/releases",raising=False)
    before=store._connect().execute("SELECT COUNT(*) FROM batch_scopes").fetchone()[0]
    assert governed_repackage_call(lambda:"ok",target_refs=["entities/a"],release_id="target-release")=="ok"
    after=store._connect().execute("SELECT COUNT(*) FROM batch_scopes").fetchone()[0]
    assert before==after==0
    stale=WriteFenceToken("migration","s","deployment","migration-team",claim["generation"]+1,"entities/a")
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE",json.dumps({k:getattr(stale,k) for k in stale.__slots__}))
    with pytest.raises(CoordinationError,match="STALE"):
        governed_repackage_call(lambda:"bad",target_refs=["entities/a"],release_id="target-release")

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t13
def test_release_native_lock_conflict_blocks_before_business_write(tmp_path, monkeypatch):
    """spec_ref: gwt-062.t13"""
    from content.release.canonical.release_operation_lock import release_operation_guard,release_operation_lock_root,ReleaseOperationConflict
    release_root=tmp_path/"output/data/releases"; release_root.mkdir(parents=True)
    lock_root=release_operation_lock_root(release_root)
    with release_operation_guard(lock_root=lock_root,release_ids=("target-release",),exclusive_releases=True):
        with pytest.raises(ReleaseOperationConflict):
            with release_operation_guard(lock_root=lock_root,release_ids=("target-release",),exclusive_releases=True):
                raise AssertionError("business write must not run")

@pytest.mark.parametrize("mutation, expected", [
    ("authorization", "AUTHORIZATION_DIGEST_DRIFT"),
    ("confirmation", "AUTHORIZATION_DIGEST_DRIFT"),
])
def test_gwt_062_t11_authority_exact_readback_drift(tmp_path,monkeypatch,capsys,mutation,expected):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11"""
    authorization=tmp_path/"authorization.json"; authorization.write_text('{"signed":true}')
    confirmation=tmp_path/"confirmation.json"; confirmation.write_text('{"confirmed":true}')
    ad="sha256:"+hashlib.sha256(authorization.read_bytes()).hexdigest(); cd="sha256:"+hashlib.sha256(confirmation.read_bytes()).hexdigest()
    registry=tmp_path/"authority-registry.json"; registry.write_text(json.dumps({str(authorization.absolute()):ad,str(confirmation.absolute()):cd}))
    _install_authority_provider(tmp_path,monkeypatch,authorization); registry.write_text(json.dumps({str(authorization.absolute()):ad,str(confirmation.absolute()):cd}))
    (authorization if mutation=="authorization" else confirmation).write_text('{"drift":true}')
    roles={role:[actor_key(_actor(role))] for role in ROLE_NAMES}; director=roles["director"][0]
    assert main(["--db",str(tmp_path/"db"),"create-repackage-task","--output",str(tmp_path/"task"),"--authorization-ref",str(authorization),"--authorization-digest",ad,"--confirmation-ref",str(confirmation),"--confirmation-digest",cd,"--confirmed-by",director,"--roles",json.dumps(roles)])==2
    assert expected in capsys.readouterr().out

@pytest.mark.parametrize("case", ["non-director","wrong-closer","root-drift","non-exact-fence","stale-generation"])
def test_gwt_062_t11_cli_handler_authority_rejection_matrix(tmp_path,monkeypatch,capsys,case):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11"""
    import argparse
    import content.release.canonical.handler as handler
    db=tmp_path/"coord.sqlite"; output=tmp_path/"output"; publish=tmp_path/"publish"; library=tmp_path/"library"; carried=tmp_path/"carried"
    for root in (output,publish,library,carried): root.mkdir()
    releases=output/"data/releases"; hd,cohort_digest=_legacy(releases)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module,"_validate_embedded_pool_rows",lambda **kwargs: [])
    (publish/".git").mkdir(); (publish/"repository.json").write_text(json.dumps({"schema":"quwoquan_data.publish_repository.v2","repositoryId":"repo","layoutVersion":2}))
    authorization=tmp_path/"authorization.json"; authorization.write_text('{"signed":true}'); confirmation=tmp_path/"confirmation.json"; confirmation.write_text('{"confirmed":true}')
    ad="sha256:"+hashlib.sha256(authorization.read_bytes()).hexdigest(); cd="sha256:"+hashlib.sha256(confirmation.read_bytes()).hexdigest()
    _install_authority_provider(tmp_path,monkeypatch,authorization); registry=tmp_path/"authority-registry.json"; source_authority=releases/SOURCE/"repository_authority.json"
    registry.write_text(json.dumps({str(authorization.absolute()):ad,str(confirmation.absolute()):cd,str(source_authority.absolute()):"sha256:"+hashlib.sha256(source_authority.read_bytes()).hexdigest()}))
    roles={role:[actor_key(_actor(role))] for role in ROLE_NAMES}; director=roles["director"][0]; task=tmp_path/"task.json"
    assert main(["--db",str(db),"create-repackage-task","--output",str(task),"--authorization-ref",str(authorization),"--authorization-digest",ad,"--confirmation-ref",str(confirmation),"--confirmation-digest",cd,"--confirmed-by",director,"--roles",json.dumps(roles)])==0
    td=json.loads(capsys.readouterr().out)["taskDigest"]; store=CoordinationStore(db); store.register_iteration("i",str(authorization),ad); store.register_deployment("i","d",roles,instance_id="instance",account_identity_ref="account",resource_reservation_ref="reservation")
    roots={"output":str(output.resolve()),"publish":str(publish.resolve()),"library":str(library.resolve()),"carried":str(carried.resolve())}; store.bind_context("i","d",task_ref=str(task),task_digest=td,roots=roots,actor=director); store.register_shard("i","s","s","scope",0,["entities/a"]); claim=store.claim("i","team","c",shard_id="s",deployment_id="d")
    token=WriteFenceToken("i","s","d","team",claim["generation"]+(case=="stale-generation"),"entities/other" if case=="non-exact-fence" else "entities/a")
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB",str(db)); monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE",json.dumps({k:getattr(token,k) for k in token.__slots__})); monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST",td); monkeypatch.setenv("QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT","wrong" if case=="wrong-closer" else "d"); monkeypatch.setenv("QWQ_CONTENT_ACTOR",json.dumps(_actor("qa" if case=="non-director" else "director")))
    monkeypatch.setattr("content.coordination.runtime.actual_roots",lambda:{**roots,"library":str(tmp_path/"drift")} if case=="root-drift" else roots)
    monkeypatch.setattr(handler,"OUTPUT_ROOT",output); monkeypatch.setattr(handler,"PUBLISH_ROOT",publish)
    args=argparse.Namespace(publish_root=str(publish),release_root=str(output/"data/releases"),source_root=str(output/"data/releases"),repository_id="repo",source_release_id=SOURCE,source_handoff_digest=hd,source_cohort_digest=cohort_digest,source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest="sha256:"+hashlib.sha256((releases/".repository-authorities"/f"{SOURCE}.json").read_bytes()).hexdigest(),target_release_id="target",milestone="M1",producer_baseline_revision="a"*40)
    with pytest.raises(SystemExit): handler.handle_repackage_legacy(args)
    assert not (output/"data/releases/target").exists()

@pytest.mark.parametrize(("case","code"),[("non-director","DIRECTOR_REQUIRED"),("wrong-closer","GLOBAL_CLOSER_REQUIRED"),("root-drift","ROOT_BINDING_MISMATCH"),("non-exact-fence","WRITE_FENCE_TARGET_OUTSIDE_SHARD"),("stale-generation","STALE_CLAIM")])
def test_gwt_062_t11_scripts_cli_parser_handler_runtime_sqlite_matrix(tmp_path,monkeypatch,case,code):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11"""
    import subprocess,sys
    from local_contract.release.test_producer_release_detachment__contract__local_contract_test import _repository_handoff_fixture
    output=tmp_path/"output"; publish=tmp_path/"publish"; library=tmp_path/"library"; carried=tmp_path/"carried"; db=tmp_path/"db.sqlite"
    for root in (output,publish,library,carried): root.mkdir()
    path,document=_repository_handoff_fixture(output); releases=output/"data/releases"; source_id=document["releaseId"]
    cohort={**document["explicitCohort"]["document"],"releaseClass":"production"}; cohort_raw=(json.dumps(cohort,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode(); (path.parent/"cohort.json").write_bytes(cohort_raw)
    legacy={k:v for k,v in document.items() if k not in {"repositoryId","artifact"}}
    for row in legacy["contentPoolObjects"]:
        query=row["queryDocument"]; query["scope"]={"usageScope":"research","variantPurpose":"not_applicable"}; query["contentLibrary"].pop("bindingRef",None)
        row["queryDigest"]="sha256:"+hashlib.sha256(json.dumps(query,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    legacy["explicitCohort"]={**legacy["explicitCohort"],"digest":"sha256:"+hashlib.sha256(cohort_raw).hexdigest(),"document":cohort}; path.write_bytes((json.dumps(legacy,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()); hd="sha256:"+hashlib.sha256(path.read_bytes()).hexdigest(); cd="sha256:"+hashlib.sha256(cohort_raw).hexdigest()
    terminal_digest="sha256:"+hashlib.sha256(json.dumps({"cohortDigest":cd,"handoffDigest":hd,"releaseId":source_id},sort_keys=True,separators=(",",":")).encode()).hexdigest(); authorities=releases/".repository-authorities"; authorities.mkdir(); source_authority=authorities/f"{source_id}.authority.json"; source_authority.write_text(json.dumps({"repositoryId":"legacy-content","sourceTerminalDigest":terminal_digest})); evidence_path=authorities/f"{source_id}.json"; evidence_path.write_text(json.dumps({"schema":"quwoquan_data.legacy_source_repository_evidence","sourceRepositoryId":"legacy-content","sourceTerminalDigest":terminal_digest,"issuer":"legacy-release-seal","authorityRef":str(source_authority),"authorityDigest":"sha256:"+hashlib.sha256(source_authority.read_bytes()).hexdigest()},sort_keys=True,separators=(",",":"))+"\n")
    (publish/".git").mkdir(); (publish/"repository.json").write_text(json.dumps({"schema":"quwoquan_data.publish_repository.v2","repositoryId":"repo","layoutVersion":2})); authorization=tmp_path/"authorization.json"; authorization.write_text('{"signed":true}'); confirmation=tmp_path/"confirmation.json"; confirmation.write_text('{"confirmed":true}')
    ad="sha256:"+hashlib.sha256(authorization.read_bytes()).hexdigest(); confd="sha256:"+hashlib.sha256(confirmation.read_bytes()).hexdigest(); registry=tmp_path/"registry.json"; verifier=tmp_path/"verifier.py"; verifier.write_text("""#!/usr/bin/env python3
import json,os,sys
r=json.loads(sys.stdin.read()); a=json.loads(open(os.environ['QWQ_TEST_AUTHORITY_REGISTRY']).read())
if a.get(r['ref']) != r['digest']: raise SystemExit(2)
print(json.dumps({**r,'state':'verified'}))
"""); verifier.chmod(0o755); registry.write_text(json.dumps({str(authorization.absolute()):ad,str(confirmation.absolute()):confd,str(source_authority.absolute()):"sha256:"+hashlib.sha256(source_authority.read_bytes()).hexdigest()})); monkeypatch.setenv("QWQ_CONTENT_AUTHORITY_VERIFIER",str(verifier)); monkeypatch.setenv("QWQ_TEST_AUTHORITY_REGISTRY",str(registry))
    roles={role:[actor_key(_actor(role))] for role in ROLE_NAMES}; director=roles["director"][0]; task=tmp_path/"task.json"; assert main(["--db",str(db),"create-repackage-task","--output",str(task),"--authorization-ref",str(authorization),"--authorization-digest",ad,"--confirmation-ref",str(confirmation),"--confirmation-digest",confd,"--confirmed-by",director,"--roles",json.dumps(roles)])==0; td="sha256:"+hashlib.sha256(task.read_bytes()).hexdigest(); store=CoordinationStore(db); store.register_iteration("i",str(authorization),ad); store.register_deployment("i","d",roles,instance_id="instance",account_identity_ref="account",resource_reservation_ref="reservation")
    refs=cohort["objectRefs"]; roots={"output":str(output.resolve()),"publish":str(publish.resolve()),"library":str(library.resolve()),"carried":str(carried.resolve())}; store.bind_context("i","d",task_ref=str(task),task_digest=td,roots=roots,actor=director); store.register_shard("i","s","s","scope",0,refs); claim=store.claim("i","team","c",shard_id="s",deployment_id="d"); target="entities/other" if case=="non-exact-fence" else refs[0]; token=WriteFenceToken("i","s","d","team",claim["generation"]+(case=="stale-generation"),target)
    env={**os.environ,"QWQ_OUTPUT_ROOT":str(output),"QWQ_PUBLISH_ROOT":str(publish),"QWQ_LIBRARY_ROOT":str(tmp_path/"drift" if case=="root-drift" else library),"QWQ_CARRIED_MEDIA_ROOT":str(carried),"QWQ_CONTENT_COORDINATION_DB":str(db),"QWQ_CONTENT_WRITE_FENCE":json.dumps({k:getattr(token,k) for k in token.__slots__}),"QWQ_CONTENT_ACTOR":json.dumps(_actor("qa" if case=="non-director" else "director")),"QWQ_CONTENT_TASK_DIGEST":td,"QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT":"wrong" if case=="wrong-closer" else "d","QWQ_CONTENT_AUTHORITY_VERIFIER":str(verifier),"QWQ_TEST_AUTHORITY_REGISTRY":str(registry)}
    command=[sys.executable,"-B","quwoquan_data/scripts/cli.py","release","repackage-legacy","--source-root",str(releases),"--repository-id","repo","--source-release-id",source_id,"--source-handoff-digest",hd,"--source-cohort-digest",cd,"--source-repository-evidence-ref",f".repository-authorities/{source_id}.json","--source-repository-evidence-digest","sha256:"+hashlib.sha256(evidence_path.read_bytes()).hexdigest(),"--target-release-id","target","--producer-baseline-revision","a"*40,"--milestone","M1","--publish-root",str(publish),"--release-root",str(releases)]; result=subprocess.run(command,cwd=Path(__file__).resolve().parents[4],env=env,text=True,capture_output=True)
    assert result.returncode==2 and code in result.stderr; assert not (releases/"target").exists()

def test_gwt_062_t13_nonblocking_native_publish_lock_blocks_callable(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t13"""
    import fcntl,subprocess,sys,time
    from content.release.canonical.object_transaction_lock import canonical_publish_lock
    from core.paths import publish_lock_path
    root=tmp_path/"publish"; root.mkdir(); (root/".git").mkdir(); (root/"repository.json").write_text(json.dumps({"schema":"quwoquan_data.publish_repository.v2","repositoryId":"lock-test","layoutVersion":2})); lock=publish_lock_path(root); lock.parent.mkdir(parents=True,exist_ok=True)
    code="import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX); print('locked',flush=True); time.sleep(5)"
    process=subprocess.Popen([sys.executable,"-c",code,str(lock)],stdout=subprocess.PIPE,text=True)
    assert process.stdout.readline().strip()=="locked"; called=[]
    try:
        with pytest.raises(RuntimeError,match="NATIVE_WRITER_LOCK_CONFLICT"):
            with canonical_publish_lock(root,blocking=False): called.append(True)
        assert called==[]
    finally:
        process.terminate(); process.wait(timeout=3)
