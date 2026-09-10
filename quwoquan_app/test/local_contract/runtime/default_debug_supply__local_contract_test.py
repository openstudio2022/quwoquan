# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
#
# Debug-nonprod 构建期自供给（build_time_self_supply）契约：
# - 无外部 canonical handoff 时，iOS Debug-nonprod / Android nonprod debug 构建阶段以当前
#   源码树调用 canonical handoff builder 现场签发 alpha test_live package + nonprod trust，
#   并以 runtime_config_activation_request 形态嵌入制品；原生 gate 在冷启动经同一
#   CAS/receipt 路径激活。
# - Profile/Release、prod 与非 alpha 环境不得物化或消费自供给；早前的双读旁路
#   （embedded_default_package）与 workspace_flutter_run/native_flutter_run 不得恢复。

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
RETIRED_SCRIPT = APP_DIR / "scripts/device/build_default_debug_supply.py"
SELF_SUPPLY_BUILDER = APP_DIR / "scripts/device/build_self_supply_request.py"
ANDROID_TRUST_GATE = APP_DIR / "android/gradle/runtime-config-assets.gradle.kts"
ANDROID_APP_GRADLE = APP_DIR / "android/app/build.gradle.kts"
IOS_PREPARE_SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
IOS_EMBED_SCRIPT = APP_DIR / "scripts/ios/build_embed_runtime_config_trust.py"
IOS_APP_DELEGATE = APP_DIR / "ios/Runner/AppDelegate.swift"
IOS_RUNTIME_CONFIG_SUPPLY = APP_DIR / "ios/Runner/NativeRuntimeConfigSupply.swift"
IOS_CANONICAL_JSON = APP_DIR / "ios/Runner/NativeRuntimeCanonicalJSON.swift"
ANDROID_STARTUP_GATE = (
    APP_DIR / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupGateActivity.java"
)
ANDROID_COORDINATOR = (
    APP_DIR
    / "android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app/RuntimeConfigActivationCoordinator.java"
)
LAUNCH_MANIFEST = REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
GENERATED_CONTRACT = (
    APP_DIR / "tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)
SELF_SUPPLY_MODE = "build_time_self_supply"
SELF_SUPPLY_REQUEST_FILE_NAME = "runtime-config-self-supply-request.json"


class BuildTimeSelfSupplyContractTest(unittest.TestCase):
    """自供给是 Debug-nonprod 的唯一构建期供给；其他制品仍 fail-closed。"""

    def test_supply_mode_is_in_the_canonical_closed_set(self) -> None:
        contract = json.loads(GENERATED_CONTRACT.read_text(encoding="utf-8"))
        modes = contract["runtimeConfigSupplyModes"]
        self.assertEqual(modes[0], "external_runtime_package")
        self.assertIn(SELF_SUPPLY_MODE, modes)
        self.assertNotIn("embedded_default_package", modes)
        self.assertIn(SELF_SUPPLY_MODE, LAUNCH_MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("workspace_flutter_run", contract["launchProvenances"])
        self.assertNotIn("native_flutter_run", contract["launchProvenances"])

    def test_retired_dual_read_bypass_stays_deleted(self) -> None:
        self.assertFalse(RETIRED_SCRIPT.exists())
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                IOS_APP_DELEGATE,
                IOS_RUNTIME_CONFIG_SUPPLY,
                ANDROID_STARTUP_GATE,
                ANDROID_COORDINATOR,
                ANDROID_TRUST_GATE,
                IOS_EMBED_SCRIPT,
                IOS_PREPARE_SCRIPT,
            )
        )
        for retired in (
            "consumeEmbeddedDefaultSupply",
            "EmbeddedDefaultSupplySource",
            "createEmbeddedDefaultSupplySource",
            "materializeDefaultDebugSupply",
            "build_default_debug_supply.py",
            "_verified_default_supply",
            "native_flutter_run",
        ):
            self.assertNotIn(retired, combined)

    def test_self_supply_builder_issues_an_embeddable_activation_request(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-self-supply-") as raw_root:
            root = Path(raw_root)
            trust_output = root / "runtime-config-trust.json"
            request_output = root / SELF_SUPPLY_REQUEST_FILE_NAME
            result = subprocess.run(
                [
                    sys.executable,
                    str(SELF_SUPPLY_BUILDER),
                    "--trust-output",
                    str(trust_output),
                    "--request-output",
                    str(request_output),
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPO_ROOT)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["runtimeConfigSupplyMode"], SELF_SUPPLY_MODE)
            self.assertEqual(summary["launchProvenance"], "workspace_ide_debug")
            self.assertEqual(summary["environment"], "alpha")
            self.assertEqual(summary["buildProfile"], "nonprod")
            request = json.loads(request_output.read_text(encoding="utf-8"))
            trust = json.loads(trust_output.read_text(encoding="utf-8"))
            self.assertEqual(request["expectedActiveDigest"], "")
            self.assertEqual(request["buildProfile"], "nonprod")
            self.assertEqual(request["target"], "alpha-local")
            manifest = request["effectiveLaunchManifest"]
            self.assertEqual(manifest["runtimeConfigSupplyMode"], SELF_SUPPLY_MODE)
            self.assertEqual(manifest["launchProvenance"], "workspace_ide_debug")
            self.assertEqual(manifest["launchPolicy"], "test_live")
            # spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
            self.assertEqual(manifest["contentSource"], "bundled_snapshot")
            self.assertFalse(manifest["requiresLocalTransport"])
            self.assertEqual(request["package"]["schema"], "app-offline-bootstrap-document")
            self.assertNotIn("expiresAt", request["package"])
            self.assertEqual(request["package"]["runtime"], {"appRuntimeEnv": "alpha"})
            self.assertEqual(request["packageDigest"], summary["packageDigest"])
            self.assertEqual(trust["buildProfile"], "nonprod")
            self.assertEqual(
                request["package"]["trustedPublicKeys"], trust["trustedPublicKeys"]
            )
            # 嵌入脚本接受该请求并把 trust + 请求一起放进 qwq_runtime/，同时清除残留 package。
            resources = root / "resources"
            runtime_dir = resources / "Runner.app" / "qwq_runtime"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "runtime-config-package.json").write_text("{}", encoding="utf-8")
            embed = subprocess.run(
                [
                    sys.executable,
                    str(IOS_EMBED_SCRIPT),
                    str(trust_output),
                    "nonprod",
                    str(resources),
                    "Runner.app",
                    "--self-supply-request",
                    str(request_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(embed.returncode, 0, embed.stderr)
            self.assertEqual(
                sorted(path.name for path in runtime_dir.iterdir()),
                sorted(["runtime-config-trust.json", SELF_SUPPLY_REQUEST_FILE_NAME]),
            )
            # Release/prod profile 不得接受自供给请求。
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(IOS_EMBED_SCRIPT),
                    str(trust_output),
                    "prod",
                    str(resources),
                    "Runner.app",
                    "--self-supply-request",
                    str(request_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("conflicts", rejected.stderr + rejected.stdout)
            # 用 nonprod trust 冒充 Release 也不行：请求校验单独拒绝非 nonprod profile。
            forged_release = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.argv=['embed']; "
                    "import importlib.util; spec=importlib.util.spec_from_file_location('embed', sys.argv0 if False else %r); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    "m._verified_self_supply_request(__import__('pathlib').Path(%r), 'prod')"
                    % (str(IOS_EMBED_SCRIPT), str(request_output)),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(forged_release.returncode, 0)
            self.assertIn("nonprod", forged_release.stderr)

    def test_self_supply_builder_rejects_outputs_inside_the_source_tree(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SELF_SUPPLY_BUILDER),
                "--trust-output",
                str(APP_DIR / "build" / "runtime-config-trust.json"),
                "--request-output",
                str(APP_DIR / "build" / SELF_SUPPLY_REQUEST_FILE_NAME),
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the source tree", result.stderr)

    def test_ios_prepare_script_self_supplies_only_debug_nonprod(self) -> None:
        source = IOS_PREPARE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"${CONFIGURATION:-}" == "Debug-nonprod"', source)
        self.assertIn("build_self_supply_request.py", source)
        self.assertIn("--self-supply-request", source)
        # 自供给材料落在源码树外的私有临时目录并在脚本退出时清除。
        self.assertIn('mktemp -d "${TMPDIR:-/tmp}/qwq-ios-self-supply', source)
        self.assertIn("trap cleanup_self_supply EXIT", source)
        # 自供给分支之后，trust 缺席对其余 configuration 仍是同一 typed blocker。
        self.assertIn("APP.LAUNCH.runtime_config_trust_missing", source)
        self.assertIn("build-profile runtime trust envelope is required", source)
        self.assertLess(
            source.index('"${CONFIGURATION:-}" == "Debug-nonprod"'),
            source.index("build-profile runtime trust envelope is required"),
        )
        # raw flutter run 不带 --target 时 Xcode 收到 lib/main.dart：接受该纯委托别名并归一。
        self.assertIn('(app_dir / "lib/main.dart").resolve()', source)
        self.assertIn('print("export FLUTTER_TARGET=" + shlex.quote("lib/main_prod.dart"))', source)

    def test_ios_native_gate_consumes_self_supply_only_in_debug(self) -> None:
        delegate = IOS_APP_DELEGATE.read_text(encoding="utf-8")
        supply = IOS_RUNTIME_CONFIG_SUPPLY.read_text(encoding="utf-8")
        self.assertIn("consumeBundledSelfSupplyRequest", supply)
        self.assertIn(f'"{SELF_SUPPLY_REQUEST_FILE_NAME}"', supply)
        self.assertIn(f'"{SELF_SUPPLY_MODE}"', supply)
        # 外部 canonical 供给已激活且新鲜时保持不变；重建后 requestDigest 变化才刷新。
        self.assertIn("ios_runtime_config_self_supply_skipped reason=external_active", supply)
        self.assertIn("activeReceipt[\"requestDigest\"] as? String == requestDigest", supply)
        self.assertIn("_ = try readVerifiedIdentity()", supply)
        self.assertIn("case .failure(let error):", supply)
        # 消费只编入 DEBUG，且位于外部 activation 之后、fatal gate 之前。
        debug_block = delegate[
            delegate.index("#if DEBUG\n      // Debug-nonprod 构建期自供给") : delegate.index(
                "confirmedPreviousBuildFatal = NativeCrashMarkerStore.shouldRecoverCurrentBuild()"
            )
        ]
        self.assertIn("consumeBundledSelfSupplyRequest()", debug_block)
        self.assertIn("#endif", debug_block)
        self.assertLess(
            delegate.index("let activation = consumePendingActivationRequest()"),
            delegate.index("consumeBundledSelfSupplyRequest()"),
        )

    def test_android_gradle_self_supplies_only_nonprod_debug(self) -> None:
        gate = ANDROID_TRUST_GATE.read_text(encoding="utf-8")
        self.assertIn("build_self_supply_request.py", gate)
        self.assertIn('val SELF_SUPPLY_VARIANT_TOKEN = "nonproddebug"', gate)
        self.assertIn("artifactSelectors.all { it.lowercase().contains(SELF_SUPPLY_VARIANT_TOKEN) }", gate)
        self.assertIn("must stay outside the source tree", gate)
        self.assertIn("root.deleteRecursively()", gate)
        # 自供给也必须过同一 validateRuntimeConfigTrust；外部注入路径仍要求 QWQ_APP_BUILD_PROFILE。
        self.assertIn("validateRuntimeConfigTrust(contract, selfSupplyAssetRoot.path, selfSupply = true)", gate)
        self.assertIn("validateRuntimeConfigTrust(contract, configuredAssetRoot)", gate)
        self.assertIn("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT is absent", gate)
        self.assertIn(".runtime_config_trust_missing", gate)
        app_gradle = ANDROID_APP_GRADLE.read_text(encoding="utf-8")
        self.assertIn('if (androidRuntimeConfigSelfSupply) "debug" else "main"', app_gradle)

    def test_android_native_gate_consumes_self_supply_only_in_debug(self) -> None:
        startup = ANDROID_STARTUP_GATE.read_text(encoding="utf-8")
        coordinator = ANDROID_COORDINATOR.read_text(encoding="utf-8")
        self.assertIn("if (BuildConfig.DEBUG) {", startup)
        self.assertIn("consumeBundledSelfSupplyRequest();", startup)
        self.assertIn(
            f'"qwq_runtime/{SELF_SUPPLY_REQUEST_FILE_NAME}"', coordinator
        )
        self.assertIn(f'SELF_SUPPLY_MODE = "{SELF_SUPPLY_MODE}"', coordinator)
        self.assertIn("return ConsumeResult.notRequested();", coordinator)
        self.assertLess(
            startup.index("runtimeConfigActivationCoordinator.consumePendingRequest(getIntent(), isTaskRoot())"),
            startup.index("consumeBundledSelfSupplyRequest();"),
        )


class NativeCanonicalJSONContractTest(unittest.TestCase):
    """只运行 host Foundation；提取生产函数而非在测试中重写规范 encoder。"""

    # spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
    @staticmethod
    def _vectors() -> dict[str, dict]:
        return {
            "mixed_case_trust_keys": {
                "trustedPublicKeys": {"key10": "ten", "key2": "two", "Key": "upper"},
                "trustEnvelopeDigest": "sha256:test-vector",
            },
            "nested_array_and_escaping": {
                "z": [True, False, None, 0, 1, -7, 1.25, 9007199254740991],
                "a": [{"trustedPublicKeys": {}, "trustEnvelopeDigest": "摘要/\\\"\n"}],
            },
        }

    def test_python_canonical_vector_preserves_case_sensitive_key_order(self) -> None:
        # 即使 Linux 没有 Swift，该纯契约断言仍运行，不把平台 skip 当原生通过。
        encoded = json.dumps(
            self._vectors()["mixed_case_trust_keys"],
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        self.assertEqual(
            encoded,
            b'{"trustEnvelopeDigest":"sha256:test-vector",'
            b'"trustedPublicKeys":{"Key":"upper","key10":"ten","key2":"two"}}',
        )

    def test_production_and_test_host_compile_the_shared_canonicalizer(self) -> None:
        supply = IOS_RUNTIME_CONFIG_SUPPLY.read_text(encoding="utf-8")
        self.assertEqual(supply.count("return try NativeRuntimeCanonicalJSON.data(document)"), 2)
        self.assertNotIn(".sortedKeys", supply)
        for project in (
            APP_DIR / "ios/Runner.xcodeproj/project.pbxproj",
            APP_DIR / "test_host/patrol/ios/Runner.xcodeproj/project.pbxproj",
        ):
            with self.subTest(project=str(project)):
                source = project.read_text(encoding="utf-8")
                self.assertEqual(source.count("/* NativeRuntimeCanonicalJSON.swift in Sources */"), 2)
                self.assertIn("path = " + (
                    "../../../../ios/Runner/" if "test_host" in project.parts else ""
                ) + "NativeRuntimeCanonicalJSON.swift;", source)

    def test_generated_supply_matches_both_production_swift_canonicalizers(self) -> None:
        swift = shutil.which("swift")
        if swift is None:
            self.skipTest(
                f"HOST_SWIFT_UNAVAILABLE platform={sys.platform}: "
                "原生 Foundation 字节一致性未执行；纯 Python 契约仍独立运行"
            )
        source = IOS_RUNTIME_CONFIG_SUPPLY.read_text(encoding="utf-8")
        # 保留生产函数体全部字节，只移除访问限制以便独立调用；缺失/迁移必须显式更新抽取边界。
        functions = re.findall(
            r"^  private static func canonicalJSONData\([^\n]+\{\n.*?^  \}",
            source, flags=re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(functions), 2, "必须覆盖 store 与 activation coordinator 两条生产路径")
        wrappers = "\n".join(
            f"enum ProductionCanonical{index} {{\n"
            + function.replace("private static func", "static func", 1)
            + "\n}"
            for index, function in enumerate(functions)
        )
        program = (
            IOS_CANONICAL_JSON.read_text(encoding="utf-8") + "\n"
            "enum NativeRuntimeConfigReadError: Error {\n"
            "  case packageMalformed, activationRequestMalformed\n}\n"
            + wrappers
            + "\nlet input = FileHandle.standardInput.readDataToEndOfFile()\n"
            "let vectors = try JSONSerialization.jsonObject(with: input) as! [[String: Any]]\n"
            "for document in vectors {\n"
            "  print(try ProductionCanonical0.canonicalJSONData(document).base64EncodedString())\n"
            "  print(try ProductionCanonical1.canonicalJSONData(document).base64EncodedString())\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory(prefix="qwq-native-canonical-") as raw_root:
            root = Path(raw_root)
            request_output = root / SELF_SUPPLY_REQUEST_FILE_NAME
            trust_output = root / "runtime-config-trust.json"
            generated = subprocess.run(
                [sys.executable, str(SELF_SUPPLY_BUILDER),
                 "--trust-output", str(trust_output), "--request-output", str(request_output)],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(REPO_ROOT)},
                capture_output=True, text=True, check=False, timeout=90,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            request_bytes = request_output.read_bytes()
            request = json.loads(request_bytes)
            vectors = {
                **self._vectors(),
                "generated_request": request,
                "generated_package": request["package"],
                "generated_manifest": request["effectiveLaunchManifest"],
                "generated_trust": json.loads(trust_output.read_bytes()),
            }
            expected = {
                name: json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                for name, value in vectors.items()
            }
            self.assertEqual(expected["generated_request"], request_bytes)
            self.assertEqual(
                "sha256:" + hashlib.sha256(expected["generated_package"]).hexdigest(),
                request["packageDigest"],
            )
            probe = root / "canonical.swift"
            probe.write_text(program, encoding="utf-8")
            native = subprocess.run(
                [swift, "-module-cache-path", str(root / "module-cache"), str(probe)],
                input=json.dumps(list(vectors.values()), ensure_ascii=False).encode("utf-8"),
                capture_output=True, check=False, timeout=90,
            )
            self.assertEqual(native.returncode, 0, native.stderr.decode("utf-8", errors="replace"))
            lines = native.stdout.splitlines()
            self.assertEqual(len(lines), len(vectors) * 2)
            for index, (name, python_bytes) in enumerate(expected.items()):
                for canonicalizer in range(2):
                    with self.subTest(vector=name, production_canonicalizer=canonicalizer):
                        swift_bytes = base64.b64decode(lines[index * 2 + canonicalizer], validate=True)
                        self.assertEqual(
                            swift_bytes, python_bytes,
                            f"{name} production[{canonicalizer}] canonical bytes differ: "
                            f"python=sha256:{hashlib.sha256(python_bytes).hexdigest()} "
                            f"swift=sha256:{hashlib.sha256(swift_bytes).hexdigest()}",
                        )


if __name__ == "__main__":
    unittest.main()
