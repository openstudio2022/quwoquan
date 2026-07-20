"""Cursor 定价必须可追溯；未知价格不能伪装成零成本。"""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.cursor_pricing import (  # noqa: E402
    COST_UNKNOWN_ISSUE,
    load_cursor_pricing,
    price_cursor_usage,
)


def test_composer_25_pricing_is_revisioned_and_calculates_known_components() -> None:
    catalog = load_cursor_pricing()
    priced = price_cursor_usage(
        model_id="composer-2.5",
        catalog=catalog,
        usage={
            "usedTokens": 1_300_000,
            "inputTokens": 1_000_000,
            "outputTokens": 100_000,
            "cacheReadTokens": 200_000,
            "cacheWriteTokens": 0,
            "costAvailable": False,
            "costUsd": None,
        },
    )
    assert priced == {
        "costUsd": 0.79,
        "costSource": "catalog_calculated",
        "pricingRevision": "cursor-public-2026-07-19",
        "costIssue": None,
    }


def test_unknown_model_or_cache_write_price_blocks_instead_of_writing_zero() -> None:
    base = {
        "usedTokens": 1,
        "inputTokens": 1,
        "outputTokens": 0,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "costAvailable": False,
        "costUsd": None,
    }
    assert price_cursor_usage(model_id="unknown-model", usage=base)["costIssue"] == (
        COST_UNKNOWN_ISSUE
    )
    with_cache_write = {
        **base,
        "inputTokens": 0,
        "cacheWriteTokens": 1,
    }
    priced = price_cursor_usage(
        model_id="composer-2.5",
        usage=with_cache_write,
    )
    assert priced["costUsd"] is None
    assert priced["costIssue"] == COST_UNKNOWN_ISSUE


def test_sdk_billed_cost_wins_over_catalog_estimation() -> None:
    priced = price_cursor_usage(
        model_id="composer-2.5",
        usage={
            "usedTokens": 10,
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "costAvailable": True,
            "costUsd": 0.123,
        },
    )
    assert priced["costUsd"] == 0.123
    assert priced["costSource"] == "sdk_billed"
