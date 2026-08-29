"""Local contracts for the App payload actually exercised by Patrol."""

from __future__ import annotations

import copy
import hashlib
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    CANONICAL_COMPARISON_KEYS,
    TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
    _host_source_digest,
    artifact_payload_digest,
    build_tested_app_artifact_binding,
    collect_tested_app_artifact_binding,
    validate_tested_app_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    TestedAppArtifactBindingError as BindingError,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    tested_app_artifact_comparison as artifact_comparison,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    tested_app_build_artifact_path as build_artifact_path_for_test,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding_report import (
    new_tested_app_artifact_binding_set,
    settle_tested_app_artifact_binding_report,
)

APPLICATION_ID = "com.quwoquan.testhost.patrol"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _host_source() -> dict[str, object]:
    return {
        "root": "quwoquan_app/test_host/patrol",
        "rootIdentityDigest": "sha256:" + "c" * 64,
        "sourceDigest": "sha256:" + "d" * 64,
        "sourceFileCount": 9,
    }


def _valid_binding() -> dict[str, object]:
    return build_tested_app_artifact_binding(
        platform="android",
        device_id="emulator-5554",
        command_application_id=APPLICATION_ID,
        build_application_id=APPLICATION_ID,
        build_artifact_path=(
            "quwoquan_app/test_host/patrol/build/app/outputs/apk/debug/app-debug.apk"
        ),
        build_artifact_digest=DIGEST_A,
        installed_application_id=APPLICATION_ID,
        installed_artifact_digest=DIGEST_A,
        installed_readback_method="adb_pm_path_pull_base_apk",
        installed_locator_digest="sha256:" + "e" * 64,
        host_source=_host_source(),
    )


def _write_ios_app(path: Path, *, payload: bytes = b"same-payload") -> None:
    path.mkdir(parents=True)
    (path / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": APPLICATION_ID})
    )
    (path / "Runner").write_bytes(payload)


class EnvironmentPatrolArtifactBindingTest(unittest.TestCase):
    def test_build_paths_select_patrols_app_under_test_outputs(self) -> None:
        android = build_artifact_path_for_test(
            {"targetPlatform": "android-arm64", "emulator": True}
        )
        ios = build_artifact_path_for_test({"targetPlatform": "ios", "emulator": True})

        self.assertTrue(
            android.as_posix().endswith("build/app/outputs/apk/debug/app-debug.apk")
        )
        self.assertTrue(
            ios.as_posix().endswith(
                "build/ios_integ/Build/Products/debug-iphonesimulator/Runner.app"
            )
        )

    def test_host_source_digest_records_a_repo_contained_symlink_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root = Path(temporary).resolve()
            target = repo_root / "canonical"
            target.mkdir()
            (target / "test.dart").write_text("canonical", encoding="utf-8")
            source = repo_root / "host" / "main.dart"
            source.parent.mkdir()
            source.write_text("host", encoding="utf-8")
            link = source.parent / "canonical"
            link.symlink_to(Path("..") / "canonical", target_is_directory=True)

            digest, count = _host_source_digest(repo_root, (source, link))

        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(count, 2)

    def test_comparison_projection_has_six_deterministic_keys_without_proxy_identity(
        self,
    ) -> None:
        binding = _valid_binding()

        projection = artifact_comparison(binding)

        self.assertEqual(tuple(projection), CANONICAL_COMPARISON_KEYS)
        self.assertEqual(projection["applicationId"], APPLICATION_ID)
        self.assertEqual(projection["artifactDigest"], DIGEST_A)
        self.assertEqual(
            {field: projection[field] for field in CANONICAL_COMPARISON_KEYS[2:]},
            {
                "sourceProjectionDigest": "",
                "runtimeConfigPackageDigest": "",
                "trustDigest": "",
                "launchAttemptId": "",
            },
        )
        self.assertEqual(
            [item["field"] for item in binding["canonicalComparison"]["typedMissing"]],
            list(CANONICAL_COMPARISON_KEYS[2:]),
        )
        self.assertTrue(
            all(
                item["errorCode"] == APP_PAGE_ARTIFACT_BINDING_BLOCKER
                for item in binding["canonicalComparison"]["typedMissing"]
            )
        )
        self.assertEqual(
            binding["provenance"],
            TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
        )
        self.assertTrue(binding["nonPromotable"])

    def test_changed_package_id_cannot_produce_passed_binding(self) -> None:
        with self.assertRaises(BindingError) as raised:
            build_tested_app_artifact_binding(
                platform="android",
                device_id="emulator-5554",
                command_application_id="com.quwoquan.changed",
                build_application_id=APPLICATION_ID,
                build_artifact_path="app-debug.apk",
                build_artifact_digest=DIGEST_A,
                installed_application_id=APPLICATION_ID,
                installed_artifact_digest=DIGEST_A,
                installed_readback_method="adb_pm_path_pull_base_apk",
                installed_locator_digest=DIGEST_B,
                host_source=_host_source(),
            )

        self.assertEqual(raised.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertIn("identity mismatch", str(raised.exception))

    def test_changed_artifact_bytes_cannot_produce_passed_binding(self) -> None:
        with self.assertRaises(BindingError) as raised:
            build_tested_app_artifact_binding(
                platform="android",
                device_id="emulator-5554",
                command_application_id=APPLICATION_ID,
                build_application_id=APPLICATION_ID,
                build_artifact_path="app-debug.apk",
                build_artifact_digest=DIGEST_A,
                installed_application_id=APPLICATION_ID,
                installed_artifact_digest=DIGEST_B,
                installed_readback_method="adb_pm_path_pull_base_apk",
                installed_locator_digest=DIGEST_A,
                host_source=_host_source(),
            )

        self.assertEqual(raised.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertIn("bytes differ", str(raised.exception))

    def test_missing_installed_readback_cannot_produce_passed_binding(self) -> None:
        with self.assertRaises(BindingError) as raised:
            build_tested_app_artifact_binding(
                platform="ios",
                device_id="SIMULATOR-UDID",
                command_application_id=APPLICATION_ID,
                build_application_id=APPLICATION_ID,
                build_artifact_path="Runner.app",
                build_artifact_digest=DIGEST_A,
                installed_application_id="",
                installed_artifact_digest="",
                installed_readback_method="",
                installed_locator_digest="",
                host_source=_host_source(),
            )

        self.assertEqual(raised.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertIn("installed artifact application identity", str(raised.exception))

    def test_canonical_binding_values_cannot_be_copied_into_test_host_projection(
        self,
    ) -> None:
        binding = copy.deepcopy(_valid_binding())
        binding["canonicalComparison"]["runtimeConfigPackageDigest"] = DIGEST_B

        with self.assertRaisesRegex(
            BindingError,
            "copied a canonical identity",
        ):
            validate_tested_app_artifact_binding(binding)

    def test_android_collector_pulls_and_hashes_the_installed_base_apk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            build_apk = Path(temporary) / "app-debug.apk"
            build_bytes = b"actual-patrol-host-apk"
            build_apk.write_bytes(build_bytes)
            installed_path = "/data/app/test/base.apk"

            def run(
                command: list[str], **_kwargs: Any
            ) -> subprocess.CompletedProcess[Any]:
                if command[0] == "/sdk/aapt":
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        f"package: name='{APPLICATION_ID}' versionCode='1'\n",
                        "",
                    )
                if command[-4:-1] == ["shell", "pm", "path"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        f"package:{installed_path}\n",
                        "",
                    )
                if "pull" in command:
                    Path(command[-1]).write_bytes(build_bytes)
                    return subprocess.CompletedProcess(
                        command, 0, "1 file pulled\n", ""
                    )
                self.fail(f"unexpected command: {command}")

            binding = collect_tested_app_artifact_binding(
                device={
                    "id": "emulator-5554",
                    "targetPlatform": "android-arm64",
                    "emulator": True,
                },
                patrol_command=[
                    "patrol",
                    "test",
                    f"--package-name={APPLICATION_ID}",
                ],
                command_env={"PATH": "/sdk"},
                artifact_path=build_apk,
                host_source=_host_source(),
                run=run,
                android_adb="/sdk/adb",
                android_aapt="/sdk/aapt",
            )

        expected_digest = "sha256:" + hashlib.sha256(build_bytes).hexdigest()
        self.assertEqual(binding["buildArtifact"]["artifactDigest"], expected_digest)
        self.assertEqual(
            binding["installedArtifactReadback"]["artifactDigest"],
            expected_digest,
        )
        self.assertEqual(
            binding["installedArtifactReadback"]["method"],
            "adb_pm_path_pull_base_apk",
        )

    def test_ios_collector_hashes_the_installed_app_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_app = root / "build" / "Runner.app"
            installed_app = root / "installed" / "Runner.app"
            _write_ios_app(build_app)
            shutil.copytree(build_app, installed_app)

            def run(
                command: list[str], **_kwargs: Any
            ) -> subprocess.CompletedProcess[Any]:
                self.assertEqual(command[0:3], ["xcrun", "simctl", "get_app_container"])
                return subprocess.CompletedProcess(
                    command, 0, str(installed_app) + "\n", ""
                )

            binding = collect_tested_app_artifact_binding(
                device={
                    "id": "SIMULATOR-UDID",
                    "targetPlatform": "ios",
                    "emulator": True,
                },
                patrol_command=[
                    "patrol",
                    "test",
                    f"--bundle-id={APPLICATION_ID}",
                ],
                command_env={"PATH": "/usr/bin"},
                artifact_path=build_app,
                host_source=_host_source(),
                run=run,
            )

            self.assertEqual(
                binding["buildArtifact"]["artifactDigest"],
                artifact_payload_digest(build_app, "ios"),
            )
            self.assertEqual(
                binding["installedArtifactReadback"]["method"],
                "simctl_get_app_container_app_tree",
            )
            self.assertEqual(
                binding["applicationIdentity"]["bundleId"],
                APPLICATION_ID,
            )

    def test_ios_installed_tree_byte_drift_is_typed_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_app = root / "build" / "Runner.app"
            installed_app = root / "installed" / "Runner.app"
            _write_ios_app(build_app, payload=b"build")
            _write_ios_app(installed_app, payload=b"installed-drift")

            def run(
                command: list[str], **_kwargs: Any
            ) -> subprocess.CompletedProcess[Any]:
                return subprocess.CompletedProcess(
                    command, 0, str(installed_app) + "\n", ""
                )

            with self.assertRaises(BindingError) as raised:
                collect_tested_app_artifact_binding(
                    device={
                        "id": "SIMULATOR-UDID",
                        "targetPlatform": "ios",
                        "emulator": True,
                    },
                    patrol_command=[f"--bundle-id={APPLICATION_ID}"],
                    command_env={"PATH": "/usr/bin"},
                    artifact_path=build_app,
                    host_source=_host_source(),
                    run=run,
                )

        self.assertEqual(raised.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertIn("bytes differ", str(raised.exception))

    def test_missing_ios_installed_container_is_typed_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            build_app = Path(temporary) / "Runner.app"
            _write_ios_app(build_app)

            def run(
                command: list[str], **_kwargs: Any
            ) -> subprocess.CompletedProcess[Any]:
                return subprocess.CompletedProcess(command, 1, "", "not installed")

            with self.assertRaises(BindingError) as raised:
                collect_tested_app_artifact_binding(
                    device={
                        "id": "SIMULATOR-UDID",
                        "targetPlatform": "ios",
                        "emulator": True,
                    },
                    patrol_command=[f"--bundle-id={APPLICATION_ID}"],
                    command_env={"PATH": "/usr/bin"},
                    artifact_path=build_app,
                    host_source=_host_source(),
                    run=run,
                )

        self.assertEqual(raised.exception.code, APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertIn("container readback is unavailable", str(raised.exception))

    def test_report_without_a_device_binding_cannot_remain_passed(self) -> None:
        report = {
            "status": "passed",
            "devices": [
                {
                    "id": "SIMULATOR-UDID",
                    "targetPlatform": "ios",
                    "emulator": True,
                }
            ],
            "testedAppArtifactBinding": new_tested_app_artifact_binding_set(),
        }

        settle_tested_app_artifact_binding_report(report)

        self.assertEqual(report["status"], "gate_block")
        collection = report["testedAppArtifactBinding"]
        self.assertEqual(collection["status"], "gate_block")
        self.assertEqual(collection["errorCode"], APP_PAGE_ARTIFACT_BINDING_BLOCKER)
        self.assertEqual(collection["bindings"][0]["status"], "gate_block")
        self.assertEqual(
            collection["bindings"][0]["installedArtifactReadback"],
            {"status": "missing"},
        )


if __name__ == "__main__":
    unittest.main()
