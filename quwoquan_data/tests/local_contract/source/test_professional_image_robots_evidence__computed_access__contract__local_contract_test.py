from __future__ import annotations

import copy

import pytest
from content.source.professional_image_robots_evidence import (
    ROBOTS_ACCESS_BLOCKED,
    ROBOTS_EVIDENCE_INVALID,
    ProfessionalImageRobotsEvidenceError,
    build_professional_image_robots_evidence,
    validate_professional_image_robots_evidence,
)

OBSERVED = "2026-08-08T08:00:00Z"
AGENT = "quwoquan-public-discovery/1"


def test_pinterest_search_is_computed_disallowed_from_robots_body() -> None:
    target = "https://www.pinterest.com/search/pins/?q=west+lake"
    evidence = build_professional_image_robots_evidence(
        provider="pinterest",
        robots_url="https://www.pinterest.com/robots.txt",
        robots_body="User-agent: *\nDisallow: /search/\nAllow: /\n",
        user_agent=AGENT,
        target_url=target,
        observed_at=OBSERVED,
    )
    assert evidence["allowed"] is False
    with pytest.raises(ProfessionalImageRobotsEvidenceError) as captured:
        validate_professional_image_robots_evidence(
            evidence, provider="pinterest", target_url=target
        )
    assert captured.value.code == ROBOTS_ACCESS_BLOCKED


def test_tuchong_explore_is_allowed_and_digest_bound() -> None:
    target = "https://tuchong.com/explore/"
    evidence = build_professional_image_robots_evidence(
        provider="tuchong",
        robots_url="https://tuchong.com/robots.txt",
        robots_body="User-agent: *\nAllow: /explore/\nDisallow: /private/\n",
        user_agent=AGENT,
        target_url=target,
        observed_at=OBSERVED,
    )
    assert validate_professional_image_robots_evidence(
        evidence, provider="tuchong", target_url=target
    ) == evidence
    drifted = copy.deepcopy(evidence)
    drifted["allowed"] = False
    with pytest.raises(ProfessionalImageRobotsEvidenceError) as captured:
        validate_professional_image_robots_evidence(
            drifted, provider="tuchong", target_url=target
        )
    assert captured.value.code == ROBOTS_EVIDENCE_INVALID


@pytest.mark.parametrize(
    ("provider", "robots_url", "target_url"),
    [
        ("pinterest", "https://tuchong.com/robots.txt", "https://www.pinterest.com/"),
        ("tuchong", "https://tuchong.com/not-robots.txt", "https://tuchong.com/explore/"),
        ("tuchong", "https://tuchong.com/robots.txt", "https://example.test/explore/"),
    ],
)
def test_robots_evidence_rejects_provider_path_and_target_drift(
    provider: str, robots_url: str, target_url: str
) -> None:
    with pytest.raises(ProfessionalImageRobotsEvidenceError) as captured:
        build_professional_image_robots_evidence(
            provider=provider,
            robots_url=robots_url,
            robots_body="User-agent: *\nAllow: /\n",
            user_agent=AGENT,
            target_url=target_url,
            observed_at=OBSERVED,
        )
    assert captured.value.code == ROBOTS_EVIDENCE_INVALID
