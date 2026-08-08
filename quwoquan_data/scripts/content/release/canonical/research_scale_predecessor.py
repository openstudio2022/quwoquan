"""Validate the immutable predecessor of a cumulative research milestone."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import _read_json
from core.paths import research_scale_promotions_root
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy


class ResearchScalePredecessorError(RuntimeError):
    pass


_PREDECESSOR_SCALE = {"M1000": "M100", "M10000": "M1000"}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_predecessor_promotion(
    path: Path | None,
    *,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    output_root: Path,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    expected_scale = _PREDECESSOR_SCALE.get(target_scale)
    if expected_scale is None:
        if path is not None:
            raise ResearchScalePredecessorError(
                "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: M100 forbids a predecessor"
            )
        return None, {carrier: 0 for carrier in ("homepage", "article", "image", "video")}
    if path is None:
        raise ResearchScalePredecessorError(
            f"DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: {target_scale} requires {expected_scale} promotion"
        )
    resolved = path.expanduser().resolve()
    root = output_root.expanduser().resolve()
    predecessor = _read_json(resolved)
    try:
        assert_valid(
            predecessor,
            "release",
            "research_scale_promotion",
            label=f"research {expected_scale} predecessor",
        )
    except (TypeError, ValueError) as exc:
        raise ResearchScalePredecessorError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor schema is invalid"
        ) from exc
    expected_path = (
        research_scale_promotions_root(output_root=root)
        / str(predecessor.get("releaseId") or "")
        / str(predecessor.get("promotionId") or "")
        / f"research-{expected_scale.lower()}.json"
    ).resolve()
    if resolved != expected_path:
        raise ResearchScalePredecessorError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor is outside the canonical promotion path"
        )
    receipt_ref = resolved.relative_to(root).as_posix()
    if (
        predecessor.get("targetScale") != expected_scale
        or predecessor.get("nextScaleEligible") != target_scale
        or predecessor.get("sourceRevision") != source_revision
        or predecessor.get("sourceDigest") != source_digest
        or predecessor.get("entityCatalogDigest") != entity_catalog_digest
    ):
        raise ResearchScalePredecessorError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor scale/source identity drift"
        )
    rows = predecessor.get("carrierCounts")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ResearchScalePredecessorError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor carrier counts are incomplete"
        )
    policy = load_content_distribution_policy()
    carried: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ResearchScalePredecessorError(
                "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor carrier row is invalid"
            )
        carrier = str(row.get("carrier") or "")
        values = {
            key: row.get(key)
            for key in (
                "targetCount",
                "predecessorCarriedCount",
                "newFinalizedCount",
                "totalUniqueFinalizedCount",
                "shortfallCount",
                "researchAcceptedCount",
            )
        }
        count = values["totalUniqueFinalizedCount"]
        if (
            carrier not in {"homepage", "article", "image", "video"}
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or carrier in carried
        ):
            raise ResearchScalePredecessorError(
                "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor cumulative count is invalid"
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in values.values()
        ):
            raise ResearchScalePredecessorError(
                "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor count arithmetic is invalid"
            )
        target = policy.scale_target(expected_scale, carrier)
        if (
            values["targetCount"] != target
            or values["shortfallCount"] != 0
            or values["predecessorCarriedCount"] + values["newFinalizedCount"]
            != count
            or values["researchAcceptedCount"] != count
            or count < target
        ):
            raise ResearchScalePredecessorError(
                "DATA.SCALE.ATTAINMENT_SHORTFALL: predecessor target/count arithmetic is not attained"
            )
        carried[carrier] = count
    if set(carried) != {"homepage", "article", "image", "video"}:
        raise ResearchScalePredecessorError(
            "DATA.SCALE.PREDECESSOR_IDENTITY_DRIFT: predecessor carriers are incomplete"
        )
    return (
        {
            "promotionId": str(predecessor["promotionId"]),
            "releaseId": str(predecessor["releaseId"]),
            "manifestDigest": str(predecessor["manifestDigest"]),
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
            "targetScale": expected_scale,
            "receiptRef": receipt_ref,
            "receiptDigest": _file_sha256(resolved),
        },
        carried,
    )


__all__ = ["ResearchScalePredecessorError", "load_predecessor_promotion"]
