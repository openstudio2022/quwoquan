"""Cursor 模型价格与权威用量计费合同。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.schema import assert_valid


PRICING_PATH = CONTROL_PLANE_SHARED_ROOT / "cursor_model_pricing.yaml"
COST_UNKNOWN_ISSUE = "GATE_BLOCK_COST_UNKNOWN"


@dataclass(frozen=True, slots=True)
class CursorModelPrice:
    model_id: str
    input_usd_per_million: float | None
    output_usd_per_million: float | None
    cache_read_usd_per_million: float | None
    cache_write_usd_per_million: float | None


@dataclass(frozen=True, slots=True)
class CursorPricingCatalog:
    revision: str
    models: tuple[CursorModelPrice, ...]

    def price_for(self, model_id: str) -> CursorModelPrice | None:
        normalized = str(model_id or "").strip()
        return next(
            (model for model in self.models if model.model_id == normalized),
            None,
        )


def _nullable_price(value: object) -> float | None:
    if value is None:
        return None
    price = float(value)
    if price < 0:
        raise ValueError("Cursor model price must not be negative")
    return price


def load_cursor_pricing(path: Path = PRICING_PATH) -> CursorPricingCatalog:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cursor model pricing unreadable: {path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("Cursor model pricing must be an object")
    payload = dict(raw)
    assert_valid(
        payload,
        "execution",
        "cursor_model_pricing",
        label=path.as_posix(),
    )
    models = tuple(
        CursorModelPrice(
            model_id=str(item["modelId"]),
            input_usd_per_million=_nullable_price(item["inputUsdPerMillion"]),
            output_usd_per_million=_nullable_price(item["outputUsdPerMillion"]),
            cache_read_usd_per_million=_nullable_price(
                item["cacheReadUsdPerMillion"]
            ),
            cache_write_usd_per_million=_nullable_price(
                item["cacheWriteUsdPerMillion"]
            ),
        )
        for item in payload["models"]
    )
    if len({model.model_id for model in models}) != len(models):
        raise ValueError("Cursor model pricing contains duplicate modelId")
    return CursorPricingCatalog(
        revision=str(payload["revision"]),
        models=models,
    )


def price_cursor_usage(
    *,
    model_id: str,
    usage: Mapping[str, object],
    catalog: CursorPricingCatalog | None = None,
) -> dict[str, object]:
    """优先使用 SDK billed cost；缺失时仅按完整、已知价格计算。"""
    resolved_catalog = catalog or load_cursor_pricing()
    if bool(usage.get("costAvailable")):
        return {
            "costUsd": float(usage.get("costUsd") or 0.0),
            "costSource": "sdk_billed",
            "pricingRevision": resolved_catalog.revision,
            "costIssue": None,
        }
    price = resolved_catalog.price_for(model_id)
    if price is None:
        return {
            "costUsd": None,
            "costSource": "unknown",
            "pricingRevision": resolved_catalog.revision,
            "costIssue": COST_UNKNOWN_ISSUE,
        }
    components = (
        ("inputTokens", price.input_usd_per_million),
        ("outputTokens", price.output_usd_per_million),
        ("cacheReadTokens", price.cache_read_usd_per_million),
        ("cacheWriteTokens", price.cache_write_usd_per_million),
    )
    component_total = sum(int(usage.get(name) or 0) for name, _ in components)
    if component_total != int(usage.get("usedTokens") or 0):
        return {
            "costUsd": None,
            "costSource": "unknown",
            "pricingRevision": resolved_catalog.revision,
            "costIssue": COST_UNKNOWN_ISSUE,
        }
    total = 0.0
    for name, unit_price in components:
        tokens = int(usage.get(name) or 0)
        if tokens and unit_price is None:
            return {
                "costUsd": None,
                "costSource": "unknown",
                "pricingRevision": resolved_catalog.revision,
                "costIssue": COST_UNKNOWN_ISSUE,
            }
        total += tokens * float(unit_price or 0.0) / 1_000_000
    return {
        "costUsd": round(total, 9),
        "costSource": "catalog_calculated",
        "pricingRevision": resolved_catalog.revision,
        "costIssue": None,
    }


__all__ = [
    "COST_UNKNOWN_ISSUE",
    "CursorModelPrice",
    "CursorPricingCatalog",
    "load_cursor_pricing",
    "price_cursor_usage",
]
