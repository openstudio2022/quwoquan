# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[6]
CANVAS = (
    APP_DIR
    / "lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart"
)
HOME_FEED_COMPOSITION = (
    APP_DIR / "lib/runtime/di/presentation/home_feed_cross_object_composition.dart"
)
CONTROLLER_FACTORY = (
    APP_DIR / "lib/runtime/platform/video_player_controller_factory.dart"
)


class WorksVideoSessionLifecycleContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = CANVAS.read_text(encoding="utf-8")
        cls.home_feed_source = HOME_FEED_COMPOSITION.read_text(encoding="utf-8")
        cls.controller_factory_source = CONTROLLER_FACTORY.read_text(encoding="utf-8")
        cls.canvas_state = cls.source.split(
            "class _WorksVideoCanvasState", 1
        )[1].split("class _WorksVideoEpisodeStage extends", 1)[0]
        cls.episode_state = cls.source.split(
            "class _WorksVideoEpisodeStageState", 1
        )[1].split("class _WorksPausedPlaybackOverlay", 1)[0]

    def test_parent_registry_only_tracks_mounted_episode_sessions(self) -> None:
        self.assertIn("_mountedSessionsByIdentity", self.canvas_state)
        self.assertNotIn("_sessionsByIdentity", self.canvas_state)
        self.assertIn(
            "identical(_mountedSessionsByIdentity[identity], session)",
            self.canvas_state,
        )
        self.assertIn(
            "_mountedSessionsByIdentity.remove(identity);",
            self.canvas_state,
        )
        self.assertNotIn("session.dispose();", self.canvas_state)

    def test_episode_stage_disposes_only_after_its_children_unmount(self) -> None:
        self.assertIn(
            "late final VideoPlaybackSession _session;",
            self.episode_state,
        )
        self.assertIn("playbackSession: _session", self.episode_state)
        self.assertIn(
            "_WorksPausedPlaybackOverlay(session: _session)",
            self.episode_state,
        )
        untrack = self.episode_state.index("widget.onSessionUnmounted(")
        dispose = self.episode_state.index("_session.dispose();")
        super_dispose = self.episode_state.index("super.dispose();")
        self.assertLess(untrack, dispose)
        self.assertLess(dispose, super_dispose)

    def test_current_and_preheated_episodes_use_texture_renderer(self) -> None:
        self.assertIn(
            "widget.isVisible && (isCurrent || shouldPreheat)",
            self.canvas_state,
        )
        self.assertIn("child: _WorksVideoEpisodeStage(", self.canvas_state)
        self.assertIn("viewType: VideoViewType.textureView", self.episode_state)

    def test_home_inline_player_keeps_android_platform_view_default(self) -> None:
        home_player = self.home_feed_source.split(
            "static Widget videoPlayer(", 1
        )[1].split("static Widget videoCenterPlayGlyph", 1)[0]
        self.assertIn("return VideoPlayerWidget(", home_player)
        self.assertNotIn("viewType:", home_player)
        self.assertIn(
            "viewType: viewType ?? preferredViewType",
            self.controller_factory_source,
        )


if __name__ == "__main__":
    unittest.main()
