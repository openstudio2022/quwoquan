from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.source.research import qunar_sources  # noqa: E402


def _date_years_ago(years: int) -> str:
    today = datetime.now(timezone(timedelta(hours=8))).date()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(month=2, day=28, year=today.year - years).isoformat()


def test_qunar_route_anchor_does_not_match_same_prefix_other_place() -> None:
    assert not qunar_sources._qunar_entity_anchor("锦里沟", "锦里")
    assert qunar_sources._qunar_entity_anchor("锦里古街", "锦里")


def test_qunar_route_anchor_rejects_homonymous_attraction_in_another_city() -> None:
    title_hit, route_hit = qunar_sources._qunar_row_anchor_signals(
        {
            "title": "潮州2天1夜平民自驾游",
            "travelRoute": ["潮州西湖"],
            "cityName": "潮州",
        },
        entity_id="杭州西湖",
        match_terms=["杭州西湖", "西湖"],
    )

    assert not title_hit
    assert not route_hit


def test_qunar_travelogue_sources_prioritize_recent_entity_anchored_rows(monkeypatch) -> None:
    rows = [
        {
            "id": "old-focused",
            "title": "初秋游毕棚沟攻略",
            "travelRoute": ["毕棚沟"],
            "publishedAt": _date_years_ago(4),
            "viewCount": 9000,
        },
        {
            "id": "false-prefix",
            "title": "武汉周边亲子旅行攻略",
            "travelRoute": ["锦里沟"],
            "publishedAt": _date_years_ago(1),
            "viewCount": 9999,
        },
        {
            "id": "recent-focused",
            "title": "最近一次毕棚沟两日游攻略",
            "travelRoute": ["毕棚沟"],
            "publishedAt": _date_years_ago(1),
            "viewCount": 100,
        },
    ]

    def fake_curl_json(url: str, timeout: int = 20):  # noqa: ARG001
        if "page=1" not in url:
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {"ret": True, "data": {"bookList": rows, "more": False}}

    monkeypatch.setattr(qunar_sources.network_io, "curl_json", fake_curl_json)
    monkeypatch.setattr(qunar_sources, "_qunar_author_books_rows", lambda **_: [])

    sources = qunar_sources._qunar_travelogue_sources("毕棚沟", limit=2)

    assert [source["url"].rsplit("/", 1)[-1] for source in sources] == [
        "recent-focused",
        "old-focused",
    ]
    assert sources[0]["sourceFreshnessTier"] == "recent_3y"
    assert sources[1]["sourceFreshnessTier"] == "stale_over_3y"
    assert float(sources[1]["matchConfidence"]) < float(sources[0]["matchConfidence"])


def test_qunar_travelogue_sources_excludes_same_prefix_route_false_positive(monkeypatch) -> None:
    rows = [
        {
            "id": "jinligou",
            "title": "武汉黄陂木兰生态旅游区攻略",
            "travelRoute": ["锦里沟", "木兰草原"],
            "publishedAt": _date_years_ago(1),
        }
    ]

    monkeypatch.setattr(
        qunar_sources.network_io,
        "curl_json",
        lambda url, timeout=20: {"ret": True, "data": {"bookList": rows, "more": False}},
    )
    monkeypatch.setattr(qunar_sources, "_qunar_author_books_rows", lambda **_: [])

    assert qunar_sources._qunar_travelogue_sources("锦里", limit=4) == []
