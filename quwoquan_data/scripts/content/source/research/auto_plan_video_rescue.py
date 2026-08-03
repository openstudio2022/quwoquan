"""Scale-safe rescue of open-license stills used for video frame sources."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from governance.content_supply_policy import load_content_supply_policy


def rescue_video_frame_pool(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    qid: str,
    wiki_title: str,
    voyage_title: str,
    rejected_image_urls: set[str],
    open_license_image_pool: list[dict[str, Any]],
    report: dict[str, Any],
    discover_image_pools: Callable[..., dict[str, list[dict[str, Any]]]],
    qualified_frame_count: Callable[..., int],
) -> list[dict[str, Any]]:
    """Expand a frame pool only when the frozen video minimum is not met."""

    minimum_frames = load_content_supply_policy(
        vertical
    ).video_delivery.minimum_source_frames
    initial_frames = qualified_frame_count(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
        image_pool=open_license_image_pool,
    )
    if initial_frames >= minimum_frames:
        return open_license_image_pool
    rescue_pools = discover_image_pools(
        entity_id,
        entity_aliases=entity_aliases,
        qid=qid,
        wiki_title=wiki_title,
        voyage_title=voyage_title,
        rejected_image_urls=rejected_image_urls,
        commons_limit=60,
        wikidata_limit=60,
        openverse_limit=80,
        page_limit=32,
    )
    rescue_pool = (
        rescue_pools["openverse"]
        + rescue_pools["commons"]
        + (rescue_pools.get("hint_commons") or [])
        + rescue_pools["wikidata_commons"]
        + rescue_pools["wiki_page_images"]
        + rescue_pools["voyage_page_images"]
    )
    known_urls = {
        str(item.get("url") or "").strip()
        for item in open_license_image_pool
        if str(item.get("url") or "").strip()
    }
    additions = [
        item
        for item in rescue_pool
        if str(item.get("url") or "").strip()
        and str(item.get("url") or "").strip() not in known_urls
    ]
    repaired_pool = [*open_license_image_pool, *additions]
    repaired_frames = qualified_frame_count(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
        image_pool=repaired_pool,
    )
    report.setdefault("rescueEvents", []).append(
        {
            "entityId": entity_id,
            "lane": "video",
            "reason": "qualified_video_frames_below_minimum",
            "qualifiedFramesBefore": initial_frames,
            "qualifiedFramesAfter": repaired_frames,
            "minimumFrames": minimum_frames,
            "addedCandidates": len(additions),
        }
    )
    return repaired_pool
