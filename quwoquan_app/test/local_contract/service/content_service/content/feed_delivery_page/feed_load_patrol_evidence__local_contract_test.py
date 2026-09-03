from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[6]
FEED_UAT = (
    APP_ROOT
    / "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_load__user_acceptance_test.dart"
)
VIDEO_UAT = (
    APP_ROOT
    / "test/user_acceptance/journeys/home_video_playback/"
    "video_playback_canary__user_acceptance_test.dart"
)
CONTROLLED_EDGE_UAT = (
    APP_ROOT
    / "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)


def test_feed_uat_emits_release_bound_evidence_through_captured_stdout() -> None:
    source = FEED_UAT.read_text(encoding="utf-8")

    config_start = source.index("config: PatrolTesterConfig(")
    callback_start = source.index("($) async {", config_start)
    config = source[config_start:callback_start]

    assert "printLogs: true" in config
    assert "print(\n        'QWQ_FEED_CONTENT_EVIDENCE " in source
    assert "$.log(\n        'QWQ_FEED_CONTENT_EVIDENCE " not in source
    assert "debugPrint(\n        'QWQ_FEED_CONTENT_EVIDENCE " not in source
    media_success = "matching: find.byKey(appImageLoadSuccessKey)"
    media_error = "matching: find.byKey(appImageLoadErrorKey)"
    evidence = source.index("QWQ_FEED_CONTENT_EVIDENCE ")
    screenshot = source.index("emitPatrolAppContentPageScreenshotReady(")
    assert "package:quwoquan_app/design_system/media/app_cached_network_image.dart" in source
    assert media_success in source and media_error in source
    assert source.index("of: visibleFeedCard") < source.index(media_success) < evidence
    assert source.index(media_error) < evidence < screenshot
    assert "GoRouterState.of(" in source
    assert "AppRoutePaths.home" in source
    assert "terminalKey: terminalKey" in source
    assert "terminalFinder: visibleFeedCard" in source
    assert "'mediaLoadStatus': 'decoded'" in source


def test_video_and_recovery_evidence_use_captured_stdout() -> None:
    video_source = VIDEO_UAT.read_text(encoding="utf-8")
    controlled_edge_source = CONTROLLED_EDGE_UAT.read_text(encoding="utf-8")

    assert "print(\n          'QWQ_VIDEO_PLAYBACK_EVIDENCE " in video_source
    assert "$.log(\n          'QWQ_VIDEO_PLAYBACK_EVIDENCE " not in video_source
    assert "debugPrint(\n          'QWQ_VIDEO_PLAYBACK_EVIDENCE " not in video_source
    for marker in (
        "QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST ",
        "QWQ_APP_CONTENT_FAULT_EVIDENCE ",
    ):
        assert f"print(\n        '{marker}" in controlled_edge_source
        assert f"$.log(\n        '{marker}" not in controlled_edge_source
        assert f"debugPrint(\n        '{marker}" not in controlled_edge_source


if __name__ == "__main__":
    test_feed_uat_emits_release_bound_evidence_through_captured_stdout()
    test_video_and_recovery_evidence_use_captured_stdout()
