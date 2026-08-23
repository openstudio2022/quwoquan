# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
BUILD_PROFILES = ("nonprod", "prod")
RETIRED_ENVIRONMENT_FLAVORS = ("alpha", "beta", "gamma")
IOS_CONFIGURATIONS = (
    ("Debug", "nonprod"),
    ("Profile", "nonprod"),
    ("Release", "nonprod"),
    ("Release", "prod"),
)


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
        self.assertNotIn("defaultConfigurationName = Release;", project)
        self.assertEqual(
            project.count('defaultConfigurationName = "Release-nonprod";'),
            3,
        )
        self.assertFalse((schemes / "Runner.xcscheme").exists())
        for environment in RETIRED_ENVIRONMENT_FLAVORS:
            self.assertFalse((schemes / f"{environment}.xcscheme").exists())
            self.assertNotIn(f"-{environment}", project)
            self.assertNotIn(f"-{environment}", podfile)
        nonprod_scheme = (schemes / "nonprod.xcscheme").read_text(encoding="utf-8")
        prod_scheme = (schemes / "prod.xcscheme").read_text(encoding="utf-8")
        for configuration in ("Debug-nonprod", "Profile-nonprod", "Release-nonprod"):
            self.assertIn(f'buildConfiguration = "{configuration}"', nonprod_scheme)
        self.assertIn('buildConfiguration = "Release-prod"', prod_scheme)
        self.assertIn('buildConfiguration = "Debug-nonprod"', prod_scheme)
        self.assertIn('buildConfiguration = "Profile-nonprod"', prod_scheme)
        self.assertIn('buildForRunning = "NO"', prod_scheme)
        self.assertIn('buildForProfiling = "NO"', prod_scheme)
        self.assertIn('buildForArchiving = "YES"', prod_scheme)
        # prod 只保留可归档的 Release 配置：Debug/Profile-prod 已从 project、Podfile
        # 与 prod scheme 三处退役，因此没有任何构建入口能选中它们。
        # xcconfig 物化面仍由 app identity codegen 产出无人引用的两份文件，
        # 收口由 environment-topology-and-packaging 的 OPEN-006 承接。
        for retired in ("Debug-prod", "Profile-prod"):
            self.assertNotIn(retired, project)
            self.assertNotIn(retired, podfile)
            self.assertNotIn(retired, prod_scheme)
        for mode, build_profile in IOS_CONFIGURATIONS:
            configuration = f"{mode}-{build_profile}"
            self.assertGreaterEqual(project.count(f"/* {configuration} */"), 4)
            self.assertIn(f"'{configuration}' =>", podfile)
            wrapper = APP / f"ios/Flutter/{configuration}.xcconfig"
            self.assertTrue(wrapper.is_file(), wrapper)

    def test_all_iOS_build_settings_match_generated_identity(self) -> None:
        for mode, build_profile in IOS_CONFIGURATIONS:
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
                identity = self.generated["identities"]["ios"][
                    f"{build_profile}/{mode.lower()}"
                ]
                self.assertEqual(
                    values.get("PRODUCT_BUNDLE_IDENTIFIER"),
                    identity["applicationId"],
                )
                self.assertEqual(
                    values.get("QWQ_APP_DISPLAY_NAME"),
                    identity["displayName"],
                )
                self.assertEqual(values.get("QWQ_APP_BUILD_PROFILE"), build_profile)
                self.assertIsNone(values.get("QWQ_APP_RUNTIME_ENV"))
                self.assertEqual(values.get("FLUTTER_TARGET"), "lib/main_prod.dart")
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
        self.assertIn('flavorDimensions += "buildProfile"', gradle)
        self.assertIn("generatedIdentityBuildProfiles.forEach", gradle)
        self.assertIn('!taskName.contains("nonprod")', gradle)
        self.assertNotIn(
            ".filter { buildProfile -> task.contains(buildProfile, ignoreCase = true) }",
            gradle,
        )
        self.assertIn("generatedModeApplicationIdSuffix", gradle)
        self.assertIn(
            'applicationIdSuffix = generatedModeApplicationIdSuffix("nonprod", "debug")',
            gradle,
        )
        self.assertIn(
            'applicationIdSuffix = generatedModeApplicationIdSuffix("nonprod", "profile")',
            gradle,
        )
        self.assertIn("androidComponents", gradle)
        self.assertIn('variantBuilder.buildType in setOf("debug", "profile")', gradle)
        self.assertIn('buildProfile != "nonprod"', gradle)
        self.assertIn("variantBuilder.enable = false", gradle)
        self.assertIn("generatedModeDisplayMark", gradle)
        for retired_field in (
            "QWQ_RUNTIME_ENVIRONMENT",
            "QWQ_RUNTIME_CONFIG_DIGEST",
            "QWQ_DART_DEFINES_DIGEST",
        ):
            self.assertNotIn(retired_field, gradle)
        self.assertIn("nativeRuntimeDefineKeys", gradle)
        self.assertIn("forbiddenRuntimeDartDefineKeys", gradle)
        self.assertNotIn("generatedIdentityEnvironments.forEach", gradle)
        for environment in RETIRED_ENVIRONMENT_FLAVORS:
            self.assertNotIn(f'create("{environment}")', gradle)

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
            self.assertIn("retired environment scheme must not exist", result.stdout)
            self.assertIn("deterministic default flavor", result.stdout)
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
