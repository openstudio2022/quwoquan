"""Build the formal video lane from individually rights-cleared source frames."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode, DataRecoveryAction
from governance.coverage.cold_start_supply import load_cold_start_supply_policy
from content.source.research.plan_state import (
    _record_unavailable,
    _safe_collection_id,
    _source_unavailable_for_entity,
    _write_lane,
)
from content.source.research.source_quality import _collection_gate


def _minimum_frame_count() -> int:
    return load_cold_start_supply_policy().video_delivery.minimum_segment_count


def _video_frame_candidate(
    raw: dict[str, Any],
    *,
    entity_id: str,
    ordinal: int,
    entity_aliases: list[str],
    vertical: str,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    item = dict(raw)
    collection_id = _safe_collection_id(
        "video_frame",
        entity_id,
        str(
            item.get("sourceCollectionId")
            or item.get("authorizationProof")
            or item.get("sourceUrl")
            or item.get("url")
            or ""
        ),
    )
    creator = str(
        item.get("creator")
        or item.get("credit")
        or "Wikimedia Commons contributor"
    ).strip()
    collection_page = str(
        item.get("collectionPageUrl")
        or item.get("sourceUrl")
        or item.get("authorizationProof")
        or item.get("url")
        or ""
    ).strip()
    item.update(
        {
            "sourceCollectionId": collection_id,
            "creator": creator,
            "credit": item.get("credit") or creator,
            "collectionPageUrl": collection_page,
            "authorizationProof": item.get("authorizationProof") or collection_page,
            "usageScope": item.get("usageScope") or "app_publish",
            "modelReleaseStatus": item.get("modelReleaseStatus") or "not_required",
            "researchLane": "video",
            "sourceId": f"video_frame_{ordinal}",
        }
    )
    collection = {
        "sourceCollectionId": collection_id,
        "creator": creator,
        "credit": item["credit"],
        "collectionPageUrl": collection_page,
        "platform": item.get("platform") or "Wikimedia Commons",
        "license": item.get("license") or "",
        "termsUrl": item.get("termsUrl") or "",
        "licenseSnapshot": item.get("licenseSnapshot") or "",
        "authorizationProof": item["authorizationProof"],
        "usageScope": item["usageScope"],
        "modelReleaseStatus": item["modelReleaseStatus"],
        "images": [item],
    }
    verdict = _collection_gate(
        collection,
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
    )
    issues = tuple(str(issue) for issue in verdict.get("issues") or ())
    return (item if verdict.get("passed") else None), issues


def write_video_lane(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    plan_dir: Path,
    force: bool,
    report: dict[str, Any],
    updated: list[dict[str, Any]],
    open_license_image_pool: list[dict[str, Any]],
) -> None:
    minimum_frames = _minimum_frame_count()
    frames: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for ordinal, raw in enumerate(open_license_image_pool, start=1):
        url = str(raw.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        frame, issues = _video_frame_candidate(
            raw,
            entity_id=entity_id,
            ordinal=ordinal,
            entity_aliases=entity_aliases,
            vertical=vertical,
        )
        report.setdefault("videoFrames", []).append(
            {
                "entityId": entity_id,
                "url": url,
                "passed": frame is not None,
                "issues": list(issues),
            }
        )
        if frame is not None:
            frames.append(frame)
        if len(frames) >= minimum_frames:
            break
    if len(frames) < minimum_frames:
        _record_unavailable(
            report,
            entity_id=entity_id,
            lane="video",
            reason=f"rights-cleared video frames={len(frames)} need>={minimum_frames}",
            code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            recovery=DataRecoveryAction.STOP,
        )
    if _write_lane(
        plan_dir / "video_source_plan.json",
        "video",
        {
            "assets": frames,
            "sourceUnavailable": _source_unavailable_for_entity(
                report,
                entity_id=entity_id,
                lane="video",
            ),
        },
        force=force,
    ):
        updated.append(
            {
                "entityId": entity_id,
                "lane": "video",
                "assets": len(frames),
            }
        )


__all__ = ["write_video_lane"]
