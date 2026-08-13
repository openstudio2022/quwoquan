"""Single extractor for closed-set homepage structured facts from body text.

`lanePolicies.homepage.structuredFactsPolicy.fields` is the governed closed
set.  Every encyclopedia body producer (Baike HTML text, MediaWiki rendered
text) must consume this one extractor so acquisition, diagnostics and tests
never fork a second field-recognition truth source.
"""
from __future__ import annotations

import re
from typing import Any

_SEASON_TAGS = {
    "春季": "Topic/时间/四季/春季",
    "夏季": "Topic/时间/四季/夏季",
    "秋季": "Topic/时间/四季/秋季",
    "冬季": "Topic/时间/四季/冬季",
}


def _time_minutes(hour: str, minute: str) -> int:
    return int(hour) * 60 + int(minute)


def extract_structured_fact_from_text(text: str) -> tuple[str, Any] | None:
    """Return the first governed closed-set (field, value) found in body text."""

    altitude = re.search(r"海拔(?:约|为|高度为)?\s*([0-9]{1,4})(?:\.[0-9]+)?\s*米", text)
    if altitude and -500 <= int(altitude.group(1)) <= 9000:
        return "altitudeMeters", int(altitude.group(1))
    duration = re.search(
        r"(?:建议|推荐)?(?:游玩|游览|参观)(?:时间|时长)?[^。\n]{0,12}?"
        r"([0-9]{1,2})(?:\s*[-—至到]\s*([0-9]{1,2}))?\s*(?:小时|钟头)",
        text,
    )
    if duration:
        lower = int(duration.group(1)) * 60
        upper = int(duration.group(2) or duration.group(1)) * 60
        if 1 <= lower <= upper <= 1440:
            return "recommendedDurationMinutes", {
                "minMinutes": lower,
                "maxMinutes": upper,
            }
    opening = re.search(
        r"(?:开放|营业)(?:时间)?[^。\n]{0,20}?"
        r"([01]?\d|2[0-3]):([0-5]\d)\s*[-—至到]\s*"
        r"([01]?\d|2[0-3]):([0-5]\d)",
        text,
    )
    if opening:
        open_minute = _time_minutes(opening.group(1), opening.group(2))
        close_minute = _time_minutes(opening.group(3), opening.group(4))
        if close_minute > open_minute:
            return "openingHours", [
                {
                    "openMinuteOfDay": open_minute,
                    "closeMinuteOfDay": close_minute,
                }
            ]
    free = re.search(r"(?:门票|票价)[^。\n]{0,12}?(?:免费|免票)", text)
    price = re.search(
        r"(?:门票|票价)[^。\n]{0,20}?([0-9]{1,4})"
        r"(?:\s*[-—至到]\s*([0-9]{1,4}))?\s*元",
        text,
    )
    if free:
        return "ticketPriceRange", {
            "currency": "CNY",
            "minAmountCents": 0,
            "maxAmountCents": 0,
            "free": True,
        }
    if price:
        lower = int(price.group(1)) * 100
        upper = int(price.group(2) or price.group(1)) * 100
        if lower <= upper <= 1_000_000:
            return "ticketPriceRange", {
                "currency": "CNY",
                "minAmountCents": lower,
                "maxAmountCents": upper,
                "free": False,
            }
    season = re.search(
        r"(?:最佳|适宜)(?:游览|旅游|旅行|观赏|参观)?"
        r"(?:季节|时间)[^。\n]{0,32}",
        text,
    )
    season_window = season.group(0) if season else ""
    seasons = [tag for name, tag in _SEASON_TAGS.items() if name in season_window]
    if "四季皆宜" in text:
        seasons = list(_SEASON_TAGS.values())
    if seasons:
        return "bestSeasonTagRefs", seasons
    return None


__all__ = ["extract_structured_fact_from_text"]
