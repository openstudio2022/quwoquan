# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md
"""只从真实 content_fidelity_audit.v1 最终 typed issue 生成隔离请求。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
sys.path.insert(0, str(SCRIPTS))
from governance.content_remediation import ContentRemediationError, generate_remediation_requests

D = "sha256:" + "a" * 64
ISSUE_CODES = ("carrier_mismatch", "source_incomplete", "semantic_fidelity_loss", "table_or_reference_loss",
               "media_loss", "article_no_independent_intent", "review_false_positive", "rights_gap")


def put(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def ratio(n=0, d=0):
    return {"numerator": n, "denominator": d, "rate": None if not d else n / d}


def object_row(ref: str, version=1, codes=None):
    return {"objectRef": ref, "carrier": "article", "identity": {"objectId": ref, "version": version, "sourceIdentity": {}},
            "digests": dict.fromkeys(("object", "version", "payload", "source", "review"), D), "sources": [],
            "coverage": {}, "compression": {}, "format": {}, "generation": {}, "reviewGate": {}, "features": {},
            "intentEvidence": {}, "issueCodes": list(codes or [])}


def audit_document(*, second_version=3):
    issues = [
        {"objectRef": "posts/article/example/2", "code": "source_incomplete", "severity": "high", "detail": "来源证据闭包不完整", "facts": {"missing": ["source"]}},
        {"objectRef": "posts/article/example/2", "code": "table_or_reference_loss", "severity": "medium", "detail": "引用未保留", "facts": {"sourceHasReference": True}},
        {"objectRef": "posts/article/example/1", "code": "rights_gap", "severity": "low", "detail": "权利事实缺失", "facts": {"missing": ["rights"]}},
    ]
    objects = [object_row("posts/article/example/2", 0, ["source_incomplete", "table_or_reference_loss"]),
               object_row("posts/article/example/1", second_version, ["rights_gap"])]
    core = {"schema": "quwoquan_data.content_fidelity_audit.v2", "purpose": "offline_read_only_mechanical_baseline",
            "reviewDisclaimer": "scanner_generated_queue_only_semantic_review_not_completed",
            "scanPolicy": {"baselineDigestScope": "canonical_manifest_without_baselineDigest"},
            "manifestInventory": [],
            "reviewScope": {"grokArticleRefs": [], "highRiskHomepageRefs": [], "strata": []},
            "counts": {"objects": 2, "issues": 3, "mechanicalFindings": 0, "semanticReviewQueue": 0,
                       "byCarrier": {"article": 2}, "byIssue": {code: sum(i["code"] == code for i in issues) for code in ISSUE_CODES}, "byReviewReason": {}},
            "metrics": {code: ratio(sum(i["code"] == code for i in issues), 2) for code in ISSUE_CODES},
            "riskLayers": {level: sorted({i["objectRef"] for i in issues if i["severity"] == level}) for level in ("high", "medium", "low")},
            "duplicates": {"snapshotOrExcerpt": [], "homepageArticleSameEntity": []}, "mechanicalFindings": [],
            "semanticReviewQueue": [], "issues": issues, "objects": objects}
    canonical = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {**core, "baselineDigest": "sha256:" + hashlib.sha256(canonical).hexdigest()}


def audit(tmp_path: Path, **kwargs) -> Path:
    document = audit_document(**kwargs)
    schema = json.loads((ROOT / "quwoquan_data/schema/governance/content_fidelity_audit.schema.json").read_text())
    Draft202012Validator(schema).validate(document)
    return put(tmp_path / "audit/fidelity.json", document)


def load_schemas():
    base = ROOT / "quwoquan_data/schema/governance"
    return [json.loads((base / name).read_text()) for name in
            ("content_remediation_request.schema.json", "content_remediation_result.schema.json")]


def test_real_v1_fixture_joins_top_level_issues_and_identity_version(tmp_path):
    manifest, output = audit(tmp_path), tmp_path / "independent-output"
    result = generate_remediation_requests(audit_manifest=manifest, output_root=output)
    request_schema, result_schema = load_schemas()
    Draft202012Validator(result_schema).validate(result)
    requests = [json.loads((output / row["requestRef"]).read_text()) for row in result["requests"]]
    assert [r["original"]["objectRef"] for r in requests] == ["posts/article/example/1", "posts/article/example/2"]
    assert [r["targetVersion"] for r in requests] == [4, 1]
    assert all(set(r["original"]["digests"]) == {"object", "version", "payload", "source", "review"} for r in requests)
    for request in requests:
        Draft202012Validator(request_schema).validate(request)
        assert request["audit"]["baselineDigest"] == result["audit"]["baselineDigest"]
        assert request["requirements"] == {"sourceRevisionReacquire": "required", "mappingGate": "required", "independentReviewGate": "required", "canonicalPublishAllowed": False}
        assert "author" not in request and "reviewer" not in request
        assert request["retireCandidate"]["executionAllowed"] is False
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert generate_remediation_requests(audit_manifest=manifest, output_root=output)["status"] == "same_replay"
    assert before == {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}


def test_real_severity_and_issue_batching(tmp_path):
    result = generate_remediation_requests(audit_manifest=audit(tmp_path), output_root=tmp_path / "out",
        issue_codes=["source_incomplete", "table_or_reference_loss"], severities=["medium"])
    assert result["counts"] == {"auditedObjects": 2, "selectedObjects": 1, "selectedIssues": 1, "semanticReviewPendingObjects": 0}
    request = json.loads((tmp_path / "out" / result["requests"][0]["requestRef"]).read_text())
    assert request["issueCodes"] == ["table_or_reference_loss"] and request["issueSeverities"] == ["medium"]
    assert request["retireCandidate"] == {"suggested": False, "executionAllowed": False, "reasonIssueCodes": []}


def test_baseline_digest_is_recomputed_not_replaced_by_file_digest(tmp_path):
    manifest = audit(tmp_path)
    document = json.loads(manifest.read_text()); document["baselineDigest"] = D; put(manifest, document)
    with pytest.raises(ContentRemediationError, match="BASELINE_DIGEST_DRIFT"):
        generate_remediation_requests(audit_manifest=manifest, output_root=tmp_path / "out")


def test_semantic_review_queue_is_not_typed_issue(tmp_path):
    document = audit_document()
    document["semanticReviewQueue"] = [{"reasons": ["intent_contract_missing"], "objectRef": "posts/article/example/1",
                                         "status": "semantic_review_required", "signals": {}}]
    document["counts"]["semanticReviewQueue"] = 1
    document["counts"]["byReviewReason"] = {"intent_contract_missing": 1}
    core = {k: v for k, v in document.items() if k != "baselineDigest"}
    document["baselineDigest"] = "sha256:" + hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = put(tmp_path / "audit/queue.json", document)
    result = generate_remediation_requests(audit_manifest=path, output_root=tmp_path / "out")
    assert result["counts"]["semanticReviewPendingObjects"] == 1
    # queue 自身不生成 issue/request；该对象已有独立最终 rights_gap，所以仍有对应 request。
    assert result["counts"]["selectedIssues"] == 3


def test_join_drift_and_non_integer_target_version_fail_closed(tmp_path):
    document = audit_document(); document["objects"][0]["issueCodes"] = ["source_incomplete"]
    core = {k: v for k, v in document.items() if k != "baselineDigest"}
    document["baselineDigest"] = "sha256:" + hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path = put(tmp_path / "audit/drift.json", document)
    with pytest.raises(ContentRemediationError, match="ISSUE_JOIN_DRIFT"):
        generate_remediation_requests(audit_manifest=path, output_root=tmp_path / "out")
    with pytest.raises(ContentRemediationError, match="TARGET_VERSION_NOT_INTEGER"):
        generate_remediation_requests(audit_manifest=audit(tmp_path / "other", second_version="R0"), output_root=tmp_path / "out2")


def test_different_replay_conflicts_and_output_is_independent(tmp_path):
    manifest, output = audit(tmp_path), tmp_path / "out"
    first = generate_remediation_requests(audit_manifest=manifest, output_root=output)
    target = output / first["requests"][0]["requestRef"]; target.write_text('{"foreign":true}\n')
    with pytest.raises(ContentRemediationError, match="CREATE_ONCE_CONFLICT"):
        generate_remediation_requests(audit_manifest=manifest, output_root=output)
    assert target.read_text() == '{"foreign":true}\n'
    with pytest.raises(ContentRemediationError, match="OUTPUT_ROOT_NOT_INDEPENDENT"):
        generate_remediation_requests(audit_manifest=manifest, output_root=manifest.parent / "generated")


def test_cli_parser_uses_audit_severity_vocabulary():
    from governance.handler import register_parser
    parser = argparse.ArgumentParser(); register_parser(parser.add_subparsers())
    args = parser.parse_args(["governance", "content-remediation", "--audit-manifest", "audit.json",
                             "--output-root", "isolated", "--issue-code", "source_incomplete", "--severity", "high"])
    assert args.governance_command == "content-remediation"
    assert args.issue_code == ["source_incomplete"] and args.severity == ["high"]
