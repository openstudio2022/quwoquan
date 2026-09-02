"""Pool delivery preserves reviewed truth across transport outages.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.execution.closure.pool_delivery import write_pool_delivery_intent
from content.execution.queue.reliabletask import jobs as reliable_jobs
from content.execution.queue.reliabletask.publish import (
    validate_pool_delivery_intent_for_job,
)
from content.release.canonical.object_source_identity import source_identity_digest
from content.release.canonical.pool_delivery_intent_inspection import (
    inspect_pool_delivery_intents,
)
from content.templates.registry import TemplateRegistry
from core.control_types import (
    QueueBackend,
    QueueJobStage,
)
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)
from governance.creators.assignment import creator_assignment_from_profile
from governance.creators.assignment import creator_assignment_issues
from support.pool_delivery_fixture import EXECUTION_ID, _DIGEST, _write_json


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "Research Creator",
        "originalCreatorProfileUrl": None,
        "platform": "Research Archive",
        "sourcePostUrl": "https://example.invalid/research/post",
        "originalAssetUrl": "https://example.invalid/research/asset.jpg",
        "attributionText": "Research Creator / internal research",
        "rightsBasis": "research-only evaluation",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": None,
        "termsUrl": None,
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": [],
    }



def _reviewed_post(root: Path) -> str:
    relative = "posts/article/china/travel/reviewed-post"
    object_dir = root / relative
    creator = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_travel_blogger_001"]
    )
    _write_json(
        object_dir / "manifest.json",
        {
            "contentType": "article",
            "contentId": "qwq_data_reviewed_post",
            "version": 1,
            "vertical": "travel",
            **creator,
            "entityRefs": ["/entity/place/china/chengdu"],
            "normalizedEntityRefs": ["entity:city:chengdu"],
            "tagRefs": ["Topic/旅行/玩法/文化体验"],
            "sourceAttribution": _source_attribution(),
            "assets": [{"ref": "assets/cover.jpg", "sha256": _DIGEST}],
        },
    )
    _write_json(
        object_dir / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    return relative


def _write_reviewed_intent(
    root: Path,
    *,
    execution_id: str = EXECUTION_ID,
    relative: str | None = None,
) -> tuple[dict[str, object], Path]:
    return write_pool_delivery_intent(
        execution_id,
        carrier="article",
        object_ref="reviewed-post",
        content_object_dir=relative or _reviewed_post(root),
        root=root,
        publish_root=root / "canonical-publish",
        reservation_root=root / "delivery-reservations",
    )


def _write_execution_identity(task_root: Path) -> None:
    source_digest = "sha256:" + "1" * 64
    entity_catalog_digest = "sha256:" + "2" * 64
    source_revision = content_source_revision(
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    target = {
        "executionId": EXECUTION_ID,
        "entityCatalogDigest": entity_catalog_digest,
    }
    target_encoded = json.dumps(
        target,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _write_json(task_root / "0.plan/target_set.json", target)
    _write_json(
        task_root / "execution_manifest.json",
        {
            "executionId": EXECUTION_ID,
            "sourceDigest": SourceDefinitionSnapshot(source_digest).to_document(),
            "executionBundle": ExecutionBundleIdentity(_DIGEST).to_document(),
            "sourceRevision": source_revision,
            "entityCatalogDigest": entity_catalog_digest,
            "sourceIdentityDigest": source_identity_digest(
                {
                    "executionId": EXECUTION_ID,
                    "sourceRevision": source_revision,
                    "sourceDigest": source_digest,
                    "entityCatalogDigest": entity_catalog_digest,
                }
            ),
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": hashlib.sha256(target_encoded).hexdigest(),
        },
    )



def test_pool_delivery_intent__create_once_preserves_review_and_rejects_drift(
    tmp_path: Path,
) -> None:
    relative = _reviewed_post(tmp_path)
    first, path = _write_reviewed_intent(tmp_path, relative=relative)
    repeated, repeated_path = _write_reviewed_intent(tmp_path, relative=relative)

    assert repeated == first
    assert repeated_path == path
    assert first["reviewEvidenceSha256"].startswith("sha256:")
    assert first["transactionInputDigest"].startswith("sha256:")
    assert first["contentId"].startswith("qwq_data_")
    assert first["version"] == 1
    assert first["creatorBindingMode"] == "manifest_exact"
    assert first["creatorBinding"]["creatorProfileId"] == "qwq_creator_travel_blogger_001"

    manifest_path = tmp_path / relative / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceAttribution"]["rightsBasis"] = "drifted rights basis"
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="DATA.POOL.IDEMPOTENCY_CONFLICT"):
        _write_reviewed_intent(tmp_path, relative=relative)


def test_pool_delivery_intent__semantic_fit_only_rebinds_registered_strong_creator(
    tmp_path: Path,
) -> None:
    relative = _reviewed_post(tmp_path)
    manifest_path = tmp_path / relative / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    highland = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_highland_travel_blogger_001"]
    )
    manifest.update(highland)
    manifest["tagRefs"] = [
        "Topic/旅行/玩法/观光游览",
        "Format/内容角度/攻略",
    ]
    _write_json(manifest_path, manifest)

    intent, _path = _write_reviewed_intent(tmp_path, relative=relative)

    assert intent["creatorBindingMode"] == "semantic_fit_recovery"
    assert intent["creatorBinding"]["creatorProfileId"] == "qwq_creator_pro_guide_001"
    assert intent["creatorBinding"]["creatorProfileId"] != manifest["creatorProfileId"]
    assert creator_assignment_issues(
        intent["creatorBinding"],
        carrier="article",
        content_vertical="travel",
        content_tag_refs=manifest["tagRefs"],
    ) == []


def test_pool_delivery_intent__semantic_recovery_rejects_nonsemantic_creator_drift(
    tmp_path: Path,
) -> None:
    relative = _reviewed_post(tmp_path)
    manifest_path = tmp_path / relative / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    highland = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_highland_travel_blogger_001"]
    )
    manifest.update(highland)
    manifest["authorId"] = "not-the-registered-author"
    manifest["tagRefs"] = ["Topic/旅行/玩法/观光游览"]
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="authorId does not match creator registry"):
        _write_reviewed_intent(tmp_path, relative=relative)


def test_pool_delivery_intent__rejects_symlinked_object_input(tmp_path: Path) -> None:
    source = tmp_path / "physical"
    relative = _reviewed_post(source)
    alias = tmp_path / "posts"
    alias.symlink_to(source / "posts", target_is_directory=True)

    with pytest.raises(ValueError, match="cannot traverse symlinks"):
        write_pool_delivery_intent(
            EXECUTION_ID,
            carrier="article",
            object_ref="reviewed-post",
            content_object_dir=relative,
            root=tmp_path,
            publish_root=tmp_path / "canonical-publish",
            reservation_root=tmp_path / "delivery-reservations",
        )


def test_pool_delivery_identity_reservation__concurrent_executions_do_not_duplicate(
    tmp_path: Path,
) -> None:
    relative = _reviewed_post(tmp_path)
    execution_ids = (EXECUTION_ID, EXECUTION_ID)

    def reserve(execution_id: str) -> dict[str, object]:
        intent, _path = write_pool_delivery_intent(
            execution_id,
            carrier="article",
            object_ref="reviewed-post",
            content_object_dir=relative,
            root=tmp_path,
            publish_root=tmp_path / "canonical-publish",
            reservation_root=tmp_path / "delivery-reservations",
        )
        return intent

    with ThreadPoolExecutor(max_workers=2) as executor:
        intents = tuple(executor.map(reserve, execution_ids))

    assert {intent["contentId"] for intent in intents} == {
        intents[0]["contentId"]
    }
    assert {intent["version"] for intent in intents} == {1}
    assert len({intent["poolIdentityReservationId"] for intent in intents}) == 1
    assert len({intent["intentId"] for intent in intents}) == 1


def test_pending_inspection_projects_physically_validated_candidate_object_path(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    task_root = output_root / "data/tasks" / EXECUTION_ID
    relative = _reviewed_post(task_root)
    _write_execution_identity(task_root)
    intent, _path = write_pool_delivery_intent(
        EXECUTION_ID,
        carrier="article",
        object_ref="reviewed-post",
        content_object_dir=relative,
        root=task_root,
        publish_root=tmp_path / "canonical-publish",
        reservation_root=tmp_path / "delivery-reservations",
    )

    pending, issues = inspect_pool_delivery_intents(
        output_root=output_root,
        publish_root=tmp_path / "canonical-publish",
        execution_ids=(EXECUTION_ID,),
    )

    assert issues == []
    assert pending[0]["objectRef"] == "reviewed-post"
    assert pending[0]["contentObjectDir"] == relative
    assert pending[0]["contentObjectDir"] == intent["contentObjectDir"]
    consumed_object_refs = frozenset(
        str(row["contentObjectDir"]).strip("/") for row in pending
    )
    assert relative in consumed_object_refs
    assert pending[0]["objectRef"] not in consumed_object_refs


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("sourceAttribution", None, "sourceAttribution"),
        ("creatorProfileId", None, "creatorAssignment.creatorProfileId required"),
        ("normalizedEntityRefs", [], "normalized entityRefs"),
        ("tagRefs", [], "tagRefs"),
    ),
)
def test_pool_delivery_intent__requires_attribution_creator_entity_tag_closure(
    tmp_path: Path,
    field: str,
    replacement: object,
    message: str,
) -> None:
    relative = _reviewed_post(tmp_path)
    manifest_path = tmp_path / relative / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if replacement is None:
        manifest.pop(field, None)
    else:
        manifest[field] = replacement
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match=message):
        write_pool_delivery_intent(
            EXECUTION_ID,
            carrier="article",
            object_ref="reviewed-post",
            content_object_dir=relative,
            root=tmp_path,
            publish_root=tmp_path / "canonical-publish",
            reservation_root=tmp_path / "delivery-reservations",
        )


def test_publish_job__binds_create_once_intent_independent_from_semantic_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "entities/place/city/chengdu"
    object_dir = tmp_path / relative
    creator = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_travel_blogger_001"]
    )
    attribution = _source_attribution()
    _write_json(
        object_dir / "_entity.json",
        {
            "entityRef": "/entity/place/city/chengdu",
            **creator,
            "tagRefs": ["Topic/旅行/玩法/文化体验"],
            "sourceRefs": ["source://chengdu"],
            "sourceAttribution": attribution,
        },
    )
    _write_json(
        object_dir / "manifest.json",
        {"assets": [], "sourceAttribution": attribution},
    )
    _write_json(
        object_dir / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    captured: dict[str, object] = {}

    def enqueue(*_args, **kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(
        reliable_jobs,
        "uses_reliabletask",
        lambda _ctx, *, stage=None: stage is QueueJobStage.PUBLISH,
    )
    monkeypatch.setattr(reliable_jobs, "enqueue_ref_job", enqueue)
    monkeypatch.setattr("core.paths.execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        "content.execution.closure.pool_delivery.execution_root",
        lambda _execution_id: tmp_path,
    )
    ctx = type("Context", (), {"execution_id": EXECUTION_ID})()

    jobs = reliable_jobs.prepare_reliable_publish_jobs(
        ctx,
        homepage_refs={"/entity/place/city/chengdu"},
    )

    assert len(jobs) == 1
    assert captured["queue_backend"] is QueueBackend.RELIABLE_TASK
    metadata = captured["meta"]
    assert metadata["poolDeliveryIntentDigest"].startswith("sha256:")
    intent_path = tmp_path / metadata["poolDeliveryIntentRef"]
    assert intent_path.is_file()

    class Job:
        execution_id = EXECUTION_ID
        job_id = "publish-homepage-001"
        ref = "/entity/place/city/chengdu"
        carrier = type("Carrier", (), {"value": "homepage"})()
        content_object_dir = relative

        @staticmethod
        def metadata_document() -> dict[str, object]:
            return dict(metadata)

    validated = validate_pool_delivery_intent_for_job(Job())
    assert validated["intentId"] == metadata["poolDeliveryIntentDigest"]
    metadata["sourceRevision"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="job routing drift"):
        validate_pool_delivery_intent_for_job(Job())
