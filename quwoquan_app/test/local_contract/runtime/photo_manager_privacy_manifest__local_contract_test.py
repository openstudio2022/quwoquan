# spec_ref: specs/feature-tree/runtime/spec.md#dom-001
#
# The vendored Darwin pod must compile only Objective-C source/header files.
# Apple's privacy manifest is a resource and must never enter Xcode's compile
# source phase, otherwise Xcode emits a per-architecture "no rule to process"
# warning for the text.xml file type.

import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
PODSPEC = (
    APP_DIR
    / "vendor/plugins/photo_manager/darwin/photo_manager.podspec"
)


class PhotoManagerPrivacyManifestContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.podspec = PODSPEC.read_text(encoding="utf-8")

    def test_source_files_are_limited_to_compilable_objective_c_files(self) -> None:
        source_files = re.search(
            r'^\s*s\.source_files\s*=\s*"([^"]+)"\s*$',
            self.podspec,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(source_files, "photo_manager source_files is missing")
        self.assertEqual(
            source_files.group(1),
            "#{package_name}/Sources/#{package_name}/**/*.{h,m}",
        )

    def test_privacy_manifest_is_declared_once_and_only_as_a_resource(self) -> None:
        manifest_path = (
            "#{package_name}/Sources/#{package_name}/Resources/"
            "PrivacyInfo.xcprivacy"
        )
        self.assertEqual(self.podspec.count("PrivacyInfo.xcprivacy"), 1)

        resource_bundles = re.search(
            r"s\.resource_bundles\s*=\s*\{(?P<body>.*?)\n\s*\}",
            self.podspec,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            resource_bundles,
            "photo_manager privacy resource bundle is missing",
        )
        self.assertIn(manifest_path, resource_bundles.group("body"))


if __name__ == "__main__":
    unittest.main()
