"""真实单对象 builder 的新包契约；只使用临时 execution/仓与来源证据。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041.t1
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
        "layoutVersion": 2,
    })
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest.update(objectRef=POST_REF, publishAngle="风光", publishTitle="西湖光影")
    _write_json(manifest_path, manifest)
    source = execution / "sources/commons"
    evidence = b"Original fixture source response; CC BY 4.0 attribution.\n"
    (source / "snapshot.html").write_bytes(evidence)
    excerpt = "# 测试来源\n\n原始来源摘录及 CC BY 4.0 署名。\n".encode("utf-8")
    (source / "source.md").write_bytes(excerpt)
    meta = {
        "schema": "quwoquan_data.atomic_source_unit", "stage": "1.download",
        "executionId": execution.name, "executionBinding": "frozen",
        "sourceUnitId": "commons", "sourcePlanRef": "sources/plans/" + "a" * 64 + ".json",
        "sourcePlanDigest": "sha256:" + "a" * 64, "chosenCandidateDigest": "sha256:" + "b" * 64,
        "sourceId": "commons", "targetRef": "posts/" + POST_REF, "carrier": "image",
        "title": "测试来源", "sourceClass": "image", "sourceUseMode": "licensed_adaptation",
        "purpose": "测试随体来源证据", "rightsClue": "CC BY 4.0 attribution",
        "canonicalUrl": manifest["sourceUrls"][0], "fetchedAt": "2026-07-18T04:00:00Z",
        "rawSha256": "sha256:" + hashlib.sha256(evidence).hexdigest(),
        "sourceMarkdownSha256": "sha256:" + hashlib.sha256(excerpt).hexdigest(),
    }
    assert_valid(meta, "source", "atomic_source_unit_meta")
    _write_json(source / "meta.json", meta)
    review = execution / "posts" / POST_REF / "5.review/content_review.json"
    return execution, package, publish, transaction_id, evidence, review.read_bytes()


def test_real_post_builder_carries_single_manifest_sources_media_and_record(tmp_path, monkeypatch):
    execution, package, publish, transaction_id, evidence, review = _package(tmp_path, monkeypatch)
    meta_path = execution / "sources/commons/meta.json"
    original_meta = meta_path.read_bytes()
    source_assets = json.loads((execution / "sources/commons/assets/index.json").read_bytes())["assets"]
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
    assert meta_path.read_bytes() == original_meta
    assert source["metadata"] == json.loads(original_meta)
    assert {row["kind"] for row in source["evidence"]} == {"source_snapshot", "source_excerpt"}
    for row in source["evidence"]:
        original_name, digest_field = (
            ("source.md", "sourceMarkdownSha256") if row["kind"] == "source_excerpt"
            else ("snapshot.html", "rawSha256")
        )
        original_bytes = (execution / "sources/commons" / original_name).read_bytes()
        assert (obj / manifest["sourceRefs"][0]).parent.joinpath(row["path"]).read_bytes() == original_bytes
        assert row["sha256"] == source["metadata"][digest_field]
        assert row["bytes"] == len(original_bytes)
    for asset in manifest["assets"]:
        fact = next(row for row in source["assets"] if row["assetId"] == asset["assetId"])
        assert fact["sourceAsset"] in source_assets
        assert fact["licenseName"] == fact["sourceAsset"]["license"]
        assert fact["author"] == fact["sourceAsset"]["creator"]
        assert fact["distributionDecision"] == fact["sourceAsset"]["distributionDecision"]
        original_manifest = json.loads((execution / "posts" / POST_REF / "manifest.json").read_bytes())
        original_asset = next(row for row in original_manifest["assets"] if row["assetId"] == asset["assetId"])
        assert fact["rightsAuditStatus"] == original_asset["rightsAuditStatus"]
        assert (fact["sha256"], fact["bytes"]) == (asset["sha256"], asset["bytes"])
        body = obj / asset["path"]
        assert body.is_file() and not body.is_symlink()
        assert body.stat().st_size == asset["bytes"]
        assert "sha256:" + hashlib.sha256(body.read_bytes()).hexdigest() == asset["sha256"]
    assert_valid(result, "release", "object_transaction_package")


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045

def _add_original_work(execution: Path) -> dict:
    unit = execution / "sources/commons"
    meta = json.loads((unit / "meta.json").read_bytes())
    response = b'{"id":"native-work","images":["b.jpg","a.jpg"],"icon":"not-adopted.svg"}'
    (unit / "evidence.json").write_bytes(response)
    meta["sourceWork"] = {
        "version": 1, "identity": {"provider": "fixture", "nativeId": "native-work", "pageUrl": meta["canonicalUrl"]},
        "capture": {"method": "media_metadata", "coverage": "partial", "scope": "仅媒体元数据，原作范围未知部分未补造", "evidenceRefs": ["metadata"]},
        "structure": [
            {"ref": meta["canonicalUrl"], "role": "gallery", "members": ["https://example.org/b.jpg", "https://example.org/a.jpg"]},
            {"ref": "https://example.org/b.jpg", "role": "cover"},
            {"ref": "https://example.org/b.jpg", "role": "poster", "anchor": "images[0]"},
        ],
    }
    meta["sourceWorkEvidence"] = [{"id": "metadata", "path": "evidence.json", "kind": "source_metadata",
        "sha256": "sha256:" + hashlib.sha256(response).hexdigest(), "bytes": len(response)}]
    assert_valid(meta, "source", "atomic_source_unit_meta")
    _write_json(unit / "meta.json", meta)
    return meta


def test_source_work_originals_survive_execution_free_copy(tmp_path, monkeypatch):
    import shutil
    from content.release.canonical.post_transaction_sources import read_object_sources
    execution, package, _, transaction_id, _, review = _package(tmp_path, monkeypatch)
    meta = _add_original_work(execution)
    post_transaction.build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package)
    detached = tmp_path / "detached"
    shutil.copytree(package / "object", detached)
    shutil.rmtree(execution)
    assert not package.exists(), "测试事务包在被移除的 execution 内"
    manifest = json.loads((detached / "manifest.json").read_bytes())
    document = read_object_sources(detached, manifest)[0]
    assert document["sourceWork"] == meta["sourceWork"]
    assert "sourceWork" not in document["metadata"]
    assert "sourceWorkEvidence" not in document["metadata"]
    assert str(tmp_path) not in json.dumps(document)
    row = next(row for row in document["evidence"] if row.get("id") == "metadata")
    assert row["kind"] == "source_metadata"
    body = (detached / document["ref"]).parent / row["path"]
    assert b"not-adopted.svg" in body.read_bytes()
    assert not list((detached / "media").glob("*.svg"))
    assert (detached / "content_review.json").read_bytes() == review
    body.write_bytes(body.read_bytes() + b"drift")
    with pytest.raises(ObjectTransactionError, match="SOURCE_EVIDENCE_DRIFT"):
        read_object_sources(detached, manifest)


@pytest.mark.parametrize("change", ["digest", "bytes", "missing", "symlink", "dangling", "duplicate"])
def test_publish_rejects_source_work_evidence_drift(tmp_path, monkeypatch, change):
    execution, package, _, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    meta = _add_original_work(execution)
    path = execution / "sources/commons/evidence.json"
    if change == "digest":
        path.write_bytes(b"different")
    elif change == "bytes":
        meta["sourceWorkEvidence"][0]["bytes"] += 1
    elif change == "missing":
        path.unlink()
    elif change == "symlink":
        other = tmp_path / "original.json"
        path.rename(other)
        path.symlink_to(other)
    elif change == "dangling":
        meta["sourceWork"]["capture"]["evidenceRefs"] = ["absent"]
    else:
        meta["sourceWorkEvidence"].append(meta["sourceWorkEvidence"][0])
    _write_json(execution / "sources/commons/meta.json", meta)
    with pytest.raises((ObjectTransactionError, ValueError), match="SOURCE_(?:WORK|EVIDENCE)"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package)
    assert not package.exists()


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
        "admission": {"processResult": "completed", "qualityResult": "passed", "rightsResult": "passed", "usageScope": "research",
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
    for asset in manifest["assets"]:
        asset["collectionPageUrl"] = manifest["sourceUrls"][0]
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
    from collections import Counter
    from content.release.canonical import aggregate_release_closure as closure
    reads = Counter()
    original_read = closure._read_json

    def counted_read(path):
        reads[path] += 1
        return original_read(path)

    monkeypatch.setattr(closure, "_read_json", counted_read)
    report = query_pool(publish, target_refs=["posts/" + POST_REF])
    assert report["counts"]["image"] == 1, report
    assert len(reads) == 2, "Post 与深层 Entity 依赖均参与定位"
    assert set(reads.values()) == {1}, "同次 query 每份 manifest 只作一次定位读取"
    manifest = json.loads((root / "manifest.json").read_bytes())
    same = query_pool(publish, candidates=[{"objectRef": "posts/" + POST_REF, "manifest": manifest}])
    assert same["preflight"][0]["occupied"] is True
    assert same["preflight"][0]["imageConflicts"] == [], "逻辑 ref 与 p0001 locator 不同仍是同一对象"
    duplicate = {**manifest, "contentId": "different-work", "objectRef": "image/风光/另一作品/1"}
    other = query_pool(publish, candidates=[{"objectRef": "posts/" + duplicate["objectRef"], "manifest": duplicate}])
    conflicts = other["preflight"][0]["imageConflicts"]
    assert any(row["code"] == "DATA.POOL.IMAGE_SHA256_DUPLICATE" for row in conflicts)
    assert all(row["objectRef"] == "posts/" + duplicate["objectRef"] for row in conflicts)


def test_source_metadata_copy_is_not_substitute_for_real_evidence(tmp_path, monkeypatch):
    execution, package, publish, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    (execution / "sources/commons/snapshot.html").unlink()
    (execution / "sources/commons/source.md").unlink()
    with pytest.raises(ObjectTransactionError, match="DATA.PUBLISH.SOURCE_EVIDENCE_MISSING"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
        )
    assert not package.exists()


def test_real_article_builder_projects_body_image_without_changing_original(tmp_path, monkeypatch):
    execution, package, _, transaction_id, _, review = _package(tmp_path, monkeypatch)
    source = execution / "posts" / POST_REF
    manifest = json.loads((source / "manifest.json").read_bytes())
    manifest.update(contentType="article", carrier="article")
    _write_json(source / "manifest.json", manifest)
    name = manifest["assets"][0]["fileName"]
    body = f'# 标题\r\n\r\n图片说明 ![西湖光影]({name} "保留标题")。\r\n'.encode()
    (source / "article.md").write_bytes(body)
    post_transaction.build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
    )
    target = package / "object"
    assert (target / "article.md").read_bytes() == body.replace(name.encode(), b"media/01.jpg")
    assert (target / "media/01.jpg").is_file()
    assert (source / "article.md").read_bytes() == body
    assert (target / "content_review.json").read_bytes() == review


@pytest.mark.parametrize("body_name", ["page.md", "article.md"])
@pytest.mark.parametrize("ref", ["old.jpg", "assets/old.jpg", "sources/unit/assets/old.jpg"])
@pytest.mark.parametrize("filename", ["old.jpg", "assets/old.jpg"])
def test_markdown_projection_binds_original_aliases_to_exact_media(tmp_path, body_name, ref, filename):
    from content.release.canonical.post_transaction_media import copy_markdown_surface
    source = tmp_path / "source.md"
    body = f'![说明]({ref})\n普通文字 assets/old.jpg 和 [链接](https://example.org) 保留。\n'
    source.write_text(body, encoding="utf-8")
    target = tmp_path / "package" / body_name
    (target.parent / "media").mkdir(parents=True)
    (target.parent / "media/01.jpg").write_bytes(b"already-verified-media")
    copy_markdown_surface(source, target,
        source_assets=[{"assetId": "a", "fileName": filename, "sourceAssetRefs": ["sources/unit/assets/old.jpg"]}],
        canonical_assets=[{"assetId": "a", "path": "media/01.jpg"}])
    assert target.read_text() == body.replace(f"]({ref})", "](media/01.jpg)")
    assert source.read_text() == body


@pytest.mark.parametrize("case", ["unknown", "ambiguous", "missing"])
def test_markdown_projection_rejects_unbound_or_missing_images(tmp_path, case):
    from content.release.canonical.post_transaction_media import copy_markdown_surface
    source = tmp_path / "source.md"
    source.write_text("![说明](assets/old.jpg)\n", encoding="utf-8")
    assets = [] if case == "unknown" else [{"assetId": "a", "fileName": "assets/old.jpg"}]
    if case == "ambiguous":
        assets.append({"assetId": "b", "fileName": "assets/old.jpg"})
    target = tmp_path / "page.md"
    with pytest.raises(ObjectTransactionError, match="DATA.PUBLISH.BODY_MEDIA_"):
        copy_markdown_surface(source, target, source_assets=assets,
            canonical_assets=[{"assetId": "a", "path": "media/01.jpg"}])
    assert not target.exists()


@pytest.mark.parametrize("filename", ["source.md", "snapshot.html"])
def test_frozen_source_tampering_is_rejected_before_packaging(tmp_path, monkeypatch, filename):
    """spec_ref: multi-carrier-release/GWT-041 — 冻结来源不可重算摘要后再签发。"""
    execution, package, _, transaction_id, _, review = _package(tmp_path, monkeypatch)
    meta_path = execution / "sources/commons/meta.json"
    original_meta = meta_path.read_bytes()
    assert_valid(json.loads(original_meta), "source", "atomic_source_unit_meta")
    original = execution / "sources/commons" / filename
    tampered = original.read_bytes() + b"Tampered after source freeze.\n"
    original.write_bytes(tampered)

    with pytest.raises(ObjectTransactionError, match=r"DATA\.PUBLISH\.SOURCE_EVIDENCE_DRIFT"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
        )
    assert not package.exists()
    assert meta_path.read_bytes() == original_meta
    assert original.read_bytes() == tampered
    assert (execution / "posts" / POST_REF / "5.review/content_review.json").read_bytes() == review


@pytest.mark.parametrize("field", ["sourceMarkdownSha256", "rawSha256"])
@pytest.mark.parametrize("missing_value", ["absent", None, ""])
def test_missing_frozen_source_digest_is_rejected(tmp_path, monkeypatch, field, missing_value):
    """spec_ref: multi-carrier-release/GWT-041 — 缺冻结摘要不得以当前字节补齐。"""
    execution, package, _, transaction_id, _, review = _package(tmp_path, monkeypatch)
    meta_path = execution / "sources/commons/meta.json"
    meta = json.loads(meta_path.read_bytes())
    if missing_value == "absent":
        meta.pop(field)
    else:
        meta[field] = missing_value
    _write_json(meta_path, meta)
    original_meta = meta_path.read_bytes()

    with pytest.raises(ObjectTransactionError, match=r"DATA\.PUBLISH\.SOURCE_EVIDENCE_DIGEST_MISSING"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
        )
    assert not package.exists()
    assert meta_path.read_bytes() == original_meta
    assert (execution / "posts" / POST_REF / "5.review/content_review.json").read_bytes() == review


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
@pytest.fixture
def no_place_video(tmp_path, monkeypatch):
    from test_post_video_poster_projection__identity_binding__local_contract_test import video_execution, REF
    from content.execution import task_init, seal
    initialize, seal_stage = task_init.initialize_execution, seal.seal_stage

    def initialize_without_place(**kwargs):
        target = kwargs["submitted_bindings"]["targets"][0]
        for key in ("entityId", "entityRef", "entityType", "region"):
            target.pop(key)
        return initialize(**kwargs)

    def seal_photography(**kwargs):
        if kwargs["stage"] == "4.draft":
            from core import paths
            path = paths.execution_root(kwargs["execution_id"]) / REF / "4.draft/video_script.json"
            draft = json.loads(path.read_bytes())
            draft["tagRefs"] = ["Topic/摄影/风光摄影"]
            _write_json(path, draft)
        return seal_stage(**kwargs)

    monkeypatch.setattr(task_init, "initialize_execution", initialize_without_place)
    monkeypatch.setattr(seal, "seal_stage", seal_photography)
    execution, package = video_execution.__wrapped__(tmp_path, monkeypatch)
    return execution, package, REF


def test_no_place_video_projection_package_and_replay(no_place_video):
    from content.release.canonical.final_surface_projection import project_publish_final_surface
    from content.release.canonical.object_transaction_contract import canonical_transaction_id
    execution, package, ref = no_place_video
    obj = execution / ref
    manifest = json.loads((obj / "manifest.json").read_bytes())
    assert manifest["entityRefs"] == [] and manifest["tagRefs"] == ["Topic/摄影/风光摄影"]
    target = json.loads((execution / "0.plan/target_set.json").read_bytes())["targets"][0]
    assert not {"entityId", "entityRef", "entityType", "region"} & target.keys()
    before = {p.relative_to(execution).as_posix(): p.read_bytes() for p in execution.rglob("*") if p.is_file()}
    replay = project_publish_final_surface(execution_root=execution, object_dir=obj, target_ref=ref, target=target, carrier="video")
    assert replay["replayed"] is True and replay["manifest"] == manifest
    kwargs = dict(execution_root=execution, object_ref=ref.removeprefix("posts/"), package_root=package,
                  transaction_id=canonical_transaction_id(execution_id=execution.name, object_kind="posts", object_ref=ref.removeprefix("posts/")))
    first = post_transaction.build_post_object_transaction_package(**kwargs)
    assert post_transaction.build_post_object_transaction_package(**kwargs) == first
    canonical = json.loads((package / "object/manifest.json").read_bytes())
    for field in ("contentId", "entityRefs", "tagRefs", "authorId", "creatorProfileId", "sourceAttribution", "sourceUrls"):
        assert canonical[field] == manifest[field]
    video = next(a for a in canonical["assets"] if a["kind"] == "video")
    poster = next(a for a in canonical["assets"] if a["assetId"] == video["posterAssetId"])
    assert video["posterFileName"] == poster["path"] and video["posterSha256"] == poster["sha256"]
    for asset in canonical["assets"]:
        assert "sha256:" + hashlib.sha256((package / "object" / asset["path"]).read_bytes()).hexdigest() == asset["sha256"]
    assert before == {p.relative_to(execution).as_posix(): p.read_bytes() for p in execution.rglob("*") if p.is_file()}
    assert not (package / "object/page.md").exists()


def test_no_place_video_release_candidates_and_closure(no_place_video, tmp_path):
    import shutil
    from support.post_object_transaction_fixture import _admit_packaged_creator
    from content.release.canonical.aggregate_release_selection import discover_explicit_cohort_candidates
    from content.release.canonical.aggregate_release_pool_closure import candidate_closure
    from content.release.canonical.environment_release_selection import discover_pool_candidates
    from content.release.canonical.aggregate_release_pool import prepare_pool_release
    from content.release.canonical.object_transaction_contract import canonical_transaction_id
    from core import paths
    execution, package, ref = no_place_video
    post_ref = ref.removeprefix("posts/")
    built = post_transaction.build_post_object_transaction_package(execution_root=execution, object_ref=post_ref,
        package_root=package, transaction_id=canonical_transaction_id(execution_id=execution.name, object_kind="posts", object_ref=post_ref))
    publish = tmp_path / "publish"
    root = publish / built["target"]["objectPath"]
    shutil.copytree(package / "object", root)
    _admit_packaged_creator(package, publish)
    tags = set(built["closure"]["tagRefs"])
    for creator in built["closure"]["creatorRefs"]:
        header = json.loads((publish / "creators" / creator / "_creator.json").read_bytes())
        tags.update(header["tagRefs"])
    for tag in tags:
        _write_json(publish / "tags" / tag / "_definition.json", json.loads((paths.CONTROL_PLANE_TAXONOMY_ROOT / tag / "_definition.json").read_bytes()))
    candidates, excluded = discover_explicit_cohort_candidates(publish_root=publish, post_refs=[post_ref])
    assert len(candidates) == 1 and excluded == []
    selected, excluded = discover_pool_candidates(publish_root=publish, post_refs=[post_ref], strict_admission=True)
    assert len(selected) == 1 and excluded == []
    # 地点白名单为空仍能选择不声明地点的视频，不能把空集合当虚构依赖。
    selected, excluded = discover_pool_candidates(
        publish_root=publish, post_refs=[post_ref], strict_admission=True,
        allowed_entity_refs=set(),
    )
    assert len(selected) == 1 and excluded == []
    entities, creators, tag_refs, media = candidate_closure(publish, post_ref=post_ref)
    assert entities == set() and creators == built["closure"]["creatorRefs"]
    assert "Topic/摄影/风光摄影" in tag_refs
    assert {asset["kind"] for asset in media} >= {"image", "video"}
    cohort = {"objectRefs": [ref], "expectedCarrierCounts": {"homepage": 0, "article": 0, "image": 0, "video": 1}, "milestone": "M1"}
    with pytest.raises(ObjectTransactionError, match="COHORT_MILESTONE_COUNT_DRIFT"):
        prepare_pool_release(publish_root=publish, cohort=cohort)
    # 显式引用必须逐项闭合，不能因 carrier 是 video 忽略假依赖。
    from content.release.canonical.aggregate_release_pool_closure import selected_pool_entity_refs
    manifest = json.loads((root / "manifest.json").read_bytes())
    _write_json(root / "manifest.json", {**manifest, "entityRefs": ["/entity/不存在"]})
    with pytest.raises(ObjectTransactionError, match="REFERENCE_MISSING"):
        selected_pool_entity_refs(publish, post_refs={post_ref})
    selected, exclusions = discover_pool_candidates(
        publish_root=publish, post_refs=[post_ref], strict_admission=True,
        allowed_entity_refs=set(),
    )
    assert selected == [] and len(exclusions) == 1
    _write_json(root / "manifest.json", manifest)
    # 删除真实摄影标签也必须阻断，不推断野生动物或伪造标签补位。
    tag_path = publish / "tags/Topic/摄影/风光摄影/_definition.json"
    tag_bytes = tag_path.read_bytes()
    tag_path.unlink()
    with pytest.raises(ObjectTransactionError, match="TAG_SNAPSHOT_MISSING"):
        candidate_closure(publish, post_ref=post_ref)
    tag_path.write_bytes(tag_bytes)
    # 删除实际被引用的媒体后，空地点也不能绕开交付完整性。
    (root / manifest["assets"][0]["path"]).unlink()
    with pytest.raises(ObjectTransactionError):
        candidate_closure(publish, post_ref=post_ref)


@pytest.mark.parametrize("carrier,target", [("homepage", {}), ("article", {}),
    ("image", {"region": "中国"}), ("image", {"entityRef": "/entity/test"}),
    ("image", {"entityRef": "/entity/test", "entityId": "test"}),
    ("image", {"entityRef": None}), ("image", {"entityRef": ""}),
    ("video", {"region": "中国"}), ("video", {"entityRef": "/entity/test"}),
    ("video", {"entityRef": "/entity/test", "entityId": "test"}),
    ("video", {"entityRef": None}), ("video", {"entityRef": ""})])
def test_final_projection_optional_place_keeps_identity_strict(carrier, target):
    from content.release.canonical.final_surface_projection import _target_entity_refs
    with pytest.raises(ObjectTransactionError, match="IDENTITY_INVALID"):
        _target_entity_refs(target, carrier=carrier)


@pytest.mark.parametrize("carrier", ["image", "video"])
def test_final_projection_omitted_place_returns_empty_entity_refs(carrier):
    from content.release.canonical.final_surface_projection import _target_entity_refs
    assert _target_entity_refs({}, carrier=carrier) == []


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-002
def test_object_lookup_scope_reuses_scan_and_restores_nested_roots(tmp_path, monkeypatch):
    from collections import Counter
    from content.release.canonical import aggregate_release_closure as closure

    outer, inner = tmp_path / "outer", tmp_path / "inner"
    ref = "video/摄影/作品/1"
    first = outer / "posts/video/摄影/p0001/作品/1"
    second = inner / "posts/video/摄影/p0002/作品/1"
    for root in (first, second):
        _write_json(root / "manifest.json", {"objectRef": ref, "version": 1})
    reads = Counter()
    original = closure._read_json

    def counted(path):
        reads[path] += 1
        return original(path)

    monkeypatch.setattr(closure, "_read_json", counted)
    with closure.object_lookup_scope(outer):
        assert closure.object_root(outer, "posts", ref) == first
        with pytest.raises(RuntimeError, match="nested failure"):
            with closure.object_lookup_scope(inner):
                assert closure.object_root(inner, "posts", ref) == second
                # 根不匹配不得借用当前 inner 的 lookup。
                assert closure.object_root(outer, "posts", ref) == first
                raise RuntimeError("nested failure")
        assert closure.object_root(outer, "posts", ref) == first
    assert reads[first / "manifest.json"] == 2
    assert reads[second / "manifest.json"] == 1
    newer = outer / "posts/video/摄影/p0001/作品/2"
    _write_json(newer / "manifest.json", {"objectRef": ref, "version": 2})
    assert closure.object_root(outer, "posts", ref) == newer
    duplicate = outer / "posts/video/摄影/p0001/重复/1"
    _write_json(duplicate / "manifest.json", {"objectRef": ref, "version": 2})
    with closure.object_lookup_scope(outer), pytest.raises(ObjectTransactionError, match="IDENTITY_CONFLICT"):
        closure.object_root(outer, "posts", ref)


def test_query_lookup_exception_cleanup_and_orphan_records(tmp_path, monkeypatch):
    from content.release.canonical import aggregate_release_closure as closure, pool_query
    ref = "video/摄影/作品/1"
    root = tmp_path / "posts/video/摄影/p0001/作品/1"
    _write_json(root / "manifest.json", {"objectRef": ref, "version": 1})
    original = pool_query._pool_facts

    def fail(publish, refs):
        assert closure.object_root(publish, "posts", ref) == root
        raise RuntimeError("query failure")

    monkeypatch.setattr(pool_query, "_pool_facts", fail)
    with pytest.raises(RuntimeError, match="query failure"):
        pool_query.query_pool(tmp_path)
    monkeypatch.setattr(pool_query, "_pool_facts", original)
    newer = tmp_path / "posts/video/摄影/p0001/作品/2"
    _write_json(newer / "manifest.json", {"objectRef": ref, "version": 2})
    assert closure.object_root(tmp_path, "posts", ref) == newer
    (tmp_path / "posts/video/孤立/records").mkdir(parents=True)
    with pytest.raises(ObjectTransactionError, match="MANIFEST_MISSING"):
        pool_query.query_pool(tmp_path)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
def test_no_place_query_lookup_once_and_fresh_source_verification(no_place_video, tmp_path, monkeypatch):
    import shutil
    from collections import Counter
    from support.post_object_transaction_fixture import _admit_packaged_creator
    from content.release.canonical import aggregate_release_closure as closure, pool_query
    from content.release.canonical.object_transaction_contract import canonical_transaction_id
    from core import paths

    execution, package, ref = no_place_video
    post_ref = ref.removeprefix("posts/")
    built = post_transaction.build_post_object_transaction_package(execution_root=execution, object_ref=post_ref,
        package_root=package, transaction_id=canonical_transaction_id(execution_id=execution.name, object_kind="posts", object_ref=post_ref))
    publish = tmp_path / "publish"
    root = publish / built["target"]["objectPath"]
    shutil.copytree(package / "object", root)
    _admit_packaged_creator(package, publish)
    tags = set(built["closure"]["tagRefs"])
    for creator in built["closure"]["creatorRefs"]:
        tags.update(json.loads((publish / "creators" / creator / "_creator.json").read_bytes())["tagRefs"])
    for tag in tags:
        _write_json(publish / "tags" / tag / "_definition.json", json.loads((paths.CONTROL_PLANE_TAXONOMY_ROOT / tag / "_definition.json").read_bytes()))
    reads, scans = Counter(), Counter()
    original_read, original_glob = closure._read_json, Path.rglob

    def counted_read(path):
        reads[path] += 1
        return original_read(path)

    def counted_glob(path, pattern):
        if path in (publish / "posts", publish / "entities") and pattern == "manifest.json":
            scans[path] += 1
        return original_glob(path, pattern)

    monkeypatch.setattr(closure, "_read_json", counted_read)
    monkeypatch.setattr(Path, "rglob", counted_glob)
    from content.release.canonical import canonical_inventory
    from core import content_library

    def forbid_write(*args, **kwargs):
        pytest.fail("只读 query 不得 bootstrap inventory 或写入 library")

    monkeypatch.setattr(canonical_inventory, "load_or_bootstrap_inventory", forbid_write)
    monkeypatch.setattr(content_library, "admit_library_entry", forbid_write)
    monkeypatch.setattr(content_library, "admit_library_bytes", forbid_write)
    missing_library = tmp_path / "unmounted-library"
    monkeypatch.setattr(content_library, "LIBRARY_ROOT", missing_library)
    monkeypatch.setattr(content_library, "LIBRARY_CAS_ROOT_BY_KIND", {"media": missing_library / "media"})
    before = {p.relative_to(publish): p.read_bytes() for p in publish.rglob("*") if p.is_file()}
    report = pool_query.query_pool(publish)
    assert report["counts"]["video"] == 1, report
    assert reads[root / "manifest.json"] == 1
    assert scans == {publish / "posts": 1, publish / "entities": 1}
    # candidate 深层 reader 共用 locator；现有只读图片索引自身仍可单独扫描一次。
    reads.clear()
    manifest = json.loads((root / "manifest.json").read_bytes())
    report = pool_query.query_pool(publish, candidates=[{"objectRef": ref, "manifest": manifest}])
    assert report["preflight"][0]["occupied"] and report["counts"]["video"] == 1
    assert reads[root / "manifest.json"] == 1
    assert before == {p.relative_to(publish): p.read_bytes() for p in publish.rglob("*") if p.is_file()}
    # 首次成功不得缓存资格：改来源原件后，新 query 必须重新验证 payload/source。
    source_path = root / manifest["sourceRefs"][0]
    source = json.loads(source_path.read_bytes())
    evidence = source_path.parent / source["evidence"][0]["path"]
    evidence.write_bytes(evidence.read_bytes() + b"tampered")
    report = pool_query.query_pool(publish)
    assert report["counts"]["video"] == 0
    assert report["invalid"][0]["code"] == "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
    assert not missing_library.exists()


def test_legacy_clean_digest_cannot_replace_frozen_source_digest(tmp_path, monkeypatch):
    """spec_ref: multi-carrier-release/GWT-041 — 不双读旧 cleanSha256。"""
    execution, package, _, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    meta_path = execution / "sources/commons/meta.json"
    meta = json.loads(meta_path.read_bytes())
    meta["cleanSha256"] = meta.pop("sourceMarkdownSha256")
    _write_json(meta_path, meta)
    original_meta = meta_path.read_bytes()

    with pytest.raises(ObjectTransactionError, match=r"DATA\.PUBLISH\.SOURCE_EVIDENCE_DIGEST_MISSING"):
        post_transaction.build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
        )
    assert not package.exists()
    assert meta_path.read_bytes() == original_meta
