"""Tiered media retention decides per library body, never per reference.

Locks the two rules that keep the library bounded without breaking discovery:
metadata and thumbnails stay because they are on the read path, and an
acquisition original becomes reclaimable only after a release holds it and the
re-derivation window has passed.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from content.release.canonical.media_retention_policy import (  # noqa: E402
    MEDIA_TIER_METADATA,
    MEDIA_TIER_ORIGINAL,
    MEDIA_TIER_THUMBNAIL,
    MediaRetentionPolicy,
    classify_media_tier,
    reclaimable_library_entries,
    retention_decision,
)

NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)
POLICY = MediaRetentionPolicy(original_retention_days=30)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("assets/001_cover.jpg", MEDIA_TIER_ORIGINAL),
        ("assets/.variants/001_cover_w480.webp", MEDIA_TIER_THUMBNAIL),
        ("assets/manifest.json", MEDIA_TIER_METADATA),
        ("assets/subtitles.vtt", MEDIA_TIER_METADATA),
    ],
)
def test_tier_follows_the_role_the_reference_plays(reference: str, expected: str) -> None:
    assert classify_media_tier(reference) == expected


def test_an_empty_reference_cannot_be_classified() -> None:
    with pytest.raises(ValueError, match="retention tier"):
        classify_media_tier("  ")


def test_a_thumbnail_reference_keeps_a_body_another_reference_calls_original() -> None:
    decision = retention_decision(
        digest="a" * 64,
        references=("assets/001_cover.jpg", "assets/.variants/001_cover_w480.webp"),
        ingested_at=NOW - timedelta(days=365),
        now=NOW,
        policy=POLICY,
    )
    assert decision.reclaimable is False
    assert decision.tier == MEDIA_TIER_THUMBNAIL


def test_an_original_is_never_reclaimed_before_a_release_holds_it() -> None:
    decision = retention_decision(
        digest="b" * 64,
        references=("assets/001_cover.jpg",),
        ingested_at=None,
        now=NOW,
        policy=POLICY,
    )
    assert decision.reclaimable is False
    assert "not ingested" in decision.reason


def test_an_ingested_original_is_held_through_the_rederivation_window() -> None:
    inside = retention_decision(
        digest="c" * 64,
        references=("assets/001_cover.jpg",),
        ingested_at=NOW - timedelta(days=29),
        now=NOW,
        policy=POLICY,
    )
    assert inside.reclaimable is False

    outside = retention_decision(
        digest="c" * 64,
        references=("assets/001_cover.jpg",),
        ingested_at=NOW - timedelta(days=31),
        now=NOW,
        policy=POLICY,
    )
    assert outside.reclaimable is True
    assert outside.tier == MEDIA_TIER_ORIGINAL


def test_reclaim_selects_only_expired_ingested_originals() -> None:
    expired, fresh, thumbnail = "d" * 64, "e" * 64, "f" * 64
    reclaimable = reclaimable_library_entries(
        references_by_digest={
            expired: ("assets/001_cover.jpg",),
            fresh: ("assets/002_cover.jpg",),
            thumbnail: ("assets/.variants/003_w480.webp",),
        },
        ingested_at_by_digest={
            expired: NOW - timedelta(days=90),
            fresh: NOW - timedelta(days=1),
            thumbnail: NOW - timedelta(days=90),
        },
        now=NOW,
        policy=POLICY,
    )
    assert [row.digest for row in reclaimable] == [expired]


def test_a_retention_window_shorter_than_a_day_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one day"):
        MediaRetentionPolicy(original_retention_days=0)
