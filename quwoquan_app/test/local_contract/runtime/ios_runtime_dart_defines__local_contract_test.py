# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
APP_DELEGATE = APP_DIR / "ios/Runner/AppDelegate.swift"
# runtime config 原生供给面的真相源。生产 Runner 与 Patrol UAT test host 两个 Xcode 工程
# 编译同一份，宿主读到的取值因此与生产同源。
RUNTIME_CONFIG_SOURCES = tuple(
    APP_DIR / "ios/Runner" / name
    for name in (
        "NativeRuntimeConfigSupply.swift",
        "NativeRuntimeConfigMigrationArchive.swift",
        "NativeRuntimeConfigActivationCoordinator.swift",
        "NativeRuntimeConfigChannel.swift",
    )
)
GENERATED_LAUNCH_CONTRACT = APP_DIR / "ios/Runner/AppLaunchContract.generated.swift"
GENERATED_LAUNCH_CONTRACT_JSON = (
    APP_DIR / "tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)
RUNNER_PROJECT = APP_DIR / "ios/Runner.xcodeproj/project.pbxproj"
PATROL_PROJECT = APP_DIR / "test_host/patrol/ios/Runner.xcodeproj/project.pbxproj"
PATROL_TRUST_SCRIPT = APP_DIR / "scripts/ios/build_test_host_embed_runtime_config_trust.sh"
STACKCTL_PYTHON_RESOLVER = APP_DIR / "scripts/ios/build_resolve_stackctl_python.sh"


def _runtime_config_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_CONFIG_SOURCES)


def _encoded_define(key: str, value: str) -> str:
    return base64.b64encode(f"{key}={value}".encode()).decode()


def _trust_envelope(root: Path, *, build_profile: str = "nonprod") -> Path:
    trust = root / "runtime-config-trust.json"
    trust.write_text(
        json.dumps(
            {
                "schema": "app-runtime-config-trust",
                "buildProfile": build_profile,
                "signatureAlgorithm": "ed25519",
                "trustedPublicKeys": {
                    "test-key": base64.b64encode(bytes(range(32))).decode("ascii")
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return trust


class IosRuntimeConfigBuildPreparationContractTest(unittest.TestCase):
    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["QWQ_IOS_STACKCTL_PYTHON"] = sys.executable
        environment["CONFIGURATION"] = "Debug-alpha"
        environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        environment["DART_DEFINES"] = _encoded_define("FLUTTER_VERSION", "test")
        return environment

    def _materialization_environment(
        self,
        root: Path,
        trust: Path,
    ) -> dict[str, str]:
        environment = self._environment()
        environment.update(
            {
                "QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH": str(trust),
                "TARGET_BUILD_DIR": str(root / "build"),
                "UNLOCALIZED_RESOURCES_FOLDER_PATH": "Runner.app",
            }
        )
        return environment

    def test_script_uses_build_profile_and_has_no_runtime_package_dual_read(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("resolve_ios_configuration", source)
        self.assertNotIn("QWQ_LAUNCH_HANDOFF_JSON", source)
        self.assertIn("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", source)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_TRUST_PATH", source)
        for retired in (
            "Debug-nonprod",
            "Profile-nonprod",
            "QWQNativeRuntime.plist",
            "runtimeDefines",
            "print_app_env_dart_defines.py",
            "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON or",
        ):
            self.assertNotIn(retired, source)
        self.assertNotIn("Debug-prod|Profile-prod", source)
        self.assertIn("target runtime package must be activated post-install", source)
        # 构建期默认供给已退役：脚本不得再引用共享默认供给脚本或其分支。
        self.assertNotIn("build_default_debug_supply.py", source)
        self.assertNotIn("RUNTIME_CONFIG_SUPPLY_KIND", source)
        self.assertNotIn("DEFAULT_SUPPLY", source)
        self.assertIn("./quwoquan_app/run.sh -d <device>", source)
        self.assertNotIn("app-activate-flutter-facade", source)
        self.assertNotIn("flutter facade", source)

    def test_generated_build_profile_identity_is_required(self) -> None:
        environment = self._environment()
        environment.pop("QWQ_APP_BUILD_PROFILE")
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("generated build-profile identity is missing", result.stderr)

    def test_compile_defines_preserve_non_runtime_values_and_add_no_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertIn("export FLUTTER_TARGET=lib/main_alpha.dart", result.stdout)
        self.assertIn(environment["DART_DEFINES"], result.stdout)
        self.assertIn("compileRuntimeDefines=0", result.stderr)
        self.assertIn("embeddedRuntimePackage=0", result.stderr)
        for forbidden in (
            "api.alpha.quwoquan.com",
            "APP_RUNTIME_ENV=",
            "APP_LAUNCH_POLICY=",
            "QWQ_LAUNCH_TARGET=",
        ):
            self.assertNotIn(forbidden, result.stdout)

    def test_runtime_and_endpoint_defines_are_rejected(self) -> None:
        for key, value in (
            ("APP_RUNTIME_ENV", "alpha"),
            ("CLOUD_GATEWAY_BASE_URL", "https://api.alpha.example"),
            ("APP_LAUNCH_POLICY", "test_live"),
            ("QWQ_LAUNCH_TARGET", "alpha-local"),
        ):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    environment = self._materialization_environment(
                        root,
                        _trust_envelope(root),
                    )
                    environment["DART_DEFINES"] = _encoded_define(key, value)
                    result = subprocess.run(
                        ["bash", str(SCRIPT)],
                        cwd=APP_DIR,
                        env=environment,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                self.assertEqual(result.returncode, 2)
                self.assertIn("compile inputs contain runtime configuration", result.stderr)

    def test_build_materializes_only_profile_trust_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            package = root / "runtime-config-package.json"
            package.write_text('{"target":"alpha-local"}', encoding="utf-8")
            subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            resource_root = root / "build/Runner.app/qwq_runtime"
            self.assertEqual(
                json.loads(
                    (resource_root / "runtime-config-trust.json").read_text(
                        encoding="utf-8"
                    )
                )["buildProfile"],
                "nonprod",
            )
            self.assertFalse((resource_root / "runtime-config-package.json").exists())

    def test_explicit_target_package_path_is_rejected_without_bundle_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            package = root / "runtime-config-package.json"
            package.write_text('{"target":"alpha-local"}', encoding="utf-8")
            environment["QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH"] = str(package)
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("activated post-install", result.stderr)
            self.assertFalse(
                (root / "build/Runner.app/qwq_runtime/runtime-config-package.json").exists()
            )

    def test_missing_or_invalid_trust_envelope_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Debug-alpha 之外的 configuration trust 缺席都 GATE_BLOCK（REQ-003：
            # 自供给只服务 Debug-alpha），且错误指引 run.sh 而非已退役的 facade。
            for configuration, build_profile in (
                ("Profile-alpha", "nonprod"),
                ("Release-nonprod", "nonprod"),
                ("Release-prod", "prod"),
            ):
                with self.subTest(configuration=configuration):
                    missing = self._environment()
                    missing["CONFIGURATION"] = configuration
                    missing["QWQ_APP_BUILD_PROFILE"] = build_profile
                    missing.pop("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", None)
                    missing.update(
                        {
                            "TARGET_BUILD_DIR": str(root / "build"),
                            "UNLOCALIZED_RESOURCES_FOLDER_PATH": "Runner.app",
                        }
                    )
                    missing_result = subprocess.run(
                        ["bash", str(SCRIPT)],
                        cwd=APP_DIR,
                        env=missing,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(missing_result.returncode, 2)
                    self.assertIn(
                        "APP.LAUNCH.runtime_config_trust_missing",
                        missing_result.stderr,
                    )
                    self.assertIn(
                        "./quwoquan_app/run.sh -d <device>",
                        missing_result.stderr,
                    )
                    self.assertNotIn(
                        "app-activate-flutter-facade",
                        missing_result.stderr,
                    )
                    self.assertNotIn("command -v flutter", missing_result.stderr)

            trust = _trust_envelope(root)
            payload = json.loads(trust.read_text(encoding="utf-8"))
            payload["environment"] = "alpha"
            trust.write_text(json.dumps(payload), encoding="utf-8")
            invalid_result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=self._materialization_environment(root, trust),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(invalid_result.returncode, 0)
            self.assertIn("canonical schema", invalid_result.stderr)
            self.assertIn(
                "APP.LAUNCH.runtime_config_trust_missing",
                invalid_result.stderr,
            )

    def test_debug_nonprod_missing_trust_self_supplies_without_readable_package(self) -> None:
        # REQ-003 build_time_self_supply：Debug-alpha 缺 canonical handoff 时由构建阶段
        # 现场签发 alpha trust + 激活请求并嵌入；可读 runtime package 仍不进入产物，
        # 也不再需要 PATH facade 或任何用户级配置。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._environment()
            environment.pop("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", None)
            environment.update(
                {
                    "CONFIGURATION": "Debug-alpha",
                    "QWQ_APP_BUILD_PROFILE": "nonprod",
                    "TARGET_BUILD_DIR": str(root / "build"),
                    "UNLOCALIZED_RESOURCES_FOLDER_PATH": "Runner.app",
                }
            )
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("runtimeConfigSupplyMode=build_time_self_supply", result.stderr)
            self.assertIn("selfSupplyRequest=1", result.stderr)
            self.assertIn("export QWQ_IOS_DART_DEFINES_READY=1", result.stdout)
            runtime_dir = root / "build/Runner.app/qwq_runtime"
            self.assertEqual(
                sorted(path.name for path in runtime_dir.iterdir()),
                ["runtime-config-self-supply-request.json", "runtime-config-trust.json"],
            )
            trust = json.loads(
                (runtime_dir / "runtime-config-trust.json").read_text(encoding="utf-8")
            )
            self.assertEqual(trust["buildProfile"], "nonprod")
            request = json.loads(
                (runtime_dir / "runtime-config-self-supply-request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(request["environment"], "alpha")
            self.assertEqual(request["target"], "alpha-local")
            self.assertEqual(request["expectedActiveDigest"], "")
            self.assertEqual(
                request["effectiveLaunchManifest"]["runtimeConfigSupplyMode"],
                "build_time_self_supply",
            )
            self.assertEqual(
                request["effectiveLaunchManifest"]["launchProvenance"],
                "workspace_ide_debug",
            )
            self.assertEqual(request["trustEnvelopeDigest"], request["effectiveLaunchManifest"]["runtimeConfigTrustEnvelopeDigest"])

    def test_debug_nonprod_external_handoff_wins_over_self_supply(self) -> None:
        # 外部 canonical handoff 已注入 trust 时不物化自供给请求：canonical launcher 路径
        # 与 raw 路径进入同一制品门，但只嵌各自应有的材料。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("selfSupplyRequest=0", result.stderr)
            runtime_dir = root / "build/Runner.app/qwq_runtime"
            self.assertEqual(
                [path.name for path in runtime_dir.iterdir()],
                ["runtime-config-trust.json"],
            )

    def test_external_injection_purges_stale_default_supply_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            resource_root = root / "build/Runner.app/qwq_runtime"
            resource_root.mkdir(parents=True)
            for stale in (
                "runtime-config-default-package.json",
                "runtime-config-default-manifest.json",
            ):
                (resource_root / stale).write_text("{}", encoding="utf-8")
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("embeddedRuntimePackage=0", result.stderr)
            self.assertEqual(
                {entry.name for entry in resource_root.iterdir()},
                {"runtime-config-trust.json"},
            )

    def test_manual_keyring_protocol_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            environment["QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON"] = "{}"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("manual trusted-public-keys JSON is retired", result.stderr)

    def test_debug_prod_and_profile_prod_are_rejected(self) -> None:
        for configuration in ("Debug-prod", "Profile-prod"):
            with self.subTest(configuration=configuration):
                environment = self._environment()
                environment["CONFIGURATION"] = configuration
                environment["QWQ_APP_BUILD_PROFILE"] = "prod"
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    cwd=APP_DIR,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("unsupported iOS configuration", result.stderr)

    def test_native_reader_and_cold_start_activation_contract_shape(self) -> None:
        source = _runtime_config_source()
        app_delegate_source = APP_DELEGATE.read_text(encoding="utf-8")
        # 退役形态在整个 iOS 原生面都不得复活，因此反向断言同时覆盖 AppDelegate。
        retired_scan = source + app_delegate_source
        for required in (
            "enum NativeRuntimeConfigReadState",
            "case present(NativeRuntimeConfigActiveProjection)",
            "case absent(NativeRuntimeConfigTrustProjection)",
            "case failure(NativeRuntimeConfigReadError)",
            'case "readRuntimeConfig"',
            'case "readRuntimeConfigState"',
            "static func activate(",
            "package rawPackage: [String: Any]",
            "try validateRequest(decoded)",
            "NativeRuntimeConfigStore.activate(",
            "expectedPackageDigest: packageDigest",
            "expectedTrustEnvelopeDigest: trustDigest",
            "expectedActiveDigest: expectedActiveDigest",
            "Curve25519.Signing.PublicKey",
            "isValidSignature",
            "FileHandle(forWritingTo: temporary)",
            "try handle.synchronize()",
            "replaceItemAt",
            "fsync(directoryHandle)",
            "runtimePackageDestinationURL(createDirectory: true)",
            "let previousActivePackage = try readCurrentActivePackageData()",
            "try atomicallyActivate(packageData)",
            "try restorePreviousActivePackage(",
            "previousActivePackage,",
            "originalError: normalizedError",
            "activationReadbackFailed",
            "activationRollbackFailed",
            "let activatedState = loadActivePackage()",
            "activated.packageDigest == validated.packageDigest",
            'subdirectory: nativeRuntimeConfigDirectory',
            "AppLaunchContract.runtimeConfigPackageRequiredFields",
            "AppLaunchContract.runtimeConfigPackageRuntimeRequiredFields",
            "AppLaunchContract.runtimeConfigTrustEnvelopeRequiredFields",
            "AppLaunchContract.runtimeConfigActivationRequestRequiredFields",
            "AppLaunchContract.appEffectiveLaunchManifestRequiredFields",
            "AppLaunchContract.runtimeConfigActivationReceiptRequiredFields",
            "AppLaunchContract.targetEnvironment[target]",
            "AppLaunchContract.runtimeConfigErrorCodes[code]",
            'envelope["launchProvenance"] = identity.launchProvenance',
            'envelope["runtimeConfigSupplyMode"] = identity.runtimeConfigSupplyMode',
            'receipt["launchProvenance"]',
            'receipt["runtimeConfigSupplyMode"]',
        ):
            self.assertIn(required, source)
        # 嵌入默认供给（embedded_default_package）已整体退役：消费入口、材料
        # 常量与激活分支在生产 Runner 与共享供给面都不得复活。
        for retired_default_supply in (
            "consumeEmbeddedDefaultSupply",
            "nativeRuntimeDefaultPackageFileName",
            "nativeRuntimeDefaultManifestFileName",
            "runtime-config-default-package.json",
            "runtime-config-default-manifest.json",
            "ios_runtime_config_embedded_default_activated",
            "ios_embedded_default_skipped",
        ):
            self.assertNotIn(retired_default_supply, retired_scan)
        for retired_closed_set in (
            "private static let packageFields: Set<String> = [",
            "private static let runtimeFields: Set<String> = [",
            "private static let targetEnvironments = [",
            '"entrypoint", "launchMode"',
            "runtime-config-effective-launch-manifest.json",
        ):
            self.assertNotIn(retired_closed_set, source)
        self.assertNotIn('event["launchMode"]', app_delegate_source)
        self.assertIn('event["launchProvenance"]', app_delegate_source)
        self.assertIn('event["runtimeConfigSupplyMode"]', app_delegate_source)
        self.assertNotIn('case "installRuntimeConfigPackage"', retired_scan)
        self.assertNotIn("installArgumentsInvalid", retired_scan)
        self.assertNotIn("Set(arguments.keys) == installFields", retired_scan)
        self.assertNotIn(
            "Bundle.main.url(\n      forResource: nativeRuntimePackageFileName",
            retired_scan,
        )
        self.assertNotIn("cachedTrustEnvelope", retired_scan)
        self.assertNotIn("readTrustEnvelope()", retired_scan)
        self.assertNotIn("dartDefinesDigest", retired_scan)
        self.assertNotIn("nativeRuntimeConfigDigest", retired_scan)
        # 启动上报读的是当前生效 package 摘要，属于 AppDelegate 的启动面而非供给面。
        self.assertIn("nativeActiveRuntimePackageDigest", app_delegate_source)
        info_plist = (APP_DIR / "ios/Runner/Info.plist").read_text(encoding="utf-8")
        for retired_key in (
            "QWQRecoveryBaseURL",
            "QWQPublicWebURL",
            "QWQAppDownloadBaseURL",
            "QWQRuntimeEnvironment",
        ):
            self.assertNotIn(retired_key, info_plist)
        podfile = (APP_DIR / "ios/Podfile").read_text(encoding="utf-8")
        self.assertIn("platform :ios, '16.0'", podfile)
        self.assertNotIn(
            "Bundle.main.url(\n      forResource: nativeRuntimePackageFileName",
            source,
        )

    def _assert_shared_source_link(self, project: Path, source: str, name: str) -> None:
        # 逐边验证 Runner → Sources → PBXBuildFile → PBXFileReference；名字或孤立对象不算编译引用。
        objects = dict(re.findall(
            r"^\t\t([A-F0-9]{24})(?: /\* [^\n]*? \*/)? = \{([^\n]*|\n.*?^\t\t)\};",
            source, flags=re.MULTILINE | re.DOTALL,
        ))
        runner_id = "97C146ED1CF9000F007C117D"
        runner = objects[runner_id]
        self.assertIn("isa = PBXNativeTarget;", runner)
        phase_list = re.search(r"buildPhases = \((.*?)\);", runner, re.DOTALL)
        self.assertIsNotNone(phase_list)
        phase_ids = re.findall(r"\b[A-F0-9]{24}\b", phase_list.group(1))
        sources = [objects[key] for key in phase_ids if "isa = PBXSourcesBuildPhase;" in objects[key]]
        self.assertEqual(len(sources), 1)
        files = re.search(r"files = \((.*?)\);", sources[0], re.DOTALL)
        self.assertIsNotNone(files)
        build_ids = re.findall(r"\b[A-F0-9]{24}\b", files.group(1))
        compiled_refs = []
        for build_id in build_ids:
            build = objects.get(build_id, "")
            self.assertIn("isa = PBXBuildFile;", build)
            ref = re.search(r"fileRef = ([A-F0-9]{24})", build)
            self.assertIsNotNone(ref)
            compiled_refs.append(ref.group(1))
        expected_path = ("../../../../ios/Runner/" if project == PATROL_PROJECT else "") + name
        refs = [key for key, body in objects.items()
                if "isa = PBXFileReference;" in body
                and f"path = {expected_path};" in body]
        self.assertEqual(len(refs), 1, f"缺失共享生产引用: {name}")
        ref_id = refs[0]
        self.assertEqual(compiled_refs.count(ref_id), 1, f"Runner Sources 漏挂或重复: {name}")
        self.assertIn('sourceTree = "<group>";', objects[ref_id])
        group_id = "97C146F01CF9000F007C117D"
        group = objects[group_id]
        self.assertIn("isa = PBXGroup;", group)
        self.assertIn("path = Runner;", group)
        self.assertIn('sourceTree = "<group>";', group)
        children = re.search(r"children = \((.*?)\);", group, re.DOTALL)
        self.assertIsNotNone(children)
        self.assertIn(ref_id, re.findall(r"\b[A-F0-9]{24}\b", children.group(1)))
        project_body = next(body for body in objects.values() if "isa = PBXProject;" in body)
        main_group = re.search(r"mainGroup = ([A-F0-9]{24})", project_body)
        self.assertIsNotNone(main_group)
        root_group = objects[main_group.group(1)]
        root_children = re.search(r"children = \((.*?)\);", root_group, re.DOTALL)
        self.assertIsNotNone(root_children)
        self.assertIn(group_id, re.findall(r"\b[A-F0-9]{24}\b", root_children.group(1)))
        self.assertNotRegex(root_group, r"\bpath\s*=")
        self.assertIn('sourceTree = "<group>";', root_group)
        targets = re.search(r"targets = \((.*?)\);", project_body, re.DOTALL)
        self.assertIsNotNone(targets)
        self.assertIn(runner_id, re.findall(r"\b[A-F0-9]{24}\b", targets.group(1)))
        self.assertIn('projectDirPath = "";', project_body)
        resolved = (project.parent.parent / "Runner" / expected_path).resolve()
        self.assertEqual(resolved, (APP_DIR / "ios/Runner" / name).resolve())
        self.assertTrue(resolved.is_file())

    def _assert_runtime_config_channel_compile_closure(
        self,
        project: Path,
        project_source: str,
        *,
        source_overrides: dict[str, str] | None = None,
    ) -> None:
        source_overrides = source_overrides or {}
        source_texts = {
            path.name: source_overrides.get(path.name, path.read_text(encoding="utf-8"))
            for path in RUNTIME_CONFIG_SOURCES
        }
        declarations: dict[str, list[str]] = {}
        for name, source_text in source_texts.items():
            for declaration in re.findall(
                r"^\s*(?:(?:private|internal)\s+)?(?:enum|struct|class|protocol)\s+"
                r"([A-Za-z_][A-Za-z0-9_]*)",
                source_text,
                flags=re.MULTILINE,
            ):
                declarations.setdefault(declaration, []).append(name)
        duplicates = {
            declaration: sources
            for declaration, sources in declarations.items()
            if len(sources) != 1
        }
        self.assertEqual(
            duplicates,
            {},
            f"runtime config 编译闭包不得包含重复顶层声明: {project}",
        )
        self.assertEqual(
            declarations.get("NativeRuntimeConfigChannel"),
            ["NativeRuntimeConfigChannel.swift"],
            f"runtime config channel 必须只由独立源码声明: {project}",
        )
        self.assertEqual(
            declarations.get("NativeRuntimeConfigActivationCoordinator"),
            ["NativeRuntimeConfigActivationCoordinator.swift"],
            f"activation coordinator 必须只由独立源码声明: {project}",
        )
        self._assert_shared_source_link(
            project,
            project_source,
            "NativeRuntimeConfigChannel.swift",
        )

    def test_runner_and_patrol_compile_one_runtime_config_channel(self) -> None:
        for project in (RUNNER_PROJECT, PATROL_PROJECT):
            with self.subTest(project=str(project)):
                self._assert_runtime_config_channel_compile_closure(
                    project,
                    project.read_text(encoding="utf-8"),
                )

    def test_runtime_config_channel_compile_closure_rejects_old_copy_and_duplicate_link(self) -> None:
        supply = (APP_DIR / "ios/Runner/NativeRuntimeConfigSupply.swift").read_text(
            encoding="utf-8"
        )
        old_copy = supply + "\nenum NativeRuntimeConfigChannel { }\n"
        old_coordinator_copy = supply + "\nenum NativeRuntimeConfigActivationCoordinator { }\n"
        for project in (RUNNER_PROJECT, PATROL_PROJECT):
            source = project.read_text(encoding="utf-8")
            with self.subTest(project=str(project), mutation="old_supply_copy"):
                with self.assertRaises(AssertionError):
                    self._assert_runtime_config_channel_compile_closure(
                        project,
                        source,
                        source_overrides={"NativeRuntimeConfigSupply.swift": old_copy},
                    )
            with self.subTest(project=str(project), mutation="old_coordinator_copy"):
                with self.assertRaises(AssertionError):
                    self._assert_runtime_config_channel_compile_closure(
                        project,
                        source,
                        source_overrides={
                            "NativeRuntimeConfigSupply.swift": old_coordinator_copy
                        },
                    )
            channel_build_entry = next(
                line
                for line in source.splitlines(keepends=True)
                if "NativeRuntimeConfigChannel.swift in Sources */," in line
            )
            duplicated = source.replace(
                channel_build_entry,
                channel_build_entry + channel_build_entry,
                1,
            )
            with self.subTest(project=str(project), mutation="duplicate_sources_entry"):
                with self.assertRaises(AssertionError):
                    self._assert_runtime_config_channel_compile_closure(
                        project,
                        duplicated,
                    )

    def test_runner_and_patrol_compile_the_same_generated_launch_contract(self) -> None:
        self.assertTrue(GENERATED_LAUNCH_CONTRACT.is_file())
        for project in (RUNNER_PROJECT, PATROL_PROJECT):
            source = project.read_text(encoding="utf-8")
            for name in (
                *(path.name for path in RUNTIME_CONFIG_SOURCES),
                "AppLaunchContract.generated.swift",
                "NativeRuntimeCanonicalJSON.swift",
            ):
                with self.subTest(project=str(project), source=name):
                    self._assert_shared_source_link(project, source, name)
        patrol = PATROL_PROJECT.read_text(encoding="utf-8")
        phases = patrol[patrol.index("97C146ED1CF9000F007C117D /* Runner */ = {") :]
        self.assertLess(
            phases.index("Embed Runtime Config Trust"),
            phases.index("9740EEB61CF901F6004384FC /* Run Script */"),
        )

    def test_shared_source_link_rejects_dangling_and_uncompiled_files(self) -> None:
        # 只变异内存文本，不改共享工程；保留名字仍必须检测出断链。
        for project in (RUNNER_PROJECT, PATROL_PROJECT):
            source = project.read_text(encoding="utf-8")
            for path in RUNTIME_CONFIG_SOURCES:
                name = re.escape(path.name)
                mutations = {
                    "sources_entry": re.sub(
                        rf"^\s+[A-F0-9]{{24}} /\* {name} in Sources \*/,\n", "", source,
                        flags=re.MULTILINE,
                    ),
                    "build_file": re.sub(
                        rf"^\s+[A-F0-9]{{24}} /\* {name} in Sources \*/ = [^\n]+\n", "", source,
                        flags=re.MULTILINE,
                    ),
                    "file_reference": re.sub(
                        rf"^\s+[A-F0-9]{{24}} /\* {name} \*/ = [^\n]+\n", "", source,
                        flags=re.MULTILINE,
                    ),
                    "runner_group": re.sub(
                        rf"^\s+[A-F0-9]{{24}} /\* {name} \*/,\n", "", source,
                        flags=re.MULTILINE,
                    ),
                    "runner_sources_phase": source.replace(
                        "97C146EA1CF9000F007C117D /* Sources */,", ""
                    ),
                    "copied_source_path": source.replace(
                        "path = " + ("../../../../ios/Runner/" if project == PATROL_PROJECT else "") + path.name + ";",
                        f"path = copied/{path.name};",
                    ),
                }
                for mutation, changed in mutations.items():
                    with self.subTest(project=str(project), source=path.name, mutation=mutation):
                        self.assertTrue(source != changed, f"变异前引用已缺失: {path.name}/{mutation}")
                        with self.assertRaises(AssertionError):
                            self._assert_shared_source_link(project, changed, path.name)

    def test_active_receipt_is_the_only_restart_launch_identity_projection(self) -> None:
        contract = json.loads(
            GENERATED_LAUNCH_CONTRACT_JSON.read_text(encoding="utf-8")
        )
        receipt_fields = set(
            contract["schemaRequiredFields"]["runtime_config_activation_receipt"]
        )
        self.assertIn("launchProvenance", receipt_fields)
        self.assertIn("runtimeConfigSupplyMode", receipt_fields)
        source = _runtime_config_source()
        self.assertIn(
            "let identity = try NativeRuntimeConfigActivationCoordinator.readVerifiedIdentity()",
            source,
        )
        self.assertIn(
            'envelope["launchProvenance"] = identity.launchProvenance',
            source,
        )
        self.assertIn(
            'envelope["runtimeConfigSupplyMode"] = identity.runtimeConfigSupplyMode',
            source,
        )
        self.assertIn(
            "let receipt = try readActiveReceiptDocument()",
            source,
        )
        self.assertNotIn("runtime-config-effective-launch-manifest.json", source)

    def test_patrol_host_missing_trust_uses_the_same_first_typed_blocker(self) -> None:
        environment = dict(os.environ)
        environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        environment["TARGET_BUILD_DIR"] = "/tmp/qwq-patrol-local-contract"
        environment["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
        environment.pop("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", None)
        # trust 缺席必须先判否，不能先被 Python/toolchain 差异遮蔽。
        environment["QWQ_IOS_STACKCTL_PYTHON"] = "/invalid/python"
        result = subprocess.run(
            ["bash", str(PATROL_TRUST_SCRIPT)],
            cwd=APP_DIR,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "APP.LAUNCH.runtime_config_trust_missing",
            result.stderr,
        )
        self.assertNotIn("requires Python", result.stderr)

    def test_configuration_identity_is_build_profile_and_mode_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            environment["PRODUCT_BUNDLE_IDENTIFIER"] = "com.leadwise.quwoquan.alpha.debug"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            environment["PRODUCT_BUNDLE_IDENTIFIER"] = "com.example.quwoquanApp.alpha"
            blocked = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("does not match", blocked.stderr)

    def test_python_resolver_skips_incompatible_path_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_python = root / "bin/python3"
            invalid_python.parent.mkdir()
            invalid_python.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            invalid_python.chmod(0o755)
            compatible_python = root / "python-cache/quwoquan-data/bin/python3"
            compatible_python.parent.mkdir(parents=True)
            compatible_python.symlink_to(Path(sys.executable))
            environment = dict(os.environ)
            environment.pop("QWQ_IOS_STACKCTL_PYTHON", None)
            environment["PATH"] = str(invalid_python.parent) + os.pathsep + environment["PATH"]
            environment["QWQ_PYTHON_CACHE_ROOT"] = str(root / "python-cache")
            result = subprocess.run(
                ["bash", str(STACKCTL_PYTHON_RESOLVER)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), compatible_python.resolve())


if __name__ == "__main__":
    unittest.main()
