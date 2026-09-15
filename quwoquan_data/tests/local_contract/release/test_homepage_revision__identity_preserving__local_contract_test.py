"""临时仓内真实 init/acquire/seal/build/audit/apply，绝不生成运营审核。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from content.execution import seal, task_init
from content.release.canonical import object_transaction, publish_object
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError, _read_json, _write_json, _tree_digest,
)
from content.release.canonical.content_pool_record import latest_pool_record, pool_payload_digest
from content.release.canonical.pool_query import query_pool
from content.source import acquire
from core import paths
from support.media_fixture import seed_system_creator_avatar_holding

REF = "entities/travel/stable/xihu"
CREATOR = "qwq_creator_geo_editor_001"
AUTHOR = {"host": "cursor", "modelFamily": "gpt", "sessionId": "fixture-author",
          "invocation": {"provider": "openai", "model": "gpt-5", "runId": "fixture-author-run"}}
REVIEWER = {**AUTHOR, "sessionId": "fixture-reviewer",
            "invocation": {**AUTHOR["invocation"], "runId": "fixture-reviewer-run"}}


def _execution(base, index, *, region="中国/浙江省/杭州市", identity="entity:xihu", ref=REF, review=True):
    execution_id = f"20260912--travel-homepage-correction--local--pilot-{index:03d}"
    target = {"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": region,
              "entityId": identity, "entityRef": "/entity/" + ref.removeprefix("entities/")}
    round_path = base / f"round-{index}.json"
    _write_json(round_path, {"schema": "quwoquan_data.round_spec", "executions": {"homepage": execution_id}, "targets": [target]})
    task_init.initialize_round(round_spec_path=round_path)
    root = paths.execution_root(execution_id)
    process_ref = _read_json(root / "0.plan/target_set.json")["targetRefs"][0]
    source = base / f"source-{index}.md"
    source.write_text(f"# 西湖\n\n测试取得的第{index}版事实。\n", encoding="utf-8")
    ingest = base / f"ingest-{index}.json"
    _write_json(ingest, {"schema": "quwoquan_data.ingest_manifest", "executionId": execution_id, "targets": [{
        "targetRef": process_ref, "sources": [{"kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
        "title": "西湖", "sourceMarkdownPath": str(source), "license": "CC BY-SA 4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "词条编辑",
        "relevance": "实体事实", "extractor": "html_text"}]}]})
    assert acquire.acquire(execution_id=execution_id, request_path=ingest)["failed"] == 0
    for stage in ("1.download", "4.draft", "5.review"):
        if stage == "4.draft":
            draft = root / process_ref / "4.draft/page.md"
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text(f"---\ntitle: 西湖\ntagRefs: [Entity/地点/景区]\ncreatorProfileId: {CREATOR}\n---\n# 西湖\n\n第{index}版已更正事实。\n", encoding="utf-8")
        if stage == "5.review" and not review:
            break
        payload = {"actor": REVIEWER if stage == "5.review" else AUTHOR, "verdict": "pass"}
        if stage == "5.review":
            payload["reviews"] = {process_ref: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        seal_path = base / f"seal-{index}-{stage}.json"
        _write_json(seal_path, payload)
        seal.seal_stage(execution_id=execution_id, stage=stage, input_path=seal_path)
    return root, process_ref


@pytest.fixture
def case(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    publish = tmp_path / "publish"
    (publish / ".git").mkdir(parents=True)
    _write_json(publish / "repository.json", {"schema": "quwoquan_data.publish_repository.v2", "repositoryId": "revision-test", "layoutVersion": 2})
    monkeypatch.setattr(paths, "OUTPUT_ROOT", output)
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", output / "data/local")
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", output / "data/tasks")
    monkeypatch.setattr(paths, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(object_transaction, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(publish_object, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(publish_object, "OUTPUT_ROOT", output)
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp_path / "library"))
    seed_system_creator_avatar_holding(CREATOR, monkeypatch=monkeypatch)
    project_creator_object(CREATOR, publish / "creators" / CREATOR)
    old, process_ref = _execution(output, 1)
    result = publish_object.publish_object(old.name, process_ref)
    old_object = publish / result["canonicalObjectPath"]
    fresh, fresh_ref = _execution(output, 2, region="中国/浙江省/杭州市/西湖区")
    return {"publish": publish, "output": output, "old": old, "old_object": old_object,
            "fresh": fresh, "fresh_ref": fresh_ref,
            "kwargs": {"execution_id": fresh.name, "target_ref": REF, "expected_current_version": 1,
                       "expected_payload_digest": pool_payload_digest(old_object), "reason": "更正正文与主行政归属"}}


def _revise(case, **changes):
    from content.release.canonical.homepage_revision import revise_homepage
    return revise_homepage(**{**case["kwargs"], **changes})


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004.t2
def test_revision_preserves_identity_history_and_unique_count(case):
    old_tree, execution_tree = _tree_digest(case["old_object"]), _tree_digest(case["old"])
    result = _revise(case)
    new = case["publish"] / result["canonicalObjectPath"]
    manifest = _read_json(new / "manifest.json")
    assert new != case["old_object"] and manifest["version"] == 2
    assert manifest["entityId"] == "entity:xihu" and manifest["entityRef"] == "/entity/travel/stable/xihu"
    assert manifest["geoTagRef"].endswith("/西湖区")
    assert "第2版已更正事实" in (new / "page.md").read_text()
    record = latest_pool_record(new, "homepage")
    assert record["contentVersion"] == 2 and record["payloadDigest"] == pool_payload_digest(new)
    assert (new / "content_review.json").read_bytes() == (case["fresh"] / case["fresh_ref"] / "5.review/content_review.json").read_bytes()
    assert _tree_digest(case["old_object"]) == old_tree and _tree_digest(case["old"]) == execution_tree
    pool = query_pool(case["publish"], target_refs=[REF])
    assert pool["objects"][0]["contentVersion"] == 2 and pool["objects"][0]["eligible"]
    assert pool["counts"]["homepage"] == 1


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004.t3
@pytest.mark.parametrize("change", ["version", "digest", "missing_review", "same_actor", "wrong_review", "id", "ref", "old_execution"])
def test_revision_rejects_preconditions_without_pool_write(case, change):
    kwargs = {}
    if change == "version":
        kwargs["expected_current_version"] = 2
    elif change == "digest":
        kwargs["expected_payload_digest"] = "sha256:" + "0" * 64
    elif change in {"id", "ref"}:
        fresh, _ = _execution(case["output"], 3, identity="other" if change == "id" else "entity:xihu",
                              ref="entities/travel/stable/other" if change == "ref" else REF)
        kwargs["execution_id"] = fresh.name
    elif change == "old_execution":
        kwargs["execution_id"] = case["old"].name
    elif change == "same_actor":
        path = case["fresh"] / "_shared/receipts/003-5.review.json"
        receipt = _read_json(path)
        receipt["actor"] = AUTHOR
        _write_json(path, receipt)
    else:
        path = case["fresh"] / case["fresh_ref"] / "5.review/content_review.json"
        if change == "missing_review":
            path.unlink()
        else:
            review = _read_json(path)
            review["objectRef"] = "entities/other"
            _write_json(path, review)
    before = _tree_digest(case["publish"])
    with pytest.raises(ObjectTransactionError):
        _revise(case, **kwargs)
    assert _tree_digest(case["publish"]) == before


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004.t4
@pytest.mark.parametrize("tamper", ["page", "record", "package", "source"])
def test_exact_replay_checks_input_record_and_canonical_bytes(case, tamper):
    result = _revise(case)
    before = _tree_digest(case["publish"])
    replay = _revise(case)
    assert replay["idempotent"] and replay["canonicalObjectPath"] == result["canonicalObjectPath"]
    assert _tree_digest(case["publish"]) == before
    with pytest.raises(ObjectTransactionError):
        _revise(case, reason="不同修正请求")
    new = case["publish"] / result["canonicalObjectPath"]
    if tamper == "page":
        (new / "page.md").write_text("被篡改", encoding="utf-8")
    elif tamper == "record":
        path = new / "records/1.json"
        record = _read_json(path)
        record["contentVersion"] = 1
        _write_json(path, record)
    elif tamper == "package":
        path = case["fresh"] / "evidence/object-transactions" / result["transactionId"] / "object/page.md"
        path.write_text("旧包替换", encoding="utf-8")
    else:
        next((case["fresh"] / "sources").glob("*/source.md")).write_text("来源变化", encoding="utf-8")
    drift = _tree_digest(case["publish"])
    with pytest.raises(ObjectTransactionError):
        _revise(case)
    assert _tree_digest(case["publish"]) == drift


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-004.t3
@pytest.mark.parametrize("drift", ["before", "review"])
def test_drift_between_audit_and_apply_never_writes_new_pool_object(case, monkeypatch, drift):
    from content.release.canonical import homepage_revision as revision
    original = revision.audit_object_transaction
    observed = {}
    def audit(**kwargs):
        result = original(**kwargs)
        path = (case["old_object"] / "page.md" if drift == "before" else
                case["fresh"] / case["fresh_ref"] / "5.review/content_review.json")
        path.write_text("存储边界故障注入", encoding="utf-8")
        observed["pool"] = _tree_digest(case["publish"])
        return result
    monkeypatch.setattr(revision, "audit_object_transaction", audit)
    with pytest.raises(ObjectTransactionError):
        _revise(case)
    assert _tree_digest(case["publish"]) == observed["pool"]
    assert len(list((case["publish"] / "entities").rglob("manifest.json"))) == 1


def test_governance_cli_requires_cas_and_regular_publish_has_no_version():
    from content.release.canonical.handler_cli import register_parser
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["release", "object-transaction", "revise-homepage", "--execution-id", "fresh",
                              "--target-ref", REF, "--expected-current-version", "1",
                              "--expected-payload-digest", "sha256:" + "1" * 64, "--reason", "事实更正"])
    assert args.expected_current_version == 1
    with pytest.raises(SystemExit):
        parser.parse_args(["release", "publish-object", "--execution-id", "fresh", "--target-ref", REF, "--version", "2"])
