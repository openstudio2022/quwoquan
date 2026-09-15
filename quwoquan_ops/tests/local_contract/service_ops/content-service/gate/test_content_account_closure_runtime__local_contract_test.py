# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
from datetime import datetime, timezone
import hashlib, hmac, json
from pathlib import Path
from uuid import UUID
import pytest

from quwoquan_ops.cli.lib.content_account_closure_runtime import ContentAccountClosureRuntimeError, ContentAccountClosureTarget, COLLECTIONS, verify_content_account_closure_current
from quwoquan_ops.cli.lib.generated.content_account_closure_runtime import *

class Binary(bytes): subtype=4
class Timestamp:
 def __init__(self,time=7,inc=1): self.time,self.inc=time,inc
class Mongo:
 name='quwoquan_content'
 def __init__(self): self.missing=None; self.rows={n:[] for n in COLLECTIONS}
 def command(self,c):
  if 'listCollections' in c:
   return {'cursor':{'firstBatch':[{'name':n,'info':{'uuid':Binary(UUID(int=i+1).bytes)}} for i,n in enumerate(COLLECTIONS) if n!=self.missing]}}
  n=c.get('aggregate'); return {'cursor':{'firstBatch':self.rows[n]},'operationTime':Timestamp()}
class Receipt:
 sourceResourceRef='redis'; sourceNamespace='0'; sourceManagedAllocationBindingId='sha256:'+'3'*64; producerBindingDigest='sha256:'+'4'*64

def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()
def digest(v): return 'sha256:'+hashlib.sha256(v).hexdigest()
def fixture(tmp_path):
 root=(tmp_path/'closure').absolute(); root.mkdir(mode=0o700); key=b'k'*32; (root/'subject.key').write_bytes(key); (root/'subject.key').chmod(0o600)
 mongo=Mongo(); rows=[]
 for i,n in enumerate(COLLECTIONS): rows.append({'collection':n,'physicalInstanceId':'mongodb-collection-uuid:'+UUID(int=i+1).bytes.hex(),'recordCount':0,'canonicalDigest':digest(b'[]')})
 src_ref=ContentAccountClosureRuntimeEvidenceRef(ref='source-creation.json',digest='sha256:'+'5'*64)
 partition=ContentAccountClosureRuntimeSourcePartition(partition='events.user.account',firstAvailablePosition='0-0',frozenThrough='0-0',deliveredThrough='0-0',appliedThrough='0-0',pendingCount=0,entryCount=0,canonicalDigest=digest(b'[]'))
 source=ContentAccountClosureRuntimeSource(mode='new_source',resourceRef='redis',namespace='0',managedAllocationBindingId='sha256:'+'3'*64,stream='events.user.account',consumerGroup='content-service-user-account-closed',producerBindingDigest='sha256:'+'4'*64,sourceCreation=src_ref,recovery=None,partitions=[partition])
 value=ContentAccountClosureRuntimeEvidence(environment='gamma',target='gamma-local',candidateDigest='sha256:'+'a'*64,dataPlaneBindingDigest='sha256:'+'b'*64,resourceRef='mongo',namespace=mongo.name,allocationAttemptId='attempt',runtimeGeneration='generation',subjectHmacKeyIdentity='sha256:'+hashlib.sha256(hmac.digest(key,b'quwoquan/content.account-closure/runtime/key-identity','sha256')).hexdigest(),source=source,collections=rows,recordCount=0,canonicalDigest=digest(canonical(rows)),initializedAt=datetime.now(timezone.utc))
 raw=canonical(value.model_dump(mode='json')); path=root/'content-account-closure-runtime.json'; path.write_bytes(raw); path.chmod(0o600)
 evidence=ContentAccountClosureRuntimeEvidenceRef(ref=path.name,digest=digest(raw)); target=ContentAccountClosureTarget('gamma','gamma-local','sha256:'+'a'*64,'sha256:'+'b'*64,'mongo',mongo.name,'attempt','generation')
 return root,mongo,evidence,target

def call(root,mongo,evidence,target,verifier=lambda **k:Receipt()):
 return verify_content_account_closure_current(expected=target,evidence=evidence,material_root=root,database=mongo,subject_key_ref='subject.key',source_expected=object(),source_binding={},source_material_root=root,pg_admin=None,redis_admin=None,old_pg_dsn='',old_redis=None,source_verifier=verifier)

def test_verifies_exact_nine_collection_source_and_key_current(tmp_path): assert call(*fixture(tmp_path)).recordCount==0
@pytest.mark.parametrize('drift', ['missing','uuid','row','key','source'])
def test_rejects_collection_rebuild_key_and_source_drift(tmp_path,drift):
 root,mongo,evidence,target=fixture(tmp_path)
 if drift=='missing': mongo.missing=COLLECTIONS[0]
 elif drift=='uuid':
  raw=json.loads((root/evidence.ref).read_text()); raw['collections'][0]['physicalInstanceId']='mongodb-collection-uuid:'+'f'*32; b=canonical(raw); (root/evidence.ref).write_bytes(b); evidence=ContentAccountClosureRuntimeEvidenceRef(ref=evidence.ref,digest=digest(b))
 elif drift=='row': mongo.rows[COLLECTIONS[0]]=[{'_id':'changed'}]
 elif drift=='key': (root/'subject.key').write_bytes(b'x'*32)
 with pytest.raises(ContentAccountClosureRuntimeError): call(root,mongo,evidence,target, (lambda **k: (_ for _ in ()).throw(RuntimeError('source drift'))) if drift=='source' else (lambda **k:Receipt()))
