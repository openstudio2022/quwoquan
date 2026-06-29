"""Contract: creator content is bound to batch-100 creators via the real router.

Covers Phase 3 of the no-breakpoint E2E closure: ``content_bind`` routes a
representative article/image/video subset through ``match_creator`` and the full
``creator_assignment_issues`` gate, producing the production binding truth source
(``creator_content.seed.json``). These assertions guarantee the binding can never
regress into wrong-carrier / wrong-coverage / non-batch authorship.
"""
from __future__ import annotations

import json

from _common.creator_assignment import creator_assignment_from_profile, creator_assignment_issues
from _common.creator_pool.io import repo_seed_fixture_dir
from _common.creator_pool.media_assets import media_root
from governance.creator_pool.content_bind import (
    CARRIERS,
    CONTENT_SEED_NAME,
    _content_document,
    build_creator_content,
)
from governance.creator_pool.content_rollout import build_prod_rollout_dryrun
from template.registry import TemplateRegistry

BATCH_PREFIX = "qwq_creator_travel_"


def _payload() -> dict:
    return build_creator_content(batch_id="travel_batch_100_v1")


def test_subset_covers_all_three_carriers_with_distinct_authors() -> None:
    payload = _payload()
    assert payload["previewOnly"] is False
    assert payload["routedBy"] == "match_creator"
    carriers = [p["carrier"] for p in payload["posts"]]
    assert carriers == list(CARRIERS)
    authors = {p["authorId"] for p in payload["posts"]}
    assert len(authors) == len(payload["posts"]) == payload["distinctAuthors"]


def test_every_post_is_bound_to_an_active_batch_creator() -> None:
    registry = TemplateRegistry.load()
    payload = _payload()
    for post in payload["posts"]:
        profile = registry.creators.get(post["creatorProfileId"])
        assert profile is not None, post["creatorProfileId"]
        assert str(profile.get("creatorProfileId")).startswith(BATCH_PREFIX)
        assert str(profile.get("status")) == "active"
        assert post["cohortId"] == "travel_batch_100_v1"


def test_carrier_matches_content_type_and_routed_via_match_creator() -> None:
    payload = _payload()
    for post in payload["posts"]:
        assert post["contentType"] == post["carrier"]
        assert post["routedBy"] == "match_creator"


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
    report = build_prod_rollout_dryrun(batch_id="travel_batch_100_v1")
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
        author.startswith("agent_author_travel_travel_batch_100_v1_") for author in report["boundAuthors"]
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
            assert profile["contentVertical"] == "travel"
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
