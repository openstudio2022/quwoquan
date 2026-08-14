"""场景组：article carrier 的 governed site frontier 回退边界。

homepage/article source-ready acquisition 契约测试（public mediawiki）。

从 test_homepage_article_source_ready_acquisition__public_mediawiki__contract__local_contract_test.py
按场景拆出：frontier 全无候选时 wikipedia 词条按原路径产出 article capsule、
非 wikipedia seed 的 frontier 拒绝不得偷换 fallback；测试逐字搬移。
共享常量与构造 helper 见
tests/support/homepage_article_source_ready_acquisition_fixture.py。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.source.research.homepage_article_source_ready_acquisition import (
    HomepageArticleSourceReadyAcquisitionError,
    acquire_homepage_article_source_ready_batch,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
)
from support.homepage_article_source_ready_acquisition_fixture import (
    CAPTURED_AT,
    IDENTITY,
    _fake_acquired,
    _planned,
    _projection,
    _seed_selection,
    _sha,
)


def test_article_site_frontier_falls_back_to_wikipedia_detail_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """governed site frontier 全部无候选时，coverage 认证过的 wikipedia 词条按原路径产出 article capsule。"""
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("文章回退实体")]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"article-fallback-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(
            evidence_root, rows
        ),
    )
    frontier_calls: list[str] = []

    def frontier(row: dict[str, object], **_: object) -> AcquiredSourceReadyCandidate:
        frontier_calls.append(str(row["candidateName"]))
        raise MediaWikiSourceReadyRejected(
            "article site frontier produced no source-ready detail page: "
            "no governed site candidate"
        )

    wikipedia_calls: list[tuple[str, str]] = []

    def wikipedia(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        wikipedia_calls.append((carrier, str(row["candidateName"])))
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(
        mod, "acquire_article_site_source_ready_candidate", frontier
    )
    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", wikipedia)
    result = acquire_homepage_article_source_ready_batch(
        coverage_run_dir=tmp_path / "coverage",
        output_root=tmp_path / "output",
        source_set_id="m100-article-wikipedia-fallback",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
        homepage_count=0,
        article_count=1,
        seed_selection=_seed_selection(
            tmp_path / "seed-selection.json",
            rows,
            homepage_count=0,
            seed_origin="current_coverage",
        ),
    )

    assert frontier_calls == ["文章回退实体"]
    assert wikipedia_calls == [("article", "文章回退实体")]
    assert result["counts"] == {"homepage": 0, "article": 1}


def test_article_non_wikipedia_seed_keeps_frontier_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 wikipedia seed 的 frontier 拒绝不得偷换成任何 fallback 页面。"""
    from content.source.research import homepage_article_source_ready_acquisition as mod

    row = _planned("头条文章实体")
    source = row["source"]
    assert isinstance(source, dict)
    source["sourceKind"] = "toutiao_baike"
    source["extractor"] = "toutiao_baike_html"
    rows = [row]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"article-no-fallback-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(
            evidence_root, rows
        ),
    )
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MediaWikiSourceReadyRejected(
                "article site frontier produced no source-ready detail page: "
                "no governed site candidate"
            )
        ),
    )

    def forbidden(*_args: object, **_kwargs: object) -> AcquiredSourceReadyCandidate:
        raise AssertionError("non-wikipedia article seed must not reach mediawiki")

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", forbidden)
    with pytest.raises(HomepageArticleSourceReadyAcquisitionError) as captured:
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-article-no-fallback",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=0,
            article_count=1,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json",
                rows,
                homepage_count=0,
                seed_origin="current_coverage",
            ),
        )
    assert captured.value.code == mod.SOURCE_POOL_SHORTFALL
    assert "no governed site candidate" in str(captured.value)
