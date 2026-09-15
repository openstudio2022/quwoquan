#!/usr/bin/env python3
"""DEC-015唯一controller adapter：中央slot、签名plane投递、ACK与连续handoff。"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
import argparse, base64, hashlib, json, os, subprocess, tempfile
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import yaml

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.contract import EXECUTION_ACTION_PARAMETERS, _canonical_bytes
from quwoquan_ops.cli.prod.hosted_release_ledger_lib.execution_delivery import sign_request

ACCESS=ROOT/'quwoquan_ops/environments/prod/access-isolation.yaml'

def digest(value:Any)->str:return 'sha256:'+hashlib.sha256(_canonical_bytes(value)).hexdigest()
def file_digest(path:Path)->str:return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
def load_contract()->dict[str,Any]:
 value=yaml.safe_load(ACCESS.read_text()); control=value['executionControl']; declared=set(control['permittedActions'])
 if declared!=set(EXECUTION_ACTION_PARAMETERS): raise RuntimeError('EXECUTION.ACTION_CONTRACT_DRIFT')
 return value

class Transport(Protocol):
 def authority(self,action:str,request:dict[str,Any])->dict[str,Any]:...
 def plane(self,placement:dict[str,Any],envelope:dict[str,Any])->dict[str,Any]:...

class SubprocessTransport:
 def __init__(self,contract:dict[str,Any]): self.contract=contract
 def authority(self,action:str,request:dict[str,Any])->dict[str,Any]:
  with tempfile.TemporaryDirectory(prefix='qwq-execution-') as d:
   req=Path(d)/'request.json'; out=Path(d)/'result.json'; req.write_bytes(_canonical_bytes(request)+b'\n')
   cmd=['bash','quwoquan_ops/cli/prod/sync_prod_plane_stack.sh','--plane','service','--operation','release-ledger-execution-'+action,'--request-path',str(req),'--output-path',str(out)]
   result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
   if result.returncode: raise RuntimeError('EXECUTION.AUTHORITY_IO_FAILED: '+(result.stderr or result.stdout).strip())
   return json.loads(out.read_bytes())
 def plane(self,placement:dict[str,Any],envelope:dict[str,Any])->dict[str,Any]:
  plane=placement['plane']; spec=next(x for x in self.contract['planes'] if x['plane']==plane); control=self.contract['executionControl']
  secret=spec['sshKeySecret']; key=Path(os.environ.get(secret+'_FILE') or os.environ.get(secret+'_PATH') or Path.home()/'.ssh/quwoquan-prod'/spec['account'])
  if not key.is_file(): raise RuntimeError(f'EXECUTION.PLANE_CREDENTIAL_MISSING: {secret}')
  helper=control['guardHelperRelative']; guard_root=placement['guardRoot']; runtime_root=placement['runtimeRoot']; pub=f"{spec['credentialsPath']}/{control['trustedController']['publicKeyDescriptorRef']}"
  encoded=base64.b64encode(_canonical_bytes(envelope)).decode('ascii')
  remote=[helper,'--root',guard_root,'--runtime-root',runtime_root,'--public-key',pub,'--controller-identity',control['trustedController']['identity'],'--controller-key-id',control['trustedController']['keyId'],'--envelope-base64',encoded]
  result=subprocess.run(['ssh','-F','/dev/null','-i',str(key),'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes',f"{spec['account']}@{placement['sshHost']}",' '.join(map(_quote,remote))],capture_output=True,text=True)
  if result.returncode: raise RuntimeError('EXECUTION.PLANE_SUBMIT_FAILED: '+(result.stderr or result.stdout).strip())
  return json.loads(result.stdout)
def _quote(value:str)->str:
 import shlex; return shlex.quote(str(value))

SESSION_SCHEMA = "quwoquan.prod.execution-controller-session.v1"
SESSION_FIELDS = frozenset({"schema", "attemptId", "expectedExecutionGeneration", "expectedReleaseGeneration", "placements", "state"})
PLACEMENT_FIELDS = frozenset({"id", "hostId", "plane", "instance", "replicaId", "guardIncarnation", "guardRoot", "runtimeRoot", "sshHost"})

def _safe_session_path(path: Path, *, must_exist: bool) -> Path:
 path = path.expanduser()
 if not path.is_absolute() or ".." in path.parts or path.is_symlink(): raise ValueError("EXECUTION.SESSION_PATH_INVALID")
 parent = path.parent
 if not parent.is_dir() or parent.is_symlink() or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o022:
  raise ValueError("EXECUTION.SESSION_PARENT_INVALID")
 if must_exist:
  info = path.stat()
  if not path.is_file() or info.st_uid != os.getuid() or info.st_mode & 0o077: raise ValueError("EXECUTION.SESSION_AUTHORITY_INVALID")
 return path

def _validate_session_payload(value: Any) -> dict[str, Any]:
 if not isinstance(value, dict) or set(value) != SESSION_FIELDS or value.get("schema") != SESSION_SCHEMA: raise ValueError("EXECUTION.SESSION_SCHEMA_INVALID")
 if not isinstance(value.get("attemptId"), str) or not value["attemptId"].startswith("sha256:") or len(value["attemptId"]) != 71: raise ValueError("EXECUTION.SESSION_ATTEMPT_INVALID")
 for field in ("expectedExecutionGeneration", "expectedReleaseGeneration"):
  if type(value.get(field)) is not int or value[field] < 0: raise ValueError("EXECUTION.SESSION_GENERATION_INVALID")
 placements=value.get("placements")
 if not isinstance(placements,list) or not placements: raise ValueError("EXECUTION.SESSION_PLACEMENTS_INVALID")
 seen=set()
 for placement in placements:
  if not isinstance(placement,dict) or set(placement)!=PLACEMENT_FIELDS or placement["id"] in seen or type(placement["guardIncarnation"]) is not int or placement["guardIncarnation"]<1: raise ValueError("EXECUTION.SESSION_PLACEMENT_INVALID")
  if placement["plane"] not in {"service","edge"} or placement["instance"] not in {"prevalidate","gray","prod"}: raise ValueError("EXECUTION.SESSION_PLACEMENT_INVALID")
  if any(not isinstance(placement[k],str) or not placement[k] for k in PLACEMENT_FIELDS-{"guardIncarnation"}): raise ValueError("EXECUTION.SESSION_PLACEMENT_INVALID")
  seen.add(placement["id"])
 state=value.get("state")
 if state is not None:
  if not isinstance(state,dict) or type(state.get("generation")) is not int or state["generation"] != value["expectedExecutionGeneration"]+1 or state.get("attemptId",value["attemptId"]) != value["attemptId"]: raise ValueError("EXECUTION.SESSION_STATE_INVALID")
 return value

def load_session(path: Path) -> "ControllerSession":
 path=_safe_session_path(path,must_exist=True)
 try: value=_validate_session_payload(json.loads(path.read_bytes()))
 except json.JSONDecodeError as error: raise ValueError("EXECUTION.SESSION_JSON_INVALID") from error
 contract=load_contract(); secret=contract["executionControl"]["trustedController"]["privateKeySecretRef"]; key_text=os.environ.get(secret,"")
 if not key_text: raise RuntimeError(f"EXECUTION.CONTROLLER_SIGNING_KEY_REQUIRED: {secret}")
 private_key=Path(key_text).expanduser()
 if not private_key.is_absolute() or not private_key.is_file() or private_key.is_symlink() or private_key.stat().st_uid != os.getuid() or private_key.stat().st_mode & 0o077: raise ValueError("EXECUTION.CONTROLLER_KEY_INVALID")
 session=ControllerSession(SubprocessTransport(contract),contract,private_key,value["attemptId"],value["expectedExecutionGeneration"],value["expectedReleaseGeneration"]);session.state=value["state"];return session

def save_session(path: Path, session: "ControllerSession", placements: list[dict[str, Any]]) -> None:
 path=_safe_session_path(path,must_exist=path.exists())
 payload=_validate_session_payload({"schema":SESSION_SCHEMA,"attemptId":session.attempt_id,"expectedExecutionGeneration":session.expected_execution_generation,"expectedReleaseGeneration":session.expected_release_generation,"placements":placements,"state":session.state})
 if path.exists():
  current=_validate_session_payload(json.loads(path.read_bytes()))
  immutable=("attemptId","expectedExecutionGeneration","expectedReleaseGeneration","placements")
  if any(current[k]!=payload[k] for k in immutable): raise RuntimeError("EXECUTION.SESSION_IDENTITY_DRIFT")
  old=current.get("state");new=payload.get("state")
  if old is not None and new is not None and (old.get("generation")!=new.get("generation") or old.get("attemptId",payload["attemptId"])!=new.get("attemptId",payload["attemptId"])): raise RuntimeError("EXECUTION.SESSION_OWNER_DRIFT")
 raw=_canonical_bytes(payload)+b"\n"; temporary=path.parent/("."+path.name+"."+str(os.getpid()))
 fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,"wb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
  os.replace(temporary,path)
  directory=os.open(path.parent,os.O_RDONLY);os.fsync(directory);os.close(directory)
 finally:
  if temporary.exists():temporary.unlink()

@dataclass
class ControllerSession:
 transport:Transport; contract:dict[str,Any]; private_key:Path; attempt_id:str; expected_execution_generation:int; expected_release_generation:int
 state:dict[str,Any]|None=None
 def acquire(self)->dict[str,Any]:
  if self.state is not None:return self.state
  result=self.transport.authority('acquire',{'attemptId':self.attempt_id,'expectedExecutionGeneration':self.expected_execution_generation,'expectedReleaseGeneration':self.expected_release_generation})
  self.state=dict(result); return self.state
 def prepare_all(self,placements:list[dict[str,Any]])->None:
  for placement in sorted(placements,key=lambda x:(x['hostId'],x['plane'],x['instance'],x['replicaId'])): self.submit(placement,'guard-prepare',{},digest({'prepare':placement['id']}))
 def close_all(self,placements:list[dict[str,Any]])->None:
  for placement in reversed(sorted(placements,key=lambda x:(x['hostId'],x['plane'],x['instance'],x['replicaId']))): self.submit(placement,'guard-close',{},digest({'close':placement['id']}))
  self.close()
 def submit(self,placement:dict[str,Any],action:str,parameters:dict[str,Any],material_digest:str)->dict[str,Any]:
  state=self.acquire(); sequence=1+sum(1 for x in state.get('submitted',[]) if x['placementId']==placement['id'])
  request={'schema':'quwoquan.prod.execution-request.v1','controllerIdentity':self.contract['executionControl']['trustedController']['identity'],'controllerKeyId':self.contract['executionControl']['trustedController']['keyId'],'attemptId':self.attempt_id,'executionGeneration':state['generation'],'releaseGeneration':self.expected_release_generation,'inventoryDigest':state['inventoryDigest'],'placementId':placement['id'],'guardIncarnation':int(placement['guardIncarnation']),'sequence':sequence,'action':action,'parameters':parameters,'materialDigest':material_digest}
  registered=self.transport.authority('register',request); request_digest=registered['stepDigest']; envelope=sign_request(request,private_key=self.private_key); result=self.transport.plane(placement,envelope)
  if result.get('requestDigest')!=request_digest or not result.get('terminal'): raise RuntimeError('EXECUTION.PLANE_RESULT_INVALID')
  try:self.transport.authority('ack',result)
  except (OSError,RuntimeError):
   replay=self.transport.plane(placement,envelope)
   if replay!=result: raise RuntimeError('EXECUTION.LOST_ACK_READBACK_DRIFT')
   self.transport.authority('ack',replay)
  state.setdefault('submitted',[]).append({'placementId':placement['id'],'requestDigest':request_digest,'result':result})
  if action.startswith('prevalidate-') and (result.get('status') not in {'completed','reconciled'} or result.get('returnCode') != 0): raise RuntimeError('EXECUTION.PLANE_ACTION_FAILED')
  return result
 def bind_human_winner(self,winner:dict[str,Any],observation_digest:str)->None:
  state=self.acquire()
  if state.get('phase')!='observing' or state.get('observationDigest')!=observation_digest: raise RuntimeError('EXECUTION.OBSERVATION_RELEASED_OR_DRIFTED')
  winner_digest=digest(winner); result=self.transport.authority('consume',{'attemptId':self.attempt_id,'executionGeneration':state['generation'],'observationDigest':observation_digest,'winnerDigest':winner_digest}); self.state=dict(result)
 def activation_cas(self,placement:dict[str,Any],parameters:dict[str,Any],material_digest:str)->dict[str,Any]:
  if not self.state or self.state.get('phase')!='consumed': raise RuntimeError('EXECUTION.HUMAN_WINNER_NOT_CONTINUOUS')
  result=self.submit(placement,'ledger-activation-cas',parameters,material_digest);self.state['phase']='activating';return result
 def close(self)->dict[str,Any]:
  if self.state is None: raise RuntimeError('EXECUTION.NOT_ACQUIRED')
  result=self.transport.authority('close',{'attemptId':self.attempt_id,'executionGeneration':self.state['generation']});self.state=None;return result



def prevalidate_placements(plan: list[Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
 control=contract["executionControl"]; relative=str(control["guardRootRelative"])
 result=[]
 for item in sorted(plan,key=lambda x:(x.host_id,x.plane,x.instance,x.replica_id)):
  if item.instance!="prevalidate": raise ValueError("EXECUTION.PREVALIDATE_SCOPE_INVALID")
  result.append({"id":f"{item.host_id}-{item.plane}-prevalidate-{item.replica_id}","hostId":item.host_id,"plane":item.plane,"instance":"prevalidate","replicaId":item.replica_id,"guardIncarnation":1,"guardRoot":f"{item.compose_root.rstrip('/')}/{relative}","runtimeRoot":item.compose_root,"sshHost":item.ssh_host})
 if len(result)!=2 or {x["plane"] for x in result}!={"service","edge"} or len({x["hostId"] for x in result})!=1:
  raise ValueError("EXECUTION.PREVALIDATE_INVENTORY_INCOMPLETE")
 return result


def run_prevalidate_coordination(session: ControllerSession, placements: list[dict[str, Any]], staged: dict[str, dict[str, str]]) -> dict[str, Any]:
 """只协调不可提升 prevalidate；不消费 Human，不写 release ledger/receipt。"""
 prepared=[];started=[];reports={}
 ordered=sorted(placements,key=lambda x:(x["hostId"],x["plane"],x["instance"],x["replicaId"]))
 try:
  session.acquire()
  for placement in ordered:
   session.submit(placement,"guard-prepare",{},digest({"prepare":placement["id"]}));prepared.append(placement)
  for placement in ordered:
   material=staged[placement["plane"]]
   destination=f"instances/prevalidate/{placement['replicaId']}"
   session.submit(placement,"prevalidate-promote-runtime",{"sourceRelative":material["stagingRelative"],"destinationRelative":destination,"treeDigest":material["treeDigest"]},material["treeDigest"])
   unit=material["unitName"];source=f"{destination}/systemd/{unit}"
   session.submit(placement,"prevalidate-install-unit",{"sourceRelative":source,"unitName":unit,"sourceDigest":material["unitDigest"]},material["unitDigest"])
   session.submit(placement,"prevalidate-start",{"unitName":unit},material["treeDigest"]);started.append((placement,unit,material["treeDigest"]))
   reports[placement["plane"]]=session.submit(placement,"prevalidate-status",{"relativePath":destination},material["treeDigest"])
  session.close_all(ordered);prepared.clear()
  return {"status":"passed","nonPromotable":True,"planes":reports}
 except BaseException:
  for placement,unit,material_digest in reversed(started):
   try:session.submit(placement,"prevalidate-stop",{"unitName":unit},material_digest)
   except BaseException:pass
  if session.state is not None:
   for placement in reversed(prepared):
    try:session.submit(placement,"guard-close",{},digest({"close":placement["id"]}))
    except BaseException:pass
   try:session.close()
   except BaseException:pass
  raise

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=('step',));parser.add_argument('--session',required=True,type=Path);parser.add_argument('--placement',default='');parser.add_argument('--plane',default='');parser.add_argument('--host-id',default='');parser.add_argument('--instance',default='');parser.add_argument('--replica-id',default='');parser.add_argument('--effect',required=True);parser.add_argument('--parameters',required=True);parser.add_argument('--material-digest',required=True)
 args=parser.parse_args(); session=load_session(args.session); data=_validate_session_payload(json.loads(args.session.read_bytes())); placement=next((x for x in data['placements'] if (args.placement and x['id']==args.placement) or (not args.placement and x['plane']==args.plane and x['hostId']==args.host_id and x['instance']==args.instance and x['replicaId']==args.replica_id)),None)
 if placement is None: raise SystemExit('EXECUTION.UNKNOWN_PLACEMENT')
 result=session.submit(placement,args.effect,json.loads(args.parameters),args.material_digest);save_session(args.session,session,data['placements']);print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
