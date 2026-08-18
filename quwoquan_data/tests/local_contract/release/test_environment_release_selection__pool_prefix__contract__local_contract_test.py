# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t3
"""Environment manifests select stable, balanced prefixes from one content pool."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import environment_release_selection as subject  # noqa: E402
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
)
from core.io import write_json  # noqa: E402
from core.source_digest import SourceDefinitionSnapshot, content_source_revision  # noqa: E402


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "source-author",
        "platform": "source-platform",
        "sourcePostUrl": "https://source.example/post",
        "originalAssetUrl": "https://source.example/asset",
        "attributionText": "source-author / source-platform",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _source_identity(
    execution_id: str = "execution-a",
) -> tuple[dict[str, object], SourceDefinitionSnapshot]:
    source_digest = "sha256:" + "1" * 64
    entity_catalog_digest = "sha256:" + "2" * 64
    identity: dict[str, object] = {
        "executionId": execution_id,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity, SourceDefinitionSnapshot(source_digest)


def _post(
    root: Path,
    *,
    content_type: str,
    work: str,
    version: int,
    author_id: str,
    usage_scope: str = "research",
    variant_purpose: str = "original",
    status: str = "active",
    entity_refs: list[str] | None = None,
) -> str:
    post_ref = f"{content_type}/{work}/{version}"
    source_identity, source_digest = _source_identity()
    object_root = root / "posts" / post_ref
    write_json(
        object_root / "attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    evidence_digest = "sha256:" + hashlib.sha256(
        (object_root / "attestation.json").read_bytes()
    ).hexdigest()
    write_json(
        object_root / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "contentId": f"content-{work}",
            "version": version,
            "sourceType": "data",
            "executionId": "execution-a",
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "contentType": content_type,
            "authorId": author_id,
            "entityRefs": list(entity_refs or []),
            "variantPurpose": variant_purpose,
            "sourceAttribution": _source_attribution(),
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": usage_scope,
                "evidenceRef": "attestation.json",
                "evidenceDigest": evidence_digest,
            },
            "status": status,
        },
    )
    write_json(object_root / "creator.refs.json", {"creatorRefs": [author_id]})
    append_pool_record(
        object_root=object_root,
        record=build_canonical_pool_record(
            object_root=object_root,
            object_type="content",
            object_ref=post_ref,
        ),
    )
    return post_ref


def test_environment_release_selection__nested_balanced_prefix_and_versions__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    refs: list[str] = []
    for content_type in ("article", "image", "video"):
        for index in range(4):
            refs.append(
                _post(
                    publish_root,
                    content_type=content_type,
                    work=f"{content_type}-{index}",
                    version=1,
                    author_id=f"author-{index % 3}",
                )
            )
    original_ref = _post(
        publish_root,
        content_type="article",
        work="versioned",
        version=1,
        author_id="author-versioned",
    )
    commercial_ref = _post(
        publish_root,
        content_type="article",
        work="versioned",
        version=2,
        author_id="author-versioned",
        usage_scope="commercial",
        variant_purpose="commercial_variant",
    )
    commercial_original_ref = _post(
        publish_root,
        content_type="video",
        work="commercial-original",
        version=1,
        author_id="author-commercial",
        usage_scope="commercial",
    )
    refs.extend((original_ref, commercial_ref, commercial_original_ref))

    monkeypatch.setitem(subject.DATA_POST_CAPS, "alpha", 4)
    monkeypatch.setitem(subject.DATA_POST_CAPS, "beta", 8)
    monkeypatch.setitem(subject.DATA_POST_CAPS, "gamma", 100)

    alpha = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="alpha",
        release_class="research",
    )
    beta = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="beta",
        release_class="research",
    )
    gamma = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="gamma",
        release_class="research",
    )
    prod = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="prod",
        release_class="research",
    )
    commercial = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="prod",
        release_class="commercial",
    )

    assert alpha.post_refs == beta.post_refs[:4]
    assert beta.post_refs == gamma.post_refs[:8]
    assert alpha.counts["total"] == 4
    assert all(alpha.counts[content_type] > 0 for content_type in ("article", "image", "video"))
    assert original_ref in gamma.post_refs
    assert commercial_ref not in gamma.post_refs
    assert prod.post_refs == gamma.post_refs
    assert commercial_original_ref in prod.post_refs
    assert commercial_ref not in prod.post_refs
    assert alpha.pool_digest == beta.pool_digest == gamma.pool_digest == prod.pool_digest
    assert commercial.release_mode == "commercial"
    assert commercial.pool_digest == prod.pool_digest
    assert commercial.post_refs == (commercial_ref, commercial_original_ref)
    assert original_ref not in commercial.post_refs
    assert {
        row.code for row in commercial.excluded
    } == {"DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED"}


def test_environment_release_selection__legacy_requires_explicit_admission__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    post_ref = "image/legacy-work/1"
    write_json(
        publish_root / "posts" / post_ref / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "contentType": "image",
            "authorId": "legacy-author",
            "reviewDecision": "approved",
        },
    )
    write_json(
        publish_root / "posts" / post_ref / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed", "issues": []},
        },
    )

    alpha = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=[post_ref],
        environment="alpha",
        release_class="research",
    )
    prod = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=[post_ref],
        environment="prod",
        release_class="research",
    )

    assert alpha.post_refs == ()
    assert prod.post_refs == ()
    assert [row.code for row in alpha.excluded] == ["DATA.POOL.POST_NOT_ADMITTED"]


def test_explicit_sidecar_cannot_supply_missing_manifest_content_identity(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    post_ref = "image/pre-sequence-sidecar/1"
    root = publish_root / "posts" / post_ref
    write_json(
        root / "manifest.json",
        {
            "contentType": "image",
            "authorId": "pre-sequence-author",
            "version": 1,
        },
    )
    write_json(
        root / "_pool/versions/1.json",
        {
            "schema": "quwoquan_data.pool_object_record",
            "objectType": "content",
            "objectId": "sidecar-must-not-be-used",
            "objectRef": post_ref,
            "version": 1,
            "status": "active",
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "research",
            "evidenceRef": "attestation.json",
            "evidenceDigest": "sha256:" + "a" * 64,
            "payloadDigest": "sha256:" + "b" * 64,
        },
    )

    selection = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=[post_ref],
        environment="alpha",
        release_class="research",
    )

    assert selection.post_refs == ()
    assert [row.code for row in selection.excluded] == [
        "DATA.POOL.RECORD_SEQUENCE_MISSING"
    ]


def test_environment_release_selection__research_keeps_all_twenty_videos__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    refs = [
        _post(
            publish_root,
            content_type="video",
            work=f"video-{index:02d}",
            version=1,
            author_id=f"author-{index % 4}",
        )
        for index in range(20)
    ]

    selected = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        environment="alpha",
        release_class="research",
    )

    assert selected.counts == {
        "article": 0,
        "image": 0,
        "video": 20,
        "total": 20,
    }
    assert set(selected.post_refs) == set(refs)


def test_environment_release_selection__retired_version_is_not_released__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    active_ref = _post(
        publish_root,
        content_type="article",
        work="active-work",
        version=1,
        author_id="author-a",
    )
    retired_ref = _post(
        publish_root,
        content_type="image",
        work="retired-work",
        version=1,
        author_id="author-b",
        status="retired",
    )

    selected = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=[active_ref, retired_ref],
        environment="alpha",
        release_class="research",
    )

    assert selected.post_refs == (active_ref,)


def test_strict_pool_selection_excludes_only_object_with_missing_entity(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    write_json(
        publish_root / "creators/author-a/profile.json",
        {
            "authorId": "author-a",
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "attestation.json",
                "evidenceDigest": "sha256:" + "b" * 64,
            },
        },
    )
    entity_root = publish_root / "entities/地点/景区/实体甲"
    source_identity, source_digest = _source_identity()
    write_json(
        entity_root / "attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    entity_evidence_digest = "sha256:" + hashlib.sha256(
        (entity_root / "attestation.json").read_bytes()
    ).hexdigest()
    write_json(
        entity_root / "manifest.json",
        {
            "entityId": "实体甲",
            "entityRef": "/entity/地点/景区/实体甲",
            "executionId": "execution-a",
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "sourceAttribution": _source_attribution(),
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": entity_evidence_digest,
            },
        },
    )
    append_pool_record(
        object_root=entity_root,
        record=build_canonical_pool_record(
            object_root=entity_root,
            object_type="homepage",
            object_ref="地点/景区/实体甲",
        ),
    )
    ready_ref = _post(
        publish_root,
        content_type="article",
        work="ready",
        version=1,
        author_id="author-a",
        entity_refs=["/entity/地点/景区/实体甲"],
    )
    pending_ref = _post(
        publish_root,
        content_type="image",
        work="pending",
        version=1,
        author_id="author-a",
        entity_refs=["/entity/地点/景区/缺失实体"],
    )
    selected = subject.select_environment_release_posts(
        publish_root=publish_root,
        post_refs=[ready_ref, pending_ref],
        environment="alpha",
        release_class="research",
        strict_admission=True,
    )

    assert selected.post_refs == (ready_ref,)
    assert selected.counts == {"article": 1, "image": 0, "video": 0, "total": 1}
    assert [(row.post_ref, row.gate, row.code) for row in selected.excluded] == [
        (pending_ref, "delivery", "DATA.POOL.REFERENCE_MISSING")
    ]


def test_m100_selector_builds_exact_deterministic_research_cohort(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    refs: list[str] = []
    for content_type, count in (("article", 105), ("image", 105), ("video", 15)):
        for index in range(count):
            ref = _post(
                publish_root,
                content_type=content_type,
                work=f"{content_type}-{index:03d}",
                version=1,
                author_id=f"author-{index % 7}",
                entity_refs=[f"/entity/地点/景区/entity-{index % 100:03d}"],
            )
            refs.append(ref)

    first = subject.select_milestone_release_posts(
        publish_root=publish_root,
        post_refs=refs,
        milestone="M100",
        strict_admission=False,
    )
    second = subject.select_milestone_release_posts(
        publish_root=publish_root,
        post_refs=list(reversed(refs)),
        milestone="M100",
        strict_admission=False,
    )

    assert first.environment is None
    assert first.release_mode == "research"
    assert first.milestone_targets == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert first.counts == {
        "article": 100,
        "image": 100,
        "video": 10,
        "total": 210,
    }
    assert first.post_refs == second.post_refs
