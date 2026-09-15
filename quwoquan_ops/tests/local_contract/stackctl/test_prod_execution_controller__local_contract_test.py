# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
import unittest
from unittest import mock
from quwoquan_ops.cli.prod.execution_controller import ControllerSession, SESSION_SCHEMA, digest, load_contract, load_session, run_prevalidate_coordination, save_session
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_delivery import sign_request
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_guard import DurablePlaneGuard, _runtime_helper_main, verify_envelope

D=lambda c='a':'sha256:'+c*64
class DirectProtocolTransport:
 def __init__(self,tmp_path:Path,private:Path,public:Path):
  self.private,self.public=private,public;self.state={'status':'closed','generation':0};self.calls=[];self.guards={}
  for plane in ('edge','service'):
   root=tmp_path/plane/'guard';runtime=tmp_path/plane/'runtime';root.mkdir(parents=True);runtime.mkdir();(root/'guard.lock').touch();self.guards[plane]=DurablePlaneGuard(root,runtime)
 def authority(self,action,request):
  self.calls.append(('authority',action,request))
  if action=='acquire': self.state={'generation':request['expectedExecutionGeneration']+1,'inventoryDigest':D('b'),'phase':'executing','submitted':[]};return dict(self.state)
  if action=='register': return {'stepDigest':digest(request)}
  if action=='ack': return {'acknowledged':True}
  if action=='consume':
   if self.state.get('phase')!='observing' or request['observationDigest']!=self.state.get('observationDigest'):raise RuntimeError('EXECUTION.OBSERVATION_RELEASED_OR_DRIFTED')
   self.state['phase']='consumed';return dict(self.state)
  if action=='close':self.state={'status':'closed','generation':request['executionGeneration']};return {'closed':True}
  raise AssertionError(action)
 def plane(self,placement,envelope):
  self.calls.append(('plane',placement['plane'],envelope))
  request=verify_envelope(envelope,public_key=self.public,expected_identity='quwoquan-prod-deployment-controller',expected_key_id='prod-execution-controller-ed25519-k1')
  return self.guards[placement['plane']].submit(request)

def keys(tmp_path):
 private=tmp_path/'private.pem';public=tmp_path/'public.pem';subprocess.run(['openssl','genpkey','-algorithm','Ed25519','-out',private],check=True);private.chmod(0o600);subprocess.run(['openssl','pkey','-in',private,'-pubout','-out',public],check=True);return private,public

def placements(tmp_path):
 return [{'id':f'h-{p}-prod-r0','hostId':'h','plane':p,'instance':'prod','replicaId':'r0','guardIncarnation':1,'guardRoot':str(tmp_path/p/'guard'),'runtimeRoot':str(tmp_path/p/'runtime'),'sshHost':'fixture'} for p in ('edge','service')]

class ProdExecutionControllerContractTest(unittest.TestCase):
    def test_real_signed_protocol_lost_ack_owner_and_partial_plane(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            tmp_path=Path(directory)
            private,public=keys(tmp_path); transport=DirectProtocolTransport(tmp_path,private,public)
            session=ControllerSession(transport,load_contract(),private,D(),0,0); ps=placements(tmp_path)
            session.acquire(); session.prepare_all(ps)
            target=Path(ps[0]['runtimeRoot'])/'runtime/artifact-identity.json'; target.parent.mkdir(); target.write_bytes(b'exact')
            result=session.submit(ps[0],'observe-runtime-identity',{'relativePath':'runtime/artifact-identity.json'},D())
            envelope=transport.calls[-2][2]; self.assertEqual(transport.plane(ps[0],envelope),result)
            bad=ControllerSession(transport,load_contract(),private,D('c'),0,0); bad.state={**session.state,'generation':2}
            with self.assertRaises(RuntimeError):
                bad.submit(ps[0],'observe-runtime-identity',{'relativePath':'runtime/artifact-identity.json'},D())
            self.assertEqual({x[1] for x in transport.calls if x[0]=='plane'},{'edge','service'})


    def test_session_load_save_is_atomic_owner_bound_and_symlink_safe(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); private,public=keys(root); ps=placements(root); path=root/"session.json"
            session=ControllerSession(DirectProtocolTransport(root,private,public),load_contract(),private,D(),4,2)
            session.state={"generation":5,"attemptId":D(),"inventoryDigest":D('b'),"phase":"executing","submitted":[]}
            save_session(path,session,ps); self.assertEqual(path.stat().st_mode & 0o777,0o600)
            secret=load_contract()["executionControl"]["trustedController"]["privateKeySecretRef"]
            with mock.patch.dict(os.environ,{secret:str(private)}):
                loaded=load_session(path)
            self.assertEqual((loaded.attempt_id,loaded.expected_execution_generation,loaded.expected_release_generation),(D(),4,2))
            self.assertEqual(loaded.state["generation"],5)
            drift=ControllerSession(session.transport,session.contract,private,D('c'),4,2);drift.state={**session.state,"attemptId":D('c')}
            with self.assertRaisesRegex(RuntimeError,"IDENTITY_DRIFT"):save_session(path,drift,ps)
            alias=root/"alias.json";alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,"PATH_INVALID"):load_session(alias)

    def test_observe_consume_activation_has_no_release_window(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            tmp_path=Path(directory); private,public=keys(tmp_path); transport=DirectProtocolTransport(tmp_path,private,public)
            session=ControllerSession(transport,load_contract(),private,D(),0,0); ps=placements(tmp_path); session.acquire(); session.prepare_all(ps)
            transport.state.update({'phase':'observing','observationDigest':D('e')}); session.state.update({'phase':'observing','observationDigest':D('e')})
            session.bind_human_winner({'winner':'yes'},D('e'))
            request=Path(ps[1]['runtimeRoot'])/'staging/activation.json'; request.parent.mkdir(); request.write_text(json.dumps({'service':'prod-stack','expectedGeneration':0,'action':'ledger-activation-cas'}))
            session.activation_cas(ps[1],{'service':'prod-stack','expectedReleaseGeneration':0,'requestRelative':'staging/activation.json'},D())
            actions=[x[1] for x in transport.calls if x[0]=='authority']; self.assertLess(actions.index('consume'),max(i for i,x in enumerate(actions) if x=='register')); self.assertNotIn('close',actions)
            session.close_all(ps)
            with self.assertRaises(RuntimeError): session.bind_human_winner({'winner':'late'},D('e'))


    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t3
    def test_runtime_helper_restarts_stops_repeats_and_cleans_failed_start(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/"runtime").mkdir(); (root/"runtime/artifact-identity.json").write_text(json.dumps({"schema":"qwq.environment-artifact-identity","environment":"prod","configDigest":D()}))
            calls=[]
            def run(argv,**kwargs): calls.append(argv); return subprocess.CompletedProcess(argv,17 if "fail-service" in argv else 0)
            with mock.patch("quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_guard.subprocess.run",side_effect=run):
                common=["--runtime-root",str(root),"--project","quwoquan-service-prevalidate-r0"]
                for _ in range(2): self.assertEqual(_runtime_helper_main(["restart-admitted",*common,"--compose-file","docker-compose.prod-hosted.yaml","--env-file","stack.env","--services","api-edge"]),0)
                self.assertEqual(_runtime_helper_main(["stop-admitted",*common,"--compose-file","docker-compose.prod-hosted.yaml","--env-file","stack.env"]),0)
                self.assertEqual(_runtime_helper_main(["restart-admitted",*common,"--compose-file","docker-compose.prod-hosted.yaml","--env-file","stack.env","--services","fail-service"]),17)
            self.assertEqual(calls[-1],["/usr/bin/podman","compose","--env-file","stack.env","-f","docker-compose.prod-hosted.yaml","-p","quwoquan-service-prevalidate-r0","stop"]); self.assertNotIn("down",json.dumps(calls))

    def test_runtime_helper_rejects_concurrent_writer_and_identity_drift(self):
        import fcntl, tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); guard=root/"process/execution-guard"; guard.mkdir(parents=True); (root/"runtime").mkdir(); identity=root/"runtime/artifact-identity.json"
            identity.write_text(json.dumps({"schema":"qwq.environment-artifact-identity","environment":"prod","configDigest":D()}))
            lock=(guard/"runtime.lock").open("w"); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,"RUNTIME_BUSY"): _runtime_helper_main(["stop-admitted","--runtime-root",str(root),"--project","quwoquan-service-prevalidate-r0","--compose-file","docker-compose.prod-hosted.yaml","--env-file","stack.env"])
            fcntl.flock(lock,fcntl.LOCK_UN); lock.close(); identity.write_text("{}")
            with self.assertRaisesRegex(ValueError,"IDENTITY_INVALID"): _runtime_helper_main(["stop-admitted","--runtime-root",str(root),"--project","quwoquan-service-prevalidate-r0","--compose-file","docker-compose.prod-hosted.yaml","--env-file","stack.env"])


class PrevalidateExecutionCoordinationTest(unittest.TestCase):
    def _fixture(self, root: Path):
        private, public = keys(root)
        transport = DirectProtocolTransport(root, private, public)
        ps = placements(root)
        for placement in ps:
            placement["instance"] = "prevalidate"
            placement["id"] = placement["id"].replace("prod", "prevalidate")
        session = ControllerSession(transport, load_contract(), private, D(), 0, 0)
        staged = {}
        from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_guard import _digest as value_digest
        for placement in ps:
            runtime = Path(placement["runtimeRoot"]); stage = runtime / "staging" / placement["plane"]
            (stage / "runtime").mkdir(parents=True); (stage / "systemd").mkdir()
            (stage / "runtime/artifact-identity.json").write_text(json.dumps({"schema":"qwq.environment-artifact-identity","environment":"prod","configDigest":D()}))
            unit = f"quwoquan-{placement['plane']}-prevalidate-r0.service"
            unit_path = stage / "systemd" / unit; unit_path.write_text("[Service]\nExecStart=/usr/bin/true\n")
            import hashlib
            def tree_digest(base):
                h=hashlib.sha256()
                for path in sorted(x for x in base.rglob("*") if x.is_file()):
                    h.update(path.relative_to(base).as_posix().encode());h.update(b"\0");h.update(hashlib.sha256(path.read_bytes()).digest())
                return "sha256:"+h.hexdigest()
            staged[placement["plane"]]={"stagingRelative":str(stage.relative_to(runtime)),"treeDigest":tree_digest(stage),"unitName":unit,"unitDigest":"sha256:"+hashlib.sha256(unit_path.read_bytes()).hexdigest()}
        return session, transport, ps, staged

    def test_staging_promote_start_readback_close_and_lost_ack(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,transport,ps,staged=self._fixture(root)
            original=[]
            for guard in transport.guards.values():
                base=guard._argv
                def argv(request, base=base, guard=guard):
                    if request["action"]=="prevalidate-install-unit": return ["/usr/bin/true"]
                    if request["action"] in {"prevalidate-start","prevalidate-stop"}: return ["/usr/bin/true"]
                    return base(request)
                guard._argv=argv
            lost={"done":False}
            authority=transport.authority
            def flaky(action,request):
                if action=="ack" and not lost["done"]:
                    lost["done"]=True; authority(action,request); raise RuntimeError("lost response")
                return authority(action,request)
            transport.authority=flaky
            result=run_prevalidate_coordination(session,ps,staged)
            self.assertEqual(result["status"],"passed");self.assertTrue(result["nonPromotable"]);self.assertIsNone(session.state)
            for placement in ps:
                immutable=Path(placement["runtimeRoot"])/"instances/prevalidate/r0"
                self.assertTrue((immutable/"runtime/artifact-identity.json").is_file())

    def test_unpromoted_status_old_generation_and_failure_cleanup(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,transport,ps,staged=self._fixture(root)
            guard=transport.guards[ps[0]["plane"]];session.acquire();session.prepare_all(ps)
            with self.assertRaises(RuntimeError): session.submit(ps[0],"prevalidate-status",{"relativePath":"instances/prevalidate/r0/immutable/missing"},D())
            journal=guard._load(); old=dict(next(x["request"] for x in journal["steps"].values() if x["request"]["action"]=="guard-prepare"));old["sequence"]=99;old["executionGeneration"]=1
            with self.assertRaisesRegex(RuntimeError,"MONOTONIC_FENCE_REJECTED"):guard.submit(old)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session,transport,ps,staged=self._fixture(root);calls=[]
            for guard in transport.guards.values():
                base=guard._argv
                def argv(request,base=base):
                    calls.append(request["action"]);
                    if request["action"]=="prevalidate-install-unit": return ["/usr/bin/true"]
                    if request["action"]=="prevalidate-start" and request["placementId"].endswith("service-prevalidate-r0"): return ["/usr/bin/false"]
                    if request["action"] in {"prevalidate-start","prevalidate-stop"}: return ["/usr/bin/true"]
                    return base(request)
                guard._argv=argv
            with self.assertRaisesRegex(RuntimeError,"PLANE_ACTION_FAILED"):run_prevalidate_coordination(session,ps,staged)
            self.assertIn("prevalidate-stop",calls);self.assertIsNone(session.state)
