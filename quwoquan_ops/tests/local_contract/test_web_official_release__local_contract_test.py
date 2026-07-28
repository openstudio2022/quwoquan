# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-005
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    _inject_noindex,
    _trusted_web_origin,
    _verify_web_build,
)


class WebOfficialReleaseContractTest(unittest.TestCase):
    def test_environment_origins_are_exact_official_hosts(self) -> None:
        self.assertEqual(
            _trusted_web_origin("alpha", "https://alpha.quwoquan.com"),
            "https://alpha.quwoquan.com",
        )
        self.assertEqual(
            _trusted_web_origin("prod", "https://quwoquan.com/"),
            "https://quwoquan.com",
        )
        for rejected in (
            "https://alpha-web.invalid",
            "https://attacker.example",
            "http://alpha.quwoquan.com",
        ):
            with self.assertRaises(WebOfficialReleaseError):
                _trusted_web_origin("alpha", rejected)

    def test_build_contract_requires_utf8_pwa_and_service_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<!doctype html><html lang="zh-CN"><head>'
                '<meta charset="utf-8">\n'
                '  <meta name="description" content="趣我圈"></head></html>',
                encoding="utf-8",
            )
            (root / "main.dart.js").write_text("main();", encoding="utf-8")
            (root / "flutter_service_worker.js").write_text(
                "self.addEventListener('fetch',()=>{});",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "display": "standalone",
                        "start_url": "/",
                        "scope": "/",
                    }
                ),
                encoding="utf-8",
            )
            _verify_web_build(root)
            _inject_noindex(root / "index.html")
            self.assertIn(
                'content="noindex,nofollow"',
                (root / "index.html").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
