"""app_artifact_manifest metadata 的 local_contract 测试。

绑定 deliver-deploy-prod-pipeline DEC-004 与 environment-topology-and-packaging
REQ-004/GWT-003：制品身份、安装回执与渠道矩阵分离建模，Debug 不进入市场/官网，
渠道回执互不替代，且工具消费 metadata 而不自持字段集合。
"""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-003

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci import render_release_application_package as render_module
from quwoquan_ops.cli.lib.app_identity import (
    AppIdentityError,
    application_id_for_build_product,
    build_profile_for_environment,
    enumerate_valid_install_launch_paths,
    resolve_app_identity,
    supported_build_modes,
    supported_build_products,
    supported_build_profiles,
    supported_environments,
    supported_identity_platforms,
)
from quwoquan_ops.cli.lib.common import load_json_yaml

METADATA_PATH = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
)
LAUNCH_MANIFEST_PATH = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
)
DART_RESOLVER_PATH = (
    ROOT / "quwoquan_app/lib/runtime/config/runtime_package_resolver.dart"
)
ANDROID_BUILD_PATH = ROOT / "quwoquan_app/android/app/build.gradle.kts"
ANDROID_MANIFEST_PATH = ROOT / "quwoquan_app/android/app/src/main/AndroidManifest.xml"
IOS_DEBUG_CONFIG_PATH = ROOT / "quwoquan_app/ios/Flutter/Base/Debug.xcconfig"
IOS_PROFILE_CONFIG_PATH = ROOT / "quwoquan_app/ios/Flutter/Base/Profile.xcconfig"
IOS_RELEASE_CONFIG_PATH = ROOT / "quwoquan_app/ios/Flutter/Base/Release.xcconfig"
IOS_PROJECT_PATH = ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
PACKAGE_APP_ARTIFACT_PATH = (
    ROOT / "quwoquan_ops/cli/commands/package_app_artifact.py"
)

RELEASE_ONLY_CLASSES = {"store", "official_web", "hosted_web"}


class AppArtifactManifestMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_json_yaml(METADATA_PATH)

    def test_identity_objects_are_modeled_separately(self) -> None:
        schemas = self.document["schemas"]
        self.assertIn("app_artifact_manifest", schemas)
        self.assertIn("app_install_receipt", schemas)
        self.assertIn("release_application_package", schemas)
        # InstallReceipt 是 append-only separate fact，独立于 artifact manifest。
        self.assertTrue(schemas["app_install_receipt"].get("append_only"))
        # 三个 schema 不共享 schema_value，防止第二真相源。
        values = {schema["schema_value"] for schema in schemas.values()}
        self.assertEqual(len(values), len(schemas))

    def test_artifact_manifest_never_carries_content_identity(self) -> None:
        for schema in self.document["schemas"].values():
            for field in schema["required_fields"]:
                self.assertNotIn("content", str(field).lower())

    def test_mobile_artifact_manifest_binds_only_profile_trust_envelope(self) -> None:
        contract = self.document["schemas"]["app_artifact_manifest"]
        self.assertNotIn(
            "runtimeConfigTrustEnvelopeDigest",
            contract["required_fields"],
        )
        self.assertEqual(
            contract["fields"]["runtimeConfigTrustEnvelopeDigest"],
            {"type": "string", "format": "sha256_identity"},
        )
        constraints = "\n".join(contract["constraints"])
        self.assertIn(
            "Android/iOS AppArtifact 必须携带 runtimeConfigTrustEnvelopeDigest",
            constraints,
        )
        self.assertIn("Web AppArtifact 禁止携带该字段", constraints)

    def test_store_and_web_channels_only_accept_release(self) -> None:
        classes = self.document["distribution_classes"]
        for name, declaration in classes.items():
            build_modes = declaration["build_modes"]
            if name in RELEASE_ONLY_CLASSES:
                self.assertEqual(build_modes, ["release"], name)
                self.assertTrue(declaration["promotable"], name)
            else:
                self.assertIn("debug", build_modes, name)
                self.assertFalse(declaration["promotable"], name)

    def test_channel_matrix_covers_required_channels_per_platform(self) -> None:
        channels = self.document["distribution_channels"]
        ios_channels = {
            key for key, value in channels.items() if value["platform"] == "ios"
        }
        android_channels = {
            key for key, value in channels.items() if value["platform"] == "android"
        }
        self.assertEqual(ios_channels, {"apple_app_store", "apple_testflight"})
        self.assertEqual(
            android_channels,
            {
                "huawei_appgallery",
                "xiaomi_getapps",
                "oppo_market",
                "vivo_market",
                "tencent_myapp",
                "official_web",
            },
        )
        for key, value in channels.items():
            self.assertIn(
                value["distribution_class"], {"store", "official_web"}, key
            )
            self.assertTrue(value["upload_format"], key)
            self.assertTrue(value["store_signing_custodian"], key)
            self.assertTrue(value["readback"], key)

    def test_install_receipt_channels_match_channel_matrix(self) -> None:
        receipt = self.document["schemas"]["app_install_receipt"]
        allowed = set(receipt["fields"]["channelId"]["allowed_values"])
        market_channels = set(self.document["distribution_channels"])
        self.assertTrue(market_channels.issubset(allowed))
        # 非市场渠道只允许非可提升 distributionClass。
        non_market = allowed - market_channels
        self.assertEqual(non_market, {"dev_direct", "simulator", "registered_device"})

    def test_ios_simulator_does_not_claim_unsupported_aot_build_modes(self) -> None:
        simulator = self.document["distribution_classes"]["simulator"]
        self.assertEqual(simulator["platform_build_modes"]["ios"], ["debug"])
        self.assertEqual(
            simulator["platform_build_modes"]["android"],
            ["debug", "profile", "release"],
        )

    def test_launch_provenance_enumerates_all_valid_entries(self) -> None:
        self.assertEqual(
            set(self.document["launch_provenances"]),
            {
                "canonical_launcher",
                "workspace_ide_debug",
                "release_package",
                "hot_restart",
                "icon_cold_launch",
            },
        )

    def test_package_compiler_scrubs_runtime_launch_identity(self) -> None:
        source = PACKAGE_APP_ARTIFACT_PATH.read_text(encoding="utf-8")
        self.assertIn('"QWQ_APP_LAUNCH_PROVENANCE"', source)
        self.assertIn('"QWQ_RUNTIME_CONFIG_SUPPLY_MODE"', source)

    def test_canonical_manifest_loads_without_optional_site_packages(self) -> None:
        probe = (
            "import json; from pathlib import Path; "
            "from quwoquan_ops.cli.lib.common import load_json_yaml; "
            "from quwoquan_ops.cli.lib.app_identity import "
            "enumerate_valid_install_launch_paths, resolve_app_identity; "
            f"document = load_json_yaml(Path({str(METADATA_PATH)!r})); "
            "identity = resolve_app_identity(platform='ios', environment='alpha', "
            "build_mode='debug'); "
            "print(json.dumps({'schema': document['schema_id'], "
            "'applicationId': identity.application_id, "
            "'pathCount': len(enumerate_valid_install_launch_paths())}, "
            "sort_keys=True))"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", probe],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "app_artifact_manifest")
        self.assertEqual(
            payload["applicationId"],
            "com.example.quwoquanApp.nonprod.debug",
        )
        self.assertGreater(payload["pathCount"], 0)

    def test_fallback_rejects_malformed_flow_collections(self) -> None:
        malformed_documents = (
            "value: [alpha, beta\n",
            "value: [alpha,, beta]\n",
            "value: {environment: alpha, target}\n",
        )
        for document in malformed_documents:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    path = Path(temporary_directory) / "malformed.yaml"
                    path.write_text(document, encoding="utf-8")
                    probe = (
                        "from pathlib import Path; "
                        "from quwoquan_ops.cli.lib.common import load_json_yaml; "
                        f"load_json_yaml(Path({str(path)!r}))"
                    )
                    result = subprocess.run(
                        [sys.executable, "-S", "-c", probe],
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Cannot parse manifest without PyYAML", result.stderr)

    def test_render_tool_consumes_metadata_not_private_field_set(self) -> None:
        contract = self.document["schemas"]["release_application_package"]
        self.assertEqual(render_module.SCHEMA, contract["schema_value"])
        self.assertEqual(
            set(render_module.GENERIC_FIELDS), set(contract["required_fields"])
        )
        self.assertEqual(
            list(render_module.BUILD_PRODUCT_IDS),
            list(self.document["build_products"]),
        )

    def test_baseline_build_products_are_exactly_the_five_product_model(self) -> None:
        products = supported_build_products()
        self.assertEqual(
            tuple(product.build_product_id for product in products),
            (
                "android-nonprod-apk",
                "android-prod-apk",
                "ios-nonprod-app",
                "ios-prod-app",
                "web-shared",
            ),
        )
        self.assertEqual(
            application_id_for_build_product("web-shared"),
            "com.leadwise.quwoquan.web",
        )
        self.assertEqual(
            next(
                product.distribution_class
                for product in products
                if product.build_product_id == "android-prod-apk"
            ),
            "store",
        )

    def test_application_identity_matrix_isolated_by_profile_and_mode(self) -> None:
        """同 profile 环境共享身份，不同 profile/mode 互不覆盖。"""

        self.assertEqual(supported_build_profiles(), ("nonprod", "prod"))
        self.assertEqual(build_profile_for_environment("alpha"), "nonprod")
        self.assertEqual(build_profile_for_environment("beta"), "nonprod")
        self.assertEqual(build_profile_for_environment("gamma"), "nonprod")
        self.assertEqual(build_profile_for_environment("prod"), "prod")
        for platform in supported_identity_platforms():
            seen: dict[str, tuple[str, str]] = {}
            for build_profile in supported_build_profiles():
                for build_mode in supported_build_modes():
                    identity = resolve_app_identity(
                        platform=platform,
                        build_profile=build_profile,
                        build_mode=build_mode,
                    )
                    self.assertNotIn(
                        identity.application_id,
                        seen,
                        f"{platform} {build_profile}/{build_mode} collides with "
                        f"{seen.get(identity.application_id)}",
                    )
                    seen[identity.application_id] = (build_profile, build_mode)
                    self.assertTrue(identity.display_name)
            for build_mode in supported_build_modes():
                nonprod_ids = {
                    resolve_app_identity(
                        platform=platform,
                        environment=environment,
                        build_mode=build_mode,
                    ).application_id
                    for environment in ("alpha", "beta", "gamma")
                }
                self.assertEqual(len(nonprod_ids), 1)

    def test_generated_identity_projection_matches_metadata(self) -> None:
        contract = self.document["application_identity"]
        generated = json.loads(
            (ROOT / "quwoquan_app/android/app/app_identity.generated.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(generated["buildProfiles"], ["nonprod", "prod"])
        self.assertEqual(
            generated["environmentProfiles"],
            {
                "alpha": "nonprod",
                "beta": "nonprod",
                "gamma": "nonprod",
                "prod": "prod",
            },
        )
        for build_profile in contract["build_profile_suffixes"]:
            for build_mode in contract["build_mode_suffixes"]:
                identity = generated["identities"]["android"][
                    f"{build_profile}/{build_mode}"
                ]
                self.assertEqual(
                    identity["applicationId"],
                    contract["base_application_ids"]["android"]["value"]
                    + contract["build_profile_suffixes"][build_profile]
                    + contract["build_mode_suffixes"][build_mode],
                )
        android_manifest = ANDROID_MANIFEST_PATH.read_text(encoding="utf-8")
        self.assertNotIn("android:taskAffinity", android_manifest)

        for build_profile in contract["build_profile_suffixes"]:
            identity_source = (
                ROOT / f"quwoquan_app/ios/Flutter/Identity/{build_profile}.xcconfig"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "QWQ_PROFILE_BUNDLE_ID_SUFFIX = "
                + contract["build_profile_suffixes"][build_profile],
                identity_source,
            )
            for build_mode in contract["build_mode_suffixes"]:
                configuration = f"{build_mode.title()}-{build_profile}"
                source = (
                    ROOT / f"quwoquan_app/ios/Flutter/{configuration}.xcconfig"
                ).read_text(encoding="utf-8")
                self.assertIn(
                    f"Pods-Runner.{build_mode}-{build_profile}.xcconfig",
                    source,
                )
                self.assertNotIn("Pods-RunnerTests", source)
                self.assertIn(
                    "QWQ_MODE_BUNDLE_ID_SUFFIX ="
                    + (
                        f" {contract['build_mode_suffixes'][build_mode]}"
                        if contract["build_mode_suffixes"][build_mode]
                        else ""
                    ),
                    source,
                )

    def test_prod_release_identity_is_the_registered_base_id(self) -> None:
        contract = self.document["application_identity"]
        for platform in supported_identity_platforms():
            identity = resolve_app_identity(
                platform=platform, environment="prod", build_mode="release"
            )
            self.assertEqual(
                identity.application_id,
                contract["base_application_ids"][platform]["value"],
            )
            self.assertEqual(
                identity.display_name, contract["display_name_base"]
            )

    def test_android_prod_id_is_registered_external_fact_and_ios_is_open(
        self,
    ) -> None:
        android = resolve_app_identity(
            platform="android", environment="prod", build_mode="release"
        )
        self.assertTrue(android.registered)
        self.assertEqual(android.application_id, "com.leadwise.quwoquan")
        # iOS App Store 正式 bundle ID 尚未登记外部事实：registered 必须为
        # False，store promotable 由消费方阻断（OPEN 承接，不得占位上架）。
        ios = resolve_app_identity(
            platform="ios", environment="prod", build_mode="release"
        )
        self.assertFalse(ios.registered)

    def test_unknown_identity_dimensions_fail_instead_of_guessing(self) -> None:
        with self.assertRaises(AppIdentityError):
            resolve_app_identity(
                platform="harmony", environment="prod", build_mode="release"
            )
        with self.assertRaises(AppIdentityError):
            resolve_app_identity(
                platform="android", environment="prod-gray", build_mode="release"
            )
        with self.assertRaises(AppIdentityError):
            resolve_app_identity(
                platform="android", environment="prod", build_mode="jit"
            )

    def test_dart_target_environment_matches_launch_manifest_metadata(self) -> None:
        launch_manifest = load_json_yaml(LAUNCH_MANIFEST_PATH)
        expected = launch_manifest["target_environment"]
        source = DART_RESOLVER_PATH.read_text(encoding="utf-8")
        for target, environment in expected.items():
            self.assertIn(f"'{target}': '{environment}'", source)
        # Dart 侧不得引入 metadata 未声明的 target。
        self.assertEqual(source.count("-local':"), 3)
        self.assertEqual(source.count("'prod-"), 2)


class InstallLaunchPathMatrixTest(unittest.TestCase):
    """有效安装启动路径矩阵只从 canonical metadata 推导（DEC-004）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = enumerate_valid_install_launch_paths()
        cls.tuples = {
            (
                path.environment,
                path.platform,
                path.build_mode,
                path.distribution_class,
                path.launch_provenance,
            )
            for path in cls.paths
        }

    def test_matrix_is_derivable_and_deduplicated(self) -> None:
        self.assertGreater(len(self.paths), 0)
        self.assertEqual(len(self.paths), len(self.tuples))

    def test_matrix_contains_the_canonical_golden_paths(self) -> None:
        # Prod 市场安装后图标冷启动（正向黄金路径）。
        self.assertIn(
            ("prod", "android", "release", "store", "icon_cold_launch"),
            self.tuples,
        )
        self.assertIn(
            ("prod", "ios", "release", "store", "release_package"),
            self.tuples,
        )
        # 受管字面 flutter run 经 launcher dispatcher 归一化为 canonical_launcher
        # 的 Debug 开发面，与官网 APK 下载安装。
        self.assertIn(
            ("alpha", "ios", "debug", "dev_direct", "canonical_launcher"),
            self.tuples,
        )
        self.assertIn(
            ("prod", "android", "release", "official_web", "icon_cold_launch"),
            self.tuples,
        )
        self.assertIn(
            ("prod", "web", "release", "hosted_web", "icon_cold_launch"),
            self.tuples,
        )

    def test_matrix_never_contains_debug_store_or_cross_platform_paths(
        self,
    ) -> None:
        for path in self.paths:
            if path.distribution_class in RELEASE_ONLY_CLASSES:
                self.assertEqual(path.build_mode, "release", path)
            if path.build_mode == "debug":
                self.assertIn(
                    path.distribution_class,
                    {"dev_direct", "simulator", "registered_device"},
                    path,
                )
            if path.distribution_class == "official_web":
                self.assertEqual(path.platform, "android", path)
            if path.distribution_class == "hosted_web":
                self.assertEqual(path.platform, "web", path)

    def test_workspace_launch_provenances_are_non_promotable(self) -> None:
        for path in self.paths:
            if path.launch_provenance in {
                "canonical_launcher",
                "workspace_ide_debug",
            }:
                self.assertFalse(path.promotable, path)
                self.assertIn(
                    path.distribution_class,
                    {"dev_direct", "simulator", "registered_device"},
                    path,
                )

    def test_promotable_paths_are_release_only_promotable_classes(self) -> None:
        for path in self.paths:
            if path.promotable:
                self.assertEqual(path.build_mode, "release", path)
                self.assertIn(
                    path.distribution_class, RELEASE_ONLY_CLASSES, path
                )


if __name__ == "__main__":
    unittest.main()
