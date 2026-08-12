from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[6]


def test_home_article_cards_consume_summary_projection_not_raw_markdown() -> None:
    view_data = (
        APP_ROOT
        / "lib/service/content_service/content/post/application/public/content_post_view_data.dart"
    ).read_text(encoding="utf-8")
    feed_media = (
        APP_ROOT
        / "lib/service/content_service/content/post/presentation/home_multi_form_feed_media.dart"
    ).read_text(encoding="utf-8")
    feed_cards = (
        APP_ROOT
        / "lib/service/content_service/content/post/presentation/home_multi_form_feed_post_cards.dart"
    ).read_text(encoding="utf-8")

    assert "String get normalizedSummary => summary.trim();" in view_data
    assert "String get articlePreviewText => normalizedSummary;" in view_data
    assert "articlePreviewText => normalizedSummary.isNotEmpty" not in view_data
    assert feed_media.count("item.articlePreviewText") >= 3
    assert feed_cards.count("item.articlePreviewText") >= 2


if __name__ == "__main__":
    test_home_article_cards_consume_summary_projection_not_raw_markdown()
