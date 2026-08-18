"""Whether an acquisition body is still staged, or was reclaimed after adoption.

An acquisition receipt declares the bodies it fetched. Once an object adopts a
body, that object carries the rights evidence in its own
``rights_snapshots/<assetId>.json`` and the content library owns the bytes, so
the acquisition copy becomes a staging remnant the collector may reclaim. The
receipt therefore outlives its bodies, and a reader has to separate two
situations that both look like "the file is not there":

reclaimed
    Every body the unit declared is gone. The unit was collected as a whole and
    the receipt is now its tombstone. A normal terminal state.

corrupt
    Some bodies are gone and some remain. Nothing in the pipeline produces that
    shape, so it is damage and stays fail-closed.

This is why a reclaimed body is never represented as ``None``. ``None`` already
means "never acquired", which is a failure for an accepted asset; collapsing a
completed reclamation into that same value would make a finished collection
indistinguishable from a broken receipt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReclaimedBody:
    """One declared body whose bytes were reclaimed after an object adopted them.

    Carries its ``assetRef`` so a partially reclaimed unit can name what is
    missing instead of only reporting a count.
    """

    asset_ref: str


# A declared body is either still staged at a path, or reclaimed. Absence of a
# declaration at all is expressed by the caller as ``None``, which is a distinct
# and stricter state that this union deliberately does not cover.
AcquiredBody = Path | ReclaimedBody


def assert_unit_reclamation_is_total(
    bodies: Sequence[AcquiredBody],
    *,
    label: str,
) -> None:
    """Refuse a unit whose bodies are only partly reclaimed.

    Reclamation is driven per acquisition unit, so a mixed unit cannot be the
    result of collection and is treated as damage.
    """

    reclaimed = sorted(
        body.asset_ref for body in bodies if isinstance(body, ReclaimedBody)
    )
    if not reclaimed:
        return
    present = sorted(
        body.name for body in bodies if isinstance(body, Path)
    )
    if present:
        raise ValueError(
            f"{label} is partially reclaimed, which is corruption rather than a "
            f"completed collection: reclaimed={','.join(reclaimed)} "
            f"present={','.join(present)}"
        )


__all__ = [
    "AcquiredBody",
    "ReclaimedBody",
    "assert_unit_reclamation_is_total",
]
