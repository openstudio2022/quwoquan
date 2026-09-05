# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md
from __future__ import annotations

from pathlib import Path

import pytest
from content.release.canonical import aggregate_release_pool as pool
from content.release.canonical.environment_release_candidate import PoolCandidate
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.schema import assert_valid


def _cohort(*, milestone: str | None = None, release_class: str = "research") -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "quwoquan_data.release_cohort",
        "releaseClass": release_class,
        "producerBaselineRevision": "a" * 40,
        "objectRefs": ["posts/article/攻略/西湖/1"],
        "expectedCarrierCounts": {
            "homepage": 0,
            "article": 1,
            "image": 0,
            "video": 0,
        },
    }
    if milestone is not None:
        document["milestone"] = milestone
    return document


def _article_candidate() -> PoolCandidate:
    return PoolCandidate(
        post_ref="article/攻略/西湖/1",
        content_id="article-1",
        version=1,
        content_type="article",
        author_id="author-1",
        variant_purpose="original",
        usage_scope="research",
        selection_identity_digest="sha256:" + "1" * 64,
        canonical_object_digest="sha256:" + "2" * 64,
        content_library_binding_digest="sha256:" + "3" * 64,
    )


def _stub_pool_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pool,
        "discover_pool_candidates",
        lambda **_kwargs: ([_article_candidate()], []),
    )
    monkeypatch.setattr(
        pool,
        "candidate_closure",
        lambda *_args, **_kwargs: (set(), [], [], []),
    )
    monkeypatch.setattr(
        pool,
        "pool_audit_provenance",
        lambda *_args, **_kwargs: (
            ["20260905--travel-article-partial--china--pilot-001"],
            (),
            (),
            "sha256:" + "4" * 64,
        ),
    )
    monkeypatch.setattr(pool, "creator_tag_refs", lambda *_args, **_kwargs: [])


def test_partial_research_cohort_omits_milestone_and_builds_exact_explicit_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cohort = _cohort()
    assert_valid(cohort, "release", "release_cohort")
    _stub_pool_facts(monkeypatch)

    prepared = pool.prepare_pool_release(
        publish_root=tmp_path / "publish",
        cohort=cohort,
        release_class="research",
    )

    assert prepared.environment_selection.selection_scope == "explicit_cohort"
    assert prepared.environment_selection.milestone is None
    assert prepared.environment_selection.milestone_targets is None
    assert prepared.environment_selection.counts == {
        "homepage": 0,
        "article": 1,
        "image": 0,
        "video": 0,
        "total": 1,
    }


def test_commercial_post_scope_rejected_before_candidate_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cohort = _cohort(release_class="commercial")
    calls: list[str] = []
    monkeypatch.setattr(
        pool,
        "discover_pool_candidates",
        lambda **_kwargs: ([_article_candidate()], []),
    )
    monkeypatch.setattr(
        pool,
        "candidate_closure",
        lambda *_args, **_kwargs: calls.append("candidate_closure"),
    )

    with pytest.raises(ObjectTransactionError, match=(
        r"DATA\.POOL\.COMMERCIAL_RIGHTS_REQUIRED: "
        r"posts/article/攻略/西湖/1"
    )):
        pool.prepare_pool_release(
            publish_root=tmp_path / "publish",
            cohort=cohort,
            release_class="commercial",
        )

    assert calls == []
    assert not (tmp_path / "publish").exists()


def test_milestone_claim_still_requires_policy_exact_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cohort = _cohort(milestone="M1")
    assert_valid(cohort, "release", "release_cohort")
    _stub_pool_facts(monkeypatch)

    with pytest.raises(ObjectTransactionError, match="MILESTONE_COUNT_DRIFT"):
        pool.prepare_pool_release(
            publish_root=tmp_path / "publish",
            cohort=cohort,
            release_class="research",
        )
