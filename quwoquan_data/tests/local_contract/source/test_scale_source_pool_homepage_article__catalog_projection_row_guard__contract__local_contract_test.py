# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
"""场景组：projection 行语义、确定性、物理复验与拒绝护栏。

从 test_scale_source_pool_homepage_article__catalog_projection__contract
__local_contract_test.py 按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.source.research.scale_source_pool import (
    build_scale_source_pool_plan,
    validate_scale_source_pool_evidence,
)
from content.source.research.scale_source_pool_homepage_article import (
    PROJECTION_INVALID,
    ScaleSourcePoolProjectionError,
    project_scale_source_pool_homepage_article,
)

from support.scale_source_pool_catalog_fixture import (
    IDENTITY,
    _article_candidate,
    _catalogs,
    _digest,
    _file_digest,
    _homepage_candidate,
)
from support.scale_source_pool_projection_fixture import (
    _clone_row,
    _project,
    _source_ready_batch,
)


def test_projection_is_deterministic_and_contains_no_go_decision(tmp_path: Path) -> None:
    projection = _project(tmp_path)
    replay = _project(tmp_path)

    assert replay == projection
    assert "decision" not in projection
    assert projection["projectionDigest"].startswith("sha256:")
    assert projection["rowCounts"] == [
        {"carrier": "homepage", "candidateCount": 1},
        {"carrier": "article", "candidateCount": 1},
    ]
    rows = {row["carrier"]: row for row in projection["rows"]}
    assert rows["homepage"]["objectRef"].startswith("entities/")
    assert rows["article"]["objectRef"].startswith("posts/article/")
    for row in rows.values():
        for prefix in ("sourceUnit", "acquisition", "rights", "quality"):
            assert row[f"{prefix}Ref"].startswith("capsules/")
            assert row[f"{prefix}Digest"].startswith("sha256:")
            assert row[f"{prefix}FileSha256"].startswith("sha256:")


def test_projection_allows_homepage_only_without_article_catalog(tmp_path: Path) -> None:
    homepage, article, homepage_path, _article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=None,
        article_catalog_digest=None,
        article_catalog_file_sha256=None,
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
        active_carriers=("homepage",),
    )

    assert [row["carrier"] for row in projection["rows"]] == ["homepage"]
    assert [row["carrier"] for row in projection["catalogBindings"]] == [
        "homepage",
        "homepage_article_source_set",
    ]


def test_projection_allows_article_only_without_homepage_catalog(tmp_path: Path) -> None:
    homepage, article, _homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=None,
        homepage_catalog_digest=None,
        homepage_catalog_file_sha256=None,
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
        active_carriers=("article",),
    )

    assert [row["carrier"] for row in projection["rows"]] == ["article"]
    assert [row["carrier"] for row in projection["catalogBindings"]] == [
        "article",
        "homepage_article_source_set",
    ]


def test_projection_rebases_nested_source_set_member_root_to_evidence_root(
    tmp_path: Path,
) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    source_set_root = tmp_path / "homepage-article-source-ready" / "m100" / "set-1"
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        source_set_root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    source_set_ref = (source_set_root / batch_ref).relative_to(tmp_path).as_posix()

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=source_set_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )

    assert {
        row["sourceReadyEvidenceRootRef"] for row in projection["rows"]
    } == {"homepage-article-source-ready/m100/set-1"}


def test_projection_accepts_different_catalog_and_capsule_order(tmp_path: Path) -> None:
    homepage, article, homepage_path, article_path = _catalogs(
        tmp_path,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(reversed(homepage["candidates"])),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )

    assert [
        row["candidateId"]
        for row in projection["rows"]
        if row["carrier"] == "homepage"
    ] == ["homepage-west-lake-0", "homepage-west-lake-1"]


def test_text_only_article_projects_without_inventing_media_or_commercial_rights(
    tmp_path: Path,
) -> None:
    article = _article_candidate()
    article["publishMediaMode"] = "text_only"
    article["assets"] = []

    projection = _project(tmp_path, article_candidates=[article])
    row = next(row for row in projection["rows"] if row["carrier"] == "article")

    assert row["publishMediaMode"] == "text_only"
    assert row["distributionDecision"] == "research_allowed"
    assert row["rightsStatus"] == "unverified"


def test_projected_refs_are_physically_reverified_by_scale_validator(
    tmp_path: Path,
) -> None:
    projection = _project(tmp_path)
    base = {row["carrier"]: row for row in projection["rows"]}
    candidates = [
        *(
            _clone_row(base["homepage"], carrier="homepage", index=index, provider="维基百科")
            for index in range(180)
        ),
        *(
            _clone_row(base["article"], carrier="article", index=index, provider="维基百科")
            for index in range(180)
        ),
    ]
    image_providers = ["Pinterest"] * 80 + ["图虫"] * 20 + ["Pexels"] * 50 + ["Wikimedia Commons"] * 30
    candidates.extend(
        _clone_row(
            base["article"],
            carrier="image",
            index=index,
            provider=provider,
            evidence_root=tmp_path,
        )
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _clone_row(
            base["article"],
            carrier="video",
            index=index,
            provider="Pexels Videos",
            evidence_root=tmp_path,
        )
        for index in range(18)
    )
    plan = build_scale_source_pool_plan(
        pool_id="projection-physical-proof",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        created_at="2026-08-08T00:00:00Z",
        candidates=candidates,
    )
    evidence = validate_scale_source_pool_evidence(plan, evidence_root=tmp_path)
    assert evidence["evidenceFileSha256Verified"] is True
    assert evidence["evidenceFileCount"] == 200
    assert evidence["evidenceBindingCount"] == 1638


def test_projection_rejects_cross_catalog_identity(tmp_path: Path) -> None:
    drifted = {**IDENTITY, "sourceDigest": "sha256:" + "d" * 64}
    with pytest.raises(
        ScaleSourcePoolProjectionError, match="source identity drift"
    ) as captured:
        _project(tmp_path, article_identity=drifted)
    assert captured.value.code == PROJECTION_INVALID


def test_projection_rejects_duplicate_object_and_content(tmp_path: Path) -> None:
    object_root = tmp_path / "object"
    homepage, article, homepage_path, article_path = _catalogs(
        object_root,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        object_root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    duplicate_ref = homepage["candidates"][0]["entityRef"]
    homepage["candidates"][1]["entityRef"] = duplicate_ref
    homepage["candidates"][1]["observedEntityRef"] = duplicate_ref
    homepage["candidates"][1]["hero"]["entityRef"] = duplicate_ref
    homepage["candidates"][1]["hero"]["observedEntityRef"] = duplicate_ref
    homepage = _redigest(homepage)
    homepage_path.write_text(
        json.dumps(homepage, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ScaleSourcePoolProjectionError, match="duplicate entityRef"):
        project_scale_source_pool_homepage_article(
            evidence_root=object_root,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )

    duplicate_content = [
        _article_candidate(0, content_seed=0),
        _article_candidate(1, content_seed=0),
    ]
    with pytest.raises(
        ScaleSourcePoolProjectionError, match="duplicate physical content"
    ):
        _project(tmp_path / "content", article_candidates=duplicate_content)


def _redigest(catalog: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    return {**stable, "catalogDigest": _digest(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")))}


@pytest.mark.parametrize("carrier", ["homepage", "article"])
def test_projection_rejects_missing_media_closure(
    tmp_path: Path,
    carrier: str,
) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    if carrier == "homepage":
        homepage["candidates"][0]["hero"]["generated"] = True
        homepage = _redigest(homepage)
        homepage_path.write_text(json.dumps(homepage, ensure_ascii=False), encoding="utf-8")
    else:
        article["candidates"][0]["assets"] = article["candidates"][0]["assets"][:1]
        article = _redigest(article)
        article_path.write_text(json.dumps(article, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ScaleSourcePoolProjectionError, match="catalog contract is invalid"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )


def test_projection_rejects_catalog_digest_and_file_drift(tmp_path: Path) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    with pytest.raises(ScaleSourcePoolProjectionError, match="catalogDigest drift"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest="sha256:" + "f" * 64,
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )

    original_sha = _file_digest(homepage_path)
    homepage_path.write_bytes(homepage_path.read_bytes() + b"\n")
    with pytest.raises(ScaleSourcePoolProjectionError, match="fileSha256 drift"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=original_sha,
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )
