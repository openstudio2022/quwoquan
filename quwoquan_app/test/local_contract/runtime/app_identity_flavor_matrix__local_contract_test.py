# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
BUILD_PROFILES = ("nonprod", "prod")
DEVELOPMENT_ENVIRONMENTS = ("alpha", "beta", "gamma")
IOS_CONFIGURATIONS = tuple(
    (mode, environment)
    for environment in DEVELOPMENT_ENVIRONMENTS
    for mode in ("Debug", "Profile")
) + (("Release", "nonprod"), ("Release", "prod"))
# xcodebuild 只在装了 Xcode 的 macOS 上存在，Linux 门禁机上根本不可能有。
# 缺席不是身份漂移，只是这台机器判不了 iOS 构建设置；装了就必须判，
# 且判不过要红——所以只在可执行文件缺席时跳过，不吞任何失败。
XCODEBUILD = shutil.which("xcodebuild")


class AppIdentityFlavorMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generated = json.loads(
            (APP / "android/app/app_identity.generated.json").read_text(
                encoding="utf-8"
            )
        )

    def test_iOS_configuration_scheme_and_podfile_matrix_is_complete(self) -> None:
        project = (APP / "ios/Runner.xcodeproj/project.pbxproj").read_text(
            encoding="utf-8"
        )
        podfile = (APP / "ios/Podfile").read_text(encoding="utf-8")
        schemes = APP / "ios/Runner.xcodeproj/xcshareddata/xcschemes"
        self.assertNotIn("Debug-prod", project)
        self.assertNotIn("Profile-prod", project)
        self.assertFalse((APP / "ios/Flutter/Debug-prod.xcconfig").exists())
        self.assertFalse((APP / "ios/Flutter/Profile-prod.xcconfig").exists())
        for mode, target in IOS_CONFIGURATIONS:
            configuration = f"{mode}-{target}"
            self.assertIn(f"'{configuration}' =>", podfile)
            self.assertTrue((APP / f"ios/Flutter/{configuration}.xcconfig").is_file())
            if target in ("alpha", "nonprod", "prod"):
                self.assertGreaterEqual(project.count(f"/* {configuration} */"), 4)
            self.assertTrue((schemes / f"{target}.xcscheme").is_file())
        for environment in DEVELOPMENT_ENVIRONMENTS:
            scheme = (schemes / f"{environment}.xcscheme").read_text(encoding="utf-8")
            self.assertIn(f'buildConfiguration = "Debug-{environment}"', scheme)
            self.assertIn(f'buildConfiguration = "Profile-{environment}"', scheme)
            self.assertIn('buildForArchiving = "NO"', scheme)
        prod_scheme = (schemes / "prod.xcscheme").read_text(encoding="utf-8")
        self.assertIn('buildConfiguration = "Release-prod"', prod_scheme)
        self.assertIn('buildForRunning = "NO"', prod_scheme)
        self.assertIn('buildForProfiling = "NO"', prod_scheme)

    @unittest.skipUnless(XCODEBUILD, "xcodebuild 不在本机 PATH 上")
    def test_all_iOS_build_settings_match_generated_identity(self) -> None:
        for mode, build_profile in IOS_CONFIGURATIONS:
            if build_profile in ("beta", "gamma"):
                continue
            with self.subTest(build_profile=build_profile, mode=mode):
                result = subprocess.run(
                    [
                        "xcodebuild",
                        "-project",
                        "ios/Runner.xcodeproj",
                        "-scheme",
                        build_profile,
                        "-configuration",
                        f"{mode}-{build_profile}",
                        "-showBuildSettings",
                        "-json",
                    ],
                    cwd=APP,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                build_settings = json.loads(result.stdout)
                self.assertEqual(len(build_settings), 1, build_settings)
                values = build_settings[0]["buildSettings"]
                identity_key = (
                    f"{build_profile}/release"
                    if mode == "Release"
                    else f"{build_profile}/{mode.lower()}"
                )
                identity = self.generated["identities"]["ios"][identity_key]
                self.assertEqual(
                    values.get("PRODUCT_BUNDLE_IDENTIFIER"),
                    identity["applicationId"],
                )
                self.assertEqual(
                    values.get("QWQ_APP_DISPLAY_NAME"),
                    identity["displayName"],
                )
                self.assertEqual(values.get("QWQ_APP_BUILD_PROFILE"), identity["buildProfile"])
                self.assertEqual(values.get("QWQ_APP_RUNTIME_ENV", ""), identity.get("environment", ""))
                effective_link_settings = " ".join(
                    values.get(key, "")
                    for key in (
                        "FRAMEWORK_SEARCH_PATHS",
                        "OTHER_LDFLAGS",
                        "OTHER_MODULE_VERIFIER_FLAGS",
                    )
                ).lower()
                for forbidden in (
                    "cocoaasyncsocket",
                    "integration_test",
                    "patrol",
                    "xctest",
                ):
                    self.assertNotIn(
                        forbidden,
                        effective_link_settings,
                        f"Runner {mode}-{build_profile} links {forbidden}",
                    )

    def test_android_build_graph_uses_only_buildProfile_flavors(self) -> None:
        gradle = (APP / "android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        self.assertIn('flavorDimensions += "identityTarget"', gradle)
        self.assertIn("generatedAndroidIdentityTargets.forEach", gradle)
        self.assertIn('!taskName.contains("nonprod")', gradle)
        self.assertNotIn(
            ".filter { buildProfile -> task.contains(buildProfile, ignoreCase = true) }",
            gradle,
        )
        self.assertIn("applicationId = identity.applicationId", gradle)
        self.assertIn("manifestPlaceholders[\"qwqAppLabel\"] = identity.displayName", gradle)
        self.assertIn("androidComponents", gradle)
        self.assertIn("identity.buildMode != variantBuilder.buildType", gradle)
        self.assertIn("identity.buildMode != variantBuilder.buildType", gradle)
        self.assertIn("variantBuilder.enable = false", gradle)
        for retired_field in (
            "QWQ_RUNTIME_ENVIRONMENT",
            "QWQ_RUNTIME_CONFIG_DIGEST",
            "QWQ_DART_DEFINES_DIGEST",
        ):
            self.assertNotIn(retired_field, gradle)
        self.assertIn("nativeRuntimeDefineKeys", gradle)
        self.assertIn("forbiddenRuntimeDartDefineKeys", gradle)
        self.assertIn("generatedIdentityEnvironments", gradle)
        for environment in DEVELOPMENT_ENVIRONMENTS:
            self.assertIn(f"{environment}/debug", self.generated["identityTargets"])
            self.assertIn(f"{environment}/profile", self.generated["identityTargets"])

    def test_android_build_graph_rejects_runtime_environment_defines(self) -> None:
        gradle = (APP / "android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        self.assertIn("Android compilation must not consume runtime environment", gradle)
        self.assertIn("forbiddenRuntimeDartDefineKeys", gradle)
        self.assertIn("forbiddenKeys.isEmpty()", gradle)

    def test_iOS_base_configs_never_include_generic_pods_graph(self) -> None:
        for mode in ("Debug", "Profile", "Release"):
            base = (APP / f"ios/Flutter/Base/{mode}.xcconfig").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                f"Pods-Runner.{mode.lower()}.xcconfig",
                base,
                f"Runner {mode} must select Pods only through a buildProfile wrapper",
            )

    def test_build_does_not_create_mutable_identity_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [
                    "python3",
                    str(
                        APP
                        / "scripts/runtime/platform/verify_app_identity_state_isolation.py"
                    ),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((APP / "ios/Flutter/QWQEnvironment.xcconfig").exists())
            self.assertFalse((APP / "scripts/ios/write_environment_xcconfig.sh").exists())
            self.assertFalse((Path(temporary_directory) / "QWQEnvironment.xcconfig").exists())

    def test_identity_state_gate_rejects_shared_state_and_unflavored_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_app = root / "quwoquan_app"
            sources = {
                "run.sh": 'flutter run --target "lib/main_alpha.dart"\n',
                "pubspec.yaml": "name: quwoquan_app\n",
                "android/app/build.gradle.kts": 'create("alpha")\n',
                "android/app/app_identity.generated.json": json.dumps(
                    {
                        "buildProfiles": [],
                        "environmentProfiles": {},
                        "identities": {"android": {}, "ios": {}},
                    }
                ),
                "ios/Flutter/QWQEnvironment.xcconfig": "QWQ_APP_RUNTIME_ENV = beta\n",
                "ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme": "<Scheme/>\n",
                "ios/Runner.xcodeproj/xcshareddata/xcschemes/alpha.xcscheme": "<Scheme/>\n",
            }
            for relative_path, content in sources.items():
                path = fixture_app / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(
                        APP
                        / "scripts/runtime/platform/verify_app_identity_state_isolation.py"
                    ),
                    "--repo-root",
                    str(root),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("shared mutable App identity state must not exist", result.stdout)
            self.assertIn("canonical development environment scheme is missing", result.stdout)
            # buildProfile 选择权归 canonical executor：launcher 既不得自持第二处选择，
            # 也不得把它下放给环境变量。
            self.assertIn(
                "run.sh must delegate buildProfile selection to canonical executor",
                result.stdout,
            )
            self.assertIn(
                "run.sh must not own a second Flutter buildProfile selection",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
