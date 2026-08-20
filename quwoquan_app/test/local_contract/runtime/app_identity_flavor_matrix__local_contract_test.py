# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
MODES = ("Debug", "Profile", "Release")


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
        self.assertNotIn("defaultConfigurationName = Release;", project)
        self.assertEqual(
            project.count('defaultConfigurationName = "Release-alpha";'),
            3,
        )
        self.assertFalse(
            (APP / "ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme").exists()
        )
        for environment in ENVIRONMENTS:
            scheme = (
                APP
                / f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{environment}.xcscheme"
            ).read_text(encoding="utf-8")
            self.assertIn(f'buildConfiguration = "Debug-{environment}"', scheme)
            self.assertIn(f'buildConfiguration = "Profile-{environment}"', scheme)
            self.assertIn(f'buildConfiguration = "Release-{environment}"', scheme)
            for mode in MODES:
                configuration = f"{mode}-{environment}"
                self.assertGreaterEqual(project.count(f"/* {configuration} */"), 4)
                self.assertIn(f"'{configuration}' =>", podfile)
                wrapper = APP / f"ios/Flutter/{configuration}.xcconfig"
                self.assertTrue(wrapper.is_file(), wrapper)

    def test_all_iOS_build_settings_match_generated_identity(self) -> None:
        for environment in ENVIRONMENTS:
            for mode in MODES:
                with self.subTest(environment=environment, mode=mode):
                    result = subprocess.run(
                        [
                            "xcodebuild",
                            "-project",
                            "ios/Runner.xcodeproj",
                            "-scheme",
                            environment,
                            "-configuration",
                            f"{mode}-{environment}",
                            "-showBuildSettings",
                        ],
                        cwd=APP,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    values: dict[str, str] = {}
                    for line in result.stdout.splitlines():
                        normalized = line.strip()
                        if " = " not in normalized:
                            continue
                        key, value = normalized.split(" = ", 1)
                        values[key] = value
                    identity = self.generated["identities"]["ios"][
                        f"{environment}/{mode.lower()}"
                    ]
                    self.assertEqual(
                        values.get("PRODUCT_BUNDLE_IDENTIFIER"),
                        identity["applicationId"],
                    )
                    self.assertEqual(
                        values.get("QWQ_APP_DISPLAY_NAME"),
                        identity["displayName"],
                    )
                    self.assertEqual(values.get("QWQ_APP_RUNTIME_ENV"), environment)
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
                            f"Runner {mode}-{environment} links {forbidden}",
                        )

    def test_iOS_base_configs_never_include_generic_pods_graph(self) -> None:
        for mode in MODES:
            base = (APP / f"ios/Flutter/Base/{mode}.xcconfig").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                f"Pods-Runner.{mode.lower()}.xcconfig",
                base,
                f"Runner {mode} must select Pods only through an environment wrapper",
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
                env={"PYTHONPYCACHEPREFIX": temporary_directory},
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((APP / "ios/Flutter/QWQEnvironment.xcconfig").exists())

    def test_identity_state_gate_rejects_shared_state_and_unflavored_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            fixture_app = fixture_root / "quwoquan_app"
            sources = {
                "run.sh": 'flutter run --flavor "$QWQ_APP_RUNTIME_ENV"\n',
                "scripts/device/run_app_instance.sh": 'command = ["--flavor", environment]\n',
                "scripts/device/verify_ios_hot_restart.py": "",
                "scripts/device/build_startup_environment_matrix.py": "",
                "scripts/ios/build_prepare_dart_defines.sh": "",
                "pubspec.yaml": "flutter:\n  default-flavor: beta\n",
                "android/app/app_identity.generated.json": json.dumps(
                    {"environments": ["alpha", "beta", "gamma", "prod"]}
                ),
                "ios/Flutter/QWQEnvironment.xcconfig": "QWQ_APP_RUNTIME_ENV = beta\n",
                "ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme": "<Scheme/>\n",
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
                    str(fixture_root),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={"PYTHONPYCACHEPREFIX": str(fixture_root / "cache")},
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("shared mutable App identity state must not exist", result.stdout)
        self.assertIn("unflavored shared Runner scheme", result.stdout)
        self.assertIn("default flavor", result.stdout)


if __name__ == "__main__":
    unittest.main()
