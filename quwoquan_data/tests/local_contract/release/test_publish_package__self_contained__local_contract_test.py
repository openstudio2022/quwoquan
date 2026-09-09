"""真实单对象 builder 的新包契约；只使用临时 execution/仓与来源证据。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.release.canonical import post_transaction
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.schema import assert_valid
from support.post_object_transaction_fixture import (
    POST_REF, _fixture, _isolate_creator_avatar_cas, _write_json,
)


def _freeze_fixture_target(execution: Path):
    """只重建测试 init fixture 的冻结摘要，不触碰真实 receipts。"""
    def digest(path):
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    run = json.loads((execution / "execution_manifest.json").read_bytes())
    target_path = execution / "0.plan/target_set.json"
    target = json.loads(target_path.read_bytes())
    identity = {"entityRef": "/entity/west-lake-stable", "entityId": "entity:west-lake"}
    for row in target["targets"]:
        row.update(identity)
    candidates = run["submittedInputs"]["immutableCandidateBindings"]
    for row in candidates["targets"]:
        row.update(identity)
    input_path = execution.parents[2] / run["initInputs"]["immutableCandidateBindings"]["ref"]
    _write_json(input_path, candidates)
    run["initInputs"]["immutableCandidateBindings"]["digest"] = digest(input_path)
    target["candidateBinding"]["digest"] = digest(input_path)
    _write_json(target_path, target)
    request_path = execution / "0.plan/request.json"
    request = json.loads(request_path.read_bytes())
    request["submittedInputs"] = run["submittedInputs"]
    request["immutableCandidateBindings"] = run["initInputs"]["immutableCandidateBindings"]
    _write_json(request_path, request)
    run["request"]["digest"] = digest(request_path)
    run["targetSet"]["digest"] = digest(target_path)
    _write_json(execution / "execution_manifest.json", run)


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    execution, package, publish, transaction_id = _fixture(tmp_path)
    monkeypatch.setattr(post_transaction, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(post_transaction, "OUTPUT_ROOT", tmp_path / "output")
    _freeze_fixture_target(execution)
    (publish / ".git").mkdir()
    _write_json(publish / "repository.json", {
        "schema": "quwoquan_data.publish_repository.v2", "repositoryId": "test-publish",
        "layoutVersion": 2, "producerContractDigest": "sha256:" + "a" * 64,
    })
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest.update(objectRef=POST_REF, publishAngle="风光", publishTitle="西湖光影")
    _write_json(manifest_path, manifest)
    source = execution / "sources/commons"
    evidence = b"Original fixture source response; CC BY 4.0 attribution.\n"
    (source / "snapshot.html").write_bytes(evidence)
    meta = json.loads((source / "meta.json").read_bytes())
    meta.update(canonicalUrl=manifest["sourceUrls"][0], fetchedAt="2026-07-18T04:00:00Z",
                rawSha256="sha256:" + hashlib.sha256(evidence).hexdigest())
    _write_json(source / "meta.json", meta)
    review = execution / "posts" / POST_REF / "5.review/content_review.json"
    return execution, package, publish, transaction_id, evidence, review.read_bytes()


def test_real_post_builder_carries_single_manifest_sources_media_and_record(tmp_path, monkeypatch):
    execution, package, publish, transaction_id, evidence, review = _package(tmp_path, monkeypatch)
    result = post_transaction.build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
    )
    assert result["target"]["objectRef"] == POST_REF
    assert result["target"]["objectPath"] == "posts/image/风光/p0001/西湖光影/1"
    obj = package / "object"
    manifest = json.loads((obj / "manifest.json").read_bytes())
    assert manifest["objectRef"] == POST_REF
    assert (obj / "content_review.json").read_bytes() == review
    assert (obj / "records/1.json").is_file()
    assert not {"sourceCatalogRef", "rightsRef"} & manifest.keys()
    assert not {"_entity.json", "rights.json", "source_catalog.json", "rights_snapshots", "assets", "_pool", "video.md"} & {p.name for p in obj.iterdir()}
    source = json.loads((obj / manifest["sourceRefs"][0]).read_bytes())
    assert_valid(source, "publish", "source")
    assert (obj / manifest["sourceRefs"][0]).parent.joinpath(source["evidence"][0]["path"]).read_bytes() == evidence
    for asset in manifest["assets"]:
        body = obj / asset["path"]
        assert body.is_file() and not body.is_symlink()
        assert body.stat().st_size == asset["bytes"]
        assert "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest() == asset["sha256"]
    assert_valid(result, "release", "object_transaction_package")


def _admit_dependencies(package: Path, publish: Path):
    import shutil
    from support.post_object_transaction_fixture import _admit_packaged_creator
    from content.release.canonical.content_pool_record import append_pool_record, build_canonical_pool_record
    _admit_packaged_creator(package, publish)
    root = publish / "entities/地点/中国/浙江省/杭州市/西湖区/景区/p0001/西湖/1"
    root.mkdir(parents=True)
    post = json.loads((package / "object/manifest.json").read_bytes())
    ref = "地点/景区/西湖"
    review = {"schema": "quwoquan_data.content_review", "stage": "5.review", "executionId": post["executionId"],
              "objectRef": "entities/" + ref, "decision": "approved", "draft": {"ref": "4.draft/page.md", "digest": "sha256:" + "1" * 64},
              "dimensions": [{"name": "content", "decision": "approved", "issues": []}], "blockingIssues": [], "assetRights": []}
    _write_json(root / "content_review.json", review)
    digest = "sha256:" + hashlib.sha256((root / "content_review.json").read_bytes()).hexdigest()
    url = "https://zh.wikipedia.org/wiki/西湖"
    manifest = {"schema": "quwoquan_data.entity_object", "entityId": "entity:west-lake", "entityRef": "/entity/" + ref,
        "version": 1, "label": "西湖", "domain": "地点", "type": "景区", "geographyMode": "administrative",
        "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区", "contentType": "homepage", "publishMediaMode": "text_only",
        "assets": [], "tagRefs": [], "sourceRefs": post["sourceRefs"], "sourceUrls": [url], "finalContentRef": "page.md",
        "executionId": post["executionId"], "sourceIdentity": post["sourceIdentity"], "sourceAttribution": post["sourceAttribution"],
        "creatorProfileId": post["creatorProfileId"], "primarySource": {"sourceKind": "wikipedia", "entityName": "西湖", "extractor": "wikipedia_api",
        "canonicalUrl": url, "sourceUrl": url, "title": "西湖", "fetchedAt": "2026-07-18T04:00:00Z", "snapshotHash": "sha256:" + "a" * 64,
        "policyRevision": "encyclopedia-primary", "sourceUseMode": "factual_reference_only"},
        "admission": {"processResult": "completed", "qualityResult": "passed", "rightsResult": "passed", "usageScope": "production",
        "evidenceRef": "content_review.json", "evidenceDigest": digest, "rightsAuthorityRef": f"entities/{ref}/content_review.json", "rightsAuthorityDigest": digest}}
    _write_json(root / "manifest.json", manifest)
    (root / "page.md").write_text("# 西湖\n\n测试来源正文。\n", encoding="utf-8")
    shutil.copytree(package / "object/sources", root / "sources")
    append_pool_record(object_root=root, record=build_canonical_pool_record(object_root=root, object_type="homepage", object_ref=ref))
    # fixture 在事务开始前显式创建依赖，随后丢弃可重建缓存。
    from content.release.canonical.canonical_inventory import canonical_inventory_path
    canonical_inventory_path(publish).unlink(missing_ok=True)


def test_real_package_audit_apply_reads_logical_identity_and_carried_bytes(tmp_path, monkeypatch):
    from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory, object_placements
    from content.release.canonical.object_transaction_audit import audit_object_transaction
    from content.release.canonical.application import apply_object_transaction
    from content.release.canonical.pool_query import query_pool
    execution, package, publish, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    # complete fixture producer provenance required by pool readers
    path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest.update(generator="agent", createdAt="2026-07-18T04:00:00Z", updatedAt="2026-07-18T04:00:00Z")
    _write_json(path, manifest)
    result = post_transaction.build_post_object_transaction_package(execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package)
    _admit_dependencies(package, publish)
    audit = audit_object_transaction(publish_root=publish, output_root=tmp_path / "output", package_root=package,
        transaction_id=transaction_id, expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"]["merkleRoot"])
    apply_object_transaction(publish_root=publish, output_root=tmp_path / "output", package_root=package, transaction_id=transaction_id,
                             dry_run_attestation_sha256=audit["dryRunAttestationSha256"])
    root = publish / result["target"]["objectPath"]
    assert (root / "media/01.jpg").read_bytes() == (package / "object/media/01.jpg").read_bytes()
    assert any(row.logical_ref == POST_REF and row.path == result["target"]["objectPath"] for row in object_placements(publish))
    report = query_pool(publish, target_refs=["posts/" + POST_REF])
    assert report["counts"]["image"] == 1, report


def test_source_metadata_copy_is_not_substitute_for_real_evidence(tmp_path, monkeypatch):
    execution, package, publish, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    (execution / "sources/commons/snapshot.html").unlink()
    with pytest.raises(ObjectTransactionError, match="DATA.PUBLISH.SOURCE_EVIDENCE_MISSING"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
        )
    assert not package.exists()
