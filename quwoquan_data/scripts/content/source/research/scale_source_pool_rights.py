"""Pure media-rights reduction for canonical source-pool projections."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class EmptyMediaRightsError(ValueError):
    """Media rights cannot be derived without physical assets."""


def aggregate_media_rights(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    if not rows:
        raise EmptyMediaRightsError(
            "media rights cannot be inferred from an empty asset set"
        )
    statuses = {str(row.get("rightsStatus") or "") for row in rows}
    if "unknown" in statuses:
        rights_status = "unknown"
    elif "unverified" in statuses:
        rights_status = "unverified"
    else:
        rights_status = "verified"
    decisions = {str(row.get("distributionDecision") or "") for row in rows}
    decision = (
        "research_allowed"
        if "research_allowed" in decisions
        else "commercial_allowed"
    )
    return rights_status, decision


__all__ = ["EmptyMediaRightsError", "aggregate_media_rights"]
