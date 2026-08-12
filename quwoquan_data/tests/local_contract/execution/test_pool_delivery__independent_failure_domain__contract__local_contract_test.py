"""Pool delivery preserves reviewed truth across transport outages.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.closure.pool_delivery import (
    validate_pool_delivery_intent_for_job,
    write_pool_delivery_intent,
)
from content.execution.controller.execute import drain_pool_delivery as delivery_drain
from content.execution.preflight import pool_delivery as delivery_preflight
from content.execution.queue.reliabletask import jobs as reliable_jobs
from content.execution.queue.reliabletask.transport import ReliableTaskFleetTransport
from content.execution.queue.reliabletask import fleet as reliabletask_fleet
from content.execution.queue.reliabletask import publish_reconciliation
from content.release.canonical.object_source_identity import source_identity_digest
from content.release.canonical.pool_delivery_intent_inspection import (
    inspect_pool_delivery_intents,
)
from content.templates.registry import TemplateRegistry
from core.control_types import (
    ExecutionStage,
    ExecutionStateStatus,
    QueueBackend,
    QueueJobStage,
    ReliableTaskDispatchStatus,
)
from core.data_issue import (
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)
from governance.creators.assignment import creator_assignment_from_profile
from governance.creators.assignment import creator_assignment_issues

EXECUTION_ID = "20260811--travel-article-m100--china--scale-201"
_DIGEST = "sha256:" + "a" * 64
DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)


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
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def _backend_envelope() -> dict[str, object]:
    return {
        "poolDeliveryBackend": "reliabletask",
        "envelopeDigest": _DIGEST,
        "scaleClass": "M100_PLUS",
    }


def _transport() -> ReliableTaskFleetTransport:
    return ReliableTaskFleetTransport(
        target="data-local",
        mongo_uri="mongodb://127.0.0.1:18440/?directConnection=true",
        redis_addr="127.0.0.1:18450",
    )


def _runtime_binding():
    campaign = {
        "rootExecutionId": EXECUTION_ID,
        "campaignRunId": "campaign-pool-delivery-001",
        "campaignGeneration": 3,
        "campaignFencingToken": "sha256:" + "b" * 64,
        "campaignPlanDigest": "sha256:" + "d" * 64,
        "campaignSourceRevision": "sha256:" + "e" * 64,
        "campaignSourceDigest": "sha256:" + "f" * 64,
        "campaignEntityCatalogDigest": "sha256:" + "1" * 64,
    }
    return (
        {
            "observerBinaryRef": "data/local/cache/worker/data-content-worker",
            "observerBinarySha256": "sha256:" + "c" * 64,
        },
        3,
        "sha256:" + "b" * 64,
        campaign,
        _transport(),
    )


def test_pool_delivery_preflight__standalone_m100_dispatch_uses_exact_pool_fence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen_selection = {
        "carrier": "article",
        "candidateIds": ["article-1"],
        "candidateCount": 1,
    }
    frozen_selection["selectionDigest"] = delivery_preflight._digest(
        frozen_selection
    )
    request = {
        "scaleSourcePool": {
            "sourceDigest": "sha256:" + "9" * 64,
            "entityCatalogDigest": "sha256:" + "2" * 64,
            "planRef": "data/local/workspace/source-acquisition/pool.json",
            "planDigest": "sha256:" + "3" * 64,
            "planFileSha256": "sha256:" + "4" * 64,
        },
        "sourcePoolEvidenceRootRef": "data/local/workspace/source-acquisition",
        "sourcePoolSelection": frozen_selection,
    }
    plan = tmp_path / "0.plan"
    plan.mkdir(parents=True)
    (plan / "request.json").write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(
        delivery_preflight,
        "execution_external_input_envelope_path",
        lambda _root: tmp_path / "missing-external-input.json",
    )
    monkeypatch.setattr(delivery_preflight, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_execution_manifest",
        lambda _execution_id: {
            "sourceDigest": {"digest": "sha256:" + "1" * 64},
            "executionBundle": {"digest": "sha256:" + "6" * 64},
        },
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_target_set",
        lambda _execution_id: {"entityCatalogDigest": "sha256:" + "2" * 64},
    )
    binding = SimpleNamespace(
        as_document=lambda: {
            "observerBinaryRef": "data/local/cache/worker/data-content-worker",
            "observerBinarySha256": "sha256:" + "7" * 64,
        }
    )
    monkeypatch.setattr(
        delivery_preflight,
        "prepare_controller_observer_binary",
        lambda: SimpleNamespace(binding=binding),
    )
    validated: list[tuple[object, str]] = []
    monkeypatch.setattr(
        "content.execution.campaign.source_pool_binding.validate_bound_scale_source_pool",
        lambda pool, *, evidence_root_ref, output_root: (
            validated.append((pool, evidence_root_ref))
            or {
                "candidates": [
                    {"carrier": "article", "candidateId": "article-1"}
                ]
            }
        ),
    )

    worker, generation, token, campaign, fleet = (
        delivery_preflight._delivery_runtime_binding(
            EXECUTION_ID,
            {
                "scaleClass": "M100_PLUS",
                "envelopeDigest": "sha256:" + "8" * 64,
            },
        )
    )

    assert worker["observerBinarySha256"] == "sha256:" + "7" * 64
    assert generation == 1
    assert token == "sha256:" + "8" * 64
    assert campaign is None
    assert fleet is None
    assert validated == [
        (request["scaleSourcePool"], "data/local/workspace/source-acquisition")
    ]


def test_publish_fleet_delivers_partial_reviewed_closure_below_semantic_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "content.execution.store.load_spec",
        lambda _execution_id: {"executionPolicy": {"approvedQuota": 12}},
    )
    monkeypatch.setattr(reliabletask_fleet, "_load_jobs", lambda _execution_id: [])

    assert (
        reliabletask_fleet._remaining_quota(
            EXECUTION_ID,
            QueueJobStage.PUBLISH,
            active_job_count=5,
        )
        == 5
    )
    with pytest.raises(ValueError, match="候选池耗尽"):
        reliabletask_fleet._remaining_quota(
            EXECUTION_ID,
            QueueJobStage.AUTHOR,
            active_job_count=5,
        )


def test_pool_delivery_preflight__binds_transport_generation_fence_and_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: _runtime_binding(),
    )
    report = delivery_preflight.build_pool_delivery_preflight_report(
        EXECUTION_ID,
        transport_resolver=_transport,
        fleet_probe=lambda: {
            "target": "data-local",
            "ready": True,
            "mongo": True,
            "redis": True,
            "owned": True,
        },
    )
    receipt = delivery_preflight.build_pool_delivery_preflight_receipt(report)

    assert report["preflightProfile"] == "pool-delivery"
    assert report["poolDeliveryReady"] is True
    assert "semanticExecutionReady" not in receipt
    assert "provider" not in receipt
    delivery_preflight.validate_pool_delivery_preflight_receipt(
        receipt,
        expected_execution_id=EXECUTION_ID,
        minimum_generation=3,
        expected_fencing_token="sha256:" + "b" * 64,
    )
    with pytest.raises(ValueError, match="generation is stale"):
        delivery_preflight.validate_pool_delivery_preflight_receipt(
            receipt,
            minimum_generation=4,
        )
    with pytest.raises(ValueError, match="fencing token is stale"):
        delivery_preflight.validate_pool_delivery_preflight_receipt(
            receipt,
            expected_fencing_token="sha256:" + "d" * 64,
        )


def test_pool_delivery_preflight__transport_down_is_delivery_pending_not_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: _runtime_binding(),
    )
    report = delivery_preflight.build_pool_delivery_preflight_report(
        EXECUTION_ID,
        transport_resolver=_transport,
        fleet_probe=lambda: {
            "target": "data-local",
            "ready": False,
            "mongo": False,
            "redis": True,
            "owned": True,
        },
    )

    assert report["poolDeliveryReady"] is False
    assert report["issueCode"] == "DATA.POOL.DELIVERY_UNAVAILABLE"
    with pytest.raises(ValueError, match="requires ready evidence"):
        delivery_preflight.build_pool_delivery_preflight_receipt(report)


def test_pool_delivery_drain__down_then_ready_consumes_same_intent_without_semantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(stage=QueueJobStage.PUBLISH, job_id="publish-001")
    intent_id = "sha256:" + "7" * 64
    dispatch_calls: list[tuple[str, ExecutionStage]] = []
    semantic_calls: list[str] = []
    outcomes = iter(
        (
            SimpleNamespace(
                status=ReliableTaskDispatchStatus.WAITING,
                attempted_count=0,
                completed_count=0,
                issues=(
                    data_issue(
                        DataIssueCode.POOL_DELIVERY_UNAVAILABLE,
                        stage=DataIssueStage.PUBLISH,
                        recovery=DataRecoveryAction.RETRY_DELIVERY,
                        message="data-local transport unavailable",
                    ),
                ),
            ),
            SimpleNamespace(
                status=ReliableTaskDispatchStatus.COMPLETED,
                attempted_count=1,
                completed_count=1,
                issues=(),
            ),
        )
    )
    frozen_spec = SimpleNamespace(
        execution_policy=SimpleNamespace(required_workers=1)
    )

    monkeypatch.setattr(
        delivery_drain, "load_frozen_execution_manifest", lambda _execution_id: {}
    )
    monkeypatch.setattr(delivery_drain.store, "load_spec", lambda _execution_id: {})
    monkeypatch.setattr(
        delivery_drain.ExecutionSpec,
        "from_mapping",
        lambda _payload: frozen_spec,
    )
    monkeypatch.setattr(
        delivery_drain,
        "ExecutionContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        delivery_drain, "coverage_entity_ids", lambda _payload: ("chengdu",)
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: (job,))
    monkeypatch.setattr(
        delivery_drain,
        "validate_pool_delivery_intent_for_job",
        lambda candidate: {"intentId": intent_id} if candidate is job else {},
    )

    def dispatch(ctx, stage):
        dispatch_calls.append((ctx.execution_id, stage))
        return next(outcomes)

    monkeypatch.setattr(
        delivery_drain, "dispatch_reliabletask_checkpoint", dispatch
    )
    monkeypatch.setattr(
        "content.execution.agent.agent_runner._managed_agent_runner_for_provider",
        lambda *_args, **_kwargs: semantic_calls.append("called"),
    )

    pending = delivery_drain.drain_pool_delivery(EXECUTION_ID)
    recovered = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert pending["status"] == "waiting"
    assert pending["issueCodes"] == ["DATA.POOL.DELIVERY_UNAVAILABLE"]
    assert recovered["status"] == "completed"
    assert pending["intentIds"] == recovered["intentIds"] == [intent_id]
    assert dispatch_calls == [
        (EXECUTION_ID, ExecutionStage.PUBLISH),
        (EXECUTION_ID, ExecutionStage.PUBLISH),
    ]
    assert semantic_calls == []


def test_pool_delivery_drain__reconciles_remote_dead_receipt_after_local_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(stage=QueueJobStage.PUBLISH, job_id="publish-001")
    intent_id = "sha256:" + "7" * 64
    frozen_spec = SimpleNamespace(
        execution_policy=SimpleNamespace(required_workers=1)
    )
    report = SimpleNamespace(
        passed=True,
        succeeded=1,
        outcomes=(SimpleNamespace(attempts=3),),
    )
    monkeypatch.setattr(
        delivery_drain, "load_frozen_execution_manifest", lambda _execution_id: {}
    )
    monkeypatch.setattr(delivery_drain.store, "load_spec", lambda _execution_id: {})
    monkeypatch.setattr(
        delivery_drain.ExecutionSpec,
        "from_mapping",
        lambda _payload: frozen_spec,
    )
    monkeypatch.setattr(
        delivery_drain,
        "ExecutionContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        delivery_drain, "coverage_entity_ids", lambda _payload: ("chengdu",)
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: (job,))
    monkeypatch.setattr(
        delivery_drain,
        "validate_pool_delivery_intent_for_job",
        lambda candidate: {"intentId": intent_id} if candidate is job else {},
    )
    monkeypatch.setattr(
        delivery_drain, "dispatch_reliabletask_checkpoint", lambda *_args: None
    )
    reconcile_calls: list[tuple[str, int]] = []

    def reconcile(execution_id: str, *, workers: int, **_kwargs):
        reconcile_calls.append((execution_id, workers))
        return report

    monkeypatch.setattr(
        publish_reconciliation,
        "reconcile_frozen_publish_recovery",
        reconcile,
    )

    result = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert result["status"] == "completed"
    assert result["executionStatePreserved"] is True
    assert result["qualifiedCount"] == result["completedCount"] == 1
    assert result["attemptedCount"] == 3
    assert result["intentIds"] == [intent_id]
    assert reconcile_calls == [(EXECUTION_ID, 1)]


def test_pool_delivery_drain__pre_capsule_promotes_only_qualified_reviewed_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qualified = SimpleNamespace(
        object_ref="qualified-object",
        publish_ref="posts/article/china/travel/qualified-post",
    )
    discarded = SimpleNamespace(
        object_ref="discarded-object",
        publish_ref="posts/article/china/travel/discarded-post",
    )
    closure = SimpleNamespace(
        carrier="article",
        qualified=(qualified,),
        discarded=(discarded,),
    )
    state = SimpleNamespace(
        status=ExecutionStateStatus.MANUAL_REQUIRED,
        last_failed_stage="publish",
    )
    intent = {"intentId": "sha256:" + "8" * 64}
    writes: list[tuple[str, str]] = []
    promotions: list[str] = []
    canonical = {
        "transactionId": "transaction-qualified",
        "applyReportRef": "data/local/qualified/apply_report.json",
        "canonicalObjectRef": "posts/article/china/travel/qualified-post",
        "canonicalObjectSha256": "sha256:" + "9" * 64,
        "objectClosureDigest": "sha256:" + "a" * 64,
    }

    monkeypatch.setattr(
        delivery_drain,
        "load_frozen_execution_manifest",
        lambda _execution_id: {
            "sourceDigest": {"digest": _DIGEST},
            "executionBundle": {"digest": _DIGEST},
        },
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: ())
    monkeypatch.setattr(delivery_drain, "load_execution_state", lambda _id: state)
    monkeypatch.setattr(
        "content.execution.closure.post_review.indexed_post_targets",
        lambda _id: {
            qualified.object_ref: qualified.publish_ref,
            discarded.object_ref: discarded.publish_ref,
        },
    )
    monkeypatch.setattr(
        "content.execution.closure.post_review.load_post_review_closure",
        lambda *_args, **_kwargs: closure,
    )

    def write_intent(_execution_id, *, object_ref, content_object_dir, **_kwargs):
        writes.append((object_ref, content_object_dir))
        return intent, Path("intent.json")

    def promote(_execution_id, post_ref, *, pool_delivery_intent):
        assert pool_delivery_intent is intent
        promotions.append(post_ref)
        return canonical

    monkeypatch.setattr(
        "content.execution.closure.pool_delivery.write_pool_delivery_intent",
        write_intent,
    )
    monkeypatch.setattr(
        "content.release.canonical.post_promotion.promote_post_object",
        promote,
    )

    result = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert result["status"] == "completed"
    assert result["recoveryMode"] == "reviewed_delivery_only"
    assert result["executionStatePreserved"] is True
    assert result["qualifiedCount"] == result["attemptedCount"] == 1
    assert result["discardedCount"] == 1
    assert result["completedCount"] == 1
    assert writes == [(qualified.object_ref, qualified.publish_ref)]
    assert promotions == [qualified.publish_ref]
    assert result["canonicalObjects"] == [canonical]


@pytest.mark.parametrize(
    ("manifest", "status", "last_failed_stage"),
    (
        ({"sourceDigest": {"digest": _DIGEST}}, ExecutionStateStatus.MANUAL_REQUIRED, "publish"),
        (
            {"sourceDigest": {"digest": _DIGEST}, "executionBundle": {"digest": _DIGEST}},
            ExecutionStateStatus.RUNNING,
            "publish",
        ),
        (
            {"sourceDigest": {"digest": _DIGEST}, "executionBundle": {"digest": _DIGEST}},
            ExecutionStateStatus.MANUAL_REQUIRED,
            "post_review",
        ),
    ),
)
def test_pool_delivery_drain__pre_capsule_admission_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, object],
    status: ExecutionStateStatus,
    last_failed_stage: str,
) -> None:
    monkeypatch.setattr(
        delivery_drain,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: ())
    monkeypatch.setattr(
        delivery_drain,
        "load_execution_state",
        lambda _id: SimpleNamespace(
            status=status,
            last_failed_stage=last_failed_stage,
        ),
    )

    with pytest.raises(ValueError, match="DATA.POOL.DELIVERY_ONLY_INVALID"):
        delivery_drain.drain_pool_delivery(EXECUTION_ID)


def test_pool_delivery_drain_is_exposed_only_through_canonical_data_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(DATA_ROOT / "scripts/cli.py"),
            "task",
            "drain-pool-delivery",
            "--help",
        ],
        cwd=DATA_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--execution-id" in completed.stdout


def test_m100_pool_delivery_preflight__missing_worker_context_is_typed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("observer unavailable")),
    )

    report = delivery_preflight.build_pool_delivery_preflight_report(EXECUTION_ID)

    assert report["poolDeliveryReady"] is False
    assert report["issueCode"] == "DATA.POOL.DELIVERY_UNAVAILABLE"
    assert "workerRef" not in report


def test_pool_delivery_preflight_recovers_frozen_campaign_fence_without_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QWQ_CAMPAIGN_ROOT_EXECUTION_ID", raising=False)
    root_execution_id = (
        "20260811--travel-homepage-m100--china--scale-205"
    )
    execution_root = tmp_path / "execution"
    envelope_path = execution_root / "0.plan/campaign_external_input_envelope.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    stable_plan = {
        "rootExecutionId": root_execution_id,
        "executionIds": {"article": EXECUTION_ID},
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "distributedRun": {
            "campaignRunId": "campaign-run-001",
            "campaignGeneration": 4,
            "campaignFencingToken": "sha256:" + "4" * 64,
        },
    }
    plan = {
        **stable_plan,
        "planDigest": delivery_preflight.sha256_payload(stable_plan),
    }
    campaigns_root = tmp_path / "campaigns"
    plan_path = campaigns_root / root_execution_id / "campaign_plan.json"
    _write_json(plan_path, plan)
    external = {
        "rootExecutionId": root_execution_id,
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "planDigest": plan["planDigest"],
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    worker = {
        "observerBinaryRef": "data/local/cache/worker/data-content-worker",
        "observerBinarySha256": "sha256:" + "5" * 64,
    }
    transport = _transport()

    monkeypatch.setattr(delivery_preflight, "execution_root", lambda _id: execution_root)
    monkeypatch.setattr(
        delivery_preflight,
        "execution_external_input_envelope_path",
        lambda _root: envelope_path,
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_external_input_envelope",
        lambda _path: external,
    )
    monkeypatch.setattr(
        delivery_preflight.CampaignRuntimePaths,
        "defaults",
        lambda: SimpleNamespace(campaigns_root=campaigns_root),
    )
    monkeypatch.setattr(delivery_preflight, "assert_valid", lambda *_a, **_k: None)
    monkeypatch.setattr(
        delivery_preflight,
        "read_runtime_snapshot",
        lambda *_a: {
            "rootExecutionId": root_execution_id,
            "planDigest": plan["planDigest"],
            "runId": "campaign-run-001",
            "generation": 4,
            "fencingToken": "sha256:" + "4" * 64,
        },
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_execution_manifest",
        lambda _id: {"sourceDigest": {"digest": plan["sourceDigest"]}},
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_target_set",
        lambda _id: {"entityCatalogDigest": plan["entityCatalogDigest"]},
    )
    monkeypatch.setattr(
        delivery_preflight,
        "resolve_campaign_observer_binary",
        lambda *_a, **_k: SimpleNamespace(as_document=lambda: worker),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "resolve_campaign_fleet_transport",
        lambda *_a, **_k: SimpleNamespace(transport=transport),
    )

    recovered_worker, generation, fence, campaign, recovered_transport = (
        delivery_preflight._delivery_runtime_binding(
            EXECUTION_ID,
            _backend_envelope(),
        )
    )

    assert recovered_worker == worker
    assert generation == 4
    assert fence == "sha256:" + "4" * 64
    assert campaign["rootExecutionId"] == root_execution_id
    assert recovered_transport == transport
