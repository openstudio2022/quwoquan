# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-021.t5
"""The read-only precheck is the production-to-release handoff gate.

It must reach the same verdict as `pool-build` without writing anything, and it
must stay usable while the pool is still far from the milestone: that is exactly
when a production session needs the per-object reasons.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import pool_precheck as subject  # noqa: E402
from content.release.canonical.aggregate_release_pool import (  # noqa: E402
    prepare_pool_release,
)
from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.environment_release_selection import (  # noqa: E402
    MILESTONE_TARGETS,
)
from content.release.canonical.object_source_identity import (  # noqa: E402
    source_identity_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from core.io import write_json  # noqa: E402
from core.paths import PUBLISH_ROOT  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)


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
        "derivedModifications": [],
    }


def _source_identity() -> tuple[dict[str, object], SourceDefinitionSnapshot]:
    source_digest = "sha256:" + "1" * 64
    entity_catalog_digest = "sha256:" + "2" * 64
    identity: dict[str, object] = {
        "executionId": "execution-a",
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity, SourceDefinitionSnapshot(source_digest)


def _admitted_creator(publish_root: Path, author_id: str) -> None:
    write_json(
        publish_root / "creators" / author_id / "profile.json",
        {
            "authorId": author_id,
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


def _admitted_entity(publish_root: Path, name: str) -> str:
    entity_ref = f"地点/景区/{name}"
    root = publish_root / "entities" / entity_ref
    write_json(
        root / "attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    evidence_digest = "sha256:" + hashlib.sha256(
        (root / "attestation.json").read_bytes()
    ).hexdigest()
    source_identity, source_digest = _source_identity()
    write_json(
        root / "manifest.json",
        {
            "entityId": name,
            "entityRef": f"/entity/{entity_ref}",
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
                "evidenceDigest": evidence_digest,
            },
        },
    )
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="homepage",
            object_ref=entity_ref,
        ),
    )
    return entity_ref


def _admitted_post(
    publish_root: Path,
    *,
    content_type: str,
    work: str,
    author_id: str,
    entity_refs: list[str],
    generator: str = "agent",
) -> str:
    post_ref = f"{content_type}/{work}/1"
    root = publish_root / "posts" / post_ref
    write_json(
        root / "attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    evidence_digest = "sha256:" + hashlib.sha256(
        (root / "attestation.json").read_bytes()
    ).hexdigest()
    source_identity, source_digest = _source_identity()
    write_json(
        root / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "contentId": f"content-{work}",
            "version": 1,
            "sourceType": "data",
            "executionId": "execution-a",
            "sourceDigest": source_digest.to_document(),
            "sourceIdentity": source_identity,
            "contentType": content_type,
            "generator": generator,
            "authorId": author_id,
            "entityRefs": list(entity_refs),
            "variantPurpose": "original",
            "sourceAttribution": _source_attribution(),
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "attestation.json",
                "evidenceDigest": evidence_digest,
            },
            "status": "active",
        },
    )
    write_json(root / "creator.refs.json", {"creatorRefs": [author_id]})
    append_pool_record(
        object_root=root,
        record=build_canonical_pool_record(
            object_root=root,
            object_type="content",
            object_ref=post_ref,
        ),
    )
    return post_ref


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_precheck_selectable_set_equals_the_real_pool_build_selection__local_contract() -> None:
    """The handoff verdict must come from pool-build's own chain, not a copy."""

    publish_root = Path(PUBLISH_ROOT).resolve()
    report = subject.precheck_pool_release(
        publish_root=publish_root,
        milestone="M100",
    )
    try:
        preparation = prepare_pool_release(
            publish_root=publish_root,
            all_publishable=True,
            release_class="research",
        )
    except ObjectTransactionError:
        # An entirely ineligible pool must still be reported as a verdict.
        assert report.status == "blocked"
        assert report.selectable_post_refs == ()
        assert report.blockers
        return

    assert report.selectable_post_refs == tuple(
        sorted(preparation.environment_selection.post_refs)
    )
    assert sum(report.carrier_counts.values()) == len(
        preparation.environment_selection.post_refs
    )
    assert report.pool_digest == preparation.environment_selection.pool_digest
    assert report.exclusion_source == "chain"
    assert {row["code"] for row in report.excluded} == {
        row["code"] for row in preparation.excluded
    }


def test_precheck_writes_nothing_to_the_canonical_pool__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    _admitted_creator(publish_root, "author-a")
    entity_ref = _admitted_entity(publish_root, "实体甲")
    _admitted_post(
        publish_root,
        content_type="article",
        work="a1",
        author_id="author-a",
        entity_refs=[f"/entity/{entity_ref}"],
    )
    before = _tree_fingerprint(publish_root)

    subject.precheck_pool_release(publish_root=publish_root, milestone="M100")

    assert _tree_fingerprint(publish_root) == before


def test_precheck_counts_stay_below_the_milestone_optimistic_publishable__local_contract(
    tmp_path: Path,
) -> None:
    """A post can pass the selector and still fail the closure.

    The milestone selector counts before any object reaches candidate_closure,
    so its `publishable` is optimistic. The precheck must report the post-closure
    truth, which is the whole reason it exists.
    """

    publish_root = tmp_path / "publish"
    _admitted_creator(publish_root, "author-a")
    # An admitted entity whose closure is incomplete: the post clears the
    # selector and is only rejected once the closure runs.
    entity_ref = _admitted_entity(publish_root, "实体甲")
    _admitted_post(
        publish_root,
        content_type="article",
        work="a1",
        author_id="author-a",
        entity_refs=[f"/entity/{entity_ref}"],
    )

    report = subject.precheck_pool_release(
        publish_root=publish_root,
        milestone="M100",
    )

    assert report.status == "blocked"
    assert report.carrier_counts["article"] == 0
    milestone_blockers = [
        blocker for blocker in report.blockers if blocker.stage == "milestone"
    ]
    assert [blocker.code for blocker in milestone_blockers] == [
        "DATA.POOL.MILESTONE_SHORTFALL"
    ]
    assert "'article': 1" in milestone_blockers[0].message
    assert report.exclusion_source == "replayed"
    assert [row["code"] for row in report.excluded] == [
        "DATA.POOL.OBJECT_INVALID"
    ]


def test_precheck_attributes_selector_stage_reasons_per_object__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    _admitted_creator(publish_root, "author-a")
    entity_ref = _admitted_entity(publish_root, "实体甲")
    _admitted_post(
        publish_root,
        content_type="image",
        work="legacy-evidence-pack",
        author_id="author-a",
        entity_refs=[f"/entity/{entity_ref}"],
        generator="image_evidence_pack",
    )
    _admitted_post(
        publish_root,
        content_type="article",
        work="dangling-entity",
        author_id="author-a",
        entity_refs=["/entity/地点/景区/缺失实体"],
    )

    report = subject.precheck_pool_release(
        publish_root=publish_root,
        milestone="M100",
    )

    assert report.status == "blocked"
    assert report.exclusion_source == "replayed"
    assert report.excluded_by_code == {
        "DATA.POOL.GENERATOR_PROVENANCE_INVALID": 1,
        "DATA.POOL.REFERENCE_MISSING": 1,
    }


def test_precheck_carrier_targets_derive_from_the_milestone_policy__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    _admitted_creator(publish_root, "author-a")

    report = subject.precheck_pool_release(
        publish_root=publish_root,
        milestone="M100",
    )

    targets = MILESTONE_TARGETS["M100"]
    assert {gap.carrier for gap in report.carrier_gaps} == set(targets)
    assert all(gap.target == targets[gap.carrier] for gap in report.carrier_gaps)
    assert all(gap.gap == gap.target - gap.selectable for gap in report.carrier_gaps)
    gaps = {gap.carrier: gap for gap in report.carrier_gaps}
    admitted_homepages = report.homepage_observation.get("admittedHomepageObjects")
    assert gaps[subject.HOMEPAGE_CARRIER].selectable == int(admitted_homepages or 0)
    assert gaps[subject.HOMEPAGE_CARRIER].target == report.homepage_observation[
        "homepageTarget"
    ]


def test_precheck_rejects_an_unknown_milestone__local_contract(
    tmp_path: Path,
) -> None:
    try:
        subject.precheck_pool_release(
            publish_root=tmp_path / "publish",
            milestone="M42",
        )
    except ObjectTransactionError as exc:
        assert "DATA.POOL.MILESTONE_INVALID" in str(exc)
    else:  # pragma: no cover - the precheck must not accept unknown milestones
        raise AssertionError("unknown milestone must fail closed")


def test_precheck_document_is_stable_and_detail_gated__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    _admitted_creator(publish_root, "author-a")
    report = subject.precheck_pool_release(
        publish_root=publish_root,
        milestone="M100",
    )

    summary = report.as_document(details=False)
    detailed = report.as_document(details=True)

    assert json.dumps(summary, ensure_ascii=False, sort_keys=True)
    assert "excluded" not in summary
    assert "selectablePostRefs" not in summary
    assert summary["status"] == "blocked"
    assert summary["exclusionSource"] in {"chain", "replayed"}
    assert detailed["excluded"] == [dict(row) for row in report.excluded]
    assert detailed["selectablePostRefs"] == list(report.selectable_post_refs)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
