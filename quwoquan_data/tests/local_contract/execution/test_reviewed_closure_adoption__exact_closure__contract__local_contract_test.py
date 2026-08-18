# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t4
"""Reviewed closure adoption is byte-exact and keeps one active source identity."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from core import source_digest as source_digest_module
from content.execution.planning.recipe import request as recipe_request
from content.execution.campaign import workspace as campaign_workspace
from content.execution.closure import adoption as reviewed_closure_adoption
from content.execution.campaign.submission import load_submissions
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.closure.adoption import adopt_reviewed_closure
from content.execution.closure.adoption_contract import (
    ReviewedClosureAdoptionError,
    canonical_digest,
    file_digest,
    validate_release_identity_incident,
    validate_reviewed_closure_adoption_receipt,
    validate_reviewed_closure_adoption_ref,
)
from content.release.canonical import aggregate_release as aggregate_release_module
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
    build_campaign_release,
)
from content.release.canonical.release_identity_incident import (
    record_release_identity_incident,
)
from core.paths import OUTPUT_ROOT, RELEASE_IDENTITY_INCIDENTS_ROOT, REPO_ROOT
from core.release_layout import objects_merkle, payload_digest
from core.source_digest import (
    content_source_revision,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

_RELEASE_ID = "reviewed-closure-source-001"
_ADOPTION_ID = "reviewed-closure-adoption-001"
_SOURCE_INPUTS = tuple(
    current_source_definition_snapshot().to_document()["inputs"]
)


def _freeze_repo_source(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen_definition = current_source_definition_snapshot()
    frozen_bundle = current_execution_bundle_identity()
    monkeypatch.setattr(
        reviewed_closure_adoption,
        "current_source_definition_snapshot",
        lambda **_kwargs: frozen_definition,
    )
    monkeypatch.setattr(
        campaign_workspace,
        "current_source_definition_snapshot",
        lambda **_kwargs: frozen_definition,
    )
    monkeypatch.setattr(
        source_digest_module,
        "current_execution_bundle_identity",
        lambda **_kwargs: frozen_bundle,
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_document(
    fill: str,
    *,
    inputs: tuple[str, ...] = _SOURCE_INPUTS,
) -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "digest": "sha256:" + fill * 64,
        "inputs": list(inputs),
    }


def _binding(path: Path, *, output_root: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(output_root).as_posix(),
        "sha256": file_digest(path),
    }


def _tree_file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _object_evidence(
    *,
    output_root: Path,
    release_root: Path,
    desired: dict[str, list[str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    reviews: list[dict[str, str]] = []
    rights: list[dict[str, str]] = []
    for kind in ("creators", "entities", "posts", "tags"):
        for ref in desired[kind]:
            root = release_root / "payload/objects" / kind / ref
            object_ref = f"{kind}/{ref}"
            if kind in {"entities", "posts"}:
                for name in ("attestation.json", "evidence_index.json"):
                    reviews.append(
                        {
                            "objectRef": object_ref,
                            **_binding(root / name, output_root=output_root),
                        }
                    )
                rights.append(
                    {
                        "objectRef": object_ref,
                        **_binding(root / "rights.json", output_root=output_root),
                    }
                )
            for snapshot in sorted((root / "rights_snapshots").glob("*.json")):
                rights.append(
                    {
                        "objectRef": object_ref,
                        **_binding(snapshot, output_root=output_root),
                    }
                )
    reviews.sort(key=lambda item: (item["objectRef"], item["ref"]))
    rights.sort(key=lambda item: (item["objectRef"], item["ref"]))
    return reviews, rights


def _fixture(tmp_path: Path) -> dict[str, object]:
    output_root = tmp_path / ".qwq_output"
    release_root = output_root / "data/releases" / _RELEASE_ID
    payload_root = release_root / "payload"
    desired = {
        "creators": ["creator-001"],
        "entities": ["地点/景区/测试地点"],
        "posts": [
            "article/攻略/测试/1",
            "image/画报/测试/1",
            "video/体验/测试/1",
        ],
        "tags": ["Topic/旅行"],
    }
    object_roots: list[tuple[str, str, Path]] = []
    for kind in ("creators", "entities", "posts", "tags"):
        for ref in desired[kind]:
            root = payload_root / "objects" / kind / ref
            root.mkdir(parents=True, exist_ok=True)
            object_roots.append((kind, ref, root))
            if kind == "tags":
                _write_json(root / "_definition.json", {"id": ref})
                continue
            if kind == "creators":
                _write_json(root / "profile.json", {"id": ref})
            else:
                _write_json(root / "manifest.json", {"id": ref, "kind": kind})
                _write_json(root / "attestation.json", {"decision": "approved"})
                _write_json(root / "evidence_index.json", {"evidence": [ref]})
                _write_json(root / "rights.json", {"status": "verified"})
            _write_json(
                root / "rights_snapshots/snapshot.json",
                {"objectRef": f"{kind}/{ref}", "status": "verified"},
            )

    media_assets: list[dict[str, object]] = []
    media_owners = [
        ("asset-avatar", "avatar", "image/webp", object_roots[0]),
        ("asset-homepage", "image", "image/webp", object_roots[1]),
        ("asset-article", "image", "image/webp", object_roots[2]),
        ("asset-image", "image", "image/webp", object_roots[3]),
        ("asset-video", "video", "video/mp4", object_roots[4]),
    ]
    for asset_id, media_kind, content_type, (kind, ref, object_root) in media_owners:
        extension = "mp4" if media_kind == "video" else "webp"
        public_slice = f"media/{media_kind}/s/asset/{asset_id}/v1/source.{extension}"
        media_path = payload_root / public_slice
        media_path.parent.mkdir(parents=True, exist_ok=True)
        media_path.write_bytes(f"immutable-bytes:{asset_id}".encode())
        media_assets.append(
            {
                "assetId": asset_id,
                "kind": media_kind,
                "contentType": content_type,
                "bytes": media_path.stat().st_size,
                "sha256": file_digest(media_path),
                "publicSliceKey": public_slice,
                "version": 1,
                "ownerRefs": [f"{kind}/{ref}"],
                "rightsSnapshotRefs": [
                    (f"objects/{kind}/{ref}/rights_snapshots/snapshot.json")
                ],
            }
        )
    media_assets.sort(key=lambda item: str(item["assetId"]))

    _write_json(
        payload_root / "desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": _RELEASE_ID,
            "desiredRefs": desired,
        },
    )
    _write_json(
        payload_root / "index/objects.json",
        {"schema": "quwoquan_data.release_object_index", **desired},
    )
    _write_json(
        payload_root / "media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": _RELEASE_ID,
            "sourceOwner": "qwq_data",
            "assets": media_assets,
            "issues": [],
            "counts": {"assets": len(media_assets), "issues": 0},
        },
    )
    _write_json(payload_root / "sample_bundle.json", {"sample": []})
    _write_json(payload_root / "asset_admission.json", {"status": "passed"})
    canonical_merkle = objects_merkle(release_root)
    upstream_execution_ids = sorted(
        [
            "20260731--travel-homepage-reviewed--china--scale-001",
            "20260731--travel-article-reviewed--china--scale-001",
            "20260731--travel-image-reviewed--china--scale-001",
            "20260731--travel-video-reviewed--china--scale-001",
        ]
    )
    upstream_sources = [_source_document("a"), _source_document("b")]
    _write_json(
        payload_root / "release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": _RELEASE_ID,
            "canonicalMerkle": canonical_merkle,
            "executionIds": upstream_execution_ids,
            "sourceDigests": upstream_sources,
        },
    )
    payload_sha256 = payload_digest(release_root)
    current_attestation = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": _RELEASE_ID,
        "payloadSha256": payload_sha256,
        "canonicalMerkle": canonical_merkle,
        "executionIds": upstream_execution_ids,
    }
    current_attestation_path = release_root / "attestations/release.json"
    _write_json(current_attestation_path, current_attestation)

    old_attestation = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": _RELEASE_ID,
        "payloadSha256": "sha256:" + "0" * 64,
        "canonicalMerkle": "sha256:" + "1" * 64,
        "executionIds": [upstream_execution_ids[0]],
    }
    old_attestation_path = (
        output_root
        / "data/release-identity-incidents/evidence"
        / _RELEASE_ID
        / "observed-001.json"
    )
    _write_json(old_attestation_path, old_attestation)
    current_identity = {
        "releaseId": _RELEASE_ID,
        "payloadSha256": payload_sha256,
        "canonicalMerkle": canonical_merkle,
        "attestationFileSha256": file_digest(current_attestation_path),
    }
    old_identity = {
        "releaseId": _RELEASE_ID,
        "payloadSha256": old_attestation["payloadSha256"],
        "canonicalMerkle": old_attestation["canonicalMerkle"],
        "attestationFileSha256": file_digest(old_attestation_path),
    }
    observations = [
        {
            **old_identity,
            "attestationRef": old_attestation_path.relative_to(output_root).as_posix(),
            "acquisitionMode": "original_file",
            "executionIds": old_attestation["executionIds"],
            "observedAt": "2026-08-04T00:00:00+00:00",
        },
        {
            **current_identity,
            "attestationRef": current_attestation_path.relative_to(
                output_root
            ).as_posix(),
            "acquisitionMode": "original_file",
            "executionIds": upstream_execution_ids,
            "observedAt": "2026-08-05T00:00:00+00:00",
        },
    ]
    observations.sort(
        key=lambda row: (
            row["releaseId"],
            row["payloadSha256"],
            row["canonicalMerkle"],
            row["attestationFileSha256"],
        )
    )
    protected_ids = sorted(
        {execution_id for row in observations for execution_id in row["executionIds"]}
    )
    incident_stable = {
        "schema": "quwoquan_data.release_identity_incident",
        "incidentId": "release-identity-incident-001",
        "releaseId": _RELEASE_ID,
        "status": "identity_collided",
        "storageClass": "append_only_create_once",
        "observedIdentities": observations,
        "protectedExecutionIds": protected_ids,
        "recordedAt": "2026-08-05T00:00:01+00:00",
    }
    incident = {
        **incident_stable,
        "receiptDigest": canonical_digest(incident_stable),
    }
    incident_path = (
        output_root
        / "data/release-identity-incidents"
        / _RELEASE_ID
        / "release-identity-incident-001.json"
    )
    _write_json(incident_path, incident)

    reviews, rights = _object_evidence(
        output_root=output_root,
        release_root=release_root,
        desired=desired,
    )
    upstream = {
        "executionIds": upstream_execution_ids,
        "sourceDigests": upstream_sources,
    }
    closure_digests = {
        "objects": canonical_merkle,
        "media": canonical_digest(media_assets),
        "review": canonical_digest(reviews),
        "rights": canonical_digest(rights),
        "upstream": canonical_digest(upstream),
    }
    source_root_ref = release_root.relative_to(output_root).as_posix()
    adoption_stable = {
        "schema": "quwoquan_data.reviewed_closure_adoption_ref",
        "adoptionId": _ADOPTION_ID,
        "sourceReleaseRootRef": source_root_ref,
        "sourceReleaseIdentity": current_identity,
        "identityIncident": {
            "ref": incident_path.relative_to(output_root).as_posix(),
            "fileSha256": file_digest(incident_path),
            "receiptDigest": incident["receiptDigest"],
        },
        "sourceEvidence": {
            "releaseAttestation": _binding(
                current_attestation_path, output_root=output_root
            ),
            "releaseHeader": _binding(
                payload_root / "release.json", output_root=output_root
            ),
            "desiredState": _binding(
                payload_root / "desired_state.json", output_root=output_root
            ),
            "objectIndex": _binding(
                payload_root / "index/objects.json", output_root=output_root
            ),
            "mediaManifest": _binding(
                payload_root / "media_manifest.json", output_root=output_root
            ),
        },
        "desiredRefs": desired,
        "mediaAssets": media_assets,
        "reviewEvidence": reviews,
        "rightsEvidence": rights,
        "upstreamProvenance": upstream,
        "closureDigests": closure_digests,
        "recordedAt": "2026-08-05T00:00:02+00:00",
    }
    adoption_ref = {
        **adoption_stable,
        "adoptionRefDigest": canonical_digest(adoption_stable),
    }
    adoption_ref_path = (
        output_root
        / "data/tasks/20260805--travel-homepage-adoption--china--pilot-001"
        / "0.plan/reviewed_closure_adoption_ref.json"
    )
    _write_json(adoption_ref_path, adoption_ref)

    target_source = _source_document("f")
    catalog_digest = "sha256:" + "e" * 64
    target_identity = {
        "sourceRevision": content_source_revision(
            source_digest=str(target_source["digest"]),
            entity_catalog_digest=catalog_digest,
        ),
        "sourceDigest": target_source,
        "entityCatalogDigest": catalog_digest,
    }
    lane_ids = {
        carrier: f"20260805--travel-{carrier}-adoption--china--pilot-001"
        for carrier in ("homepage", "article", "image", "video")
    }
    receipt_stable = {
        "schema": "quwoquan_data.reviewed_closure_adoption_receipt",
        "adoptionId": _ADOPTION_ID,
        "adoptionRef": {
            "ref": adoption_ref_path.relative_to(output_root).as_posix(),
            "fileSha256": file_digest(adoption_ref_path),
            "adoptionRefDigest": adoption_ref["adoptionRefDigest"],
        },
        "sourceReleaseIdentity": current_identity,
        "targetSourceIdentity": target_identity,
        "laneExecutions": [
            {
                "carrier": "homepage",
                "executionId": lane_ids["homepage"],
                "adoptedObjectRefs": [f"entities/{ref}" for ref in desired["entities"]],
            },
            *[
                {
                    "carrier": carrier,
                    "executionId": lane_ids[carrier],
                    "adoptedObjectRefs": [
                        f"posts/{ref}"
                        for ref in desired["posts"]
                        if ref.startswith(f"{carrier}/")
                    ],
                }
                for carrier in ("article", "image", "video")
            ],
        ],
        "sharedObjectRefs": [
            *[f"creators/{ref}" for ref in desired["creators"]],
            *[f"tags/{ref}" for ref in desired["tags"]],
        ],
        "closureDigests": closure_digests,
        "upstreamProvenance": upstream,
        "status": "passed",
        "recordedAt": "2026-08-05T00:00:03+00:00",
    }
    receipt = {
        **receipt_stable,
        "receiptDigest": canonical_digest(receipt_stable),
    }
    return {
        "outputRoot": output_root,
        "releaseRoot": release_root,
        "incident": incident,
        "incidentPath": incident_path,
        "adoptionRef": adoption_ref,
        "adoptionRefPath": adoption_ref_path,
        "receipt": receipt,
    }


def _redigest(document: dict[str, object], field: str) -> None:
    document[field] = canonical_digest(
        {key: value for key, value in document.items() if key != field}
    )


def test_exact_reviewed_closure_and_single_source_receipt_pass(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    incident = validate_release_identity_incident(
        fixture["incident"], output_root=fixture["outputRoot"]
    )
    adoption_ref = validate_reviewed_closure_adoption_ref(
        fixture["adoptionRef"], output_root=fixture["outputRoot"]
    )
    receipt = validate_reviewed_closure_adoption_receipt(
        fixture["receipt"], output_root=fixture["outputRoot"]
    )

    assert incident.release_id == _RELEASE_ID
    assert len(incident.observed_identities) == 2
    assert adoption_ref.upstream_source_digests == (
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
    )
    assert receipt.target_source_digest == "sha256:" + "f" * 64
    assert len(receipt.lane_execution_ids) == 4


def test_incident_rejects_incomplete_gc_protection(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    incident = copy.deepcopy(fixture["incident"])
    incident["protectedExecutionIds"] = incident["protectedExecutionIds"][:-1]
    _redigest(incident, "receiptDigest")

    with pytest.raises(
        ReviewedClosureAdoptionError,
        match="protectedExecutionIds must equal",
    ):
        validate_release_identity_incident(incident, output_root=fixture["outputRoot"])


def test_adoption_ref_rejects_media_byte_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    media_path = (
        fixture["releaseRoot"] / "payload/media/video/s/asset/asset-video/v1/source.mp4"
    )
    media_path.write_bytes(b"mutated-media")

    with pytest.raises(ReviewedClosureAdoptionError, match="PAYLOAD_DRIFT"):
        validate_reviewed_closure_adoption_ref(
            fixture["adoptionRef"], output_root=fixture["outputRoot"]
        )


def test_receipt_rejects_upstream_digest_as_new_active_source(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt = copy.deepcopy(fixture["receipt"])
    upstream_source = receipt["upstreamProvenance"]["sourceDigests"][0]
    receipt["targetSourceIdentity"]["sourceDigest"] = upstream_source
    receipt["targetSourceIdentity"]["sourceRevision"] = content_source_revision(
        source_digest=upstream_source["digest"],
        entity_catalog_digest=receipt["targetSourceIdentity"]["entityCatalogDigest"],
    )
    _redigest(receipt, "receiptDigest")

    with pytest.raises(
        ReviewedClosureAdoptionError,
        match="target sourceDigest must identify the new adoption execution",
    ):
        validate_reviewed_closure_adoption_receipt(
            receipt, output_root=fixture["outputRoot"]
        )


def test_receipt_rejects_lane_object_omission(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt = copy.deepcopy(fixture["receipt"])
    receipt["laneExecutions"][2]["adoptedObjectRefs"] = []
    _redigest(receipt, "receiptDigest")

    with pytest.raises(ReviewedClosureAdoptionError, match="object closure drifted"):
        validate_reviewed_closure_adoption_receipt(
            receipt, output_root=fixture["outputRoot"]
        )


def _record_fixture_incident(
    fixture: dict[str, object],
) -> tuple[dict[str, object], Path]:
    output_root = fixture["outputRoot"]
    assert isinstance(output_root, Path)
    observations = fixture["incident"]["observedIdentities"]
    paths = tuple(output_root / row["attestationRef"] for row in observations)
    return record_release_identity_incident(
        release_id=_RELEASE_ID,
        incident_id="release-identity-incident-canonical-001",
        original_attestations=paths,
        recovery_provenances=(),
        output_root=output_root,
    )


def test_identity_incident_writer_is_append_only_and_local(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    document, path = _record_fixture_incident(fixture)
    first_bytes = path.read_bytes()

    replay, replay_path = _record_fixture_incident(fixture)

    assert path == replay_path
    assert replay == document
    assert replay_path.read_bytes() == first_bytes
    expected_root = RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(OUTPUT_ROOT)
    assert path.relative_to(fixture["outputRoot"]).is_relative_to(expected_root)
    assert validate_release_identity_incident(
        replay,
        output_root=fixture["outputRoot"],
    ).protected_execution_ids == tuple(document["protectedExecutionIds"])


def test_adoption_cli_path_freezes_four_lane_campaign_without_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_repo_source(monkeypatch)
    fixture = _fixture(tmp_path)
    _incident, incident_path = _record_fixture_incident(fixture)
    output_root = fixture["outputRoot"]
    assert isinstance(output_root, Path)
    execution_ids = {
        carrier: f"20260805--travel-{carrier}-adoption--china--pilot-011"
        for carrier in ("homepage", "article", "image", "video")
    }
    runtime = CampaignRuntimePaths(
        repo_root=REPO_ROOT,
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/content-campaign-workspaces",
    )

    result = adopt_reviewed_closure(
        adoption_id="reviewed-closure-adoption-canonical-001",
        source_release_id=_RELEASE_ID,
        identity_incident_path=incident_path,
        execution_ids=execution_ids,
        region_ref="china",
        runtime=runtime,
        lease_seconds=2,
    )
    replay = adopt_reviewed_closure(
        adoption_id="reviewed-closure-adoption-canonical-001",
        source_release_id=_RELEASE_ID,
        identity_incident_path=incident_path,
        execution_ids=execution_ids,
        region_ref="china",
        runtime=runtime,
        lease_seconds=2,
    )

    assert result == replay
    assert result["releaseCreated"] is False
    assert result["selectionDigest"].startswith("sha256:")
    assert sorted(
        path.name for path in (output_root / "data/releases").iterdir()
    ) == [_RELEASE_ID]
    submissions = load_submissions(
        execution_ids["homepage"],
        root=runtime.campaigns_root,
    )
    assert {
        carrier: row["operation"] for carrier, row in submissions.items()
    } == {
        carrier: f"{carrier}.adoptReviewedClosure" for carrier in execution_ids
    }
    plan = json.loads(
        (
            runtime.campaigns_root
            / execution_ids["homepage"]
            / "campaign_plan.json"
        ).read_text(encoding="utf-8")
    )
    assert plan["reviewedClosureAdoption"]["adoptionId"] == result["adoptionId"]
    for carrier, execution_id in execution_ids.items():
        task_binding = (
            output_root
            / "data/tasks"
            / execution_id
            / "0.plan/reviewed_closure_adoption.json"
        )
        publish_receipt = (
            runtime.campaigns_root
            / execution_ids["homepage"]
            / "receipts"
            / f"{carrier}-publish.json"
        )
        assert task_binding.is_file()
        assert publish_receipt.is_file()

    roots = CampaignReleaseRoots(
        output_root=output_root,
        campaigns_root=runtime.campaigns_root,
        tasks_root=output_root / "data/tasks",
        publish_root=runtime.publish_root,
        release_root=output_root / "data/releases",
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=execution_ids["homepage"],
            release_id=_RELEASE_ID,
            release_class="research",
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_IDENTITY_REUSE_FORBIDDEN"


def test_adoption_campaign_aggregates_byte_exact_source_closure_to_new_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_repo_source(monkeypatch)
    fixture = _fixture(tmp_path)
    _incident, incident_path = _record_fixture_incident(fixture)
    output_root = fixture["outputRoot"]
    source_release_root = fixture["releaseRoot"]
    assert isinstance(output_root, Path)
    assert isinstance(source_release_root, Path)
    execution_ids = {
        carrier: f"20260805--travel-{carrier}-adoption--china--pilot-012"
        for carrier in ("homepage", "article", "image", "video")
    }
    runtime = CampaignRuntimePaths(
        repo_root=REPO_ROOT,
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/content-campaign-workspaces",
    )
    adopt_reviewed_closure(
        adoption_id="reviewed-closure-adoption-canonical-aggregate-001",
        source_release_id=_RELEASE_ID,
        identity_incident_path=incident_path,
        execution_ids=execution_ids,
        region_ref="china",
        runtime=runtime,
        lease_seconds=2,
    )

    def _admission(
        *,
        release_id: str,
        objects_root: Path,
        desired: dict[str, list[str]],
        release_class: str,
    ) -> dict[str, object]:
        del objects_root
        carriers = {
            "homepage": len(desired["entities"]),
            **{
                carrier: sum(
                    ref.startswith(f"{carrier}/") for ref in desired["posts"]
                )
                for carrier in ("article", "image", "video")
            },
        }
        return {
            "schema": "quwoquan_data.release_asset_admission",
            "releaseId": release_id,
            "releaseClass": release_class,
            "productLifecycleState": release_class,
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": sum(carriers.values()),
            "commercialAcceptedCount": 0,
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "objectCount": count,
                    "assetCount": count,
                    "researchAcceptedCount": count,
                    "commercialAcceptedCount": 0,
                }
                for carrier, count in carriers.items()
            ],
            "articleMediaCoverage": {
                "articleCount": carriers["article"],
                "illustratedCount": carriers["article"],
                "textOnlyCount": 0,
                "illustratedRate": 1.0,
                "textOnlyRate": 0.0,
            },
            "sourceAssetCounts": [],
            "assets": [],
        }

    monkeypatch.setattr(
        aggregate_release_module,
        "build_release_asset_admission",
        _admission,
    )
    monkeypatch.setattr(
        aggregate_release_module,
        "scan_release_contract",
        lambda *_args, **_kwargs: {
            "status": "passed",
            "blockingIssues": [],
        },
    )

    def _mutable_publish_path_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("adoption aggregate touched mutable canonical publish")

    for helper in (
        "execution_publish_closure",
        "validate_publish_invariants",
        "build_release_media_manifest",
        "bind_release_object_media_assets",
        "copy_release_media_objects",
    ):
        monkeypatch.setattr(
            aggregate_release_module,
            helper,
            _mutable_publish_path_forbidden,
        )
    roots = CampaignReleaseRoots(
        output_root=output_root,
        campaigns_root=runtime.campaigns_root,
        tasks_root=output_root / "data/tasks",
        publish_root=runtime.publish_root,
        release_root=output_root / "data/releases",
    )
    release_id = "reviewed-closure-adopted-release-001"
    source_before = _tree_file_digests(source_release_root)
    source_payload_before = payload_digest(source_release_root)
    source_objects_before = _tree_file_digests(
        source_release_root / "payload/objects"
    )
    source_media_before = _tree_file_digests(source_release_root / "payload/media")

    result = build_campaign_release(
        root_execution_id=execution_ids["homepage"],
        release_id=release_id,
        release_class="research",
        roots=roots,
    )
    selection_path = Path(result["campaignSelectionAttestation"])
    selection_bytes = selection_path.read_bytes()
    replay = build_campaign_release(
        root_execution_id=execution_ids["homepage"],
        release_id=release_id,
        release_class="research",
        roots=roots,
    )

    target = roots.release_root / release_id
    source_media_manifest = json.loads(
        (source_release_root / "payload/media_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    target_media_manifest = json.loads(
        (target / "payload/media_manifest.json").read_text(encoding="utf-8")
    )
    target_header = json.loads(
        (target / "payload/release.json").read_text(encoding="utf-8")
    )
    plan = json.loads(
        (
            runtime.campaigns_root
            / execution_ids["homepage"]
            / "campaign_plan.json"
        ).read_text(encoding="utf-8")
    )
    target_attestation = json.loads(
        (target / "attestations/release.json").read_text(encoding="utf-8")
    )
    assert result["idempotent"] is False
    assert replay["idempotent"] is True
    assert selection_path.read_bytes() == selection_bytes
    assert target_header["releaseId"] == release_id
    assert target_header["executionIds"] == sorted(execution_ids.values())
    assert target_header["sourceDigest"] == plan["sourceDigest"]
    assert target_header["sourceRevision"] == plan["sourceRevision"]
    assert target_header["entityCatalogDigest"] == plan["entityCatalogDigest"]
    assert target_header["reviewedClosureAdoption"] == plan[
        "reviewedClosureAdoption"
    ]
    assert target_attestation["payloadSha256"] == payload_digest(target)
    assert objects_merkle(target) == objects_merkle(source_release_root)
    assert _tree_file_digests(target / "payload/objects") == source_objects_before
    assert _tree_file_digests(target / "payload/media") == source_media_before
    assert target_media_manifest["assets"] == source_media_manifest["assets"]
    assert target_media_manifest["releaseId"] == release_id
    assert source_media_manifest["releaseId"] == _RELEASE_ID
    assert _tree_file_digests(source_release_root) == source_before
    assert payload_digest(source_release_root) == source_payload_before
    assert not runtime.publish_root.exists()


def test_task_execute_adoption_bypasses_generation_request_and_model_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[object] = []
    monkeypatch.setattr(
        reviewed_closure_adoption,
        "handle_adopt_reviewed_closure",
        lambda args: observed.append(args),
    )
    args = SimpleNamespace(
        stage="adopt-reviewed-closure",
        execution_id="20260805--travel-homepage-adoption--china--pilot-021",
        article_execution_id="20260805--travel-article-adoption--china--pilot-021",
        image_execution_id="20260805--travel-image-adoption--china--pilot-021",
        video_execution_id="20260805--travel-video-adoption--china--pilot-021",
        adoption_id="adoption-021",
        source_release_id=_RELEASE_ID,
        identity_incident="/protected/incident.json",
        region_ref="china",
    )

    recipe_request.handle_execute(args, None, owner=SimpleNamespace())

    assert observed == [args]
