# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001
"""迁移盘点只认可原始链；转换不能代签 review，也不能掩盖 payload drift。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from content.release.canonical import pool_cutover_inventory as subject
from content.release.canonical.object_transaction_contract import _digest_file, _read_json, _tree_digest
from core import paths
from local_contract.release.test_pool_cutover__exact_cas__contract__local_contract_test import (
    CREATOR, HOME, PROCESS_HOME, _execution, _publish, _write,
)


def _review() -> dict:
    return {"schema": "quwoquan_data.content_review", "stage": "5.review", "executionId": "original",
            "objectRef": HOME, "decision": "approved", "blockingIssues": [],
            "dimensions": [{"name": "overall", "decision": "approved", "issues": []}],
            "draft": {"ref": "4.draft/page.md", "digest": "sha256:" + "1" * 64},
            "qualityScores": {"readability": 4}, "qualityNotes": "原 reviewer 原话",
            "assetRights": [{"assetRef": "sources/a/assets/a.jpg", "sourceUrl": "https://example.org/a",
                             "license": "CC BY 4.0", "termsUrl": "https://example.org/terms",
                             "authorizationProof": None,
                             "decision": "rejected", "issues": ["原权利问题保留"]}]}


@pytest.mark.parametrize("scope", ["research", "commercial"])
def test_conversion_removes_known_review_classification_and_preserves_judgments(
        scope: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # 该最小历史 review fixture 只隔离转换语义；完整现行 schema 由真实对象测试覆盖。
    monkeypatch.setattr(subject, "assert_valid", lambda *args, **kwargs: None)
    original = _review()
    original["assetRights"][0].update(usageScope=scope, distributionDecision="blocked")
    frozen = copy.deepcopy(original)
    converted = subject.convert_review_document(original)
    assert original == frozen
    assert "usageScope" not in converted["assetRights"][0]
    assert "distributionDecision" not in converted["assetRights"][0]
    restored = copy.deepcopy(converted)
    restored["assetRights"][0].update(usageScope=scope, distributionDecision="blocked")
    assert restored == frozen


@pytest.mark.parametrize("scope", ["production", "default", "unknown", None])
def test_conversion_rejects_invalid_review_scope(scope: object) -> None:
    review = _review()
    review["assetRights"][0]["usageScope"] = scope
    with pytest.raises(ValueError, match="RETIRED_CLASSIFICATION_VALUE_INVALID"):
        subject.convert_review_document(review)


def test_conversion_never_fills_missing_rights_facts() -> None:
    review = _review()
    del review["assetRights"][0]["termsUrl"]
    with pytest.raises(ValueError):
        subject.convert_review_document(review)


@pytest.fixture
def original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    execution = _execution(tmp_path, monkeypatch)
    active, package = _publish(tmp_path, execution, monkeypatch)
    return {"execution": execution, "active": active, "tmp": tmp_path, "package": package,
            "authority": paths.CONTROL_PLANE_CREATOR_POOL_ROOT / "evidence/system_builtin_author_admission.json"}


def _inventory(case: dict) -> dict:
    return subject.inventory_pool(publish_root=case["active"], executions_root=case["execution"].parent,
                                  author_authority=case["authority"])


def test_inventory_is_only_exposed_through_release_cli(monkeypatch, capsys) -> None:
    import argparse
    from content.release.canonical.handler_cli import register_parser

    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args([
        "release", "pool-cutover", "inventory", "--publish-root", "/unused/publish",
        "--executions-root", "/unused/executions", "--author-authority", "/unused/authority.json",
        "--summary",
    ])
    monkeypatch.setattr(subject, "inventory_pool", lambda **kwargs: {"objects": [], "purpose": "offline_inventory_not_admission_or_decision"})
    args.handler(args)
    assert json.loads(capsys.readouterr().out) == {"purpose": "offline_inventory_not_admission_or_decision"}
    assert "__main__" not in Path(subject.__file__).read_text(encoding="utf-8")


def test_inventory_validates_real_seals_and_never_writes_originals(original: dict) -> None:
    roots = (original["active"], original["execution"])
    before = [_tree_digest(root) for root in roots]
    report = _inventory(original)
    content = next(row for row in report["objects"] if row["objectRef"] == HOME)
    assert content["classification"] == "text_surface_mechanical_candidate"
    assert content["originalReviewAuthority"]["reviewDigest"] == _digest_file(original["active"] / HOME / "content_review.json")
    assert content["originalReviewAuthority"]["author"]["sessionId"] != content["originalReviewAuthority"]["reviewer"]["sessionId"]
    assert report["purpose"] == "offline_inventory_not_admission_or_decision"
    assert [_tree_digest(root) for root in roots] == before
    assert report["counts"]["occupied"] == 2
    assert report["counts"]["classification"]["creator_mechanical_candidate"] == 1


@pytest.mark.parametrize("fault,code", [
    ("canonical_payload", "ORIGINAL_PAYLOAD_DRIFT"),
    ("execution_draft", "ORIGINAL_CHAIN_INVALID"),
    ("review_identity", "ORIGINAL_REVIEW_BINDING_DRIFT"),
    ("same_actor", "ORIGINAL_CHAIN_INVALID"),
    ("missing_execution", "ORIGINAL_CHAIN_INVALID"),
])
def test_inventory_does_not_requalify_drift_or_missing_authority(original: dict, fault: str, code: str) -> None:
    root, execution = original["active"] / HOME, original["execution"]
    if fault == "canonical_payload":
        _write(root / "page.md", "unreviewed canonical replacement")
    elif fault == "execution_draft":
        _write(execution / PROCESS_HOME / "4.draft/page.md", "unreviewed draft replacement")
    elif fault == "review_identity":
        review = _read_json(root / "content_review.json")
        review["executionId"] = "other-execution"
        _write(root / "content_review.json", review)
    elif fault == "same_actor":
        receipt = _read_json(execution / "_shared/receipts/003-5.review.json")
        receipt["actor"] = _read_json(execution / "_shared/receipts/002-4.draft.json")["actor"]
        _write(execution / "_shared/receipts/003-5.review.json", receipt)
    else:
        original["execution"] = original["tmp"] / "missing-tasks" / execution.name
    report = _inventory(original)
    row = next(row for row in report["objects"] if row["objectRef"] == HOME)
    assert row["classification"] == "requires_author_review_or_evidence_recovery"
    assert any(issue["code"] == "DATA.CUTOVER.INVENTORY." + code for issue in row["issues"])


def test_creator_conversion_preserves_profile_and_requires_exact_authority(original: dict) -> None:
    profile = _read_json(original["active"] / "creators" / CREATOR / "profile.json")
    converted = subject.convert_creator_profile(profile, original["authority"])
    assert converted["version"] == profile["version"] + 1
    converted["version"] = profile["version"]
    assert converted == profile
    profile["admission"]["evidenceDigest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="AUTHOR_AUTHORITY_DRIFT"):
        subject.convert_creator_profile(profile, original["authority"])


def test_text_conversion_preserves_original_review_and_validates_current_record(original: dict) -> None:
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    from content.release.canonical.content_pool_record import latest_pool_record, is_pool_record_admitted
    from core.schema import assert_valid
    before = _tree_digest(original["active"])
    converted = convert_text_object(object_root=original["active"] / HOME,
                                    execution_root=original["execution"], object_ref=HOME)
    stage = original["tmp"] / "converted-object"
    for relative, raw in converted.items():
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    record = latest_pool_record(stage, "homepage")
    assert is_pool_record_admitted(record)
    assert_valid(record, "release", "pool_object_record")
    assert record["contentVersion"] == 2
    assert (stage / "content_review.json").read_bytes() == (original["active"] / HOME / "content_review.json").read_bytes()
    assert _tree_digest(original["active"]) == before
    assert not any(path.name in {"asset.refs.json", "tag.refs.json", "creator.refs.json"} for path in converted)


def _install_legacy_classification(original: dict, *, invalid_scope: str | None = None) -> None:
    root, execution = original["active"] / HOME, original["execution"]
    review_path = execution / PROCESS_HOME / "5.review/content_review.json"
    review_digest = _digest_file(review_path)
    receipt_path = execution / "_shared/receipts/003-5.review.json"
    receipt = _read_json(receipt_path)
    binding = {"scope": "execution", "ref": PROCESS_HOME + "/5.review/content_review.json", "digest": review_digest}
    receipt["resultRefs"] = [binding if row.get("ref") == binding["ref"] else row for row in receipt["resultRefs"]]
    _write(receipt_path, receipt)

    publication = "commercial_release"
    manifest = _read_json(root / "manifest.json")
    manifest["admission"].update(usageScope=invalid_scope or "commercial", evidenceDigest=review_digest,
                                 rightsAuthorityDigest=review_digest)
    manifest.update(variantPurpose="commercial_variant")
    manifest["sourceAttribution"]["publicationAdmission"] = publication
    _write(root / "manifest.json", manifest)
    entity_path = root / "_entity.json"
    entity = _read_json(entity_path) if entity_path.is_file() else dict(manifest)
    entity["sourceAttribution"]["publicationAdmission"] = publication
    _write(entity_path, entity)
    rights_path = root / "rights.json"
    if not rights_path.is_file():
        _write(rights_path, {"schema": "quwoquan_data.asset_rights_closure", "publishMediaMode": "text_only", "assets": []})

    record_path = root / "records/1.json"
    record = _read_json(record_path)
    record.update(usageScope="commercial", sourceAttribution=manifest["sourceAttribution"],
                  evidenceDigest=review_digest, rightsAuthorityDigest=review_digest)
    _write(record_path, record)
    from content.release.canonical.content_pool_record import pool_payload_digest
    record["payloadDigest"] = pool_payload_digest(root)
    record["canonicalObjectDigest"] = record["payloadDigest"]
    _write(record_path, record)


def _without_classification(value: object) -> object:
    if isinstance(value, dict):
        return {key: _without_classification(item) for key, item in value.items()
                if key not in {"usageScope", "distributionDecision", "publicationAdmission", "variantPurpose"}}
    if isinstance(value, list):
        return [_without_classification(item) for item in value]
    return value


def test_legacy_text_conversion_removes_only_known_classification(original: dict) -> None:
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    root = original["active"] / HOME
    _install_legacy_classification(original)
    before_digest = _tree_digest(root)
    before_bytes = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    before_manifest = _read_json(root / "manifest.json")
    before_review = _read_json(root / "content_review.json")
    before_rights = _read_json(root / "rights.json")

    result = convert_text_object(object_root=root, execution_root=original["execution"], object_ref=HOME)
    successor = json.loads(result[Path("manifest.json")])
    successor_review = json.loads(result[Path("content_review.json")])
    assert Path("rights.json") not in result
    successor_record = json.loads(result[Path("records/1.json")])

    assert _tree_digest(root) == before_digest
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before_bytes
    assert successor["version"] == before_manifest["version"] + 1
    assert successor_record["contentVersion"] == successor["version"]
    assert successor_record["payloadDigest"] != _read_json(root / "records/1.json")["payloadDigest"]
    assert _without_classification(successor) == _without_classification({**before_manifest, "version": successor["version"]})
    assert _without_classification(successor_review) == _without_classification(before_review)
    assert before_rights["publishMediaMode"] == "text_only" and before_rights["assets"] == []
    for document in (successor, successor_review, successor_record):
        encoded = json.dumps(document, ensure_ascii=False)
        assert not any(field in encoded for field in ("publicationAdmission", "distributionDecision", "variantPurpose"))
    assert "usageScope" not in successor.get("admission", {})
    assert "usageScope" not in successor_record
    assert successor_review == before_review
    assert successor["admission"]["evidenceDigest"] == _digest_file(root / "content_review.json")


@pytest.mark.parametrize("value", ["production", "default", "unknown"])
def test_legacy_text_conversion_rejects_invalid_classification(original: dict, value: str) -> None:
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    _install_legacy_classification(original, invalid_scope=value)
    with pytest.raises(ValueError, match="RETIRED_CLASSIFICATION_VALUE_INVALID"):
        convert_text_object(object_root=original["active"] / HOME,
                            execution_root=original["execution"], object_ref=HOME)


def test_text_conversion_refuses_digest_refresh_as_repair(original: dict) -> None:
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    _write(original["active"] / HOME / "page.md", "unreviewed changed page")
    with pytest.raises(ValueError, match="ORIGINAL_PAYLOAD_DRIFT"):
        convert_text_object(object_root=original["active"] / HOME,
                            execution_root=original["execution"], object_ref=HOME)


def test_text_conversion_rejects_pool_changes_during_conversion(original: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_cutover_text_conversion as conversion
    text_bytes = conversion._text_bytes

    def changed_bytes(root: Path, ref: str, final_ref: str) -> dict:
        result = text_bytes(root, ref, final_ref)
        _write(root / final_ref, "concurrent unreviewed replacement")
        return result

    monkeypatch.setattr(conversion, "_text_bytes", changed_bytes)
    with pytest.raises(ValueError, match="POOL_CHANGED_DURING_CONVERSION"):
        conversion.convert_text_object(object_root=original["active"] / HOME,
                                       execution_root=original["execution"], object_ref=HOME)


def test_recovery_finds_exact_execution_review_without_repairing_canonical(original: dict) -> None:
    root = original["active"] / HOME
    (root / "content_review.json").unlink()
    before = _tree_digest(original["active"])
    report = subject.feasibility_report(publish_root=original["active"], executions_root=original["execution"].parent,
                                        author_authority=original["authority"], archive_roots=[])
    row = report["recovery"][0]
    assert row["canonicalReview"]["exists"] is False
    alternative = row["availableExecutionReviews"][0]
    assert alternative["sameOriginalExecution"] is True
    assert alternative["canonicalTextMatchesReviewedDraft"] is True
    assert alternative["status"] == "independent_chain_verified_not_migration_admission"
    assert _tree_digest(original["active"]) == before
    assert not (root / "content_review.json").exists()


def test_archive_copy_without_receipts_never_becomes_recovered_authority(original: dict) -> None:
    import shutil
    archive = original["tmp"] / "archive"
    destination = archive / "release-one/payload/objects" / HOME / "content_review.json"
    destination.parent.mkdir(parents=True)
    shutil.copyfile(original["active"] / HOME / "content_review.json", destination)
    report = _inventory(original)
    row = next(item for item in report["objects"] if item["objectRef"] == HOME)
    copies = subject._review_copies([archive], {HOME})
    recovery = subject._recovery_row(row, original["active"], original["tmp"] / "missing", [], copies, {})
    assert recovery["archiveReviewCopies"][0]["role"] == "archive_copy_not_receipt_authority"
    assert recovery["recoveryFact"] == "no_verified_chain_in_declared_search_scope"


def test_dependency_closure_propagates_missing_refs_without_delete_decisions() -> None:
    rows = [{"objectRef": ref, "before": {"dependencyRefs": dependencies}}
            for ref, dependencies in (("creator", []), ("home", ["missing"]), ("post", ["home", "creator"]))]
    result = subject.dependency_closure({"objects": rows}, {"creator", "home", "post"})
    assert result["closedObjectRefs"] == ["creator"]
    assert len(result["pruningRounds"]) == 2
    assert result["purpose"] == "dependency_arithmetic_not_admission_or_delete_decision"


def test_asset_identity_facts_distinguish_shared_assets_and_duplicate_works(tmp_path: Path) -> None:
    refs = ["posts/article/a/a/1", "posts/image/a/a/1", "posts/image/a/b/1"]
    asset = {"assetId": "same", "sha256": "sha256:" + "1" * 64, "kind": "image",
             "sourceUrl": "https://example.org/work", "originalAssetUrl": "https://example.org/a.jpg",
             "perceptualHash": "0123456789abcdef"}
    for index, ref in enumerate(refs):
        _write(tmp_path / ref / "manifest.json", {"assets": [asset], "contentId": str(index), "version": 1})
    report = {"objects": [{"objectRef": ref} for ref in refs]}
    facts = subject.asset_identity_facts(report, tmp_path)
    assert facts["assetIdBindingDriftGroups"] == []
    assert len(facts["sharedSha256Groups"]) == 1
    assert len(facts["existingImageConflictRules"]) == 1
    assert facts["existingImageConflictRules"][0]["code"] == "DATA.POOL.IMAGE_SHA256_DUPLICATE"
    asset["originalAssetUrl"] = "https://example.org/changed.jpg"
    _write(tmp_path / refs[-1] / "manifest.json", {"assets": [asset], "contentId": "2", "version": 1})
    assert len(subject.asset_identity_facts(report, tmp_path)["assetIdBindingDriftGroups"]) == 1


def test_media_schema_report_does_not_mutate_frozen_review(tmp_path: Path) -> None:
    ref = "posts/image/a/a/1"
    path = _write(tmp_path / ref / "content_review.json", _review())
    before = path.read_bytes()
    report = subject.media_review_compatibility({"objects": [{"objectRef": ref, "issues": []}]}, tmp_path)
    assert report["counts"] == {"original_review_bytes_current_schema_invalid": 1}
    assert path.read_bytes() == before


def test_report_writer_is_create_once_and_rejects_pool_paths(original: dict) -> None:
    workspace = paths.DATA_LOCAL_ROOT / "workspace/unified-cutover"
    workspace.mkdir(parents=True)
    report = {"purpose": "offline_inventory_not_admission_or_decision"}
    target = workspace / "bounded.v1.json"
    result = subject.write_inventory_report(report, target)
    assert result["digest"] == _digest_file(target)
    with pytest.raises(FileExistsError):
        subject.write_inventory_report(report, target)
    with pytest.raises(ValueError, match="REPORT_PATH_FORBIDDEN"):
        subject.write_inventory_report(report, original["active"] / "report.json")
    linked = workspace / "linked.json"
    linked.symlink_to(original["active"] / HOME / "manifest.json")
    with pytest.raises(ValueError, match="REPORT_PATH_FORBIDDEN"):
        subject.write_inventory_report(report, linked)


def test_archived_receipt_chain_facts_reject_predecessor_or_actor_drift(original: dict) -> None:
    path = original["tmp"] / "handoff.json"
    receipts = [_read_json(path) for path in sorted((original["execution"] / "_shared/receipts").glob("*.json"))]
    chain = {"executionId": original["execution"].name, "receipts": receipts}
    _write(path, chain)
    facts = subject._archived_chain_facts(chain, {}, path)
    assert facts["status"] == "independent_actor_and_predecessor_bytes_verified"
    assert facts["reviewBindings"][0]["embeddedBytesPresent"] is False
    receipts[2]["actor"] = receipts[1]["actor"]
    assert subject._archived_chain_facts(chain, {}, path)["status"] == "blocked"


def test_archive_handoff_rejects_forged_embedded_digest(tmp_path: Path) -> None:
    import base64
    root = tmp_path / "archive"
    _write(root / "release/producer_release_handoff.json", {"frozenReferences": [{
        "contentBase64": base64.b64encode(b"original").decode(), "scope": "execution", "ref": "review.json",
        "digest": "sha256:" + "0" * 64}], "receiptChains": []})
    with pytest.raises(ValueError, match="ARCHIVED_BYTES_DRIFT"):
        subject._archive_handoffs([root])


def test_report_writer_rejects_protected_root_reconfiguration(original: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_cutover as cutover
    local = original["active"] / "local"
    workspace = local / "workspace/unified-cutover"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", local)
    monkeypatch.setattr(paths, "PUBLISH_ROOT", original["active"])
    with pytest.raises(cutover.PoolCutoverError, match="PATH_OVERLAP"):
        subject.write_inventory_report({"purpose": "not_admission"}, workspace / "forbidden.json")


def test_converted_text_passes_existing_staging_validator_without_new_execution(original: dict) -> None:
    import shutil
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    from content.release.canonical import pool_cutover
    from content.release.canonical.object_transaction_contract import _closure_digest, _review_binding
    from local_contract.release.test_pool_cutover__exact_cas__contract__local_contract_test import _binding
    stage, package = original["tmp"] / "isolated-stage", original["tmp"] / "isolated-package"
    shutil.copytree(original["active"], stage)
    shutil.copytree(original["package"], package)
    converted = convert_text_object(object_root=original["active"] / HOME,
                                    execution_root=original["execution"], object_ref=HOME)
    for root in (stage / HOME, package / "object"):
        shutil.rmtree(root)
        for relative, raw in converted.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    from content.release.canonical.canonical_inventory import canonical_inventory_path
    canonical_inventory_path(stage).unlink(missing_ok=True)
    for root in (stage / "creators" / CREATOR, package / "creator_objects" / CREATOR):
        profile = subject.convert_creator_profile(_read_json(root / "profile.json"), original["authority"])
        _write(root / "profile.json", profile)
    document = _read_json(package / "object_transaction_package.json")
    for row in document["closure"]["creatorObjects"]:
        row["treeDigest"] = _tree_digest(package / row["packageRef"])
    document["objectClosureDigest"] = _closure_digest(
        object_root=package / "object", object_kind="entities", object_ref=document["target"]["objectRef"],
        target_schema="quwoquan_data.entity_object", source_policy_revision=document["sourcePolicyRevision"],
        closure=document["closure"], cas_rows=[], review=_review_binding(package / "object", document))
    _write(package / "object_transaction_package.json", document)
    after = {row["objectRef"]: row for row in pool_cutover.snapshot_pool(stage)["objects"]}
    actions = []
    for before in pool_cutover.snapshot_pool(original["active"])["objects"]:
        evidence = [_binding(original["authority"], role="author_authority")] if before["objectRef"].startswith("creators/") else [
            _binding(original["execution"], role="execution"), _binding(package, role="package")]
        actions.append({"before": before, "after": after[before["objectRef"]], "action": "migrate", "evidence": evidence})
    query = pool_cutover._validate_staging({"objects": actions}, stage)
    assert query["counts"]["homepage"] == 1
    assert not query["excluded"]
