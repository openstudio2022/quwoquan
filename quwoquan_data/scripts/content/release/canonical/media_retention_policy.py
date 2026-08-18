"""Tiered retention for media the content library owns.

Discovery and delivery need different things from the same acquired media, and
keeping every original forever is what makes the library grow without bound:

``metadata``
    The facts a surface needs to describe media it does not display: digest,
    dimensions, licence, provenance. Never reclaimed, because losing it makes an
    already-published object undescribable.

``thumbnail``
    The small derivative discovery surfaces actually render. Retained for as long
    as the object is discoverable, because it is cheap and is on the read path.

``original``
    The acquired full-resolution body. Reclaimable, but only once the object it
    belongs to is ingested — a release holds it, so the object no longer depends
    on the acquisition workspace — and only after a window during which a
    re-cut can still re-derive from the original rather than re-acquire it.

Reclaiming is decided per library entry, never per reference: an entry is one
body shared by every reference to it, so it survives while any tier or any
un-ingested object still needs it. The policy answers only "may this be
reclaimed"; the collector remains the single component that removes anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

MEDIA_TIER_METADATA = "metadata"
MEDIA_TIER_THUMBNAIL = "thumbnail"
MEDIA_TIER_ORIGINAL = "original"

MEDIA_TIERS = (MEDIA_TIER_METADATA, MEDIA_TIER_THUMBNAIL, MEDIA_TIER_ORIGINAL)

# Variant derivatives are written beside their source under this directory by the
# source unit writer; they are the discovery-tier bodies.
_VARIANT_DIR = ".variants"
_METADATA_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".vtt", ".md"})

# An original stays re-derivable for this long after ingestion. Shorter than the
# acquisition provider's own retention would make a re-cut re-acquire; longer
# just holds bytes that a release already binds by digest.
DEFAULT_ORIGINAL_RETENTION_DAYS = 30


@dataclass(frozen=True, slots=True)
class MediaRetentionPolicy:
    original_retention_days: int = DEFAULT_ORIGINAL_RETENTION_DAYS

    def __post_init__(self) -> None:
        if self.original_retention_days < 1:
            raise ValueError(
                "original retention window must be at least one day: "
                f"{self.original_retention_days}"
            )

    @property
    def original_retention(self) -> timedelta:
        return timedelta(days=self.original_retention_days)


@dataclass(frozen=True, slots=True)
class MediaRetentionDecision:
    """Why one library entry may or may not be reclaimed."""

    digest: str
    tier: str
    reclaimable: bool
    reason: str


def classify_media_tier(relative_path: str) -> str:
    """Classify one media reference by the role it plays, not by its size."""

    text = str(relative_path or "").strip()
    if not text:
        raise ValueError("media reference is required to classify a retention tier")
    path = Path(text)
    if path.suffix.lower() in _METADATA_SUFFIXES:
        return MEDIA_TIER_METADATA
    if _VARIANT_DIR in path.parts:
        return MEDIA_TIER_THUMBNAIL
    return MEDIA_TIER_ORIGINAL


def retention_decision(
    *,
    digest: str,
    references: Iterable[str],
    ingested_at: datetime | None,
    now: datetime,
    policy: MediaRetentionPolicy,
) -> MediaRetentionDecision:
    """Decide retention for the single body addressed by ``digest``.

    ``references`` are every path that currently points at the entry and
    ``ingested_at`` is when a release first bound it, or ``None`` while the entry
    is still only held by an acquisition workspace.
    """

    tiers = {classify_media_tier(reference) for reference in references}
    if not tiers:
        return MediaRetentionDecision(
            digest=digest,
            tier=MEDIA_TIER_ORIGINAL,
            reclaimable=True,
            reason="no reference points at this entry",
        )
    # The strongest claim among the references wins: one discovery-tier reference
    # is enough to keep a body that some other reference treats as an original.
    for tier in (MEDIA_TIER_METADATA, MEDIA_TIER_THUMBNAIL):
        if tier in tiers:
            return MediaRetentionDecision(
                digest=digest,
                tier=tier,
                reclaimable=False,
                reason=f"{tier} is on the discovery read path",
            )
    if ingested_at is None:
        return MediaRetentionDecision(
            digest=digest,
            tier=MEDIA_TIER_ORIGINAL,
            reclaimable=False,
            reason="original is not ingested yet",
        )
    elapsed = now - ingested_at
    if elapsed < policy.original_retention:
        remaining = policy.original_retention - elapsed
        return MediaRetentionDecision(
            digest=digest,
            tier=MEDIA_TIER_ORIGINAL,
            reclaimable=False,
            reason=f"original is re-derivable for another {remaining.days}d",
        )
    return MediaRetentionDecision(
        digest=digest,
        tier=MEDIA_TIER_ORIGINAL,
        reclaimable=True,
        reason=(
            f"original was ingested {elapsed.days}d ago and is bound by digest in a release"
        ),
    )


def reclaimable_library_entries(
    *,
    references_by_digest: Mapping[str, Iterable[str]],
    ingested_at_by_digest: Mapping[str, datetime],
    now: datetime,
    policy: MediaRetentionPolicy | None = None,
) -> tuple[MediaRetentionDecision, ...]:
    """Return the reclaimable subset of the library, in stable digest order.

    ``references_by_digest`` is ``ReferenceGraph.library_holdings``: retention
    reads the collector's own reachability, so a body that any governed reference
    still reaches can never be selected here.
    """

    resolved = policy or MediaRetentionPolicy()
    decisions = [
        retention_decision(
            digest=digest,
            references=references_by_digest[digest],
            ingested_at=ingested_at_by_digest.get(digest),
            now=now,
            policy=resolved,
        )
        for digest in sorted(references_by_digest)
    ]
    return tuple(decision for decision in decisions if decision.reclaimable)


__all__ = [
    "DEFAULT_ORIGINAL_RETENTION_DAYS",
    "MEDIA_TIERS",
    "MEDIA_TIER_METADATA",
    "MEDIA_TIER_ORIGINAL",
    "MEDIA_TIER_THUMBNAIL",
    "MediaRetentionDecision",
    "MediaRetentionPolicy",
    "classify_media_tier",
    "reclaimable_library_entries",
    "retention_decision",
]
