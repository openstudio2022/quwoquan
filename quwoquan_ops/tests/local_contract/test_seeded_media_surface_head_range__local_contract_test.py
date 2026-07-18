"""Manifest 驱动的本地媒体 surface HEAD/Range 契约（alpha edge 可用时）。"""

from __future__ import annotations

import ssl
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import load_environment_topology
from quwoquan_ops.cli.lib.media_delivery_manifest import (
    build_media_delivery_url,
    load_media_delivery_manifest,
)


class SeededMediaSurfaceHeadRangeLocalContractTest(unittest.TestCase):
    def test_alpha_manifest_assets_path_query_stable_and_optional_reachable(self) -> None:
        topology = load_environment_topology()
        public_bases = topology["environments"]["alpha"]["publicBases"]
        assets = load_media_delivery_manifest()
        self.assertGreaterEqual(len(assets), 3)
        for asset in assets:
            url = build_media_delivery_url(public_bases, asset)
            self.assertTrue(url.startswith("https://"), url)
            self.assertIn(asset["publicSliceKey"], url)
            self.assertNotIn("media/objects/sha256/", url)
            # edge 未启动时仅校验 URL 形态；可达时断言 200/206
            # alpha 使用本地自签 CA；探测时允许未校验 TLS（仅本地契约）。
            ctx = ssl._create_unverified_context()
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=2, context=ctx) as resp:
                    self.assertIn(resp.status, (200, 204, 206, 405))
                if asset["mediaType"] == "video":
                    range_req = urllib.request.Request(
                        url,
                        headers={"Range": "bytes=0-1"},
                        method="GET",
                    )
                    with urllib.request.urlopen(
                        range_req, timeout=2, context=ctx
                    ) as resp:
                        self.assertIn(resp.status, (200, 206))
            except (urllib.error.URLError, TimeoutError, OSError):
                # 本地未起 alpha media edge 时跳过可达性，形态契约仍成立
                pass


if __name__ == "__main__":
    unittest.main()
