"""Pre-acquisition revisions and source guards share one canonical identity."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.execution.campaign import external_inputs as campaign_external_inputs
from content.execution.campaign import request_envelope as envelopes
from content.execution.campaign import request_envelope_build as envelope_build
from content.execution.campaign.scale import campaign_workload_targets
from content.execution.controller.execute import pre_acquisition_handoff as handoffs
from content.source.research.scale_source_pool import (
    build_scale_source_pool_plan,
    required_candidate_counts,
    write_create_once_scale_source_pool,
)
from content.source import professional_image_acquisition as image_acquisition
from content.source import professional_video_acquisition as video_acquisition
from core.io import write_json
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)

SOURCE_A = "sha256:" + "a" * 64
SOURCE_B = "sha256:" + "b" * 64
CATALOG = "sha256:" + "c" * 64
TARGETS = {
    "homepage": 100,
    "article": 100,
    "image": 100,
    "video": 10,
}


def _source_document(digest: str = SOURCE_A) -> dict[str, object]:
    document = SourceDefinitionSnapshot(digest=digest).to_document()
    return document


def _execution_bundle_document() -> dict[str, object]:
    return ExecutionBundleIdentity(digest="sha256:" + "d" * 64).to_document()


def _write_handoff(
    output_root: Path,
    *,
    revision: int = 1,
    supersedes: Path | None = None,
    scale: str = "M100",
    workload_targets: dict[str, int] | None = None,
) -> tuple[dict[str, object], Path]:
    return handoffs.write_pre_acquisition_handoff(
        handoff_id="travel-m100-20260807",
        handoff_revision=revision,
        supersedes_handoff=supersedes,
        scale=scale,
        vertical="travel",
        scope="china",
        region_ref="china",
        topic=None,
        run_date="20260807",
        campaign_sequence=1,
        campaign_retry_of=None,
        source_digest=_source_document(),
        execution_bundle=_execution_bundle_document(),
        entity_catalog_digest=CATALOG,
        workload_targets=workload_targets or campaign_workload_targets(scale),
        output_root=output_root,
    )


def test_m10000_handoff_supports_preset_and_explicit_workload_targets(
    tmp_path: Path,
) -> None:
    targets = campaign_workload_targets("M10000")
    assert targets == {
        "homepage": 10000,
        "article": 10000,
        "image": 10000,
        "video": 1000,
    }

    handoff, _path = _write_handoff(
        tmp_path / "valid",
        scale="M10000",
        workload_targets=targets,
    )
    assert handoff["workloadTargets"] == targets

    explicit_targets = {**targets, "video": 10000}
    explicit, _explicit_path = _write_handoff(
        tmp_path / "explicit",
        scale="M10000",
        workload_targets=explicit_targets,
    )
    assert explicit["workloadTargets"] == explicit_targets


def _pool_source_attribution() -> dict[str, object]:
    source_url = "https://zh.wikipedia.org/wiki/测试实体"
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "维基百科贡献者",
        "originalCreatorProfileUrl": None,
        "platform": "维基百科",
        "sourcePostUrl": source_url,
        "originalAssetUrl": source_url,
        "attributionText": "正文事实来源：维基百科（维基百科贡献者）",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": source_url,
        "termsUrl": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-07T00:00:00Z",
        "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
    }


def _write_scale_source_pool(output_root: Path) -> tuple[Path, Path]:
    evidence_root = output_root / "data/local/workspace/scale-source-pools/m100/evidence"
    evidence: dict[str, tuple[str, str]] = {}
    for kind in ("source-unit", "acquisition", "rights", "quality", "playability"):
        path = evidence_root / f"{kind}.json"
        write_json(path, {"schema": f"quwoquan_data.test_{kind}_evidence"})
        evidence[kind] = (
            path.relative_to(evidence_root).as_posix(),
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    source_revision = content_source_revision(
        source_digest=SOURCE_A,
        entity_catalog_digest=CATALOG,
    )
    candidates: list[dict[str, object]] = []
    for carrier, count in required_candidate_counts("M100").items():
        for index in range(count):
            if carrier == "homepage":
                object_ref = f"entities/地点/景区/fixture-{index:03d}"
            else:
                object_ref = f"posts/{carrier}/测试/fixture-{index:03d}/001"
            provider = "fixture_provider"
            if carrier == "image":
                provider = "pinterest" if index < 100 else "tuchong" if index < 150 else "pexels"
            playability = evidence["playability"] if carrier == "video" else (None, None)
            source_ready_binding: dict[str, object] = {}
            if carrier in {"homepage", "article"}:
                source_ready_binding = {
                    "sourceReadyEvidenceRootRef": ".",
                    "sourceAttribution": _pool_source_attribution(),
                }
            if carrier == "article":
                source_ready_binding["publishMediaMode"] = "text_only"
            candidates.append(
                {
                    **source_ready_binding,
                    "candidateId": f"{carrier}-candidate-{index:03d}",
                    "carrier": carrier,
                    "objectRef": object_ref,
                    "entityRef": "地点/景区/测试实体",
                    "observedEntityRef": "地点/景区/测试实体",
                    "sourceRevision": source_revision,
                    "sourceDigest": SOURCE_A,
                    "entityCatalogDigest": CATALOG,
                    "sourceUnitRef": evidence["source-unit"][0],
                    "sourceUnitDigest": evidence["source-unit"][1],
                    "sourceUnitFileSha256": evidence["source-unit"][1],
                    "provider": provider,
                    "contentSha256": "sha256:" + hashlib.sha256(
                        f"{carrier}:{index}".encode()
                    ).hexdigest(),
                    "acquisitionStatus": "acquired",
                    "acquisitionRef": evidence["acquisition"][0],
                    "acquisitionDigest": evidence["acquisition"][1],
                    "acquisitionFileSha256": evidence["acquisition"][1],
                    "rightsStatus": "verified",
                    "distributionDecision": "commercial_allowed",
                    "rightsRef": evidence["rights"][0],
                    "rightsDigest": evidence["rights"][1],
                    "rightsFileSha256": evidence["rights"][1],
                    "qualityStatus": "passed",
                    "qualityRef": evidence["quality"][0],
                    "qualityDigest": evidence["quality"][1],
                    "qualityFileSha256": evidence["quality"][1],
                    "generated": False,
                    "playabilityRef": playability[0],
                    "playabilityDigest": playability[1],
                    "playabilityFileSha256": playability[1],
                    "videoReadiness": None
                    if carrier != "video"
                    else {
                        "playable": True,
                        "motion": True,
                        "premiumEligible": True,
                        "playCount": 100 + index,
                        "likeCount": 20 + index,
                        "commentCount": 5 + index,
                        "shareCount": 3 + index,
                        "favoriteCount": 7 + index,
                        "observedAt": "2026-08-07T00:00:00Z",
                        "popularityPercentile": round(index / max(1, count - 1), 6),
                        "comparisonBucket": {
                            "provider": provider,
                            "topic": "travel",
                            "timeBucket": "2026-W32",
                            "candidateCount": count,
                        },
                    },
                }
            )
    plan = build_scale_source_pool_plan(
        pool_id="pre-acquisition-handoff-m100-pool",
        target_scale="M100",
        source_revision=source_revision,
        source_digest=SOURCE_A,
        entity_catalog_digest=CATALOG,
        created_at="2026-08-07T00:00:00Z",
        candidates=candidates,
    )
    plan_path = output_root / "data/local/workspace/scale-source-pools/m100/plan.json"
    write_create_once_scale_source_pool(plan_path, plan, evidence_root=evidence_root)
    return plan_path, evidence_root


def test_handoff_revision_is_create_once_and_preserves_superseded_bytes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _revision_one, revision_one_path = _write_handoff(output_root)
    original_bytes = revision_one_path.read_bytes()

    revision_two, path = _write_handoff(
        output_root,
        revision=2,
        supersedes=revision_one_path,
    )
    repeated, repeated_path = _write_handoff(
        output_root,
        revision=2,
        supersedes=revision_one_path,
    )

    assert repeated_path == path
    assert repeated == revision_two
    assert revision_one_path.read_bytes() == original_bytes
    assert revision_two["handoffRevision"] == 2
    assert revision_two["campaignSequence"] == 1
    assert revision_two["campaignRetryOf"] is None
    assert revision_two["supersedes"] == {
        "handoffId": "travel-m100-20260807",
        "handoffRevision": 1,
        "handoffRef": (
            "data/local/workspace/content-pre-acquisition-handoffs/"
            "travel-m100-20260807/revision-001.json"
        ),
        "handoffFileDigest": handoffs._file_digest(revision_one_path),
    }

    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="COLLISION",
    ):
        handoffs.write_pre_acquisition_handoff(
            handoff_id="travel-m100-20260807",
            handoff_revision=2,
            supersedes_handoff=revision_one_path,
            scale="M100",
            vertical="travel",
            scope="china",
            region_ref="china",
            topic="collision-probe",
            run_date="20260807",
            campaign_sequence=1,
            campaign_retry_of=None,
            source_digest=_source_document(),
            execution_bundle=_execution_bundle_document(),
            entity_catalog_digest=CATALOG,
            workload_targets=TARGETS,
            output_root=output_root,
        )


def test_superseding_retired_wire_shape_revision_keeps_chain_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    """历史 revision 以其创建时 schema 冻结：契约改名不得使 supersession 链失效，篡改仍必须被拒。"""
    import json

    output_root = tmp_path / "output"
    revision_one, revision_one_path = _write_handoff(output_root)
    # 模拟契约字段改名前冻结的历史 wire 形态（digest 自洽但不再过当前 schema）。
    retired = json.loads(revision_one_path.read_text(encoding="utf-8"))
    requirements = retired["carrierRequirements"]
    for carrier in requirements:
        requirements[carrier]["retiredWireField"] = requirements[carrier].pop(
            "externalInputMode"
        )
    stable = {
        key: value
        for key, value in retired.items()
        if key not in {"handoffDigest", "createdAt"}
    }
    retired["handoffDigest"] = "sha256:" + hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    revision_one_path.write_text(
        json.dumps(retired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(handoffs.PreAcquisitionHandoffError):
        handoffs.load_pre_acquisition_handoff(revision_one_path)

    revision_two, _path = _write_handoff(
        output_root, revision=2, supersedes=revision_one_path
    )
    assert revision_two["supersedes"]["handoffRevision"] == 1
    assert revision_two["supersedes"]["handoffFileDigest"] == handoffs._file_digest(
        revision_one_path
    )

    tampered = json.loads(revision_one_path.read_text(encoding="utf-8"))
    tampered["sourceRevision"] = SOURCE_B
    revision_one_path.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(
        handoffs.PreAcquisitionHandoffError, match="DIGEST_DRIFT"
    ):
        _write_handoff(
            output_root, revision=3, supersedes=revision_one_path
        )


def test_handoff_revision_rejects_manual_predecessor(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    revision_one, _revision_one_path = _write_handoff(output_root)
    manual_predecessor = output_root / "data/local/workspace/manual-handoff.json"
    write_json(manual_predecessor, revision_one)

    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="LOCATION_INVALID",
    ):
        _write_handoff(
            output_root,
            revision=2,
            supersedes=manual_predecessor,
        )


def test_handoff_revision_does_not_create_execution_retry(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    revision_one, revision_one_path = _write_handoff(output_root)
    revision_two, _ = _write_handoff(
        output_root,
        revision=2,
        supersedes=revision_one_path,
    )

    assert revision_one["campaignSequence"] == revision_two["campaignSequence"] == 1
    assert revision_one["campaignRetryOf"] is revision_two["campaignRetryOf"] is None
    assert revision_two["supersedes"]["handoffRevision"] == 1


def test_envelopes_bind_handoff_and_derive_article_no_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    _handoff, handoff_path = _write_handoff(output_root)
    repo = tmp_path / "repo"
    (repo / "quwoquan_data/reference/travel/entities/china").mkdir(parents=True)
    monkeypatch.setattr(
        envelope_build,
        "current_source_definition_snapshot",
        lambda **_kwargs: SourceDefinitionSnapshot(digest=SOURCE_A),
    )
    monkeypatch.setattr(
        envelope_build,
        "current_execution_bundle_identity",
        lambda **_kwargs: ExecutionBundleIdentity(digest="sha256:" + "d" * 64),
    )
    monkeypatch.setattr(envelope_build, "entity_catalog_digest", lambda _ref: CATALOG)
    monkeypatch.setattr(
        envelopes,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(envelopes, "_git_branch", lambda _repo: "dev1.0")
    monkeypatch.setattr(envelopes, "_git_commit", lambda _repo: "d" * 40)
    monkeypatch.setattr(
        campaign_external_inputs,
        "bind_external_input_refs",
        lambda carrier, _refs, **_kwargs: (
            []
            if carrier == "article"
            else [{"kind": "professional_image_acquisition"}]
        ),
    )

    wave_targets = ("测试实体",)
    homepage = envelopes.build_envelope(
        scale="M100",
        carrier="homepage",
        region_ref="china",
        repo_root=repo,
        day="20260807",
        target_names=wave_targets,
        workloads={"homepage": 1},
        pre_acquisition_handoff=handoff_path,
        pre_acquisition_handoff_output_root=output_root,
        external_input_refs=[{"kind": "professional_image_acquisition"}],
    )
    article = envelopes.build_envelope(
        scale="M100",
        carrier="article",
        region_ref="china",
        repo_root=repo,
        day="20260807",
        target_names=wave_targets,
        workloads={"article": 1},
        pre_acquisition_handoff=handoff_path,
        pre_acquisition_handoff_output_root=output_root,
    )

    assert homepage["preAcquisitionHandoff"]["handoffId"] == (
        "travel-m100-20260807"
    )
    assert homepage["preAcquisitionHandoff"]["handoffRevision"] == 1
    assert article["externalInputRefs"] == []
    assert (
        _handoff["carrierRequirements"]["article"]["externalInputMode"]
        == "execution_source_unit_freeze"
    )
    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="IDENTITY_DRIFT",
    ):
        envelopes.build_envelope(
            scale="M100",
            carrier="article",
            region_ref="china",
            repo_root=repo,
            day="20260808",
            target_names=wave_targets,
            workloads={"article": 1},
            pre_acquisition_handoff=handoff_path,
            pre_acquisition_handoff_output_root=output_root,
        )


def test_shared_guard_accepts_exact_identity_and_rejects_stale_source(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    handoff, handoff_path = _write_handoff(output_root)
    manifest = {
        "sourceDigest": SOURCE_A,
        "entityCatalogDigest": CATALOG,
        "sourceRevision": content_source_revision(
            source_digest=SOURCE_A,
            entity_catalog_digest=CATALOG,
        ),
    }
    assert handoffs.guard_acquisition_source_identity(
        manifest,
        handoff_ref=handoff_path,
        repo_root=tmp_path,
    ) == handoff

    manifest["sourceDigest"] = SOURCE_B
    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="SOURCE_IDENTITY_DRIFT",
    ):
        handoffs.guard_acquisition_source_identity(
            manifest,
            handoff_ref=handoff_path,
            repo_root=tmp_path,
        )


def test_stale_identity_blocks_image_and_video_before_any_output_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    _handoff, handoff_path = _write_handoff(output_root)
    manifest = {
        "sourceDigest": SOURCE_B,
        "entityCatalogDigest": CATALOG,
        "sourceRevision": content_source_revision(
            source_digest=SOURCE_A,
            entity_catalog_digest=CATALOG,
        ),
        "items": [],
    }
    manifest_path = tmp_path / "inputs/stale-manifest.json"
    write_json(manifest_path, manifest)
    monkeypatch.setattr(
        image_acquisition,
        "assert_valid",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        video_acquisition,
        "assert_valid",
        lambda *_args, **_kwargs: None,
    )
    image_output = tmp_path / "image-acquisition"
    video_output = tmp_path / "video-acquisition"

    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="SOURCE_IDENTITY_DRIFT",
    ):
        image_acquisition.acquire_professional_images(
            manifest_path,
            handoff_ref=handoff_path,
            repo_root=tmp_path,
            output_root=image_output,
        )
    with pytest.raises(
        handoffs.PreAcquisitionHandoffError,
        match="SOURCE_IDENTITY_DRIFT",
    ):
        video_acquisition.acquire_professional_videos(
            manifest_path,
            handoff_ref=handoff_path,
            repo_root=tmp_path,
            output_root=video_output,
        )

    assert not image_output.exists()
    assert not video_output.exists()
