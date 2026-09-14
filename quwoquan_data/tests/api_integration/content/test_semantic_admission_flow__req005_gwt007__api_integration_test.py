# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#req-005
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-007
from __future__ import annotations
import pytest
from core.semantic_quality_gates import SemanticGateError, assert_review_admissible

P={"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0"}
T={"contentRevision":2,"sourceRevision":1,"layoutRevision":1}

def review(outcome="auto_continue", protocol=P, revision=T):
 disposition={"issueId":"i","objectRef":"entities/x","sourceAnchor":{"origin":"source","start":0,"end":1,"selector":"p"},"sourceDigest":"sha256:"+"1"*64,"targetDigest":"sha256:"+"2"*64,"detectedType":"SEMANTIC_EXACT","proposedMapping":None,"lossFields":[],"severity":"info","actor":{"actorId":"reviewer","actorType":"independent_reviewer"},"reason":"reviewed exact revision","policyVersion":"1.0.0","reviewStatus":"reviewed_confirmed","outcome":outcome,"processingDisposition":"preserved" if outcome=="auto_continue" else "degraded","protocol":protocol,"objectRevision":revision}
 return {"decision":"approved","protocol":protocol,"objectRevision":revision,"dispositions":[disposition]}

def test_new_tuple_requires_new_independent_review_and_pending_is_blocked():
 assert_review_admissible(review())
 with pytest.raises(SemanticGateError,match="BLOCKING_DISPOSITION"): assert_review_admissible(review("requires_human_decision"))
 drift=review();drift["dispositions"][0]["objectRevision"]={"contentRevision":1,"sourceRevision":1,"layoutRevision":1}
 with pytest.raises(SemanticGateError,match="BINDING_DRIFT"): assert_review_admissible(drift)

def test_versions_and_capabilities_cannot_be_human_overridden():
 for protocol in [{**P,"schemaVersion":"2.0.0"},{**P,"dialectVersion":"2.0.0"},{**P,"canonicalizationVersion":"2.0.0"}]:
  with pytest.raises(SemanticGateError,match="INCOMPATIBLE"): assert_review_admissible(review(protocol=protocol))

def test_workbench_offline_authority_shape_cannot_enter_canonical_admission():
 suggestion={"authority":"offline_suggestion","root":"quwoquan_data/control_plane/content_workbench/portal","decision":"approved"}
 with pytest.raises(SemanticGateError,match="BINDING_MISSING"): assert_review_admissible(suggestion)
