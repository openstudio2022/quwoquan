"""Single extractor for closed-set homepage structured facts from body text.

`lanePolicies.homepage.structuredFactsPolicy.fields` is the governed closed
set.  Every encyclopedia body producer (Baike HTML text, MediaWiki rendered
text) must consume this one extractor so acquisition, diagnostics and tests
never fork a second field-recognition truth source.
"""
from __future__ import annotations

import html as html_module
import re
from typing import Any

_SEASON_TAGS = {
    "春季": "Topic/时间/四季/春季",
    "夏季": "Topic/时间/四季/夏季",
    "秋季": "Topic/时间/四季/秋季",
    "冬季": "Topic/时间/四季/冬季",
}
_INFOBOX_FIELDS = {
    "开放时间": "openingHours",
    "营业时间": "openingHours",
    "门票价格": "ticketPriceRange",
    "票价": "ticketPriceRange",
    "门票": "ticketPriceRange",
    "海拔": "altitudeMeters",
    "海拔高度": "altitudeMeters",
    "建议游玩时长": "recommendedDurationMinutes",
    "建议游览时长": "recommendedDurationMinutes",
    "游玩时长": "recommendedDurationMinutes",
    "适宜游玩季节": "bestSeasonTagRefs",
    "最佳游览时间": "bestSeasonTagRefs",
    "最佳旅游时间": "bestSeasonTagRefs",
    "官方网站": "officialWebsite",
    "官网": "officialWebsite",
}
_INFOBOX_KEY = '"type":"infobox_key"'
_INFOBOX_VALUE = '"type":"infobox_value"'
_PROPERTY_ID = re.compile(r'"property_id":"([^"]+)"')
_NODE_TEXT = re.compile(r'"text":"([^"]*)"')
_HTTPS_SITE = re.compile(r"https://[^\s\"'<>\\]+")


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


def _infobox_rows(raw_html: bytes) -> list[tuple[str, str]]:
    decoded = html_module.unescape(
        raw_html.decode("utf-8", errors="replace").replace('\\"', '"')
    )
    rows: list[tuple[str, str]] = []
    for segment in decoded.split(_INFOBOX_KEY)[1:]:
        key_match = _PROPERTY_ID.search(segment)
        if key_match is None:
            continue
        parts = segment.split(_INFOBOX_VALUE, 1)
        if len(parts) != 2:
            continue
        value_segment = parts[1].split(_INFOBOX_KEY, 1)[0]
        values = [
            text.strip() for text in _NODE_TEXT.findall(value_segment) if text.strip()
        ]
        if values:
            rows.append((key_match.group(1).strip(), " ".join(values)))
    return rows


def extract_structured_fact_from_baike_infobox(
    raw_html: bytes,
) -> tuple[str, Any] | None:
    """Return one governed fact that a Baike infobox declares about itself.

    The rendered summary a Baike page serves to an anonymous fetch stops before
    the infobox, so opening hours and ticket prices — the fields an encyclopedia
    publishes as first-hand structured data — are absent from body text while
    sitting in the page bytes as escaped JSON.  Reading only the summary
    therefore rejects real, well-sourced scenic entities at the source-pool
    gate for lacking a fact their own source states.

    A value must answer its own key: the closed-set field derived from the
    value has to be the field the key promises, so an adjacent altitude cell
    cannot be admitted under an `开放时间` label.  Field precedence stays the
    one in `extract_structured_fact_from_text`, keeping a single recognition
    truth source across body text and infobox.
    """

    rows = _infobox_rows(raw_html)
    if not rows:
        return None
    declared: dict[str, tuple[str, Any]] = {}
    for key, value in rows:
        expected = _INFOBOX_FIELDS.get(key)
        if expected is None or expected in declared:
            continue
        if expected == "officialWebsite":
            site = _HTTPS_SITE.search(value)
            if site is not None:
                declared[expected] = (
                    expected,
                    site.group(0).rstrip(".,;:)]}，。；：）】"),
                )
            continue
        extracted = extract_structured_fact_from_text(f"{key}{value}")
        if extracted is not None and extracted[0] == expected:
            declared[expected] = extracted
    for field in (
        "altitudeMeters",
        "recommendedDurationMinutes",
        "openingHours",
        "ticketPriceRange",
        "bestSeasonTagRefs",
        "officialWebsite",
    ):
        if field in declared:
            return declared[field]
    return None


__all__ = [
    "extract_structured_fact_from_baike_infobox",
    "extract_structured_fact_from_text",
]
