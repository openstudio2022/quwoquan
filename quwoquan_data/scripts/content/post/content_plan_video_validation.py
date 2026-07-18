"""Validate formal video items inside an immutable content plan."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.image_safety import assess_image_publish_prefilter
from core.io import read_json
from governance.coverage.cold_start_supply import load_cold_start_supply_policy


Claim = Callable[[str, str], None]


def validate_video_plan_item(
    *,
    root: Path,
    item: Mapping[str, Any],
    ref: str,
    claim_asset: Claim,
    claim_asset_sha: Claim,
) -> list[str]:
    issues: list[str] = []
    if str(item.get("researchLane") or "") != "video":
        issues.append(f"item[{ref}]: video work must use researchLane=video")
    asset_refs = item.get("assetRefs")
    source_frames = item.get("sourceFrames")
    minimum_frames = (
        load_cold_start_supply_policy().video_delivery.minimum_segment_count
    )
    if not isinstance(asset_refs, list) or len(asset_refs) < minimum_frames:
        issues.append(
            f"item[{ref}]: video assetRefs must contain at least "
            f"{minimum_frames} source frames"
        )
        return issues
    if len({str(value) for value in asset_refs}) != len(asset_refs):
        issues.append(f"item[{ref}]: video assetRefs contains duplicates")
    if not isinstance(source_frames, list) or len(source_frames) != len(asset_refs):
        issues.append(
            f"item[{ref}]: video sourceFrames must align one-to-one with assetRefs"
        )
        return issues
    frame_by_asset = {
        str(frame.get("assetRef") or ""): frame
        for frame in source_frames
        if isinstance(frame, Mapping)
    }
    if set(frame_by_asset) != {str(value) for value in asset_refs}:
        issues.append(f"item[{ref}]: video sourceFrames asset set mismatch")
        return issues
    for raw_asset_ref in asset_refs:
        asset_ref = str(raw_asset_ref)
        frame = frame_by_asset[asset_ref]
        required_fields = (
            "sourceRef",
            "rightsRef",
            "sourceUrl",
            "creator",
            "license",
            "sha256",
            "sourceCollectionId",
        )
        missing = [field for field in required_fields if not str(frame.get(field) or "").strip()]
        if missing:
            issues.append(f"item[{ref}]: video frame {asset_ref} missing {missing}")
            continue
        asset_path = root / asset_ref
        if not asset_path.is_file():
            issues.append(f"item[{ref}]: video frame not found: {asset_ref}")
            continue
        source_meta_path = asset_path.parent.parent / "meta.json"
        try:
            source_meta = read_json(source_meta_path)
        except (OSError, TypeError, ValueError):
            source_meta = {}
        if str(source_meta.get("researchLane") or "") != "video":
            issues.append(
                f"item[{ref}]: video frame must come from researchLane=video: {asset_ref}"
            )
        index_path = asset_path.parent / "index.json"
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, TypeError, ValueError):
            rows = []
        row = next(
            (
                candidate
                for candidate in rows
                if isinstance(candidate, Mapping)
                and str(candidate.get("fileName") or "") == asset_path.name
            ),
            None,
        )
        if row is None:
            issues.append(f"item[{ref}]: video frame absent from source index: {asset_ref}")
            continue
        for field in ("sourceUrl", "creator", "license", "sha256", "sourceCollectionId"):
            row_value = row.get(field)
            if field == "creator" and not row_value:
                row_value = row.get("credit")
            if str(frame.get(field) or "") != str(row_value or ""):
                issues.append(f"item[{ref}]: video frame {asset_ref} {field} mismatch")
        expected_rights_ref = (
            f"{index_path.resolve().relative_to(root.resolve()).as_posix()}#"
            f"{row.get('sourceAssetId') or ''}"
        )
        if str(frame.get("rightsRef") or "") != expected_rights_ref:
            issues.append(f"item[{ref}]: video frame {asset_ref} rightsRef mismatch")
        verdict = assess_image_publish_prefilter(asset_path)
        if verdict.blocks_image_publish:
            issues.append(f"item[{ref}]: video frame blocked by image safety: {asset_ref}")
        claim_asset(ref, asset_ref)
        claim_asset_sha(ref, str(row.get("sha256") or ""))
    return issues


__all__ = ["validate_video_plan_item"]
