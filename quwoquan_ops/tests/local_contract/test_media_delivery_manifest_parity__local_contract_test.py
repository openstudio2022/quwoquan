from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.media_delivery_manifest import build_media_delivery_url
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke
from quwoquan_ops.cli import stackctl


class MediaDeliveryManifestParityTest(unittest.TestCase):
    def test_attachment_and_background_share_image_origin_without_new_role(self) -> None:
        public_bases = get_target(
            load_environment_topology(), "gamma-local"
        )["publicBases"]
        attachment = build_media_delivery_url(
            public_bases,
            {
                "mediaType": "attachment",
                "publicSliceKey": "media/attachment/s/a/v1/source.pdf",
                "version": 1,
            },
        )
        background = build_media_delivery_url(
            public_bases,
            {
                "mediaType": "background",
                "publicSliceKey": "media/background/s/b/v1/source.webp",
                "version": 1,
            },
        )
        self.assertEqual(
            attachment,
            "https://cdn.gamma.quwoquan.com:19100/media/attachment/s/a/v1/source.pdf",
        )
        self.assertEqual(
            background,
            "https://cdn.gamma.quwoquan.com:19100/media/background/s/b/v1/source.webp",
        )

    def test_gamma_topology_keeps_distinct_image_and_upload_bases(self) -> None:
        topology = load_environment_topology()
        target = get_target(topology, "gamma-local")
        public_bases = target["publicBases"]

        self.assertIn("19100", str(public_bases["mediaImage"]))
        self.assertIn("19130", str(public_bases["mediaUpload"]))
        self.assertNotEqual(public_bases["mediaImage"], public_bases["mediaUpload"])

    def test_stackctl_gamma_page_smoke_passes_four_media_bases(self) -> None:
        command = stackctl._environment_page_smoke_profile_command(
            "gamma",
            "gamma-local",
            Path("/tmp/gamma-media-parity"),
        )
        self.assertIsNotNone(command)
        argv = command["argv"]
        self.assertEqual(
            argv[argv.index("--media-image-base-url") + 1],
            "https://cdn.gamma.quwoquan.com:19100/media/image",
        )
        self.assertEqual(
            argv[argv.index("--media-upload-base-url") + 1],
            "https://upload.gamma.quwoquan.com:19130",
        )
        self.assertIn("--media-avatar-base-url", argv)
        self.assertIn("--media-video-base-url", argv)

    def test_patrol_requires_four_typed_media_bases(self) -> None:
        namespace = type(
            "Args",
            (),
            {
                "media_avatar_base_url": "",
                "media_image_base_url": "",
                "media_video_base_url": "",
                "media_upload_base_url": "",
            },
        )()
        actual = smoke._resolved_media_base_urls(namespace)
        self.assertEqual(
            actual,
            {
                "mediaAvatarBaseUrl": "",
                "mediaImageBaseUrl": "",
                "mediaVideoBaseUrl": "",
                "mediaUploadBaseUrl": "",
            },
        )


if __name__ == "__main__":
    unittest.main()
