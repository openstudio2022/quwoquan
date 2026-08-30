"""Android 安装下限跟随 Flutter SDK，且对应系统须满五年。

spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-003
spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-003.t1
spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-003.t2
"""

from __future__ import annotations

import os
import re
import shutil
import unittest
from datetime import date
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[4]
GRADLE = APP_DIR / "android" / "app" / "build.gradle.kts"
FIVE_YEARS = 5

# Android 各 API 首次稳定发布日。未知 API 必须 fail-closed，不得猜测。
ANDROID_API_STABLE_RELEASE = {
    24: date(2016, 8, 22),
    25: date(2016, 10, 4),
    26: date(2017, 8, 21),
    27: date(2017, 12, 5),
    28: date(2018, 8, 6),
    29: date(2019, 9, 3),
    30: date(2020, 9, 8),
    31: date(2021, 10, 4),
    32: date(2022, 3, 7),
    33: date(2022, 8, 15),
    34: date(2023, 10, 4),
    35: date(2024, 10, 15),
    36: date(2025, 6, 10),
}


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _resolve_flutter_root() -> Path:
    env = os.environ.get("FLUTTER_ROOT", "").strip()
    if env:
        return Path(env)
    local_props = APP_DIR / "android" / "local.properties"
    if local_props.is_file():
        for line in local_props.read_text(encoding="utf-8").splitlines():
            if line.startswith("flutter.sdk="):
                return Path(line.split("=", 1)[1].strip())
    generated = APP_DIR / "ios" / "Flutter" / "Generated.xcconfig"
    if generated.is_file():
        for line in generated.read_text(encoding="utf-8").splitlines():
            if line.startswith("FLUTTER_ROOT="):
                return Path(line.split("=", 1)[1].strip())
    flutter_bin = shutil.which("flutter")
    if flutter_bin is not None:
        root = Path(flutter_bin).resolve().parent.parent
        if (root / "packages" / "flutter_tools").is_dir():
            return root
    raise AssertionError("FLUTTER_ROOT is unavailable")


def _read_flutter_min_sdk(flutter_root: Path) -> int:
    extension = (
        flutter_root
        / "packages"
        / "flutter_tools"
        / "gradle"
        / "src"
        / "main"
        / "kotlin"
        / "FlutterExtension.kt"
    )
    utils = (
        flutter_root
        / "packages"
        / "flutter_tools"
        / "lib"
        / "src"
        / "android"
        / "gradle_utils.dart"
    )
    extension_match = re.search(
        r"val minSdkVersion:\s*Int\s*=\s*(\d+)",
        extension.read_text(encoding="utf-8"),
    )
    utils_match = re.search(
        r"const minSdkVersionInt\s*=\s*(\d+);",
        utils.read_text(encoding="utf-8"),
    )
    if extension_match is None or utils_match is None:
        raise AssertionError("Flutter SDK minSdkVersion declaration is missing")
    extension_value = int(extension_match.group(1))
    utils_value = int(utils_match.group(1))
    if extension_value != utils_value:
        raise AssertionError(
            f"Flutter minSdkVersion mismatch: extension={extension_value} "
            f"utils={utils_value}",
        )
    return extension_value


class AndroidMinimumOsContractTest(unittest.TestCase):
    def test_app_min_sdk_follows_flutter_sdk(self) -> None:
        text = GRADLE.read_text(encoding="utf-8")
        assignments = re.findall(r"^\s*minSdk\s*=\s*(.+?)\s*$", text, re.MULTILINE)
        self.assertEqual(assignments, ["flutter.minSdkVersion"])

    def test_flutter_min_sdk_os_is_at_least_five_years_old(self) -> None:
        api = _read_flutter_min_sdk(_resolve_flutter_root())
        released = ANDROID_API_STABLE_RELEASE.get(api)
        self.assertIsNotNone(
            released,
            f"Android API {api} has no recorded stable release date",
        )
        self.assertLessEqual(
            _add_years(released, FIVE_YEARS),
            date.today(),
            f"Flutter minSdk API {api} released {released} is not yet {FIVE_YEARS} years old",
        )
