# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-002
#
# 构建期默认供给（embedded_default_package / native_flutter_run）退役负例：
# 无 canonical handoff 的构建不得物化任何默认 trust/package，raw SDK 绝对路径
# 旁路在既有 trust gate 以 APP.LAUNCH.runtime_config_trust_missing fail-closed。

from __future__ import annotations

import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
RETIRED_SCRIPT = APP_DIR / "scripts/device/build_default_debug_supply.py"
ANDROID_TRUST_GATE = APP_DIR / "android/gradle/runtime-config-assets.gradle.kts"
IOS_PREPARE_SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
IOS_EMBED_SCRIPT = APP_DIR / "scripts/ios/build_embed_runtime_config_trust.py"
IOS_APP_DELEGATE = APP_DIR / "ios/Runner/AppDelegate.swift"
IOS_RUNTIME_CONFIG_SUPPLY = APP_DIR / "ios/Runner/NativeRuntimeConfigSupply.swift"
ANDROID_STARTUP_GATE = (
    APP_DIR / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupGateActivity.java"
)
ANDROID_SHARED_JAVA_ROOT = (
    APP_DIR / "android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app"
)


class DefaultDebugSupplyRetirementContractTest(unittest.TestCase):
    """默认供给旁路必须物理退役，缺 canonical supply 一律 typed fail-closed。"""

    def test_shared_default_supply_script_is_deleted(self) -> None:
        self.assertFalse(RETIRED_SCRIPT.exists())

    def test_android_trust_gate_has_no_default_supply_branch(self) -> None:
        source = ANDROID_TRUST_GATE.read_text(encoding="utf-8")
        for retired in (
            "materializeDefaultDebugSupply",
            "validateDefaultSupplyMaterial",
            "defaultDebugSupplyRoot",
            "defaultSupplyMode",
            "isDebugArtifactTask",
            "build_default_debug_supply.py",
            "runtime-config-default-package.json",
            "runtime-config-default-manifest.json",
        ):
            self.assertNotIn(retired, source)
        # 缺 handoff 即 fail-closed：asset root 缺席只剩 typed reject，
        # trust gate 码与 canonical launcher 指引仍在。
        self.assertIn("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT is absent", source)
        self.assertIn(".runtime_config_trust_missing", source)
        self.assertIn("./quwoquan_app/run.sh -d <device>", source)

    def test_android_native_gate_has_no_embedded_default_consumption(self) -> None:
        sources = [ANDROID_STARTUP_GATE.read_text(encoding="utf-8")]
        for java_file in sorted(ANDROID_SHARED_JAVA_ROOT.glob("*.java")):
            sources.append(java_file.read_text(encoding="utf-8"))
        combined = "\n".join(sources)
        for retired in (
            "consumeEmbeddedDefaultSupply",
            "EmbeddedDefaultSupplySource",
            "DEFAULT_PACKAGE_ASSET_NAME",
            "DEFAULT_MANIFEST_ASSET_NAME",
            "createEmbeddedDefaultSupplySource",
            "android_runtime_config_embedded_default_activated",
        ):
            self.assertNotIn(retired, combined)

    def test_ios_prepare_script_fails_closed_without_external_trust(self) -> None:
        source = IOS_PREPARE_SCRIPT.read_text(encoding="utf-8")
        for retired in (
            "build_default_debug_supply.py",
            "RUNTIME_CONFIG_SUPPLY_KIND",
            "DEFAULT_SUPPLY",
            "runtime-config-default-package.json",
            "runtime-config-default-manifest.json",
        ):
            self.assertNotIn(retired, source)
        # trust 缺席对一切 configuration 都是同一 typed blocker。
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", source)
        self.assertIn(
            "build-profile runtime trust envelope is required", source
        )
        self.assertIn("./quwoquan_app/run.sh -d <device>", source)

    def test_ios_embed_script_only_embeds_trust_and_purges_retired_material(self) -> None:
        source = IOS_EMBED_SCRIPT.read_text(encoding="utf-8")
        # 退役说明性注释允许提及枚举名；这里只判否功能分支的结构性标识。
        for retired in (
            "_verified_default_supply",
            "--default-package",
            "--default-manifest",
            "native_flutter_run",
            "_DEFAULT_SUPPLY_BUILD_PROFILE",
        ):
            self.assertNotIn(retired, source)
        # 增量构建残留的退役默认供给材料必须在装配期清除。
        self.assertIn("_RETIRED_DEFAULT_PACKAGE_FILE_NAME", source)
        self.assertIn("_RETIRED_DEFAULT_MANIFEST_FILE_NAME", source)
        self.assertIn('_remove_if_present(resource_root / "runtime-config-package.json")', source)

    def test_ios_native_gate_has_no_embedded_default_consumption(self) -> None:
        combined = IOS_APP_DELEGATE.read_text(
            encoding="utf-8"
        ) + IOS_RUNTIME_CONFIG_SUPPLY.read_text(encoding="utf-8")
        for retired in (
            "consumeEmbeddedDefaultSupply",
            "nativeRuntimeDefaultPackageFileName",
            "nativeRuntimeDefaultManifestFileName",
            "runtime-config-default-package.json",
            "runtime-config-default-manifest.json",
            "ios_runtime_config_embedded_default_activated",
            "ios_embedded_default_skipped",
        ):
            self.assertNotIn(retired, combined)


if __name__ == "__main__":
    unittest.main()
