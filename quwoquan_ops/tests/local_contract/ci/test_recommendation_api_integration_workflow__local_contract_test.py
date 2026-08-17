from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_recommendation_api_integration_pr_targets_only_main() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:\n    branches:\n      - main\n    paths:" in workflow


def test_recommendation_api_integration_uses_canonical_content_post_package() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    assert "./services/content-service/tests/api_integration/content/post/" in workflow
    assert "./services/content-service/tests/api_integration/content/content/post/" not in workflow
    assert "sudo apt-get install -y --no-install-recommends ffmpeg" in workflow


def test_recommendation_required_tests_follow_current_object_owners() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    for required in (
        "TestBehaviorBatchAssistantInterestAllowsEmptyContentID",
        "TestBehaviorBatchPersistsCanonicalFunnelStates",
        "test_premium_pool_stream_projects_mongo_admission_before_ack",
        "test_flywheel_funnel_multi_dimension_honest_counts",
    ):
        assert required in workflow
    for retired in (
        "TestPremiumPoolEventChainServesAndEjectsPremiumFeed",
        "TestBehaviorBatchAssistantInterestProjectsTagInteraction",
        "TestBehaviorBatchSevenStateImpressionExcludesVisibleCountsClick",
    ):
        assert retired not in workflow


def test_recommendation_failure_log_is_short_lived_and_non_blocking() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    assert "if: ${{ failure() && !cancelled() }}" in workflow
    assert "continue-on-error: true" in workflow
    assert "retention-days: 3" in workflow
