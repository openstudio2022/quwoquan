from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_alpha_media_fixture_surface as media_surface
from quwoquan_ops.gate.verify_alpha_media_fixture_surface import _resolve_local_root_ca


class SeededMediaCAPathContractTest(unittest.TestCase):
    def test_app_mock_group_avatar_refs_match_the_versioned_materialized_paths(
        self,
    ) -> None:
        refs = media_surface._collect_app_mock_group_avatar_refs()

        self.assertIn(
            "media/avatar/s/archived-avatar/conversation/conv_002/v1/mock.png",
            refs,
        )
        self.assertIn(
            "media/avatar/s/archived-avatar/conversation/conv_grid_16/v1/mock.png",
            refs,
        )
        self.assertTrue(
            all((media_surface.MEDIA_ROOT / reference).is_file() for reference in refs),
        )

    def test_seeded_media_probes_keep_kind_specific_bases_under_parallel_execution(
        self,
    ) -> None:
        base_urls = {
            "avatar": "https://avatar.example.test",
            "image": "https://image.example.test",
            "video": "https://video.example.test",
        }
        object_keys = [
            "media/avatar/s/archived-avatar/user/a/v1/avatar.png",
            "media/image/s/archived-image/post/a/v1/cover.png",
            "media/video/s/video-a/post/a/source.mp4",
        ]

        with mock.patch.object(
            media_surface,
            "_curl_probe",
            return_value=("206", "video/mp4"),
        ) as probe:
            results = media_surface._probe_seeded_media_objects(
                object_keys,
                base_urls=base_urls,
                cacert=Path("/tmp/local-root.crt"),
                resolve_local=True,
            )

        self.assertEqual(set(results), set(object_keys))
        called_urls = {call.args[0] for call in probe.call_args_list}
        self.assertEqual(
            called_urls,
            {
                "https://avatar.example.test/media/avatar/s/archived-avatar/user/a/v1/avatar.png",
                "https://image.example.test/media/image/s/archived-image/post/a/v1/cover.png",
                "https://video.example.test/media/video/s/video-a/post/a/source.mp4",
            },
        )
        video_call = next(
            call
            for call in probe.call_args_list
            if call.args[0].startswith("https://video.example.test/")
        )
        self.assertTrue(video_call.kwargs["range_probe"])
        self.assertTrue(video_call.kwargs["resolve_local"])

    def test_local_ca_is_resolved_from_external_deploy_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            alpha_root = deploy_root / "alpha-local" / "certificates" / "root.crt"
            gamma_root = deploy_root / "gamma-local" / "certificates" / "root.crt"
            alpha_root.parent.mkdir(parents=True)
            gamma_root.parent.mkdir(parents=True)
            alpha_root.write_text("alpha root", encoding="utf-8")
            gamma_root.write_text("gamma root", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                self.assertEqual(
                    _resolve_local_root_ca("alpha-local", ""),
                    alpha_root,
                )
                self.assertEqual(
                    _resolve_local_root_ca("gamma-local", ""),
                    gamma_root,
                )


if __name__ == "__main__":
    unittest.main()
