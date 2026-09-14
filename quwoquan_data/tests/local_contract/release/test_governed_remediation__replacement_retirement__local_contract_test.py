# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#req-001
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-003
from pathlib import Path
import pytest
from content.release.canonical.governed_remediation import make_article_disposition
from core.semantic_quality_gates import digest, write_human_decision, SemanticGateError

P={"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0"}
T={"contentRevision":1,"sourceRevision":1,"layoutRevision":1}

def test_decision_input_drift_is_rejected(tmp_path: Path):
    issue={"issueId":"i","objectRef":"posts/article/x","sourceDigest":"sha256:"+"1"*64,"targetDigest":"sha256:"+"2"*64,"detectedType":"ARTICLE.CARRIER_DEVIATION","proposedMapping":None,"lossFields":[],"severity":"critical","actor":{"actorId":"author","actorType":"producer"},"reason":"wrong article","policyVersion":"1.0.0","reviewStatus":"human_decision_pending","outcome":"requires_human_decision","processingDisposition":"blocked_unsafe","protocol":P,"objectRevision":T}
    decision={"schema":"quwoquan_data.semantic_human_decision","decisionId":"d","issueId":"i","inputDigest":"sha256:"+"0"*64,"decision":"abandon_object","actor":{"actorId":"cursor_user_authorized_operator","actorType":"human_operator"},"reason":"retire","inputProtocol":P,"inputObjectRevision":T,"resultProtocol":P,"resultObjectRevision":T}
    with pytest.raises(SemanticGateError,match="INPUT_DRIFT"): write_human_decision(tmp_path/"decision.json",decision,issue)
    assert not (tmp_path/"decision.json").exists()

def test_abandon_tuple_is_identical_and_create_once(tmp_path: Path):
    issue={"issueId":"i","objectRef":"posts/article/x","sourceDigest":"sha256:"+"1"*64,"targetDigest":"sha256:"+"2"*64,"detectedType":"ARTICLE.CARRIER_DEVIATION","proposedMapping":None,"lossFields":[],"severity":"critical","actor":{"actorId":"author","actorType":"producer"},"reason":"wrong article","policyVersion":"1.0.0","reviewStatus":"human_decision_pending","outcome":"requires_human_decision","processingDisposition":"blocked_unsafe","protocol":P,"objectRevision":T}
    decision={"schema":"quwoquan_data.semantic_human_decision","decisionId":"d","issueId":"i","inputDigest":digest(issue),"decision":"abandon_object","actor":{"actorId":"cursor_user_authorized_operator","actorType":"human_operator"},"reason":"retire","inputProtocol":P,"inputObjectRevision":T,"resultProtocol":P,"resultObjectRevision":T}
    assert write_human_decision(tmp_path/"decision.json",decision,issue)=="created"
    assert write_human_decision(tmp_path/"decision.json",decision,issue)=="replayed"
