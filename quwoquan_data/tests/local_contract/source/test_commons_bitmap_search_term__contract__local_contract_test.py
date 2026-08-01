"""Commons scenic-name searches must prefer bitmap files over djvu/pdf books."""

from __future__ import annotations

from content.source.research.image_search_providers import _commons_bitmap_search_term


def test_commons_bitmap_search_term_appends_filetype_filter() -> None:
    assert _commons_bitmap_search_term("西湖") == "西湖 filetype:bitmap"
    assert _commons_bitmap_search_term("West Lake") == "West Lake filetype:bitmap"


def test_commons_bitmap_search_term_keeps_explicit_filetype() -> None:
    assert (
        _commons_bitmap_search_term("西湖 filetype:bitmap")
        == "西湖 filetype:bitmap"
    )
    assert (
        _commons_bitmap_search_term("西湖 filetype:video")
        == "西湖 filetype:video"
    )
