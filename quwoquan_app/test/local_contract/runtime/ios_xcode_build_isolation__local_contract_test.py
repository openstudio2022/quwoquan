# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
#
# Xcode 中间产物按当前工作树隔离：raw `flutter run` / Xcode 直接构建与 canonical executor
# 必须落到同一组本树 build/ios 目录，不共用用户级 DerivedData（多 worktree 互相污染、
# 跨树 stale 警告）。

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
BASE_DIR = APP_DIR / "ios/Flutter/Base"
ISOLATION = BASE_DIR / "BuildIsolation.xcconfig"
EXECUTOR = APP_DIR / "scripts/device/run_app_instance.py"


def _executor_isolation_paths() -> dict[str, Path]:
    sys.path.insert(0, str(APP_DIR / "scripts/device"))
    spec = importlib.util.spec_from_file_location("qwq_test_run_app_instance", EXECUTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return dict(module.IOS_XCODE_BUILD_ISOLATION_RELATIVE_PATHS)


class IosXcodeBuildIsolationContractTest(unittest.TestCase):
    def test_every_base_configuration_includes_build_isolation(self) -> None:
        for name in ("Debug.xcconfig", "Profile.xcconfig", "Release.xcconfig"):
            source = (BASE_DIR / name).read_text(encoding="utf-8")
            self.assertIn('#include "BuildIsolation.xcconfig"', source, name)

    def test_isolation_settings_match_canonical_executor(self) -> None:
        source = ISOLATION.read_text(encoding="utf-8")
        settings = dict(re.findall(r"^([A-Z_]+) = \$\(SRCROOT\)/\.\./(\S+)$", source, flags=re.M))
        executor = _executor_isolation_paths()
        expected = {
            "OBJROOT": executor["FLUTTER_XCODE_OBJROOT"],
            "MODULE_CACHE_DIR": executor["FLUTTER_XCODE_MODULE_CACHE_DIR"],
            "SHARED_PRECOMPS_DIR": executor["FLUTTER_XCODE_SHARED_PRECOMPS_DIR"],
        }
        self.assertEqual({key: Path(value) for key, value in settings.items()}, expected)
        for value in settings.values():
            self.assertTrue(value.startswith("build/ios/"), value)


if __name__ == "__main__":
    unittest.main()
