# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#req-005
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-007
from __future__ import annotations
import json
from pathlib import Path
import pytest
from core.semantic_quality_gates import SemanticGateError, compare_fidelity, digest, dispositions_from_document, evaluate_batch, write_human_decision
from generated.semantic_document import CAPABILITY_IDS

D="sha256:"+"1"*64
P={"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0"}
T={"contentRevision":1,"sourceRevision":1,"layoutRevision":1}
A={"actorId":"producer-1","actorType":"producer"}

def envelope(disposition="preserved", *, schema="1.0.0"):
 return {"schemaVersion":schema,"dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0","offsetEncoding":"unicode_scalar_value","nodes":[{"nodeId":"n1","kind":"paragraph","disposition":disposition,"policyVersion":"1.0.0","requiredCapabilities":["parse.markdown","parse.html","serialize.markdown","render.app","render.web","render.workbench","author.editContent"],"losses":[],"semanticFingerprint":D,"sourceAnchor":{"origin":"source","start":0,"end":1,"selector":"p1"}}],"requiredCapabilities":sorted(CAPABILITY_IDS),"assets":{},"sourceMap":{"n1":{"origin":"source","start":0,"end":1,"selector":"p1"}},"policyVersion":"1.0.0","losses":[],"semanticFingerprint":D,"canonicalDigest":D}

def rows(doc): return dispositions_from_document(envelope=doc,object_ref="entities/x",object_revision=T,source_digest=D,target_digest=D,actor=A,policy_version="1.0.0",available_capabilities=CAPABILITY_IDS)

def test_three_dispositions_and_compatibility_fail_closed():
 assert rows(envelope())[0]["outcome"]=="auto_continue"
 assert rows(envelope("degraded"))[0]["outcome"]=="requires_human_decision"
 bad=envelope("blocked_unsafe"); assert rows(bad)[0]["outcome"]=="definitive_reject"
 for field,value,code in [("schemaVersion","2.0.0","SCHEMA_MAJOR"),("dialectVersion","2.0.0","DIALECT_MAJOR"),("canonicalizationVersion","2.0.0","CANONICALIZATION")]:
  doc=envelope();doc[field]=value;assert code in rows(doc)[0]["detectedType"]
 doc=envelope();doc["requiredCapabilities"].append("render.quantum");assert rows(doc)[0]["detectedType"]=="SEMANTIC_DOCUMENT.CAPABILITY.MISSING"
 partial=dispositions_from_document(envelope=envelope(),object_ref="entities/x",object_revision=T,source_digest=D,target_digest=D,actor=A,policy_version="1.0.0",available_capabilities=CAPABILITY_IDS,semantic_parse_coverage="partial")
 assert partial[0]["detectedType"]=="SEMANTIC_DOCUMENT.PARSE_PARTIAL" and partial[0]["outcome"]=="definitive_reject"
 mismatch=dispositions_from_document(envelope=envelope(),object_ref="entities/x",object_revision=T,source_digest=D,target_digest=D,actor=A,policy_version="1.0.0",available_capabilities=CAPABILITY_IDS,expected_canonical_digest="sha256:"+"9"*64)
 assert mismatch[0]["detectedType"]=="SEMANTIC_DOCUMENT.CANONICAL_DIGEST_MISMATCH"

def test_human_decision_create_once_replay_drift_and_new_tuple(tmp_path:Path):
 issue=rows(envelope("degraded"))[0]
 decision={"schema":"quwoquan_data.semantic_human_decision","decisionId":"d1","issueId":issue["issueId"],"inputDigest":digest(issue),"decision":"revise_content","actor":{"actorId":"human-1","actorType":"human_operator"},"reason":"修正文意","inputProtocol":P,"inputObjectRevision":T,"resultProtocol":P,"resultObjectRevision":{"contentRevision":2,"sourceRevision":1,"layoutRevision":1}}
 path=tmp_path/"decision.json";assert write_human_decision(path,decision,issue)=="created";before=path.read_bytes();assert write_human_decision(path,decision,issue)=="replayed";assert path.read_bytes()==before
 drift={**decision,"reason":"另一理由"}
 with pytest.raises(SemanticGateError,match="CREATE_ONCE_CONFLICT"):write_human_decision(path,drift,issue)
 old={**decision,"decisionId":"d2","resultObjectRevision":T}
 with pytest.raises(SemanticGateError,match="NEW_TUPLE_REQUIRED"):write_human_decision(tmp_path/"old.json",old,issue)
 reject=rows(envelope("blocked_unsafe"))[0]
 with pytest.raises(SemanticGateError,match="cannot override"):write_human_decision(tmp_path/"reject.json",{**decision,"issueId":reject["issueId"],"inputDigest":digest(reject)},reject)

def test_fidelity_carrier_and_viewport_layout_revision():
 source={"title":"t","headingTree":[1,2],"paragraphOrder":["a","b"],"links":["u"],"nestedLists":[["x"]],"tableLogicalGrid":[["c"]],"footnoteGraph":{"r":"d"},"mediaCaptionOrder":[["m","c"]]}
 assert compare_fidelity(carrier="homepage",source=source,target=dict(source))==[]
 for field in source:
  target=dict(source);target[field]="drift";assert len(compare_fidelity(carrier="homepage",source=source,target=target))==1
 assert compare_fidelity(carrier="article",source={},target={"writingIntent":"decision_experience","publishAngle":"route","encyclopediaFaithfulCopy":False})==[]
 assert "ARTICLE.ENCYCLOPEDIA_COPY" in compare_fidelity(carrier="article",source={},target={"writingIntent":"x","publishAngle":"x","encyclopediaFaithfulCopy":True})
 assert compare_fidelity(carrier="image",source={},target={"carrier":"video"})==["CARRIER.MISMATCH"]
 desktop={"layoutRevision":3,"nodes":["a","b"],"order":["a","b"]};mobile={**desktop,"viewport":"mobile"};assert mobile["layoutRevision"]==desktop["layoutRevision"] and mobile["nodes"]==desktop["nodes"] and mobile["order"]==desktop["order"]

def test_five_batch_anomalies_normal_and_required_policy():
 policy={"approvedRateRejectAtOrAbove":1,"singleSourceRateRejectAtOrAbove":1,"mediaShortfallRateRejectAtOrAbove":1,"singleScoreRateRejectAtOrAbove":1,"headingTemplateRateRejectAtOrAbove":1,"minimumBatchSize":3}
 base=[{"approved":False,"sourceId":str(i),"hasMedia":True,"score":i,"headingTemplate":str(i)} for i in range(3)]
 assert evaluate_batch(batch_id="normal",objects=base,policy=policy,policy_version="1.0.0")["verdict"]=="approved"
 mutations=[("approved",True),("sourceId","one"),("hasMedia",False),("score",5),("headingTemplate","same")]
 for field,value in mutations:
  objects=[{**row,field:value,"modelBatch":"grok"} for row in base];result=evaluate_batch(batch_id=field,objects=objects,policy=policy,policy_version="1.0.0");assert result["verdict"]=="rejected" and len(result["issues"])==1
 with pytest.raises(SemanticGateError,match="MISSING_REQUIRED_CONFIG"):evaluate_batch(batch_id="x",objects=base,policy={},policy_version="1.0.0")
