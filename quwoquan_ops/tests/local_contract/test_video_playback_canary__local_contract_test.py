from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import verify_video_playback_canary as canary


class VideoPlaybackCanaryContractTest(unittest.TestCase):
    def _topology_target(self) -> dict[str, object]:
        return {
            "publicBases": {
                "mediaVideo": "https://cdn.quwoquan.com",
            }
        }

    def test_gray_initial_release_canary_requires_auth_and_range_mime(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_TEST_AUTH_TOKEN": "secret-token",
                    "PROD_ROLLOUT_STAGE": "gray-initial",
                    "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY": (
                        "media/video/s/release-video-20260716/post/canary.mp4"
                    ),
                },
                clear=True,
            ),
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(canary, "get_target", return_value=self._topology_target()),
            mock.patch.object(
                canary,
                "_probe_https_video",
                return_value=(206, "video/mp4"),
            ) as probe,
            redirect_stdout(output),
        ):
            status = canary.main([])

        self.assertEqual(status, 0)
        self.assertIn('"status": "passed"', output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())
        self.assertEqual(
            probe.call_args.args[0],
            "https://cdn.quwoquan.com/media/video/s/release-video-20260716/post/canary.mp4",
        )

    def test_missing_authentication_blocks_hosted_patrol_preflight(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_ROLLOUT_STAGE": "gray-initial",
                    "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY": (
                        "media/video/s/release-video-20260716/post/canary.mp4"
                    ),
                },
                clear=True,
            ),
            redirect_stdout(output),
        ):
            status = canary.main([])

        self.assertEqual(status, 2)
        self.assertIn("required authentication prerequisite", output.getvalue())

    def test_topology_selects_release_canary_slice_environment_variable(self) -> None:
        output = io.StringIO()
        target = self._topology_target()
        target["playbackCanary"] = {
            "publicSliceKeyEnv": "PUBLISHED_CANARY_SLICE",
        }
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_TEST_AUTH_TOKEN": "secret-token",
                    "PROD_ROLLOUT_STAGE": "gray-initial",
                    "PUBLISHED_CANARY_SLICE": (
                        "media/video/s/release-video-20260716/post/canary.mp4"
                    ),
                },
                clear=True,
            ),
            mock.patch.object(canary, "load_environment_topology", return_value={}),
            mock.patch.object(canary, "get_target", return_value=target),
            mock.patch.object(
                canary,
                "_probe_https_video",
                return_value=(206, "video/mp4"),
            ),
            redirect_stdout(output),
        ):
            status = canary.main([])

        self.assertEqual(status, 0)
        self.assertIn('"status": "passed"', output.getvalue())

    def test_fixture_key_cannot_be_a_production_release_canary(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "PROD_TEST_AUTH_TOKEN": "secret-token",
                    "PROD_ROLLOUT_STAGE": "gray-initial",
                    "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY": (
                        "media/video/s/fixture_video_001/source.mp4"
                    ),
                },
                clear=True,
            ),
            redirect_stdout(output),
        ):
            status = canary.main([])

        self.assertEqual(status, 2)
        self.assertIn("must not reference fixture/mock/seed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
