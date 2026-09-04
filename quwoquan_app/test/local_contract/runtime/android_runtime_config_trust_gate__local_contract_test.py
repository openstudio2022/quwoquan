"""Behavior contract for the shared Android AppArtifact trust gate.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
GRADLEW = APP_DIR / "android/gradlew"
TRUST_GATE = APP_DIR / "android/gradle/runtime-config-assets.gradle.kts"
GENERATED_CONTRACT = (
    APP_DIR / "tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)
SHARED_JAVA_ROOT = (
    APP_DIR
    / "android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app"
)
PATROL_KOTLIN_ROOT = APP_DIR / "test_host/patrol/android/app/src/main/kotlin"
RUNTIME_CONFIG_JAVA_TEST = (
    APP_DIR
    / "android/app/src/test/java/com/quwoquan/quwoquan_app/RuntimeConfigPackageStoreTest.java"
)
MAIN_ACTIVITY = (
    APP_DIR
    / "android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
)


class AndroidRuntimeConfigTrustGateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="qwq-android-trust-gate-")
        self.root = Path(self.temp_dir.name)
        self.gradle_project = self.root / "gradle-project"
        self.gradle_project.mkdir()
        build_script = f"""
extra["qwq.repositoryRoot"] = {json.dumps(str(REPO_ROOT))}
apply(from = file({json.dumps(str(TRUST_GATE))}))

tasks.register("packageArtifact")
tasks.register("testDebugUnitTest")
tasks.register("assembleNonprodDebug")
tasks.register("assembleNonprodRelease")
tasks.register("assembleNonprodProfile")
"""
        (self.gradle_project / "settings.gradle.kts").write_text(
            'rootProject.name = "runtime-config-trust-gate-contract"\n',
            encoding="utf-8",
        )
        (self.gradle_project / "build.gradle.kts").write_text(
            build_script,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(
        self,
        task: str,
        *,
        trust_root: Path | None = None,
        extra_environment: dict[str, str] | None = None,
        extra_arguments: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", None)
        environment.pop("QWQ_APP_BUILD_PROFILE", None)
        if trust_root is not None:
            environment["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"] = str(trust_root)
            environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [
                str(GRADLEW),
                "--no-daemon",
                "--offline",
                "-p",
                str(self.gradle_project),
                *extra_arguments,
                task,
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=180,
        )

    def _valid_trust_root(self) -> Path:
        generated = json.loads(GENERATED_CONTRACT.read_text(encoding="utf-8"))
        launch_manifest = generated["appLaunchManifest"]
        schema = launch_manifest["schemas"]["runtime_config_trust_envelope"]
        fields = schema["fields"]
        trust = {
            "schema": schema["schema_value"],
            "buildProfile": "nonprod",
            "signatureAlgorithm": fields["signatureAlgorithm"]["const"],
            "trustedPublicKeys": {
                "local-contract": base64.b64encode(bytes(range(32))).decode("ascii")
            },
        }
        self.assertEqual(set(trust), set(schema["required_fields"]))
        trust_root = self.root / "trust-assets"
        runtime_root = trust_root / "qwq_runtime"
        runtime_root.mkdir(parents=True)
        (runtime_root / "runtime-config-trust.json").write_text(
            json.dumps(trust, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return trust_root

    def _replace_trusted_public_keys(
        self, trust_root: Path, keyring: dict[str, object]
    ) -> None:
        trust_file = trust_root / "qwq_runtime/runtime-config-trust.json"
        trust = json.loads(trust_file.read_text(encoding="utf-8"))
        trust["trustedPublicKeys"] = keyring
        trust_file.write_text(
            json.dumps(trust, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def _gradle_user_home(self) -> Path:
        configured = os.environ.get("GRADLE_USER_HOME", "").strip()
        return Path(configured).expanduser() if configured else Path.home() / ".gradle"

    def _android_sdk_root(self) -> Path:
        configured = (
            os.environ.get("ANDROID_SDK_ROOT", "").strip()
            or os.environ.get("ANDROID_HOME", "").strip()
        )
        if configured:
            return Path(configured).expanduser()
        return Path.home() / "Library/Android/sdk"

    def _single_cached_jar(self, pattern: str) -> Path:
        cache_root = self._gradle_user_home()
        matches = sorted(cache_root.glob(pattern))
        self.assertEqual(
            len(matches),
            1,
            f"cached jar mismatch below {cache_root} for {pattern}: {matches}",
        )
        return matches[0]

    def test_help_and_pure_unit_task_are_explicitly_exempt(self) -> None:
        for task in ("help", "testDebugUnitTest"):
            with self.subTest(task=task):
                result = self._run(task)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)

    def test_artifact_task_without_trust_fails_with_generated_typed_blocker(self) -> None:
        result = self._run("packageArtifact")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)
        self.assertIn("./quwoquan_app/run.sh -d <device>", result.stdout)

    def test_artifact_task_accepts_only_profile_trust_asset(self) -> None:
        trust_root = self._valid_trust_root()

        result = self._run("packageArtifact", trust_root=trust_root)

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_artifact_task_rejects_noncanonical_ed25519_keyrings(self) -> None:
        trust_root = self._valid_trust_root()
        canonical_key = base64.b64encode(bytes(range(32))).decode("ascii")
        cases = (
            ({}, "non-empty object"),
            ({".invalid": canonical_key}, "key id is not canonical"),
            ({"local-contract": "***"}, "strict canonical base64"),
            ({"local-contract": "AA=="}, "32-byte Ed25519 key"),
            ({"local-contract": canonical_key.rstrip("=")}, "32-byte Ed25519 key"),
        )
        for keyring, expected_reason in cases:
            with self.subTest(keyring=keyring):
                self._replace_trusted_public_keys(trust_root, keyring)

                result = self._run("packageArtifact", trust_root=trust_root)

                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)
                self.assertIn(expected_reason, result.stdout)

    def test_debug_artifact_without_asset_root_stays_gate_blocked(self) -> None:
        # 构建期默认供给（embedded_default_package）已退役：Debug artifact 缺
        # asset root 时不再物化仓库外私有默认供给目录，直接 typed GATE_BLOCK。
        # user.home 定向到临时目录以断言零物化，GRADLE_USER_HOME 显式固定回
        # 真实缓存以保住 --offline 的依赖解析。
        private_home = self.root / "private-home"
        private_home.mkdir()
        result = self._run(
            "assembleNonprodDebug",
            extra_environment={
                "GRADLE_USER_HOME": str(self._gradle_user_home()),
            },
            extra_arguments=(f"-Duser.home={private_home}",),
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)
        self.assertIn("./quwoquan_app/run.sh -d <device>", result.stdout)
        self.assertEqual(
            sorted(private_home.glob(".cache/quwoquan/default-debug-supply/**/*")),
            [],
            result.stdout,
        )

    def test_release_and_profile_artifacts_without_asset_root_stay_gate_blocked(
        self,
    ) -> None:
        for task in ("assembleNonprodRelease", "assembleNonprodProfile"):
            with self.subTest(task=task):
                result = self._run(task)

                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    "APP.LAUNCH.runtime_config_trust_missing", result.stdout
                )
                self.assertIn("./quwoquan_app/run.sh -d <device>", result.stdout)

    def test_external_injection_rejects_default_supply_material_in_assets(self) -> None:
        trust_root = self._valid_trust_root()
        (trust_root / "qwq_runtime/runtime-config-default-package.json").write_text(
            "{}",
            encoding="utf-8",
        )

        result = self._run("packageArtifact", trust_root=trust_root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)
        self.assertIn("target runtime package", result.stdout.lower())

    def test_target_runtime_package_cannot_enter_artifact_assets(self) -> None:
        trust_root = self._valid_trust_root()
        (trust_root / "qwq_runtime/runtime-config-package.json").write_text(
            "{}",
            encoding="utf-8",
        )

        result = self._run("packageArtifact", trust_root=trust_root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", result.stdout)
        self.assertIn("target runtime package", result.stdout.lower())

    def test_main_activity_logs_only_generated_launch_identity_fields(self) -> None:
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")

        self.assertNotIn('"launchMode"', source)
        self.assertNotIn("QWQ_APP_LAUNCH_MODE", source)
        self.assertIn('payload.optString("launchProvenance", "")', source)
        self.assertIn('payload.optString("runtimeConfigSupplyMode", "")', source)
        self.assertIn("AppLaunchContract.LAUNCH_PROVENANCES", source)
        self.assertIn("AppLaunchContract.RUNTIME_CONFIG_SUPPLY_MODES", source)

    def test_shared_java_and_patrol_activities_compile_in_isolation(self) -> None:
        android_jar = self._android_sdk_root() / "platforms/android-37.0/android.jar"
        gson_jar = self._single_cached_jar(
            "caches/modules-2/files-2.1/com.google.code.gson/gson/2.13.2/*/gson-2.13.2.jar"
        )
        tink_jar = self._single_cached_jar(
            "caches/modules-2/files-2.1/com.google.crypto.tink/tink-android/1.23.0/*/tink-android-1.23.0.jar"
        )
        flutter_embedding = self._single_cached_jar(
            "caches/modules-2/files-2.1/io.flutter/flutter_embedding_debug/*/*/flutter_embedding_debug-*.jar"
        )
        lifecycle_common = self._single_cached_jar(
            "caches/modules-2/files-2.1/androidx.lifecycle/lifecycle-common/2.7.0/*/lifecycle-common-2.7.0.jar"
        )
        junit_jar = self._single_cached_jar(
            "caches/modules-2/files-2.1/junit/junit/4.13.2/*/junit-4.13.2.jar"
        )
        hamcrest_jar = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.hamcrest/hamcrest-core/1.3/*/hamcrest-core-1.3.jar"
        )
        for dependency in (
            android_jar,
            gson_jar,
            tink_jar,
            flutter_embedding,
            lifecycle_common,
            junit_jar,
            hamcrest_jar,
        ):
            self.assertTrue(dependency.is_file(), dependency)

        java_output = self.root / "native-java-classes"
        java_output.mkdir()
        java_compile = subprocess.run(
            [
                "javac",
                "--release",
                "17",
                "-cp",
                os.pathsep.join(
                    map(
                        str,
                        (
                            android_jar,
                            gson_jar,
                            tink_jar,
                            flutter_embedding,
                            junit_jar,
                            hamcrest_jar,
                        ),
                    )
                ),
                "-d",
                str(java_output),
                *map(str, sorted(SHARED_JAVA_ROOT.glob("*.java"))),
                str(RUNTIME_CONFIG_JAVA_TEST),
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=120,
        )
        self.assertEqual(java_compile.returncode, 0, java_compile.stdout)

        java_test = subprocess.run(
            [
                "java",
                "-cp",
                os.pathsep.join(
                    map(
                        str,
                        (
                            java_output,
                            android_jar,
                            gson_jar,
                            tink_jar,
                            flutter_embedding,
                            junit_jar,
                            hamcrest_jar,
                        ),
                    )
                ),
                "org.junit.runner.JUnitCore",
                "com.quwoquan.quwoquan_app.RuntimeConfigPackageStoreTest",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=120,
        )
        self.assertEqual(java_test.returncode, 0, java_test.stdout)

        kotlin_compiler = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.4.0/*/kotlin-compiler-embeddable-2.4.0.jar"
        )
        kotlin_stdlib = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.4.0/*/kotlin-stdlib-2.4.0.jar"
        )
        kotlin_script_runtime = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-script-runtime/2.4.0/*/kotlin-script-runtime-2.4.0.jar"
        )
        kotlin_daemon = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-daemon-embeddable/2.4.0/*/kotlin-daemon-embeddable-2.4.0.jar"
        )
        kotlin_reflect = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-reflect/1.6.10/*/kotlin-reflect-1.6.10.jar"
        )
        kotlin_coroutines = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.8.1/*/kotlinx-coroutines-core-jvm-1.8.1.jar"
        )
        trove = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains.intellij.deps/trove4j/1.0.20200330/*/trove4j-1.0.20200330.jar"
        )
        annotations = self._single_cached_jar(
            "caches/modules-2/files-2.1/org.jetbrains/annotations/23.0.0/*/annotations-23.0.0.jar"
        )
        kotlin_output = self.root / "patrol-kotlin-classes"
        kotlin_output.mkdir()
        compiler_classpath = os.pathsep.join(
            map(
                str,
                (
                    kotlin_compiler,
                    kotlin_stdlib,
                    kotlin_script_runtime,
                    kotlin_daemon,
                    kotlin_reflect,
                    kotlin_coroutines,
                    trove,
                    annotations,
                ),
            )
        )
        source_classpath = os.pathsep.join(
            map(
                str,
                (
                    android_jar,
                    gson_jar,
                    tink_jar,
                    flutter_embedding,
                    lifecycle_common,
                    kotlin_stdlib,
                    java_output,
                ),
            )
        )
        kotlin_compile = subprocess.run(
            [
                "java",
                "-cp",
                compiler_classpath,
                "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                "-no-reflect",
                "-no-stdlib",
                "-jvm-target",
                "17",
                "-classpath",
                source_classpath,
                "-d",
                str(kotlin_output),
                *map(str, sorted(PATROL_KOTLIN_ROOT.rglob("*.kt"))),
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=180,
        )
        self.assertEqual(kotlin_compile.returncode, 0, kotlin_compile.stdout)


if __name__ == "__main__":
    unittest.main()
