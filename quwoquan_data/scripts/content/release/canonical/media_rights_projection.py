"""媒体权利投影：水印、衍生修改与音轨状态的资产行转录与对象级汇总。

final_surface_projection 只搬运 ingest 从 AI 申报与实际处理转录下来的事实，不做业务假定。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def asset_rights_fields(source: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """单条资产行的水印三字段、衍生修改与（视频）音轨状态。"""
    fields: dict[str, Any] = {
        "watermarkStatus": str(source.get("watermarkStatus") or "unknown"),
        "watermarkKind": str(source.get("watermarkKind") or "unknown"),
        "watermarkNote": str(source.get("watermarkNote") or ""),
        "derivedModifications": sorted(
            {str(value) for value in source.get("derivedModifications") or [] if str(value)}
        ),
    }
    if kind == "video":
        attribution = source.get("sourceAttribution")
        declared_audio = (
            str(attribution.get("audioRightsStatus") or "").strip()
            if isinstance(attribution, Mapping)
            else ""
        )
        fields["audioRightsStatus"] = declared_audio or "unverified"
    return fields


def object_rights_rollup(assets: Sequence[Mapping[str, Any]], carrier: str) -> dict[str, Any]:
    """对象级汇总：水印取「最重」判定（present > unknown > absent），音轨缺席时保守记 unverified。"""
    statuses = [str(raw.get("watermarkStatus") or "unknown") for raw in assets]
    if "present" in statuses:
        watermark_status = "present"
        watermark_kind = next(
            (
                str(raw.get("watermarkKind") or "other")
                for raw in assets
                if str(raw.get("watermarkStatus") or "") == "present"
            ),
            "other",
        )
    elif "unknown" in statuses:
        watermark_status, watermark_kind = "unknown", "unknown"
    else:
        watermark_status, watermark_kind = "absent", "none"
    if carrier == "video":
        audio = next(
            (
                str(raw.get("audioRightsStatus"))
                for raw in assets
                if str(raw.get("kind") or "") == "video" and raw.get("audioRightsStatus")
            ),
            "unverified",
        )
    else:
        audio = "no_audio"
    return {
        "watermarkStatus": watermark_status,
        "watermarkKind": watermark_kind,
        "audioRightsStatus": audio,
        "derivedModifications": sorted(
            {str(value) for raw in assets for value in raw.get("derivedModifications") or [] if str(value)}
        ),
    }
