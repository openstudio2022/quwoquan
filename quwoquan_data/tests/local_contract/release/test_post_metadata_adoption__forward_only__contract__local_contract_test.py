# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/image-commercial-scale-closure/spec.md#gwt-004
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from content.execution.runtime_contract import canonical_sha256
from content.release.canonical.application import rollback_object_transaction
from content.release.canonical.content_pool_record import latest_pool_record
from content.release.canonical.environment_release_selection import (
    select_all_publishable_release_posts,
)
from content.release.canonical.object_transaction_contract import (
    _tree_digest,
    is_canonical_document,
)
from content.release.canonical.object_transaction_delta import load_transaction_delta
from content.release.canonical.post_metadata_adoption import (
    PostMetadataAdoptionError,
    apply_post_metadata_adoption,
    build_post_metadata_adoption_package,
)
from core.article_package import compute_asset_manifest_sha256
from core.io import read_json

from support.media_fixture import admit_media_body
from support.post_object_transaction_fixture import (
    POST_REF,
    _admit_packaged_creator,
    _fixture,
    _isolate_creator_avatar_cas,
    _write_json,
    build_post_object_transaction_package,
)


def _source_reviewed_package(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    execution, unversioned_package, publish, _transaction_id = _fixture(tmp_path)
    versioned_ref = f"{POST_REF}/1"
    source_post = execution / "posts" / POST_REF
    temporary_post = source_post.with_name(f".{source_post.name}.source")
    source_post.replace(temporary_post)
    post = execution / "posts" / versioned_ref
    post.parent.mkdir(parents=True, exist_ok=True)
    temporary_post.replace(post)
    transaction_id = (
        f"{execution.name}--post-"
        f"{hashlib.sha256(versioned_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    package = execution / "evidence/object-transactions" / transaction_id
    if unversioned_package.exists():
        shutil.rmtree(unversioned_package)
    manifest_path = post / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(
        generator="image_evidence_pack",
        createdAt="2026-08-17T00:00:00Z",
        updatedAt="2026-08-17T00:00:00Z",
        publishTitle="西湖光影",
        publishSeq=1,
        sourceCollectionId="fixture:west-lake-image",
        creator="Fixture Photographer",
        collectionPageUrl="https://commons.wikimedia.org/wiki/File:Example.jpg",
        rightsAuditStatus="verified",
    )
    _write_json(manifest_path, manifest)
    provenance = {
        "schema": "quwoquan_data.provenance",
        "ref": manifest["topicId"],
        "final": {
            "contentType": "image",
            "publishTitle": manifest["publishTitle"],
            "publishSeq": 1,
            "generator": "image_evidence_pack",
            "model": "test-author-model",
            "agentRunId": "run-author-source",
            "agentId": "agent-author-source",
            "sessionTrace": None,
            "styleFamily": "",
            "openingStrategy": None,
            "entityRefs": list(manifest["entityRefs"]),
            "assetDigest": compute_asset_manifest_sha256(manifest["assets"]),
        },
        "agentInput": {
            "writingPack": "3.compose/writing_pack.json",
            "prompt": "4.draft/prompt.md",
            "title": manifest["title"],
            "styleFamily": "",
            "promptSha256": "sha256:" + "1" * 64,
            "writingPackSha256": "sha256:" + "2" * 64,
            "sourceBundleSha256": "sha256:" + "3" * 64,
            "draftSha256": "sha256:" + "4" * 64,
        },
        "originalSources": [
            {
                "path": "sources/commons/assets/cover.jpg",
                "url": manifest["sourceUrls"][0],
            }
        ],
        "gateResults": {"decision": "approved", "checks": {"imageGate": True}},
        "citedSourcePaths": ["sources/commons/assets/cover.jpg"],
    }
    provenance_path = post / "5.review/provenance.json"
    _write_json(provenance_path, provenance)
    attestation_path = post / "5.review/attestation.json"
    attestation = read_json(attestation_path)
    attestation["independentReviewer"].update(
        provider="test-provider",
        model="test-reviewer-model",
        runId="run-reviewer-source",
        resultHash="sha256:" + "5" * 64,
    )
    _write_json(attestation_path, attestation)
    _write_json(
        post / "5.review/evidence_index.json",
        {
            "schema": "quwoquan_data.evidence_index",
            "stage": "5.review",
            "executionId": execution.name,
            "executionBinding": "frozen",
            "objectRef": manifest["topicId"],
            "evidence": [
                {
                    "kind": "runtime_review",
                    "ref": "5.review/provenance.json",
                    "sha256": canonical_sha256(provenance),
                }
            ],
        },
    )
    _write_json(
        execution / "_shared/post_review_closure.json",
        {
            "schema": "quwoquan_data.post_review_closure",
            "executionId": execution.name,
            "carrier": "image",
            "approvedQuota": 1,
            "objects": [
                {
                    "objectRef": manifest["topicId"],
                    "publishRef": f"posts/{versioned_ref}",
                    "disposition": "qualified",
                    "issues": [],
                }
            ],
        },
    )
    _write_json(
        execution / "publish_ref.json",
        {
            "schema": "quwoquan_data.execution_publish_ref",
            "executionId": execution.name,
            "canonicalPublishRoot": "canonical-publish",
            "publishedRefs": {"entities": [], "posts": [versioned_ref]},
            "publishDiscards": [],
        },
    )
    for work_unit, run_id, agent_id in (
        ("author", "run-author-source", "agent-author-source"),
        ("reviewer", "run-reviewer-source", "agent-reviewer-source"),
    ):
        _write_json(
            execution
            / f"_shared/semantic_tasks/{work_unit}/attempts/0001.json",
            {
                "schema": "quwoquan_data.semantic_task_journal_attempt",
                "workUnitId": work_unit,
                "attempt": 1,
                "runId": run_id,
                "agentId": agent_id,
                "provider": "test-provider",
                "status": "finished",
                "started": True,
            },
        )
    _write_json(
        execution / "_shared/execution_state.json",
        {
            "schema": "quwoquan.content.execution_state",
            "executionId": execution.name,
            "completed": ["post_author", "post_review"],
            "status": "waiting_agent",
            "failedIssueRecords": [
                {
                    "code": "DATA.POOL.DELIVERY_UNAVAILABLE",
                    "recovery": "retry_delivery",
                }
            ],
        },
    )
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=versioned_ref,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    return execution, package, publish, versioned_ref


def _materialize_canonical_predecessor(package: Path, destination: Path) -> None:
    """Put v1 where an applied transaction would have left it.

    A transaction splits its package: documents become canonical files and every
    body it carries goes to the content library, so a predecessor staged by copying
    the whole packaged object would make publish own bytes no transaction could
    have put there.
    """

    source_object = package / "object"
    for source in sorted(source_object.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_object)
        if not is_canonical_document(relative):
            admit_media_body(source.read_bytes())
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for row in read_json(package / "object_transaction_package.json")["closure"][
        "casRefs"
    ]:
        admit_media_body((package / row["sourceRef"]).read_bytes())


def _without_allowed_manifest_changes(document: dict[str, object]) -> dict[str, object]:
    result = json.loads(json.dumps(document, ensure_ascii=False))
    result.pop("generator", None)
    result.pop("version", None)
    return result


def test_reviewed_image_metadata_adoption_is_forward_only_and_reuses_audit_package(
    tmp_path: Path,
) -> None:
    execution, source_package, publish, versioned_ref = _source_reviewed_package(
        tmp_path
    )
    source_package_digest = _tree_digest(source_package)
    source_semantic_digest = _tree_digest(execution / "_shared/semantic_tasks")
    output_root = tmp_path / "output"

    result = build_post_metadata_adoption_package(
        source_execution_root=execution,
        source_package_root=source_package,
        adoption_id="image-generator-forward-adoption",
        output_root=output_root,
        publish_root=publish,
    )

    target_package = Path(result["packageRoot"])
    source_manifest = read_json(source_package / "object/manifest.json")
    target_manifest = read_json(target_package / "object/manifest.json")
    assert target_manifest["contentId"] == source_manifest["contentId"]
    assert target_manifest["version"] == source_manifest["version"] + 1
    assert target_manifest["generator"] == "agent"
    assert _without_allowed_manifest_changes(target_manifest) == (
        _without_allowed_manifest_changes(source_manifest)
    )

    source_provenance = read_json(
        execution / "posts" / versioned_ref / "5.review/provenance.json"
    )
    target_provenance = read_json(target_package / "object/provenance.json")
    assert target_provenance["final"]["generator"] == "agent"
    target_provenance["final"]["generator"] = "image_evidence_pack"
    assert target_provenance == source_provenance

    for relative in (
        "attestation.json",
        "evidence_index.json",
        "rights.json",
        "source_catalog.json",
        "asset.refs.json",
        "creator.refs.json",
        "tag.refs.json",
    ):
        assert (target_package / "object" / relative).read_bytes() == (
            source_package / "object" / relative
        ).read_bytes()

    receipt = read_json(target_package / "object/metadata_adoption.json")
    assert receipt["allowedChanges"] == [
        "manifest.generator",
        "manifest.version",
        "provenance.final.generator",
        "poolRecord",
    ]
    assert receipt["invocationCounts"] == {
        "acquisition": 0,
        "semantic": 0,
        "author": 0,
        "review": 0,
    }
    assert receipt["source"]["semanticInventoryDigest"] == source_semantic_digest
    assert receipt["source"]["contentId"] == target_manifest["contentId"]
    assert receipt["target"]["contentVersion"] == 2

    record = latest_pool_record(target_package / "object", "content")
    assert record is not None
    assert record["recordSequence"] == 1
    assert record["contentVersion"] == 2
    assert record["objectRef"].endswith("/2")
    assert record["evidenceRef"] == "metadata_adoption.json"

    assert _tree_digest(source_package) == source_package_digest
    assert _tree_digest(execution / "_shared/semantic_tasks") == source_semantic_digest
    assert result["sourceObjectRef"].endswith("/1")
    assert result["targetObjectRef"].endswith("/2")


@pytest.mark.parametrize(
    ("remove", "error"),
    (
        ("provenance", "PROVENANCE_MISSING"),
        ("cas", "SOURCE_CAS_MISSING"),
        ("qualification", "SOURCE_NOT_QUALIFIED"),
        ("published", "SOURCE_NOT_PUBLISHED"),
    ),
)
def test_metadata_adoption_fails_closed_when_terminal_evidence_is_missing(
    tmp_path: Path,
    remove: str,
    error: str,
) -> None:
    execution, source_package, publish, versioned_ref = _source_reviewed_package(
        tmp_path
    )
    if remove == "provenance":
        (execution / "posts" / versioned_ref / "5.review/provenance.json").unlink()
    elif remove == "cas":
        package = read_json(source_package / "object_transaction_package.json")
        (source_package / package["closure"]["casRefs"][0]["sourceRef"]).unlink()
        manifest = read_json(source_package / "object/manifest.json")
        (execution / manifest["assets"][0]["sourceAssetRef"]).unlink(missing_ok=True)
    elif remove == "qualification":
        closure_path = execution / "_shared/post_review_closure.json"
        closure = read_json(closure_path)
        closure["objects"][0]["disposition"] = "discarded"
        _write_json(closure_path, closure)
    else:
        publish_ref_path = execution / "publish_ref.json"
        publish_ref = read_json(publish_ref_path)
        publish_ref["publishedRefs"]["posts"] = []
        _write_json(publish_ref_path, publish_ref)

    with pytest.raises(PostMetadataAdoptionError, match=error):
        build_post_metadata_adoption_package(
            source_execution_root=execution,
            source_package_root=source_package,
            adoption_id=f"missing-{remove}",
            output_root=tmp_path / "output",
            publish_root=publish,
        )
    assert not (
        tmp_path
        / "output/data/local/workspace/post-metadata-adoptions"
        / f"missing-{remove}"
    ).exists()
    assert not (publish / "posts" / versioned_ref.rsplit("/", 1)[0] / "2").exists()


def test_metadata_adoption_create_once_rejects_snapshot_tamper(
    tmp_path: Path,
) -> None:
    execution, source_package, publish, _versioned_ref = _source_reviewed_package(
        tmp_path
    )
    output_root = tmp_path / "output"
    build_post_metadata_adoption_package(
        source_execution_root=execution,
        source_package_root=source_package,
        adoption_id="tamper-source-snapshot",
        output_root=output_root,
        publish_root=publish,
    )
    snapshot = (
        output_root
        / "data/local/workspace/post-metadata-adoptions/tamper-source-snapshot"
        / "source-evidence/provenance.json"
    )
    snapshot.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PostMetadataAdoptionError, match="CREATE_ONCE_CONFLICT"):
        build_post_metadata_adoption_package(
            source_execution_root=execution,
            source_package_root=source_package,
            adoption_id="tamper-source-snapshot",
            output_root=output_root,
            publish_root=publish,
        )


def test_metadata_adoption_can_create_v2_from_package_when_v1_is_not_materialized(
    tmp_path: Path,
) -> None:
    execution, source_package, publish, _versioned_ref = _source_reviewed_package(
        tmp_path
    )
    output_root = tmp_path / "output"

    result = apply_post_metadata_adoption(
        source_execution_root=execution,
        source_package_root=source_package,
        adoption_id="image-generator-forward-without-canonical",
        output_root=output_root,
        publish_root=publish,
    )

    assert result["status"] == "applied"
    assert result["targetObjectRef"].endswith("/2")
    assert (
        publish / "posts" / result["targetObjectRef"] / "manifest.json"
    ).is_file()


def test_metadata_adoption_uses_existing_audit_apply_and_rollback_without_touching_v1(
    tmp_path: Path,
) -> None:
    execution, source_package, publish, versioned_ref = _source_reviewed_package(
        tmp_path
    )
    _materialize_canonical_predecessor(
        source_package,
        publish / "posts" / versioned_ref,
    )
    source_canonical = publish / "posts" / versioned_ref
    source_digest = _tree_digest(source_canonical)
    output_root = tmp_path / "output"

    result = apply_post_metadata_adoption(
        source_execution_root=execution,
        source_package_root=source_package,
        adoption_id="image-generator-forward-apply",
        output_root=output_root,
        publish_root=publish,
    )

    target = publish / "posts" / result["targetObjectRef"]
    assert result["status"] == "applied"
    assert target.is_dir()
    assert _tree_digest(source_canonical) == source_digest
    assert read_json(target / "manifest.json")["generator"] == "agent"

    replay = apply_post_metadata_adoption(
        source_execution_root=execution,
        source_package_root=source_package,
        adoption_id="image-generator-forward-apply",
        output_root=output_root,
        publish_root=publish,
    )
    assert replay["idempotent"] is True
    assert replay["canonicalObjectSha256"] == result["canonicalObjectSha256"]
    run_root = (
        output_root
        / "data/local/workspace/object-transactions"
        / result["transactionId"]
    )
    delta = load_transaction_delta(run_root=run_root)
    assert {row["operation"] for row in delta["entries"]} == {"create"}
    assert all(
        not row["destination"].startswith(f"posts/{versioned_ref}/")
        for row in delta["entries"]
    )
    assert not any(
        row["destination"].startswith("media/objects/")
        for row in delta["entries"]
    )

    selection = select_all_publishable_release_posts(
        publish_root=publish,
        post_refs=[versioned_ref, result["targetObjectRef"]],
        release_class="research",
        strict_admission=False,
    )
    assert selection.post_refs == (result["targetObjectRef"],)
    assert any(
        exclusion.post_ref == versioned_ref
        and exclusion.code == "DATA.POOL.GENERATOR_PROVENANCE_INVALID"
        for exclusion in selection.excluded
    )

    rollback = rollback_object_transaction(
        publish_root=publish,
        output_root=output_root,
        transaction_id=result["transactionId"],
    )
    assert rollback["status"] == "rolled_back"
    assert not target.exists()
    assert _tree_digest(source_canonical) == source_digest
