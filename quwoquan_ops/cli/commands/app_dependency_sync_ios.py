"""iOS projection validation for app dependency synchronization."""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.package_reuse.dependency_fs import read_regular_nofollow


def assert_ios_generated_metadata(app_root: Path) -> None:
    """Require fresh projection-bound CocoaPods metadata without SwiftPM residue."""

    ios_root = app_root / "ios"
    encoded, _mode = read_regular_nofollow(
        ios_root / "Flutter/Generated.xcconfig", label="fresh Generated.xcconfig"
    )
    expected = f"FLUTTER_APPLICATION_PATH={app_root}"
    if expected not in encoded.decode("utf-8").splitlines():
        raise ValueError("APP.DEPENDENCY.generated_xcconfig_projection_mismatch")
    read_regular_nofollow(
        ios_root / "Flutter/Flutter.podspec", label="fresh Flutter.podspec"
    )
    project, _mode = read_regular_nofollow(
        ios_root / "Runner.xcodeproj/project.pbxproj", label="iOS project"
    )
    if b"FlutterGeneratedPluginSwiftPackage" in project or list(
        ios_root.rglob("FlutterGeneratedPluginSwiftPackage")
    ):
        raise ValueError("APP.DEPENDENCY.flutter_spm_residue_forbidden")
