"""What makes a stored media body admissible into an immutable release.

The body an immutable release freezes is what the four declared delivery
profiles transform *from*, so each declared width is an upper bound on delivery
rather than a ceiling on storage: capping the stored body at the widest declared
width is exactly what stops that profile from ever delivering the width it
declares.  The long edge is a second, unrelated axis that instant transformation
never constrains, so refusing a portrait body on it pushes a width that is
already inside every profile even further down.

That leaves one per-asset judgement here: can the stored body be decoded.  A
body that cannot be is a typed failure rather than an in-band verdict, because a
nullable problem string would make "this body is fine" and "nothing could be
measured" indistinguishable at the call site.  Rights and quality admission
happen earlier; byte volume is the single-object storage budget measured on the
whole object closure elsewhere.
"""
from __future__ import annotations

from pathlib import Path

from core.image_decode import ImageDecodeFailure, probe_image_bytes

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"})


class MediaNormalizationError(ValueError):
    """A stored media body could not be proven decodable."""

    def __init__(self, *, label: str, failure: ImageDecodeFailure) -> None:
        self.label = label
        self.failure = failure
        super().__init__(
            f"{label}: image body could not be probed ({failure}), so it cannot "
            "enter an object as a decodable storage baseline"
        )


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_SUFFIXES


def publishable_image_issue(body: bytes, *, label: str) -> None:
    """Admit one stored image body, or raise the typed decode failure.

    The return value stays nullable-shaped so admission call sites read the same
    for image and non-image media, but there is no admissible-with-an-issue
    outcome: either the body decodes and enters the object, or the asset fails.
    """

    probe = probe_image_bytes(body)
    if not probe.succeeded:
        raise MediaNormalizationError(
            label=label,
            failure=probe.failure or ImageDecodeFailure.UNREADABLE,
        )
    return None


def publishable_media_issue(source: Path, *, label: str) -> None:
    """Admit one stored media file.

    Non-image media are out of scope here: video normalization is already proven
    by the encode budget its own package applies.
    """

    if not is_image_path(source):
        return None
    return publishable_image_issue(source.read_bytes(), label=label)


__all__ = [
    "MediaNormalizationError",
    "is_image_path",
    "publishable_image_issue",
    "publishable_media_issue",
]
