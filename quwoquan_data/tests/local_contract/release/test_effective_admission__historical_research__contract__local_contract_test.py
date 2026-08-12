from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical import (  # noqa: E402
    aggregate_release_pool as aggregate_subject,
)
from content.release.canonical import (  # noqa: E402
    aggregate_release_pool_closure as aggregate_closure_subject,
)
from content.release.canonical import (  # noqa: E402
    environment_release_selection as selection_subject,
)
from content.release.canonical import (  # noqa: E402
    pool_inspection as inspection_subject,
)
from content.release.canonical.content_pool_record import (  # noqa: E402
    is_pool_record_admitted,
    pool_payload_digest,
)
from content.release.canonical.effective_admission import (  # noqa: E402
    EffectiveAdmission,
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.io import write_json  # noqa: E402


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "历史作者",
        "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:history.jpg",
        "originalAssetUrl": "https://upload.wikimedia.org/history.jpg",
        "attributionText": "历史作者 / Wikimedia Commons",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-01T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "authorizationProofUrl": "https://commons.wikimedia.org/wiki/File:history.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    }


def _historical_post(
    publish: Path,
    *,
    quality_result: str = "passed",
    evidence_digest: str | None = None,
    include_attribution: bool = True,
) -> tuple[Path, dict[str, object]]:
    root = publish / "posts/article/history/1"
    manifest: dict[str, object] = {
        "contentId": "content-history",
        "version": 1,
        "executionId": "execution-history",
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "1" * 64,
            "inputs": [
                "quwoquan_data/control_plane",
                "quwoquan_data/schema",
                "quwoquan_data/scripts",
            ],
        },
        "contentType": "article",
        "authorId": "author-history",
        "status": "active",
        "reviewDecision": "approved",
        "entityRefs": ["/entity/地点/景区/历史实体"],
    }
    if include_attribution:
        manifest["sourceAttribution"] = _attribution()
    write_json(root / "manifest.json", manifest)
    attestation = {
        "schema": "quwoquan_data.review_attestation",
        "executionId": "execution-history",
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {"status": "passed"},
        "mediaRefReview": {"status": "passed", "issues": []},
    }
    write_json(root / "attestation.json", attestation)
    attestation_sha = (
        "sha256:" + hashlib.sha256((root / "attestation.json").read_bytes()).hexdigest()
    )
    write_json(
        root / "_pool/versions/1.json",
        {
            "schema": "quwoquan_data.pool_object_record",
            "objectType": "content",
            "objectId": "content-history",
            "objectRef": "article/history/1",
            "version": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": quality_result,
            "eligibilityResult": "passed",
            "usageScope": "commercial",
            "evidenceRef": "attestation.json",
            "evidenceDigest": evidence_digest or attestation_sha,
            "payloadDigest": pool_payload_digest(root),
        },
    )
    return root, manifest


def _author(publish: Path) -> None:
    write_json(
        publish / "creators/author-history/profile.json",
        {
            "authorId": "author-history",
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
        },
    )


def _historical_homepage(publish: Path) -> tuple[Path, dict[str, object]]:
    root = publish / "entities/地点/景区/历史实体"
    manifest: dict[str, object] = {
        "entityId": "entity-history",
        "entityRef": "/entity/地点/景区/历史实体",
        "version": 1,
        "executionId": "execution-history",
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "2" * 64,
            "inputs": [
                "quwoquan_data/control_plane",
                "quwoquan_data/schema",
                "quwoquan_data/scripts",
            ],
        },
        "authorId": "author-history",
        "status": "active",
        "reviewDecision": "approved",
    }
    write_json(root / "manifest.json", manifest)
    write_json(
        root / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "executionId": "execution-history",
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed", "issues": []},
        },
    )
    evidence_digest = (
        "sha256:" + hashlib.sha256((root / "attestation.json").read_bytes()).hexdigest()
    )
    write_json(
        root / "_pool/versions/1.json",
        {
            "schema": "quwoquan_data.pool_object_record",
            "objectType": "homepage",
            "objectId": "entity-history",
            "objectRef": "地点/景区/历史实体",
            "version": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "commercial",
            "evidenceRef": "attestation.json",
            "evidenceDigest": evidence_digest,
            "payloadDigest": pool_payload_digest(root),
        },
    )
    return root, manifest


def test_historical_approved_evidence_defaults_only_to_research(tmp_path: Path) -> None:
    root, manifest = _historical_post(tmp_path / "publish")

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "historical_approved_research"
    assert is_pool_record_admitted(effective.record)
    assert effective.record is not None
    assert effective.record["usageScope"] == "research"
    assert effective.record["sourceAttribution"] == manifest["sourceAttribution"]
    assert effective.record["sourceAttribution"]["publicationAdmission"] == (
        "commercial_release"
    )


def test_historical_approved_research_without_attribution_keeps_legacy_identity(
    tmp_path: Path,
) -> None:
    root, manifest = _historical_post(
        tmp_path / "publish",
        include_attribution=False,
    )

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "historical_approved_research"
    assert effective.record is not None
    assert effective.record["sourceAttribution"] == {}
    source_identity = effective.record["sourceIdentity"]
    assert source_identity["identityKind"] == "legacy_canonical_migration"
    assert source_identity["executionId"] == "execution-history"
    assert source_identity["sourceDigest"] == "sha256:" + "1" * 64
    assert (
        source_identity["canonicalObjectDigest"]
        == effective.record["canonicalObjectDigest"]
    )
    assert source_identity["migrationEvidenceDigest"].startswith("sha256:")
    assert source_identity["identityDigest"].startswith("sha256:")


def test_effective_attribution_gate_is_relaxed_only_for_historical_research() -> None:
    historical = EffectiveAdmission(
        record={"usageScope": "research", "sourceAttribution": {}},
        source="historical_approved_research",
    )
    modern = EffectiveAdmission(
        record={"usageScope": "research", "sourceAttribution": {}},
        source="explicit",
    )

    assert effective_source_attribution_ready(historical, release_mode="research")
    assert not effective_source_attribution_ready(
        historical,
        release_mode="commercial",
    )
    assert not effective_source_attribution_ready(modern, release_mode="research")
    assert not effective_source_attribution_ready(modern, release_mode="commercial")


def test_historical_research_without_attribution_preserves_missing_entity_issue(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _root, _manifest = _historical_post(
        publish,
        include_attribution=False,
    )

    selection = selection_subject.select_environment_release_posts(
        publish_root=publish,
        post_refs=["article/history/1"],
        environment="alpha",
        strict_admission=True,
    )

    assert selection.post_refs == ()
    assert [(row.gate, row.code) for row in selection.excluded] == [
        ("delivery", "DATA.POOL.REFERENCE_MISSING")
    ]


def test_historical_homepage_without_attribution_is_shared_by_inspect_and_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    _author(publish)
    _historical_homepage(publish)

    aggregate_closure_subject._validate_entity_pool_identity(
        publish,
        entity_refs={"地点/景区/历史实体"},
        release_mode="research",
    )
    assert aggregate_closure_subject.pool_execution_ids(
        publish,
        entity_refs={"地点/景区/历史实体"},
        post_refs=set(),
    ) == ["execution-history"]
    with pytest.raises(ObjectTransactionError, match="OBJECT_NOT_ADMITTED"):
        aggregate_closure_subject._validate_entity_pool_identity(
            publish,
            entity_refs={"地点/景区/历史实体"},
            release_mode="commercial",
        )

    monkeypatch.setattr(
        inspection_subject,
        "entity_candidate_closure",
        lambda *_args, **_kwargs: ([], []),
    )
    report = inspection_subject.inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=True,
    )

    assert report["supply"]["homepage"]["admitted"] == 1
    assert report["supply"]["homepage"]["publishable"] == 1
    assert not any(
        row["code"] == "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE"
        for row in report["issues"]
    )


@pytest.mark.parametrize("quality_result", ["", "unknown"])
def test_historical_unknown_quality_fails_closed(
    tmp_path: Path,
    quality_result: str,
) -> None:
    root, manifest = _historical_post(
        tmp_path / "publish",
        quality_result=quality_result,
    )

    with pytest.raises(ObjectTransactionError, match="RECORD_QUALITY_INVALID"):
        resolve_effective_admission(
            root,
            object_type="content",
            document=manifest,
        )


def test_historical_failed_quality_remains_excluded(tmp_path: Path) -> None:
    root, manifest = _historical_post(
        tmp_path / "publish",
        quality_result="failed",
    )

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "missing"
    assert effective.record is None


def test_historical_evidence_digest_drift_fails_closed(tmp_path: Path) -> None:
    root, manifest = _historical_post(
        tmp_path / "publish",
        evidence_digest="sha256:" + "0" * 64,
    )

    with pytest.raises(ObjectTransactionError, match="EVIDENCE_DIGEST_DRIFT"):
        resolve_effective_admission(
            root,
            object_type="content",
            document=manifest,
        )


def test_modern_explicit_failure_has_priority_over_historical_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, manifest = _historical_post(tmp_path / "publish")
    explicit = {
        "schema": "quwoquan_data.pool_object_record",
        "objectType": "content",
        "objectId": "content-history",
        "objectRef": "article/history/1",
        "recordSequence": 2,
        "contentVersion": 1,
        "status": "active",
        "processResult": "completed",
        "qualityResult": "failed",
        "eligibilityResult": "failed",
        "usageScope": "research",
        "evidenceRef": "attestation.json",
        "evidenceDigest": "sha256:" + "2" * 64,
        "payloadDigest": "sha256:" + "3" * 64,
    }
    monkeypatch.setattr(
        "content.release.canonical.effective_admission.latest_pool_record",
        lambda *_args, **_kwargs: explicit,
    )

    effective = resolve_effective_admission(
        root,
        object_type="content",
        document=manifest,
    )

    assert effective.source == "explicit"
    assert effective.record is explicit
    assert not is_pool_record_admitted(effective.record)


def test_inspect_build_and_environment_selector_share_effective_record(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    root, manifest = _historical_post(publish)

    inspection_record = inspection_subject._admission_record(
        root,
        manifest,
        object_type="content",
    )
    selection_record = selection_subject._effective_record(
        root,
        manifest,
        object_type="content",
    )
    build_record = aggregate_subject._effective_record(
        root,
        manifest,
        object_type="content",
    )

    assert inspection_record == selection_record == build_record
    assert inspection_record is not None
    assert inspection_record["usageScope"] == "research"
    assert json.dumps(inspection_record, sort_keys=True) == json.dumps(
        build_record,
        sort_keys=True,
    )
    source_digests, identities, identity_set_digest = (
        aggregate_subject._pool_source_identity_closure(
            publish,
            entity_refs=set(),
            post_refs={"article/history/1"},
        )
    )
    assert [row.digest for row in source_digests] == ["sha256:" + "1" * 64]
    assert len(identities) == 1
    assert identities[0]["identityKind"] == "legacy_canonical_migration"
    assert identity_set_digest.startswith("sha256:")
