#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_ROOT / "scripts" / "tools" / "ios"))

from ios_shortcut_log_hygiene import (
    audit_ios_shortcut_sources,
    filter_shortcut_log_noise,
)


BENIGN_WF_BLOCK = [
    "-[WFIsolatedShortcutRunner init] Taking sandbox extensions for execution\n",
    "-[WFIsolatedShortcutRunner init]_block_invoke Sandbox extensions acquired\n",
    "Indexing for request: <WFToolKitIndexingRequest: 0x600001704c40>\n",
    "Inserted en/languageModel in preferred localizations.\n",
    "Resolved Preferred localizations: [locale: en, locale: zh_CN]\n",
    "Indexed: 0\n",
    "Errored: 0\n",
    "Skipped: [:]\n",
    "Finished in 0.313837s\n",
    "-[WFIsolatedShortcutRunner unaliveProcess] Releasing sandbox extensions\n",
]


class IosShortcutLogHygieneTest(unittest.TestCase):
    def test_audit_passes_clean_ios_project(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            ios_root = Path(raw_dir)
            runner = ios_root / "Runner"
            runner.mkdir()
            (runner / "Info.plist").write_text(
                """
                <plist>
                  <dict>
                    <key>CFBundleName</key>
                    <string>Runner</string>
                  </dict>
                </plist>
                """,
                encoding="utf-8",
            )
            (runner / "AppDelegate.swift").write_text(
                "import Flutter\nimport UIKit\n",
                encoding="utf-8",
            )

            self.assertEqual(audit_ios_shortcut_sources(ios_root), [])

    def test_audit_flags_siri_entitlement(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            ios_root = Path(raw_dir)
            (ios_root / "Runner").mkdir()
            entitlement = ios_root / "Runner" / "Runner.entitlements"
            entitlement.write_text(
                """
                <plist>
                  <dict>
                    <key>com.apple.developer.siri</key>
                    <true/>
                  </dict>
                </plist>
                """,
                encoding="utf-8",
            )

            findings = audit_ios_shortcut_sources(ios_root)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].label, "siri-entitlement")
            self.assertEqual(findings[0].path, entitlement)

    def test_filter_removes_complete_benign_wf_block(self) -> None:
        video_error = (
            "flutter: [VideoPlayerWidget] candidate init failed "
            "error=PlatformException(VideoError)\n"
        )
        lines = [
            "flutter: app started\n",
            *BENIGN_WF_BLOCK,
            video_error,
        ]

        filtered = filter_shortcut_log_noise(lines)

        self.assertEqual(filtered, ["flutter: app started\n", video_error])

    def test_filter_preserves_non_benign_wf_block(self) -> None:
        non_benign = [
            line.replace("Errored: 0", "Errored: 1")
            for line in BENIGN_WF_BLOCK
        ]

        filtered = filter_shortcut_log_noise(non_benign)

        self.assertEqual(filtered, non_benign)

    def test_filter_does_not_swallow_interleaved_flutter_error(self) -> None:
        lines = [
            "-[WFIsolatedShortcutRunner init] Taking sandbox extensions for execution\n",
            "flutter: Unhandled exception: visible failure\n",
            "Indexed: 0\n",
            "Errored: 0\n",
        ]

        filtered = filter_shortcut_log_noise(lines)

        self.assertEqual(filtered, lines)


if __name__ == "__main__":
    unittest.main()
