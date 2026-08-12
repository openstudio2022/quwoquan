from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[6]
REPO_ROOT = APP_ROOT.parent


def test_home_creator_snapshot_has_one_content_to_app_projection_path() -> None:
    feed_service = (
        REPO_ROOT
        / "quwoquan_service/services/content-service/internal/content/post/application/feed/feed_service.go"
    ).read_text(encoding="utf-8")
    generated_wire = (
        APP_ROOT
        / "packages/quwoquan_cloud_contracts/lib/src/content/content_operation_contracts.g.dart"
    ).read_text(encoding="utf-8")
    view_data = (
        APP_ROOT
        / "lib/service/content_service/content/post/application/public/content_post_view_data.dart"
    ).read_text(encoding="utf-8")
    home_cards = (
        APP_ROOT
        / "lib/service/content_service/content/post/presentation/home_multi_form_feed_post_cards.dart"
    ).read_text(encoding="utf-8")

    assert "AuthorDisplayName:        post.AuthorDisplayName" in feed_service
    assert 'authorDisplayName: map["authorDisplayName"]' in generated_wire
    assert "displayName: wire.authorDisplayName?.trim() ?? ''" in view_data
    assert "name: item.displayName" in home_cards
    assert "未知用户" not in home_cards


if __name__ == "__main__":
    test_home_creator_snapshot_has_one_content_to_app_projection_path()
