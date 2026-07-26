"""FilterCatalogRelease 的强类型 canonical payload 与摘要合同。"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
import hashlib
import math
import re

from content.filter_catalog.codec import canonical_json_bytes


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class CatalogContractError(ValueError):
    """目录产物不满足 metadata 约束。"""


@dataclass(frozen=True)
class FilterAdjustmentValues:
    """与 metadata FilterAdjustmentValues 一一对应的 15 项调整值。"""

    lightSense: Decimal
    brightness: Decimal
    exposure: Decimal
    contrast: Decimal
    saturation: Decimal
    vibrance: Decimal
    texture: Decimal
    sharpen: Decimal
    structure: Decimal
    highlight: Decimal
    shadow: Decimal
    temperature: Decimal
    tint: Decimal
    grain: Decimal
    fade: Decimal

    @classmethod
    def from_payload(
        cls,
        value: object,
        *,
        label: str,
    ) -> "FilterAdjustmentValues":
        payload = _mapping(value, label)
        expected = set(ADJUSTMENT_FIELD_NAMES)
        unknown = sorted(set(payload) - expected)
        missing = sorted(expected - set(payload))
        if unknown:
            raise CatalogContractError(f"{label} 含未知调整字段：{unknown}")
        if missing:
            raise CatalogContractError(f"{label} 缺少调整字段：{missing}")
        values = {
            name: _decimal(payload[name], f"{label}.{name}")
            for name in ADJUSTMENT_FIELD_NAMES
        }
        return cls(**values)

    def to_payload(self) -> dict[str, Decimal]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }

    @property
    def is_identity(self) -> bool:
        return all(value == 0 for value in self.to_payload().values())


ADJUSTMENT_FIELD_NAMES = tuple(
    field.name for field in fields(FilterAdjustmentValues)
)


def canonical_digest_for_payload(
    *,
    categories: Sequence[Mapping[str, object]],
    presets: Sequence[Mapping[str, object]],
    recommended_fallback_preset_ids: Sequence[str],
) -> str:
    projection = {
        "categories": sorted(
            categories,
            key=lambda item: (
                _integer(item.get("sort"), "categories[].sort"),
                _string(item.get("categoryId"), "categories[].categoryId"),
            ),
        ),
        "presets": sorted(
            presets,
            key=lambda item: (
                _string(item.get("categoryId"), "presets[].categoryId"),
                _integer(item.get("sort"), "presets[].sort"),
                _string(item.get("presetId"), "presets[].presetId"),
            ),
        ),
        "recommendedFallbackPresetIds": list(
            recommended_fallback_preset_ids
        ),
    }
    return hashlib.sha256(canonical_json_bytes(projection)).hexdigest()


def normalize_release(
    value: object,
    *,
    verify_digest: bool = True,
) -> dict[str, object]:
    payload = _mapping(value, "FilterCatalogRelease")
    _require_exact_keys(
        payload,
        {
            "releaseId",
            "sourceOwner",
            "canonicalDigest",
            "categories",
            "presets",
            "recommendedFallbackPresetIds",
        },
        "FilterCatalogRelease",
    )
    release_id = _string(payload["releaseId"], "releaseId")
    if not _RELEASE_ID_RE.fullmatch(release_id):
        raise CatalogContractError(
            "releaseId 只允许小写字母、数字、点、下划线和连字符"
        )
    source_owner = _string(payload["sourceOwner"], "sourceOwner")
    digest = _string(payload["canonicalDigest"], "canonicalDigest")
    if not _DIGEST_RE.fullmatch(digest):
        raise CatalogContractError("canonicalDigest 必须为 64 位小写 SHA-256")

    raw_categories = _list(payload["categories"], "categories")
    if not 1 <= len(raw_categories) <= 32:
        raise CatalogContractError("categories 数量必须在 1..32")
    categories = [
        _normalize_category(item, index=index)
        for index, item in enumerate(raw_categories)
    ]
    category_ids = [str(item["categoryId"]) for item in categories]
    _require_unique(category_ids, "categoryId")
    _require_unique(
        [int(item["sort"]) for item in categories],
        "category sort",
    )
    categories = sorted(
        categories,
        key=lambda item: (int(item["sort"]), str(item["categoryId"])),
    )
    if category_ids != [str(item["categoryId"]) for item in categories]:
        raise CatalogContractError("categories 必须按 sort、categoryId 排序")

    raw_presets = _list(payload["presets"], "presets")
    if not 1 <= len(raw_presets) <= 256:
        raise CatalogContractError("presets 数量必须在 1..256")
    presets = [
        _normalize_preset(item, index=index)
        for index, item in enumerate(raw_presets)
    ]
    preset_ids = [str(item["presetId"]) for item in presets]
    _require_unique(preset_ids, "presetId")
    _require_unique(
        [
            (str(item["categoryId"]), int(item["sort"]))
            for item in presets
        ],
        "同分类 preset sort",
    )
    category_by_id = {
        str(item["categoryId"]): item for item in categories
    }
    for preset in presets:
        category_id = str(preset["categoryId"])
        category = category_by_id.get(category_id)
        if category is None:
            raise CatalogContractError(
                f"preset {preset['presetId']} 引用未知 categoryId={category_id}"
            )
        if bool(preset["enabled"]) and not bool(category["enabled"]):
            raise CatalogContractError(
                f"enabled preset {preset['presetId']} 引用 disabled category"
            )
    presets = sorted(
        presets,
        key=lambda item: (
            str(item["categoryId"]),
            int(item["sort"]),
            str(item["presetId"]),
        ),
    )
    if preset_ids != [str(item["presetId"]) for item in presets]:
        raise CatalogContractError(
            "presets 必须按 categoryId、sort、presetId 排序"
        )

    original = next(
        (
            preset
            for preset in presets
            if preset["presetId"] == "original"
        ),
        None,
    )
    if original is None:
        raise CatalogContractError("必须存在 presetId=original")
    if (
        not bool(original["enabled"])
        or _decimal(original["defaultStrength"], "original.defaultStrength")
        != 0
        or not FilterAdjustmentValues.from_payload(
            original["adjustments"],
            label="original.adjustments",
        ).is_identity
    ):
        raise CatalogContractError(
            "original 必须 enabled、defaultStrength=0 且 15 项 adjustments 全为 0"
        )

    raw_fallbacks = _list(
        payload["recommendedFallbackPresetIds"],
        "recommendedFallbackPresetIds",
    )
    fallbacks = [
        _string(item, f"recommendedFallbackPresetIds[{index}]")
        for index, item in enumerate(raw_fallbacks)
    ]
    _require_unique(fallbacks, "recommendedFallbackPresetIds")
    preset_by_id = {
        str(item["presetId"]): item for item in presets
    }
    for preset_id in fallbacks:
        preset = preset_by_id.get(preset_id)
        if preset is None or not bool(preset["enabled"]):
            raise CatalogContractError(
                f"recommended fallback 必须引用 enabled preset：{preset_id}"
            )

    normalized: dict[str, object] = {
        "releaseId": release_id,
        "sourceOwner": source_owner,
        "canonicalDigest": digest,
        "categories": categories,
        "presets": presets,
        "recommendedFallbackPresetIds": fallbacks,
    }
    computed = canonical_digest_for_payload(
        categories=categories,
        presets=presets,
        recommended_fallback_preset_ids=fallbacks,
    )
    if verify_digest and digest != computed:
        raise CatalogContractError(
            f"canonicalDigest 不匹配：expected={computed} actual={digest}"
        )
    return normalized


def _normalize_category(value: object, *, index: int) -> dict[str, object]:
    label = f"categories[{index}]"
    payload = _mapping(value, label)
    _require_exact_keys(
        payload,
        {
            "categoryId",
            "displayNameZhHans",
            "displayNameEn",
            "sort",
            "enabled",
        },
        label,
    )
    return {
        "categoryId": _string(payload["categoryId"], f"{label}.categoryId"),
        "displayNameZhHans": _string(
            payload["displayNameZhHans"],
            f"{label}.displayNameZhHans",
        ),
        "displayNameEn": _optional_string(
            payload["displayNameEn"],
            f"{label}.displayNameEn",
        ),
        "sort": _integer(payload["sort"], f"{label}.sort"),
        "enabled": _boolean(payload["enabled"], f"{label}.enabled"),
    }


def _normalize_preset(value: object, *, index: int) -> dict[str, object]:
    label = f"presets[{index}]"
    payload = _mapping(value, label)
    _require_exact_keys(
        payload,
        {
            "presetId",
            "categoryId",
            "displayNameZhHans",
            "displayNameEn",
            "sort",
            "enabled",
            "defaultStrength",
            "adjustments",
        },
        label,
    )
    default_strength = _decimal(
        payload["defaultStrength"],
        f"{label}.defaultStrength",
    )
    if not 0 <= default_strength <= 100:
        raise CatalogContractError(
            f"{label}.defaultStrength 必须在 0..100"
        )
    adjustments = FilterAdjustmentValues.from_payload(
        payload["adjustments"],
        label=f"{label}.adjustments",
    )
    for name, adjustment in adjustments.to_payload().items():
        if not -100 <= adjustment <= 100:
            raise CatalogContractError(
                f"{label}.adjustments.{name} 必须在 -100..100"
            )
    return {
        "presetId": _string(payload["presetId"], f"{label}.presetId"),
        "categoryId": _string(
            payload["categoryId"],
            f"{label}.categoryId",
        ),
        "displayNameZhHans": _string(
            payload["displayNameZhHans"],
            f"{label}.displayNameZhHans",
        ),
        "displayNameEn": _optional_string(
            payload["displayNameEn"],
            f"{label}.displayNameEn",
        ),
        "sort": _integer(payload["sort"], f"{label}.sort"),
        "enabled": _boolean(payload["enabled"], f"{label}.enabled"),
        "defaultStrength": default_strength,
        "adjustments": adjustments.to_payload(),
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise CatalogContractError(f"{label} 必须为 string-keyed object")
    return value


def _list(value: object, label: str) -> list[object]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise CatalogContractError(f"{label} 必须为 array")
    return list(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CatalogContractError(f"{label} 必须为非空、无首尾空白 string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CatalogContractError(f"{label} 必须为 bool")
    return value


def _integer(value: object, label: str) -> int:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise CatalogContractError(f"{label} 必须为整数")
    return int(number)


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float, Decimal),
    ):
        raise CatalogContractError(f"{label} 必须为有限 JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogContractError(f"{label} 必须为有限 JSON number")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise CatalogContractError(f"{label} 不是合法十进制数") from exc
    if not number.is_finite():
        raise CatalogContractError(f"{label} 必须为有限 JSON number")
    return number


def _require_exact_keys(
    payload: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        raise CatalogContractError(
            f"{label} 字段不合法：missing={missing} unknown={unknown}"
        )


def _require_unique(values: Sequence[object], label: str) -> None:
    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise CatalogContractError(f"{label} 必须唯一：{duplicates}")
