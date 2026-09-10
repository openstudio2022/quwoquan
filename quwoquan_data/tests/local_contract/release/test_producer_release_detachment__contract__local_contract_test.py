# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
from __future__ import annotations

import ast
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from content.release.canonical import aggregate_release_builder as builder
from content.release.canonical.aggregate_release_documents import (
    release_header_document,
)
from content.release.canonical.aggregate_release_result import (
    aggregate_release_result,
)
from content.release.canonical.object_source_identity import source_identity_set
from core.source_digest import SourceDefinitionSnapshot

_DATA_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_ROOT = _DATA_ROOT / "scripts/content/release/canonical"
_FORBIDDEN_HEADER_FIELDS = {
    "targetEnvironment",
    "selectionScope",
    "releaseMode",
    "samplePlanRef",
    "samplePlanDigest",
    "contractMigration",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _selection(milestone: str) -> SimpleNamespace:
    targets = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
    return SimpleNamespace(
        pool_digest="sha256:" + "3" * 64,
        eligible_count=sum(targets.values()),
        milestone=milestone,
        milestone_targets=targets,
    )


def test_m1000_header_and_result_need_no_sampling_authority_or_uat_plan() -> None:
    execution_id = "20260906--travel-article-detach--china--scale-1000"
    source_digest = "sha256:" + "1" * 64
    identities, identity_set_digest = source_identity_set(
        [
            {
                "executionId": execution_id,
                "sourceRevision": "sha256:" + "4" * 64,
                "sourceDigest": source_digest,
                "entityCatalogDigest": "sha256:" + "5" * 64,
            }
        ]
    )
    counts = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100, "total": 3100}
    contents = [
        {
            "contentId": f"content-{index}",
            "version": 1,
            "postRef": f"article/m1000/{index}",
            "selectionIdentityDigest": "sha256:" + f"{index:064x}",
            "canonicalObjectDigest": "sha256:" + f"{index + 3000:064x}",
            "contentLibraryBindingDigest": "sha256:" + f"{index + 6000:064x}",
        }
        for index in range(1, 2101)
    ]
    header = release_header_document(
        release_id="m1000-detached-001",
        execution_ids=[execution_id],
        source_revision=None,
        source_digest=None,
        entity_catalog_digest=None,
        source_digest_documents=[SourceDefinitionSnapshot(source_digest).to_document()],
        asset_admission={
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {"verified": 0, "unverified": 0, "restricted": 0, "unknown": 0},
            "authorizationRequiredAssetIds": [],
            "acceptedCount": 0,
        },
        canonical_merkle="sha256:" + "2" * 64,
        pool_digest="sha256:" + "3" * 64,
        counts=counts,
        contents=contents,
        authors=[],
        milestone="M1000",
        milestone_targets={"homepage": 1000, "article": 1000, "image": 1000, "video": 100},
        source_identities=identities,
        source_identity_set_digest=identity_set_digest,
    )
    result = aggregate_release_result(
        release_id="m1000-detached-001",
        release_root="/release/m1000-detached-001",
        execution_ids=[execution_id],
        entity_count=1000,
        post_count=2100,
        creator_count=1,
        carrier_counts=counts,
        canonical_merkle="sha256:" + "2" * 64,
        manifest_digest="sha256:" + "6" * 64,
        cohort_selection=_selection("M1000"),
        excluded=(),
    )

    assert header.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)
    assert result.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)


def test_aggregate_builder_source_does_not_create_uat_artifact() -> None:
    builder = _CANONICAL_ROOT / "aggregate_release_builder.py"
    source = builder.read_text(encoding="utf-8")
    imports = _imports(builder)

    assert "uat/sample_plan.json" not in source
    assert "build_release_uat_sample_plan_artifact" not in source
    assert "sampling_authority" not in source
    assert not any("release_uat" in name for name in imports)
    assert not any("readback" in name for name in imports)


def test_producer_forward_import_graph_has_no_environment_edge() -> None:
    entry_modules = {
        "content.release.canonical.aggregate_release",
        "content.release.canonical.aggregate_release_builder",
        "content.release.canonical.aggregate_release_existing",
        "content.release.canonical.aggregate_release_documents",
        "content.release.canonical.aggregate_release_pool",
        "content.release.canonical.aggregate_release_pool_closure",
        "content.release.canonical.aggregate_release_result",
        "content.release.canonical.aggregate_release_selection",
        "content.release.canonical.producer_release_handoff",
        "content.release.canonical.integrity",
        "content.release.canonical.release_consistency",
        "content.release.canonical.release_header",
        "content.release.canonical.release_media_consistency",
    }
    imports: set[str] = set()
    for module in entry_modules:
        path = _CANONICAL_ROOT / (module.rsplit(".", 1)[-1] + ".py")
        imports.update(_imports(path))

    assert not any(name.startswith("content.release.environment") for name in imports)


def test_producer_release_graph_has_no_consumer_named_selection_model() -> None:
    for name in (
        "aggregate_release_builder.py",
        "aggregate_release_existing.py",
        "aggregate_release_pool.py",
        "aggregate_release_selection.py",
    ):
        source = (_CANONICAL_ROOT / name).read_text(encoding="utf-8")
        assert "EnvironmentRelease" not in source
        assert "environment_selection" not in source
        assert "selection_scope" not in source
        assert "targetEnvironment" not in source


def test_producer_cli_registration_does_not_load_consumer_modules() -> None:
    source = (_CANONICAL_ROOT / "handler.py").read_text(encoding="utf-8")

    for forbidden in (
        "acceptance_lease import",
        "lifecycle_exit import",
        "build_lookup_indexes import",
        "reset import",
        "object_transaction_replay import",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("milestone", ("M100", "M1000"))
def test_milestone_build_writes_no_uat_artifact_or_consumer_fields(
    milestone: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "releases"
    release_id = f"{milestone.lower()}-detached-001"
    execution_id = f"20260906--travel-article-{milestone.lower()}--china--scale-100"
    counts = {"homepage": 1, "article": 0, "image": 0, "video": 0, "total": 1}
    selection = SimpleNamespace(
        pool_digest="sha256:" + "3" * 64,
        eligible_count=1,
        milestone=milestone,
        milestone_targets={"homepage": 1, "article": 0, "image": 0, "video": 0},
    )
    preparation = SimpleNamespace(
        excluded=(),
        cohort_selection=selection,
        execution_ids=[execution_id],
        source_digests=(SourceDefinitionSnapshot("sha256:" + "1" * 64),),
        source_identities=({
            "sourceRevision": "sha256:" + "4" * 64,
            "sourceDigest": "sha256:" + "1" * 64,
            "entityCatalogDigest": "sha256:" + "5" * 64,
            "executionIds": [execution_id],
        },),
        source_identity_set_digest="sha256:" + "6" * 64,
        entity_catalog_digest=None,
        source_revision=None,
        desired={
            "creators": [],
            "entities": ["地点/景区/fixture"],
            "posts": [],
            "tags": [],
        },
    )
    captured_header: dict[str, object] = {}

    monkeypatch.setattr(builder, "prepare_pool_release", lambda **_kwargs: preparation)
    monkeypatch.setattr(builder, "build_release_contents", lambda _selection: [])
    monkeypatch.setattr(builder, "build_release_authors", lambda *_args, **_kwargs: [])

    def copy_object(_source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(builder, "_copy_tree", copy_object)
    monkeypatch.setattr(
        builder,
        "build_release_media_manifest",
        lambda **_kwargs: {"issues": [], "assets": []},
    )
    monkeypatch.setattr(builder, "bind_release_object_media_assets", lambda **_kwargs: None)
    monkeypatch.setattr(
        builder,
        "build_release_asset_admission",
        lambda **_kwargs: {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "acceptedCount": 0,
        },
    )
    monkeypatch.setattr(builder, "assert_valid", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(builder, "objects_merkle", lambda *_args, **_kwargs: "sha256:" + "2" * 64)

    def header_document(**kwargs: object) -> dict[str, object]:
        captured_header.update(kwargs)
        return {
            "schema": "quwoquan_data.release",
            "releaseId": release_id,
            "canonicalMerkle": "sha256:" + "2" * 64,
            "executionIds": [execution_id],
            "counts": counts,
            "milestone": milestone,
        }

    monkeypatch.setattr(builder, "release_header_document", header_document)
    monkeypatch.setattr(
        builder,
        "release_desired_state_document",
        lambda **_kwargs: {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": preparation.desired,
        },
    )
    monkeypatch.setattr(builder, "copy_release_media_objects", lambda **_kwargs: None)
    monkeypatch.setattr(
        builder,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed", "blockingIssues": []},
    )
    monkeypatch.setattr(
        builder,
        "release_attestation_document",
        lambda **_kwargs: {"schema": "quwoquan_data.release_attestation"},
    )
    monkeypatch.setattr(builder, "assert_environment_neutral", lambda _root: None)
    monkeypatch.setattr(builder, "payload_digest", lambda _root: "sha256:" + "7" * 64)

    result = builder._build_aggregate_release.__wrapped__(
        publish_root=publish_root,
        release_root=release_root,
        release_id=release_id,
        cohort={"milestone": milestone},
    )

    release_dir = release_root / release_id
    assert not (release_dir / "payload/uat/sample_plan.json").exists()
    assert captured_header.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)
    assert result.keys().isdisjoint(_FORBIDDEN_HEADER_FIELDS)


def test_release_asset_admission_allows_identical_asset_reuse_across_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.release.canonical import release_admission

    shared = {
        "assetId": "shared-cover",
        "contentSha256": "sha256:" + "1" * 64,
        "sourceUrl": "https://example.com/shared.jpg",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://example.com/proof",
        "creator": "Fixture Creator",
        "platform": "Fixture",
        "capturedAt": "2026-09-06T00:00:00Z",
        "acquisitionStatus": "acquired",
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "research_allowed",
        "rightsIssues": [],
        "generated": False,
    }
    objects = [
        {"objectRef": "entities/fixture", "carrier": "homepage", "assets": [{**shared, "objectRef": "entities/fixture"}], "manifest": {"assets": [{"assetId": "shared-cover", "kind": "image"}], "publishMediaMode": "not_applicable"}, "contentReviewApproved": True},
        {"objectRef": "posts/image/fixture/1", "carrier": "image", "assets": [{**shared, "objectRef": "posts/image/fixture/1"}], "manifest": {"assets": [{"assetId": "shared-cover", "kind": "image"}]}, "contentReviewApproved": True},
    ]
    monkeypatch.setattr(release_admission, "_object_rows", lambda *_args, **_kwargs: objects)

    document = release_admission.build_release_asset_admission(
        release_id="reuse-001",
        objects_root=tmp_path,
        desired={"entities": ["fixture"], "posts": ["image/fixture/1"]},
    )

    assert len(document["assets"]) == 2
    assert document["acceptedCount"] == 2
    for row in objects:
        row["assets"][0].update(rightsStatus="unverified", authorizationProof="", authorizationRequired=True, rightsIssues=["授权未核实"])
    unverified = release_admission.build_release_asset_admission(
        release_id="reuse-unverified-001", objects_root=tmp_path,
        desired={"entities": ["fixture"], "posts": ["image/fixture/1"]},
    )
    assert unverified["acceptedCount"] == 2
    assert unverified["rightsStatusCounts"]["unverified"] == 2
    assert unverified["authorizationRequiredAssetIds"] == ["shared-cover"]


def test_release_asset_admission_rejects_reused_id_with_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.release.canonical import release_admission

    base = {
        "assetId": "shared-cover",
        "contentSha256": "sha256:" + "1" * 64,
        "sourceUrl": "https://example.com/shared.jpg",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://example.com/proof",
        "creator": "Fixture Creator",
        "platform": "Fixture",
        "capturedAt": "2026-09-06T00:00:00Z",
        "acquisitionStatus": "acquired",
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "research_allowed",
        "rightsIssues": [],
        "generated": False,
    }
    objects = [
        {"objectRef": "entities/fixture", "carrier": "homepage", "assets": [{**base, "objectRef": "entities/fixture"}], "manifest": {"assets": [{"assetId": "shared-cover", "kind": "image"}], "publishMediaMode": "not_applicable"}, "contentReviewApproved": True},
        {"objectRef": "posts/image/fixture/1", "carrier": "image", "assets": [{**base, "objectRef": "posts/image/fixture/1", "contentSha256": "sha256:" + "2" * 64}], "manifest": {"assets": [{"assetId": "shared-cover", "kind": "image"}]}, "contentReviewApproved": True},
    ]
    monkeypatch.setattr(release_admission, "_object_rows", lambda *_args, **_kwargs: objects)

    with pytest.raises(Exception, match="asset ID identity conflict"):
        release_admission.build_release_asset_admission(
            release_id="reuse-drift-001",
            objects_root=tmp_path,
            desired={"entities": ["fixture"], "posts": ["image/fixture/1"]},
        )


def _sealed_handoff_fixture(
    root: Path, *, logical_ref: str, review_ref: str, source_identity: bool = False,
) -> tuple[Path, dict, dict, dict, dict]:
    from content.release.canonical.content_pool_handoff import ContentPoolHandoffQuery
    from content.release.canonical.producer_release_handoff import canonical_digest

    execution_id = "20260909--travel-homepage-binding--test--pilot-001"
    digest = "sha256:" + "1" * 64
    review = {
        "schema": "quwoquan_data.content_review", "stage": "5.review",
        "executionId": execution_id, "objectRef": review_ref, "decision": "approved",
        "draft": {"ref": "4.draft/page.md", "digest": digest},
        "dimensions": [{"name": "overall", "decision": "approved", "issues": []}],
        "blockingIssues": [], "assetRights": [],
    }
    review_raw = json.dumps(review, ensure_ascii=False, sort_keys=True).encode()
    review_digest = "sha256:" + hashlib.sha256(review_raw).hexdigest()
    admission = {
        "processResult": "completed", "qualityResult": "passed", "rightsResult": "passed",
        "rightsAuthorityRef": f"{review_ref}/content_review.json",
        "rightsAuthorityDigest": review_digest, "evidenceRef": "content_review.json",
        "evidenceDigest": review_digest, "usageScope": "research",
    }
    manifest = {
        "entityId": "entity-a", "version": 1, "executionId": execution_id,
        "contentType": "homepage", "publishMediaMode": "text_only", "assets": [],
        "admission": admission,
        "sourceIdentity": {"executionId": execution_id},
    }
    if source_identity:
        manifest["sourceIdentity"]["objectRef"] = review_ref
    projected_ref = logical_ref.removeprefix("entities/")
    record = {
        **admission, "objectType": "homepage", "objectId": "entity-a",
        "objectRef": projected_ref, "recordSequence": 1, "contentVersion": 1,
        "canonicalObjectDigest": digest, "payloadDigest": digest,
    }
    query = ContentPoolHandoffQuery(
        object_type="homepage", object_id="entity-a", object_ref=projected_ref,
        carrier="homepage", content_version=1, record_sequence=1, author_id=None,
        status="active", process_result="completed", quality_result="passed",
        eligibility_result="passed", rights_result="passed",
        rights_authority_ref=admission["rightsAuthorityRef"], rights_authority_digest=review_digest,
        usage_scope="research", variant_purpose="not_applicable",
        evidence_ref="content_review.json", evidence_digest=review_digest,
        payload_digest=digest, canonical_object_digest=digest, selection_identity_digest=digest,
        canonical_object_ref=logical_ref, manifest_ref=f"{logical_ref}/manifest.json",
        pool_record_ref=f"{logical_ref}/records/1.json",
        content_library_binding_ref=f"{logical_ref}/manifest.json",
        content_library_binding_digest=canonical_digest([]), content_library_bindings=(),
    ).as_document()
    row = {"objectRef": logical_ref, "carrier": "homepage", "queryDocument": query,
           "queryDigest": canonical_digest(query)}
    sealed_root = root / "payload/objects"
    object_root = sealed_root / logical_ref
    object_root.mkdir(parents=True)
    (object_root / "content_review.json").write_bytes(review_raw)
    _write_handoff_fixture_documents(sealed_root, row, manifest, record)
    return sealed_root, row, manifest, record, review


def _write_handoff_fixture_documents(sealed_root: Path, row: dict, manifest: dict, record: dict) -> None:
    from content.release.canonical.producer_release_handoff import canonical_digest

    object_root = sealed_root / row["objectRef"]
    for path, document in (
        (object_root / "manifest.json", manifest),
        (object_root / "records/1.json", record),
        (sealed_root.parent / "media_manifest.json", {"assets": []}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    row["queryDigest"] = canonical_digest(row["queryDocument"])


@pytest.mark.parametrize("source_identity", [False, True])
@pytest.mark.parametrize("logical_ref", [
    "entities/地点/景区/entity-a", "entities/travel/hubei/yichang/three-gorges-dam",
])
def test_handoff_separates_sealed_locator_from_frozen_review_owner(
    tmp_path: Path, logical_ref: str, source_identity: bool,
) -> None:
    """spec_ref: multi-carrier-release/REQ-008 — 逻辑搬迁不改写原审核引用及摘要。"""
    from content.release.canonical.producer_release_handoff import _validate_embedded_pool_rows

    sealed, row, _manifest, _record, _review = _sealed_handoff_fixture(
        tmp_path, logical_ref=logical_ref, review_ref="entities/地点/景区/entity-a",
        source_identity=source_identity,
    )
    before = {path: path.read_bytes() for path in sealed.parent.rglob("*") if path.is_file()}
    assert _validate_embedded_pool_rows(
        rows=[row], sealed_root=sealed, object_refs=[logical_ref], header={},
    ) == [row]
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("mutation", [
    "wrong_authority_owner", "logical_authority_owner", "authority_suffix", "evidence_ref",
    "authority_digest", "evidence_digest", "review_owner", "review_execution",
    "source_identity_owner", "source_identity_execution", "unapproved", "review_asset_set",
])
def test_handoff_rejects_drift_even_when_query_and_pool_agree(
    tmp_path: Path, mutation: str,
) -> None:
    """spec_ref: multi-carrier-release/REQ-008 — 原 owner/ref/digest/资产覆盖仍精确绑定。"""
    from content.release.canonical.producer_release_handoff import (
        ProducerReleaseHandoffError, _validate_embedded_pool_rows,
    )

    logical_ref = "entities/travel/hubei/yichang/three-gorges-dam"
    sealed, row, manifest, record, review = _sealed_handoff_fixture(
        tmp_path, logical_ref=logical_ref, review_ref="entities/地点/景区/entity-a",
        source_identity=True,
    )
    admission_mutations = {
        "wrong_authority_owner": ("rightsAuthorityRef", "entities/地点/景区/other/content_review.json"),
        "logical_authority_owner": ("rightsAuthorityRef", f"{logical_ref}/content_review.json"),
        "authority_suffix": ("rightsAuthorityRef", "unrelated/content_review.json"),
        "evidence_ref": ("evidenceRef", "other/content_review.json"),
        "authority_digest": ("rightsAuthorityDigest", "sha256:" + "2" * 64),
        "evidence_digest": ("evidenceDigest", "sha256:" + "2" * 64),
    }
    if mutation in admission_mutations:
        field, value = admission_mutations[mutation]
        for admission in (manifest["admission"], record, row["queryDocument"]["admission"]):
            admission[field] = value
    elif mutation.startswith("source_identity_"):
        field = "objectRef" if mutation.endswith("owner") else "executionId"
        manifest["sourceIdentity"][field] = "entities/地点/景区/other" if field == "objectRef" else "other-execution"
    else:
        if mutation == "review_owner":
            review["objectRef"] = "entities/地点/景区/other"
        elif mutation == "review_execution":
            review["executionId"] = "other-execution"
        elif mutation == "unapproved":
            review["decision"] = "rejected"
        else:
            review["assetRights"] = [{
                "assetRef": "sources/a/assets/cover.jpg", "sourceUrl": "https://example.test/cover.jpg",
                "license": "CC BY 4.0", "termsUrl": "https://example.test/terms",
                "authorizationProof": None, "usageScope": "research", "decision": "approved", "issues": [],
            }]
        review_raw = json.dumps(review, ensure_ascii=False, sort_keys=True).encode()
        (sealed / logical_ref / "content_review.json").write_bytes(review_raw)
        digest = "sha256:" + hashlib.sha256(review_raw).hexdigest()
        for admission in (manifest["admission"], record, row["queryDocument"]["admission"]):
            admission.update(rightsAuthorityDigest=digest, evidenceDigest=digest)
    _write_handoff_fixture_documents(sealed, row, manifest, record)
    with pytest.raises(ProducerReleaseHandoffError, match="DATA.RELEASE.HANDOFF_POOL_RIGHTS_DRIFT"):
        _validate_embedded_pool_rows(rows=[row], sealed_root=sealed, object_refs=[logical_ref], header={})


@pytest.mark.parametrize("mutation", [None, "source_rights", "source_evidence", "asset_digest"])
def test_handoff_review_locator_keeps_source_and_asset_digest_bindings(
    tmp_path: Path, mutation: str | None,
) -> None:
    """spec_ref: multi-carrier-release/REQ-008 — locator 分离不放宽来源事实及摘要。"""
    from content.release.canonical.content_pool_handoff import project_content_library_bindings
    from content.release.canonical.producer_release_handoff import (
        ProducerReleaseHandoffError, _validate_embedded_pool_rows, canonical_digest,
    )

    logical_ref = "entities/travel/hubei/yichang/three-gorges-dam"
    sealed, row, manifest, record, review = _sealed_handoff_fixture(
        tmp_path, logical_ref=logical_ref, review_ref="entities/地点/景区/entity-a",
    )
    source_ref, asset_ref = "sources/s001/source.json", "sources/s001/assets/cover.jpg"
    source_asset = {"sourceUrl": "https://example.test/cover.jpg", "license": "CC BY 4.0",
                    "termsUrl": "https://example.test/terms", "authorizationProof": None}
    asset = {
        "assetId": "cover", "objectKey": f"media/objects/sha256/aa/aa/{'a' * 64}.jpg",
        "sha256": "sha256:" + "a" * 64, "sourceAssetRefs": [asset_ref],
        "acquisitionReceiptRefs": ["receipts/acquired.json"], "sourceRefs": [source_ref],
    }
    manifest.update(assets=[asset], sourceRefs=[source_ref], publishMediaMode="illustrated")
    bindings = [binding.as_document() for binding in project_content_library_bindings([asset])]
    row["queryDocument"]["contentLibrary"].update(bindings=bindings, bindingDigest=canonical_digest(bindings))
    review["assetRights"] = [{**source_asset, "assetRef": asset_ref, "usageScope": "research",
                              "decision": "approved", "issues": []}]
    review_raw = json.dumps(review, ensure_ascii=False, sort_keys=True).encode()
    (sealed / logical_ref / "content_review.json").write_bytes(review_raw)
    digest = "sha256:" + hashlib.sha256(review_raw).hexdigest()
    for admission in (manifest["admission"], record, row["queryDocument"]["admission"]):
        admission.update(rightsAuthorityDigest=digest, evidenceDigest=digest)
    source_root = sealed / logical_ref / "sources/s001"
    source_root.mkdir(parents=True)
    evidence = b"Frozen source rights evidence."
    (source_root / "evidence.txt").write_bytes(evidence)
    source = {
        "schema": "quwoquan_data.publish_source", "sourceId": "s001",
        "sourceUrl": "https://example.test/cover.jpg", "sourceUseMode": "licensed_adaptation",
        "fetchedAt": "2026-09-09T00:00:00Z", "metadata": {},
        "assets": [{"sourceAssetRef": asset_ref, "sourceAsset": source_asset}],
        "evidence": [{"path": "evidence.txt", "sha256": "sha256:" + hashlib.sha256(evidence).hexdigest(),
                      "bytes": len(evidence), "kind": "source_excerpt"}],
    }
    if mutation == "source_rights":
        source_asset["license"] = "unknown"
    elif mutation == "source_evidence":
        (source_root / "evidence.txt").write_bytes(b"Tampered source evidence.")
    elif mutation == "asset_digest":
        asset["sha256"] = "sha256:" + "b" * 64
    (source_root / "source.json").write_text(json.dumps(source), encoding="utf-8")
    _write_handoff_fixture_documents(sealed, row, manifest, record)
    if mutation is None:
        assert _validate_embedded_pool_rows(rows=[row], sealed_root=sealed, object_refs=[logical_ref], header={}) == [row]
    else:
        code = "BINDING" if mutation == "asset_digest" else "RIGHTS"
        with pytest.raises(ProducerReleaseHandoffError, match=f"DATA.RELEASE.HANDOFF_POOL_{code}_DRIFT"):
            _validate_embedded_pool_rows(rows=[row], sealed_root=sealed, object_refs=[logical_ref], header={})
