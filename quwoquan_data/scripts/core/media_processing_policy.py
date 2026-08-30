"""Typed loader for the repository-owned media processing policy."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.schema import assert_valid


MEDIA_PROCESSING_POLICY_PATH = CONTROL_PLANE_SHARED_ROOT / "media_processing.policy.yaml"
# 载体表必须声明的档位。`default` 是全部图文载体的取值，缺它就没有任何载体能取到
# 预算；两者都由 schema 强制 required，此处只是把消费侧依赖写明。
OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER = "default"


@dataclass(frozen=True, slots=True)
class MediaProcessingPolicy:
    source_asset_max_bytes: int
    page_image_rendition_width: int
    max_publishable_image_pixels: int
    object_storage_budget_bytes_by_carrier: Mapping[str, int]
    max_assessment_image_pixels: int
    assessment_jpeg_quality: int
    ocr_image_pixels: int
    base_draft_image_candidates: int
    image_fetch_target_surplus: int
    image_candidate_surplus: int
    webp_method: int
    homepage_base_draft_max_chars: int


def _required_int(document: dict[str, object], field: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"media processing policy {field} must be an integer")
    return value


def _required_carrier_budget_table(
    document: dict[str, object],
    field: str,
) -> Mapping[str, int]:
    """读逐载体预算表；缺 `default` 档即装配期判否，不替它挑一个数。"""
    raw = document.get(field)
    if not isinstance(raw, dict):
        raise ValueError(f"media processing policy {field} must be an object")
    table: dict[str, int] = {}
    for carrier, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"media processing policy {field}.{carrier} must be an integer"
            )
        table[str(carrier)] = value
    if OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER not in table:
        raise ValueError(
            f"media processing policy {field} must declare "
            f"{OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER!r}: without it no carrier "
            "can resolve its single-object storage budget"
        )
    return MappingProxyType(table)


@lru_cache(maxsize=1)
def media_processing_policy() -> MediaProcessingPolicy:
    try:
        raw = yaml.safe_load(MEDIA_PROCESSING_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f"media processing policy unreadable: {MEDIA_PROCESSING_POLICY_PATH}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("media processing policy must be an object")
    assert_valid(
        raw,
        "content",
        "media_processing_policy",
        label=MEDIA_PROCESSING_POLICY_PATH.as_posix(),
    )
    return MediaProcessingPolicy(
        source_asset_max_bytes=_required_int(raw, "sourceAssetMaxBytes"),
        page_image_rendition_width=_required_int(raw, "pageImageRenditionWidth"),
        max_publishable_image_pixels=_required_int(raw, "maxPublishableImagePixels"),
        object_storage_budget_bytes_by_carrier=_required_carrier_budget_table(
            raw, "objectStorageBudgetBytesByCarrier"
        ),
        max_assessment_image_pixels=_required_int(raw, "maxAssessmentImagePixels"),
        assessment_jpeg_quality=_required_int(raw, "assessmentJpegQuality"),
        ocr_image_pixels=_required_int(raw, "ocrImagePixels"),
        base_draft_image_candidates=_required_int(raw, "baseDraftImageCandidates"),
        image_fetch_target_surplus=_required_int(raw, "imageFetchTargetSurplus"),
        image_candidate_surplus=_required_int(raw, "imageCandidateSurplus"),
        webp_method=_required_int(raw, "webpMethod"),
        homepage_base_draft_max_chars=_required_int(raw, "homepageBaseDraftMaxChars"),
    )


MEDIA_PROCESSING_POLICY = media_processing_policy()


__all__ = [
    "MEDIA_PROCESSING_POLICY",
    "MEDIA_PROCESSING_POLICY_PATH",
    "OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER",
    "MediaProcessingPolicy",
    "media_processing_policy",
]
