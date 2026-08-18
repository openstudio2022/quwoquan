"""What makes an image body publishable, derived from the variant contract.

The variant policy in ``content-service/contracts/media/media_asset`` already
decides every size the product ever serves; the widest of those profiles is
therefore the widest body a release can usefully hold.  A camera original is
larger than every profile, so publishing it ships bytes no surface will ever
request.

This module owns that one rule so the download side (which legitimately keeps
originals for provenance) and the publish side (which may only hold normalized
bodies) cannot drift into two different definitions of "normalized".
"""
from __future__ import annotations

from pathlib import Path

from core.image_decode import probe_image_bytes
from core.media_asset_url import IMAGE_VARIANT_PROFILES


# The widest profile the product serves; nothing wider has a consumer.
PUBLISHABLE_MAX_WIDTH = max(int(row["width"]) for row in IMAGE_VARIANT_PROFILES.values())

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"})


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_SUFFIXES


def publishable_image_issue(body: bytes, *, label: str) -> str | None:
    """Return why this image body may not be published, or ``None`` if it may.

    Absent probing capability is not a pass: an undecodable body is reported so a
    missing decoder can never silently widen what reaches a release.
    """
    probe = probe_image_bytes(body)
    if not probe.succeeded:
        return f"{label}: image body could not be probed, so it cannot be proven normalized"
    if max(probe.width, probe.height) > PUBLISHABLE_MAX_WIDTH:
        return (
            f"{label}: {probe.width}x{probe.height} exceeds the widest served "
            f"profile ({PUBLISHABLE_MAX_WIDTH}px); publish a normalized derivative"
        )
    return None


def publishable_media_issue(source: Path, *, label: str) -> str | None:
    """Return why this media file may not be published, or ``None`` if it may.

    Non-image media are out of scope here: video normalization is already proven
    by the encode budget its own package applies.
    """
    if not is_image_path(source):
        return None
    return publishable_image_issue(source.read_bytes(), label=label)


__all__ = [
    "PUBLISHABLE_MAX_WIDTH",
    "is_image_path",
    "publishable_image_issue",
    "publishable_media_issue",
]
