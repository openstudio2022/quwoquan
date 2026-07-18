from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import local_gamma_media


class LocalGammaMediaContractTest(unittest.TestCase):
    def test_materialization_copies_and_verifies_canonical_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "source"
            target = root / "target"
            key = "media/video/s/asset/mas_video_001/v1/source.mp4"
            video = source / key
            video.parent.mkdir(parents=True)
            video.write_bytes(b"canonical-video")
            digest = f"sha256:{hashlib.sha256(video.read_bytes()).hexdigest()}"
            manifest = root / "media_delivery_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "logicalAssetId": "content-video-primary",
                                "publicSliceKey": key,
                                "sha256": digest,
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(local_gamma_media, "CANONICAL_MEDIA_ROOT", source),
                mock.patch.object(local_gamma_media, "MEDIA_DELIVERY_MANIFEST", manifest),
            ):
                report = local_gamma_media.materialize_local_gamma_media(target)

            self.assertEqual(report["publicSliceKey"], key)
            self.assertEqual(report["sha256"], digest)
            self.assertEqual((target / key).read_bytes(), b"canonical-video")

    def test_verification_fails_when_canonical_video_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            manifest = root / "media_delivery_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "logicalAssetId": "content-video-primary",
                                "publicSliceKey": "media/video/s/missing/v1/source.mp4",
                                "sha256": "sha256:00",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(local_gamma_media, "MEDIA_DELIVERY_MANIFEST", manifest),
                self.assertRaisesRegex(
                    local_gamma_media.LocalGammaMediaError,
                    "canonical video materialization missing",
                ),
            ):
                local_gamma_media.verify_canonical_video_materialization(root / "target")


if __name__ == "__main__":
    unittest.main()
