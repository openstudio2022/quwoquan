"""iOS 可安装下限锁定 16.0。

iOS 16.0 发布于 2022-09-12；满五年（2027-09-12）前不得把工程下限抬到 16.0 以上。

spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-002
spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-002.t1
spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-002.t2
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[4]
PODFILE = APP_DIR / "ios" / "Podfile"
PBXPROJ = APP_DIR / "ios" / "Runner.xcodeproj" / "project.pbxproj"
IOS_FLOOR = "16.0"


class IosMinimumOsContractTest(unittest.TestCase):
    def test_podfile_platform_is_ios_16(self) -> None:
        text = PODFILE.read_text(encoding="utf-8")
        match = re.search(r"^platform :ios, '([0-9.]+)'$", text, re.MULTILINE)
        self.assertIsNotNone(match, "Podfile must declare platform :ios")
        self.assertEqual(match.group(1), IOS_FLOOR)

    def test_podfile_post_install_deployment_target_is_ios_16(self) -> None:
        text = PODFILE.read_text(encoding="utf-8")
        targets = re.findall(
            r"\['IPHONEOS_DEPLOYMENT_TARGET'\] = '([0-9.]+)'",
            text,
        )
        self.assertEqual(targets, [IOS_FLOOR])

    def test_xcode_deployment_target_is_ios_16(self) -> None:
        text = PBXPROJ.read_text(encoding="utf-8")
        targets = re.findall(
            r"IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);",
            text,
        )
        self.assertGreater(len(targets), 0, "pbxproj must set IPHONEOS_DEPLOYMENT_TARGET")
        self.assertEqual(set(targets), {IOS_FLOOR})


if __name__ == "__main__":
    unittest.main()
