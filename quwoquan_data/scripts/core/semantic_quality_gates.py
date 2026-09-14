"""REQ-005/GWT-007 semantic disposition、人工决定与批次硬门。"""
from __future__ import annotations
import hashlib, json, os
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence
from generated.semantic_document import (CANONICALIZATION_VERSION, DIALECT_VERSION, SCHEMA_VERSION, ProcessingDisposition, ValidationCode, validate_envelope)
from core.schema import assert_valid

class SemanticGateError(ValueError): pass

def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
def digest(value: object) -> str: return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
def _major(v: str) -> str: return v.split(".",1)[0]

def validate_protocol(protocol: Mapping[str, str]) -> None:
    if _major(str(protocol.get("schemaVersion", ""))) != _major(SCHEMA_VERSION): raise SemanticGateError("SEMANTIC_DOCUMENT.INCOMPATIBLE.SCHEMA_MAJOR")
    if _major(str(protocol.get("dialectVersion", ""))) != _major(DIALECT_VERSION): raise SemanticGateError("SEMANTIC_DOCUMENT.INCOMPATIBLE.DIALECT_MAJOR")
    if protocol.get("canonicalizationVersion") != CANONICALIZATION_VERSION: raise SemanticGateError("SEMANTIC_DOCUMENT.INCOMPATIBLE.CANONICALIZATION_VERSION")

def dispositions_from_document(*, envelope: Mapping[str, Any], object_ref: str, object_revision: Mapping[str,int], source_digest: str, target_digest: str, actor: Mapping[str,str], policy_version: str, available_capabilities: frozenset[str], capture_coverage: str = "complete", semantic_parse_coverage: str = "complete", expected_canonical_digest: str | None = None, expected_semantic_fingerprint: str | None = None) -> list[dict[str,Any]]:
    protocol={k:str(envelope.get(k,"")) for k in ("schemaVersion","dialectVersion","canonicalizationVersion")}
    result=validate_envelope(envelope, available_capabilities)
    rows=[]
    def add(code:str,outcome:str,processing:str,reason:str,node:Mapping[str,Any]|None=None,loss_fields:Sequence[str]=()):
        anchor=(node or {}).get("sourceAnchor") or {"origin":"document","start":0,"end":0,"selector":"document"}
        row={"issueId":digest({"objectRef":object_ref,"code":code,"nodeId":(node or {}).get("nodeId"),"protocol":protocol,"objectRevision":object_revision}),"objectRef":object_ref,"sourceAnchor":anchor,"sourceDigest":source_digest,"targetDigest":target_digest,"detectedType":code,"proposedMapping":None,"lossFields":list(loss_fields),"severity":"error" if outcome!="auto_continue" else "info","actor":dict(actor),"reason":reason,"policyVersion":policy_version,"reviewStatus":"human_decision_pending" if outcome=="requires_human_decision" else "not_reviewed","outcome":outcome,"processingDisposition":processing,"protocol":protocol,"objectRevision":dict(object_revision)}
        if (node or {}).get("nodeId"): row["nodeId"]=node["nodeId"]
        assert_valid(row,"content","semantic_disposition",label="semantic disposition")
        rows.append(row)
    if result.code != ValidationCode.OK:
        add(result.code.value,"definitive_reject",ProcessingDisposition.BLOCKED_UNSAFE.value,result.detail or result.code.value)
        return rows
    hard_mismatches = []
    if capture_coverage != "complete": hard_mismatches.append("SEMANTIC_DOCUMENT.CAPTURE_PARTIAL")
    if semantic_parse_coverage != "complete": hard_mismatches.append("SEMANTIC_DOCUMENT.PARSE_PARTIAL")
    if expected_canonical_digest is not None and envelope.get("canonicalDigest") != expected_canonical_digest: hard_mismatches.append("SEMANTIC_DOCUMENT.CANONICAL_DIGEST_MISMATCH")
    if expected_semantic_fingerprint is not None and envelope.get("semanticFingerprint") != expected_semantic_fingerprint: hard_mismatches.append("SEMANTIC_DOCUMENT.FINGERPRINT_MISMATCH")
    for code in hard_mismatches: add(code,"definitive_reject",ProcessingDisposition.BLOCKED_UNSAFE.value,code)
    if hard_mismatches: return rows
    for loss in envelope.get("losses") or []: add(str(loss.get("code") or "SEMANTIC_LOSS"),"requires_human_decision",ProcessingDisposition.DEGRADED.value,str(loss.get("detailKey") or "semantic loss"),loss,loss.keys())
    for node in envelope.get("nodes") or []:
        disposition=str(node.get("disposition") or "")
        if disposition in {ProcessingDisposition.DEGRADED.value,ProcessingDisposition.UNSUPPORTED_OPAQUE.value}: add("SEMANTIC_NODE_UNRESOLVED","requires_human_decision",disposition,"unresolved node disposition",node,["disposition"])
        elif disposition==ProcessingDisposition.BLOCKED_UNSAFE.value: add("SEMANTIC_NODE_BLOCKED","definitive_reject",disposition,"unsafe node",node,["disposition"])
        for diagnostic in node.get("diagnostics") or []:
            code=str(diagnostic.get("code") or "SEMANTIC_DOCUMENT.DIAGNOSTIC")
            diagnostic_disposition=str(diagnostic.get("disposition") or disposition)
            outcome="definitive_reject" if diagnostic.get("severity") == "error" or diagnostic_disposition == ProcessingDisposition.BLOCKED_UNSAFE.value else "requires_human_decision"
            add(code,outcome,diagnostic_disposition,str(diagnostic.get("messageKey") or code),node,["diagnostics"])
    if not rows: add("SEMANTIC_EXACT","auto_continue",ProcessingDisposition.PRESERVED.value,"no semantic loss")
    return rows


def compare_fidelity(*, carrier: str, source: Mapping[str, Any], target: Mapping[str, Any]) -> list[str]:
    """对来源语义证据与目标做机械关系对账；只允许调用方先完成的 contract normalization。"""
    homepage_fields = {
        "title": "HOMEPAGE_FIDELITY.TITLE",
        "headingTree": "HOMEPAGE_FIDELITY.HEADING_TREE",
        "paragraphOrder": "HOMEPAGE_FIDELITY.PARAGRAPH_ORDER",
        "links": "HOMEPAGE_FIDELITY.LINKS",
        "nestedLists": "HOMEPAGE_FIDELITY.NESTED_LISTS",
        "tableLogicalGrid": "HOMEPAGE_FIDELITY.TABLE_LOGICAL_GRID",
        "footnoteGraph": "HOMEPAGE_FIDELITY.FOOTNOTE_GRAPH",
        "mediaCaptionOrder": "HOMEPAGE_FIDELITY.MEDIA_CAPTION_ORDER",
    }
    if carrier == "homepage":
        return [code for field, code in homepage_fields.items() if source.get(field) != target.get(field)]
    if carrier == "article":
        issues=[]
        if not str(target.get("writingIntent") or "").strip(): issues.append("ARTICLE.WRITING_INTENT_MISSING")
        if not str(target.get("publishAngle") or "").strip(): issues.append("ARTICLE.PUBLISH_ANGLE_MISSING")
        if target.get("encyclopediaFaithfulCopy") is not False: issues.append("ARTICLE.ENCYCLOPEDIA_COPY")
        return issues
    expected={"image":"image","video":"video"}.get(carrier)
    return [] if expected is None or target.get("carrier")==expected else ["CARRIER.MISMATCH"]

def write_human_decision(path: Path, decision: Mapping[str,Any], issue: Mapping[str,Any]) -> str:
    assert_valid(dict(decision),"content","semantic_human_decision",label="human decision")
    if issue.get("outcome") != "requires_human_decision": raise SemanticGateError("human decision cannot override non-decision disposition")
    if decision.get("issueId") != issue.get("issueId") or decision.get("inputProtocol") != issue.get("protocol") or decision.get("inputObjectRevision") != issue.get("objectRevision") or decision.get("inputDigest") != digest(issue): raise SemanticGateError("SEMANTIC_DECISION.INPUT_DRIFT")
    if decision.get("decision") != "abandon_object":
        old=issue["objectRevision"]; new=decision.get("resultObjectRevision") or {}
        if not any(int(new.get(k,0)) > int(old[k]) for k in old) or any(int(new.get(k,0)) < int(old[k]) for k in old): raise SemanticGateError("SEMANTIC_DECISION.NEW_TUPLE_REQUIRED")
        validate_protocol(decision.get("resultProtocol") or decision["inputProtocol"])
    data=canonical_bytes(decision); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()==data:return "replayed"
        raise SemanticGateError("SEMANTIC_DECISION.CREATE_ONCE_CONFLICT")
    tmp=path.with_name(f".{path.name}.{os.getpid()}.tmp");tmp.write_bytes(data);os.replace(tmp,path);return "created"

def assert_review_admissible(review: Mapping[str,Any]) -> None:
    protocol=review.get("protocol"); revision=review.get("objectRevision"); dispositions=review.get("dispositions")
    if not isinstance(protocol,Mapping) or not isinstance(revision,Mapping) or not isinstance(dispositions,list): raise SemanticGateError("SEMANTIC_REVIEW.BINDING_MISSING")
    validate_protocol(protocol)
    if any(row.get("protocol")!=protocol or row.get("objectRevision")!=revision for row in dispositions): raise SemanticGateError("SEMANTIC_REVIEW.BINDING_DRIFT")
    if any(row.get("outcome")!="auto_continue" for row in dispositions): raise SemanticGateError("SEMANTIC_REVIEW.BLOCKING_DISPOSITION")
    if review.get("decision")!="approved": raise SemanticGateError("SEMANTIC_REVIEW.NOT_APPROVED")

def evaluate_batch(*,batch_id:str,objects:Sequence[Mapping[str,Any]],policy:Mapping[str,Any],policy_version:str)->dict[str,Any]:
    required=("approvedRateRejectAtOrAbove","singleSourceRateRejectAtOrAbove","mediaShortfallRateRejectAtOrAbove","singleScoreRateRejectAtOrAbove","headingTemplateRateRejectAtOrAbove","minimumBatchSize")
    if any(k not in policy for k in required): raise SemanticGateError("BATCH_QUALITY_POLICY.MISSING_REQUIRED_CONFIG")
    if len(objects)<int(policy["minimumBatchSize"]): raise SemanticGateError("BATCH_QUALITY_POLICY.INSUFFICIENT_BATCH")
    n=len(objects); rates={
      "BATCH.ALL_APPROVED":sum(o.get("approved") is True for o in objects)/n,
      "BATCH.SINGLE_SOURCE":max(Counter(str(o.get("sourceId")) for o in objects).values())/n,
      "BATCH.MEDIA_SHORTFALL":sum(not o.get("hasMedia",False) for o in objects)/n,
      "BATCH.SINGLE_SCORE":max(Counter(str(o.get("score")) for o in objects).values())/n,
      "BATCH.HEADING_TEMPLATE_HOMOGENEITY":max(Counter(str(o.get("headingTemplate")) for o in objects).values())/n}
    thresholds=dict(zip(rates, [policy[k] for k in required[:5]])); issues=[]
    for code,rate in rates.items():
      if rate>=float(thresholds[code]):
       issue={"code":code,"severity":"reject","observedRate":rate,"threshold":thresholds[code]}
       batches={str(o.get("modelBatch") or "") for o in objects}
       if len(batches)==1 and "" not in batches: issue["modelBatch"]=next(iter(batches))
       issues.append(issue)
    result={"schema":"quwoquan_data.batch_quality_gate","policyVersion":policy_version,"policy":dict(policy),"batchId":batch_id,"verdict":"rejected" if issues else "approved","issues":issues};assert_valid(result,"release","batch_quality_gate");return result
