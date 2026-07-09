"""Contract: creator content is bound to the canonical travel-photo 1k creators via the real router.

Covers Phase 3 of the no-breakpoint E2E closure: ``content_bind`` routes a
representative article/image/video subset through ``match_creator`` and the full
``creator_assignment_issues`` gate, producing the production binding truth source
(``creator_content.travel_photo_1k_v1.seed.json``). These assertions guarantee the binding can never
regress into wrong-carrier / wrong-coverage / non-batch authorship.
"""
from __future__ import annotations

import json
from pathlib import Path

from _common.creator_assignment import creator_assignment_from_profile, creator_assignment_issues
from _common.creator_pool.io import repo_seed_fixture_dir
from _common.creator_pool.media_assets import media_root
from _common.io import read_json
from governance.creator_pool.content_bind import (
    CARRIERS,
    CONTENT_SEED_NAME,
    WORKLOAD_LANES,
    _content_document,
    build_creator_content,
)
from governance.creator_pool.content_rollout import build_prod_rollout_dryrun
from template.registry import TemplateRegistry

BATCH_ID = "travel_photo_1k_v1"
REPO = Path(__file__).resolve().parents[4]
ENTITY_SCENARIOS = REPO / "quwoquan_service/contracts/metadata/entity/test_fixtures/scenarios/entity_scenarios.json"
CIRCLE_SCENARIOS = REPO / "quwoquan_service/contracts/metadata/social/circle/test_fixtures/scenarios/circle_scenarios.json"


def _payload() -> dict:
    return build_creator_content(batch_id=BATCH_ID)


def test_workload_covers_all_three_carriers_and_lanes_with_distinct_authors() -> None:
    payload = _payload()
    assert payload["previewOnly"] is False
    assert payload["routedBy"] == "match_creator"
    carriers = {p["carrier"] for p in payload["posts"]}
    lanes = {p["workloadLane"] for p in payload["posts"]}
    assert carriers == set(CARRIERS)
    assert lanes == set(WORKLOAD_LANES)
    authors = {p["authorId"] for p in payload["posts"]}
    assert len(payload["posts"]) == len(CARRIERS) * len(WORKLOAD_LANES)
    assert len(authors) == len(payload["posts"]) == payload["distinctAuthors"]


def test_every_post_is_bound_to_an_active_batch_creator() -> None:
    registry = TemplateRegistry.load()
    payload = _payload()
    for post in payload["posts"]:
        profile = registry.creators.get(post["creatorProfileId"])
        assert profile is not None, post["creatorProfileId"]
        assert str(profile.get("cohortId")) == BATCH_ID
        assert str(profile.get("status")) == "active"
        assert post["cohortId"] == BATCH_ID
        assert post["authorDisplayName"]
        assert post["authorAvatarObjectKey"] == post["authorAvatarUrl"]
        assert post["contentTagRefs"] == post["tagRefs"]
        assert isinstance(post["entityRefs"], list)
        assert isinstance(post["circleRefs"], list)
        assert post["workloadLane"] in WORKLOAD_LANES


def test_carrier_matches_content_type_and_routed_via_match_creator() -> None:
    payload = _payload()
    for post in payload["posts"]:
        assert post["contentType"] == post["carrier"]
        assert post["routedBy"] == "match_creator"


def test_workload_reaches_travel_photo_and_cross_homepage_circle_surfaces() -> None:
    payload = _payload()
    entity_refs = {ref for post in payload["posts"] for ref in post["entityRefs"]}
    circle_refs = {ref for post in payload["posts"] for ref in post["circleRefs"]}
    cross_posts = [post for post in payload["posts"] if post["workloadLane"] == "cross"]
    entity_fixture = read_json(ENTITY_SCENARIOS)
    circle_fixture = read_json(CIRCLE_SCENARIOS)
    homepage_ids = {
        row["homepageId"]
        for row in entity_fixture["seedSets"]["entity_homepage_core"]["homepages"]
    }
    circle_ids = {
        row["id"]
        for row in circle_fixture["seedSets"]["circle_core"]["circles"]
    }
    assert any(ref == "fixture_homepage_travel_photo_west_lake" for ref in entity_refs)
    assert any(ref == "fixture_homepage_travel_gear_sony_a7m4" for ref in entity_refs)
    assert any(ref == "fixture_circle_travel" for ref in circle_refs)
    assert any(ref == "fixture_circle_photo" for ref in circle_refs)
    assert entity_refs <= homepage_ids
    assert circle_refs <= circle_ids
    assert cross_posts
    assert any(
        "Topic/旅行/" in " ".join(post["tagRefs"]) and "Topic/摄影/" in " ".join(post["tagRefs"])
        for post in cross_posts
    )


def test_every_binding_passes_the_assignment_gate_on_revalidation() -> None:
    registry = TemplateRegistry.load()
    payload = _payload()
    for post in payload["posts"]:
        profile = registry.creators[post["creatorProfileId"]]
        assignment = creator_assignment_from_profile(profile)
        revalidation = {
            **assignment,
            "vertical": post["vertical"],
            "region": post["region"],
            "tagRefs": post["tagRefs"],
        }
        issues = creator_assignment_issues(
            revalidation,
            carrier=post["carrier"],
            content_vertical=post["vertical"],
            content_region=post["region"],
            content_tag_refs=post["tagRefs"],
        )
        assert issues == [], f"{post['postId']}: {issues}"


def test_referenced_media_exists_in_vcs() -> None:
    root = media_root()
    payload = _payload()
    for post in payload["posts"]:
        for key in (post["authorAvatarUrl"], post["coverUrl"]):
            assert key, post["postId"]
            assert (root / key).is_file(), f"missing media: {key}"


def test_prod_rollout_dryrun_is_go_with_pure_prod_invariant() -> None:
    report = build_prod_rollout_dryrun(batch_id=BATCH_ID)
    assert report["decision"] == "go", report["issues"]
    assert report["dryRun"] is True
    stages = [s["stage"] for s in report["rolloutStages"]]
    assert stages == ["shadow", "canary", "ramp", "ga"]
    purity = report["prodPurity"]
    assert purity["singleProdPackage"] is True
    assert purity["prodGrayPackageExists"] is False
    assert purity["prodDataSource"] == "remote"
    assert purity["prodCarriesTestFixtures"] is False
    assert report["boundAuthors"] and all(
        author.startswith(("sys_travel_", "sys_photo_", "sys_travelphoto_")) and author.endswith("_sub_01")
        for author in report["boundAuthors"]
    )


def test_article_projection_carries_markdown_kernel_not_article_document() -> None:
    """The article content document must use the Markdown kernel (articleMarkdown +
    articleRenderProfile, never articleDocument), so the markdown-article gate and the
    end-to-end reader contract hold for the cold-start creator article."""
    payload = _payload()
    for index, post in enumerate(payload["posts"]):
        doc = _content_document(post, index)
        if post["carrier"] == "article":
            assert "articleDocument" not in doc
            markdown = doc["articleMarkdown"]
            assert isinstance(markdown, str) and markdown.strip()
            assert markdown.startswith("---"), "article markdown must carry front matter"
            assert "template: journal" in markdown
            profile = doc["articleRenderProfile"]
            assert isinstance(profile, dict)
            assert profile["template"] == "journal"
            assert profile["contentVertical"] == post["vertical"]
            assert isinstance(profile["layoutPolicy"], dict)
        else:
            # image/video carriers must not leak the article-only kernel fields.
            assert "articleMarkdown" not in doc
            assert "articleRenderProfile" not in doc
            assert "articleDocument" not in doc


def test_persisted_seed_matches_producer_output() -> None:
    """The committed seed must be a faithful, reproducible match_creator output."""
    seed_path = repo_seed_fixture_dir() / CONTENT_SEED_NAME
    assert seed_path.is_file(), seed_path
    on_disk = json.loads(seed_path.read_text(encoding="utf-8"))
    fresh = _payload()
    # generatedAt is a timestamp; everything else must be deterministic.
    on_disk.pop("generatedAt", None)
    fresh.pop("generatedAt", None)
    assert on_disk == fresh
