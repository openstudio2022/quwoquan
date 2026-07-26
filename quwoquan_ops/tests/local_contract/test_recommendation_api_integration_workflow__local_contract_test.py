from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_recommendation_api_integration_uses_canonical_content_post_package() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    assert "./services/content-service/tests/api_integration/content/post/" in workflow
    assert "./services/content-service/tests/api_integration/content/content/post/" not in workflow


def test_recommendation_failure_log_is_short_lived_and_non_blocking() -> None:
    workflow = (ROOT / ".github/workflows/recommendation_api_integration.yml").read_text(
        encoding="utf-8"
    )

    assert "if: ${{ failure() && !cancelled() }}" in workflow
    assert "continue-on-error: true" in workflow
    assert "retention-days: 3" in workflow
