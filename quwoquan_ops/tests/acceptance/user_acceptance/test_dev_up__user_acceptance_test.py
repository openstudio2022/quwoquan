from __future__ import annotations

import io
import json
import re
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli.lib.dev_up import (
    app_target_for_env,
    deployment_render_root,
    detect_device_kind,
    env_cache_target_root,
    observability_runtime_logs_root,
    pick_dev_up_env,
    resolve_app_endpoint_overrides,
    run_root,
    runtime_env_for_dev_env,
    target_process_root,
)
from quwoquan_ops.cli.lib.output_paths import (
    certificate_export_dir,
    legal_static_deployment_package_dir,
)
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_media_origin import LocalMediaOriginHandler
from quwoquan_ops.cli.lib.mock_public_plane import MockPublicPlaneHandler
from quwoquan_ops.cli.stackctl import (
    _health_checks_for_target,
    _target_media_preflight_profile_command,
)

ROOT = Path(__file__).resolve().parents[4]
class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpTest(unittest.TestCase):
    def test_detect_device_kind_distinguishes_ios_simulator_and_physical_device(
        self,
    ) -> None:
        self.assertEqual(
            detect_device_kind(
                "SIMULATOR-UDID",
                target_platform="ios",
                emulator=True,
            ),
            "ios-simulator",
        )
        self.assertEqual(
            detect_device_kind(
                "PHYSICAL-UDID",
                target_platform="ios",
                emulator=False,
            ),
            "ios-physical",
        )

    def test_alpha_android_physical_keeps_canonical_public_authorities(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "alpha",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://api.alpha.quwoquan.com:17000",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://alpha.quwoquan.com:17000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://cdn.alpha.quwoquan.com:17100/media/image",
        )

    def test_beta_android_emulator_keeps_canonical_public_authorities(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_emulator",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("beta"), "beta-local")
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://api.beta.quwoquan.com:18000",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://beta.quwoquan.com:18000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://cdn.beta.quwoquan.com:18100/media/image",
        )

    def test_beta_android_physical_keeps_canonical_public_authorities(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://api.beta.quwoquan.com:18000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://cdn.beta.quwoquan.com:18100/media/image",
        )

    def test_android_local_envs_use_canonical_topology_projection(self) -> None:
        topology = load_environment_topology()
        cases = {
            "alpha": (
                "https://api.alpha.quwoquan.com:17000",
                "https://alpha.quwoquan.com:17000/legal",
                "https://cdn.alpha.quwoquan.com:17100/media/image",
            ),
            "beta": (
                "https://api.beta.quwoquan.com:18000",
                "https://beta.quwoquan.com:18000/legal",
                "https://cdn.beta.quwoquan.com:18100/media/image",
            ),
            "gamma": (
                "https://api.gamma.quwoquan.com:19000",
                "https://gamma.quwoquan.com:19000/legal",
                "https://cdn.gamma.quwoquan.com:19100/media/image",
            ),
            "prod-sim": (
                "https://api.sim.quwoquan.com:20000",
                "https://sim.quwoquan.com:20000/legal",
                "https://cdn.sim.quwoquan.com:20100/media/image",
            ),
        }
        for env_name, expected in cases.items():
            with self.subTest(env_name=env_name):
                overrides = resolve_app_endpoint_overrides(
                    env_name,
                    "android_physical",
                    topology=topology,
                )
                self.assertEqual(overrides["gatewayBaseUrl"], expected[0])
                self.assertEqual(overrides["legalBaseUrl"], expected[1])
                self.assertEqual(overrides["mediaImageBaseUrl"], expected[2])
                self.assertNotIn("10.0.2.2", "\n".join(overrides.values()))

    def test_prod_android_keeps_hosted_public_addresses(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "prod",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(overrides["gatewayBaseUrl"], "https://api.quwoquan.com")
        self.assertEqual(overrides["legalBaseUrl"], "https://quwoquan.com/legal")
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://cdn.quwoquan.com/media/image",
        )
        self.assertEqual(overrides["mediaUploadBaseUrl"], "https://upload.quwoquan.com")
        joined = "\n".join(overrides.values())
        # 守卫必须覆盖任意裸 IP authority，而不是某一台历史主机的地址。
        self.assertIsNone(
            re.search(r"://(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?/", joined + "/"),
            joined,
        )
        self.assertNotIn("10.0.2.2", joined)

    def test_gamma_web_uses_local_gamma_public_bases(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "gamma",
            "web",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("gamma"), "gamma-local")
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://gamma.quwoquan.com:19000/api",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://gamma.quwoquan.com:19000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://cdn.gamma.quwoquan.com:19100/media/image",
        )

    def test_prod_sim_maps_to_prod_runtime_env(self) -> None:
        self.assertEqual(runtime_env_for_dev_env("prod-sim"), "prod")

    def test_local_runtime_roots_are_split_by_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "output"
            deploy_root = Path(tmp_dir) / "deploy"
            observability_root = Path(tmp_dir) / "obs-run"
            explicit_run_root = Path(tmp_dir) / "run"
            with mock.patch.dict(
                "os.environ",
                {
                    "QWQ_OUTPUT_ROOT": str(output_root),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                    "QWQ_OBSERVABILITY_RUN_ROOT": str(observability_root),
                    "QWQ_RUN_ROOT": str(explicit_run_root),
                },
                clear=False,
            ):
                self.assertEqual(
                    deployment_render_root("gamma-local"),
                    (deploy_root / "gamma-local/rendered").resolve(),
                )
                self.assertEqual(
                    env_cache_target_root("gamma", "gamma-local"),
                    output_root / "env/gamma/local/gamma-local/cache",
                )
                self.assertEqual(
                    observability_runtime_logs_root("gamma"),
                    observability_root / "logs/service",
                )
                self.assertEqual(run_root("gamma"), explicit_run_root)
                self.assertEqual(
                    target_process_root("gamma", "gamma-local"),
                    output_root / "env/gamma/local/gamma-local/process",
                )
                self.assertEqual(
                    certificate_export_dir("gamma-local"),
                    (deploy_root / "gamma-local/certificates").resolve(),
                )

    def test_local_runtime_roots_use_immutable_run_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "output"
            with mock.patch.dict(
                "os.environ",
                {
                    "QWQ_OUTPUT_ROOT": str(output_root),
                },
                clear=False,
            ):
                with mock.patch.dict(
                    "os.environ",
                    {
                        "QWQ_OBSERVABILITY_RUN_ROOT": "",
                        "QWQ_RUN_ROOT": "",
                    },
                    clear=False,
                ):
                    self.assertEqual(
                        observability_runtime_logs_root("beta"),
                        output_root / "env/beta/observability/local-beta-local/logs/service",
                    )
                    self.assertEqual(
                        run_root("beta"),
                        output_root / "env/beta/runs/local-beta-local",
                    )

    def test_prod_dev_up_uses_canonical_legal_base_url(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "prod",
            "ios_or_macos",
            topology=topology,
        )
        self.assertEqual(overrides["legalBaseUrl"], "https://quwoquan.com/legal")

    def test_pick_dev_up_env_requires_tty_when_missing(self) -> None:
        with (
            mock.patch("sys.stdin.isatty", return_value=False),
            mock.patch("sys.stderr.isatty", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "dev-up environment is missing"):
                pick_dev_up_env()

    def test_pick_dev_up_env_accepts_numeric_choice(self) -> None:
        with (
            mock.patch("sys.stdin", new=_TtyStringIO("2\n")),
            mock.patch("sys.stderr", new=_TtyStringIO()),
        ):
            self.assertEqual(
                pick_dev_up_env(("alpha", "beta", "gamma")),
                "beta",
            )

    def test_local_media_origin_does_not_own_business_avatar_aliases(self) -> None:
        handler = LocalMediaOriginHandler.__new__(LocalMediaOriginHandler)
        self.assertFalse(hasattr(handler, "_resolve_alias"))
        self.assertFalse(hasattr(handler, "conversation_avatar_alias_enabled"))

    def test_local_media_origin_supports_byte_range_probe(self) -> None:
        self.assertEqual(
            LocalMediaOriginHandler._parse_byte_range("bytes=0-1", 1128375),
            (0, 1),
        )

    def test_stackctl_media_health_does_not_enumerate_fixture_assets(self) -> None:
        topology = load_environment_topology()
        checks = _health_checks_for_target(topology, "alpha-local", "media")
        names = {str(item["name"]) for item in checks}
        self.assertIn("media-edge-health", names)
        self.assertFalse(
            any(name.startswith("media-public-") for name in names),
        )
        self.assertFalse(any(name.startswith("media-origin-") for name in names))

    def test_stackctl_runtime_media_requires_release_bound_video_canary(self) -> None:
        for env_name in ("alpha", "beta", "gamma"):
            with self.subTest(env_name=env_name):
                command = _target_media_preflight_profile_command(
                    f"{env_name}-local",
                    Path(f"/tmp/{env_name}-report"),
                )
                self.assertIsNotNone(command)
                assert command is not None
                argv = command["argv"]
                self.assertEqual(
                    command["name"],
                    f"{env_name}-local-release-video-canary-preflight",
                )
                self.assertIn(
                    "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
                    argv,
                )
                self.assertIn("--target", argv)
                self.assertIn(f"{env_name}-local", argv)
                self.assertNotIn("verify_alpha_media_fixture_surface.py", " ".join(argv))
                self.assertTrue(command["stopOnFailure"])

    def test_alpha_local_content_release_has_no_fixture_authorities(self) -> None:
        script = (
            ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("test_fixtures", script)
        self.assertNotIn("mock.png", script)

    def test_beta_manual_uses_release_owned_media_origin(self) -> None:
        script = (ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("quwoquan_ops/cli/lib/local_media_origin.py", script)
        self.assertIn('MEDIA_DIR="$CACHE_DIR/media"', script)
        self.assertIn("ship apply is the only writer of this directory", script)
        self.assertIn("path.is_symlink()", script)
        self.assertNotIn("contracts/metadata/_shared/test_fixtures", script)
        self.assertNotIn("fixture_photo_001", script)
        self.assertNotIn("python3 -m http.server", script)

    def test_android_launchers_use_system_public_ca_only(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        alpha_run = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
        ).read_text(encoding="utf-8")
        combined = build_gradle + alpha_run + beta_manual
        self.assertNotIn("QWQ_ANDROID_LOCAL_ENV_CA", combined)
        self.assertNotIn("local_env_debug_root", combined)
        self.assertIn("--allow-unprovisioned-system-trust", build_gradle)
        self.assertIn("--allow-unprovisioned-system-trust", alpha_run)

    def test_plain_android_flutter_run_is_env_package_backed(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        instance_launcher = (
            ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
        launcher_handoff_builder = (
            ROOT / "quwoquan_app/scripts/device/build_launcher_handoff.py"
        )
        launch_manifest_metadata = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
            ).read_text(encoding="utf-8")
        )
        handoff_result = subprocess.run(
            [
                "python3",
                str(launcher_handoff_builder),
                "--env",
                "prod",
                "--target",
                "prod-hosted",
                "--launch-mode",
                "user_acceptance",
            ],
            cwd=ROOT / "quwoquan_app",
            check=True,
            capture_output=True,
            text=True,
        )
        launcher_handoff = json.loads(handoff_result.stdout)
        effective_handoff = launcher_handoff["effectiveLaunchManifest"]
        effective_schema = launch_manifest_metadata["schemas"][
            "app_effective_launch_manifest"
        ]
        handoff_schema = launch_manifest_metadata["schemas"][
            "app_launcher_handoff"
        ]
        alpha_script = (
            ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("tasks.withType<FlutterTask>()", build_gradle)
        self.assertIn("verifyAndroidLocalLauncherContract", build_gradle)
        self.assertIn("requireCompleteRuntimeDartDefines", build_gradle)
        self.assertIn(
            'runtimeEnvironment in setOf("alpha", "beta", "gamma", "prod")',
            build_gradle,
        )
        self.assertIn(
            '"CLOUD_GATEWAY_BASE_URL"',
            build_gradle,
        )
        self.assertIn(
            '"APP_LEGAL_BASE_URL"',
            build_gradle,
        )
        self.assertIn(
            '"MEDIA_IMAGE_CDN_BASE_URL"',
            build_gradle,
        )
        self.assertNotIn("rewriteAlphaLocalTransport", build_gradle)
        self.assertNotIn("prepareAndroidLocalAlphaStack", build_gradle)
        self.assertNotIn("prepareAndroidLocalAdbReverse", build_gradle)
        self.assertNotIn('loadRuntimePackageDartDefines("alpha")', build_gradle)
        self.assertIn("android.adbExecutable", build_gradle)
        self.assertIn('"reverse",', build_gradle)
        self.assertIn("QWQ_CONSUMER_LEASE_ACQUIRED", build_gradle)
        self.assertIn("QWQ_ANDROID_LOCAL_PORTS", build_gradle)
        self.assertIn('bash "$APP_DIR/run.sh"', instance_launcher)
        self.assertIn("launch_release_artifact.py", instance_launcher)
        self.assertNotIn("build_launcher_handoff.py", instance_launcher)
        self.assertNotIn("flutter run", instance_launcher)
        self.assertEqual(
            launch_manifest_metadata["target_environment"]["prod-sim"],
            "prod",
        )
        self.assertEqual(
            launcher_handoff["entrypoint"],
            effective_schema["fields"]["entrypoint"]["const"],
        )
        self.assertEqual(
            launcher_handoff["entrypoint"],
            effective_handoff["entrypoint"],
        )
        self.assertEqual(
            launcher_handoff["schema"],
            handoff_schema["schema_value"],
        )
        self.assertEqual(
            set(launcher_handoff),
            set(handoff_schema["required_fields"]),
        )
        self.assertNotIn("QWQ_ANDROID_LOCAL_ENV_CA", instance_launcher)
        self.assertIn("--launch-receipt", instance_launcher)
        self.assertIn("--artifact-manifest", instance_launcher)
        self.assertIn("certificate_paths(TARGET)", alpha_script)
        self.assertIn("/etc/caddy/tls/fullchain.pem", alpha_script)
        self.assertNotIn("tls internal", alpha_script)
        self.assertNotIn("--resolve", alpha_script)
        self.assertNotIn("curl -k", alpha_script)

    def test_start_app_instance_accepts_legal_base_url_override(self) -> None:
        script = (
            ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--legal-base-url", script)
        self.assertIn("APP_LEGAL_BASE_URL", script)

    def test_app_env_defines_require_active_immutable_candidate_first(self) -> None:
        script = ROOT / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(
                "os.environ",
                {"QWQ_DEPLOY_WORK_ROOT": tmp_dir},
                clear=False,
            ):
                result = subprocess.run(
                    [
                        "python3",
                        str(script),
                        "--env",
                        "alpha",
                        "--format",
                        "json",
                    ],
                    cwd=str(ROOT),
                    text=True,
                    capture_output=True,
                    check=False,
                )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("packaged app runtime config not found", result.stderr)

    def test_prod_app_env_defines_reject_noncanonical_gateway_override(self) -> None:
        script = ROOT / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"
        result = subprocess.run(
            [
                "python3",
                str(script),
                "--env",
                "prod",
                "--format",
                "json",
                "--gateway-base-url",
                "https://192.0.2.10:19000",
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must equal canonical topology projection", result.stderr)

    def test_plain_ios_flutter_run_uses_system_store_without_app_trust_injection(self) -> None:
        project = (
            ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
        ).read_text(encoding="utf-8")
        prepare_defines = (
            ROOT / "quwoquan_app/scripts/ios/build_prepare_dart_defines.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Prepare Alpha HTTPS Local Plane", project)
        self.assertNotIn("Bundle Local HTTPS Trust Root", project)
        self.assertFalse(
            (ROOT / "quwoquan_app/scripts/ios/prepare_alpha_local_https.sh").exists()
        )
        self.assertIn("build_launcher_handoff.py", prepare_defines)
        self.assertIn('DIRECT_TARGET="${DIRECT_ENVIRONMENT}-local"', prepare_defines)
        self.assertIn('--target "$DIRECT_TARGET"', prepare_defines)
        self.assertIn("--launch-mode direct_flutter_run", prepare_defines)
        self.assertIn(
            'device-trust --target "$DIRECT_TARGET"',
            prepare_defines,
        )
        self.assertIn("--platform ios-simulator", prepare_defines)
        self.assertIn("--defer-endpoint-probe", prepare_defines)
        self.assertIn('${CONFIGURATION:-}" == Debug*', prepare_defines)
        self.assertIn("export FLUTTER_TARGET=", prepare_defines)
        self.assertIn("lib/main_prod.dart", prepare_defines)

    def test_local_device_builds_do_not_package_private_trust_roots(self) -> None:
        android_build = (
            ROOT / "quwoquan_app" / "android" / "app" / "build.gradle.kts"
        ).read_text(encoding="utf-8")

        self.assertFalse(
            (
                ROOT
                / "quwoquan_app"
                / "scripts"
                / "ios"
                / "prepare_local_https_trust_bundle.sh"
            ).exists()
        )
        self.assertNotIn("local_env_debug_root", android_build)
        self.assertNotIn("materialize-app-trust-bundle", android_build)

    def test_android_local_network_security_forbids_cleartext(self) -> None:
        self.assertFalse(
            (
                ROOT
                / "quwoquan_app/android/app/src/debug/res/xml/beta_debug_network_security_config.xml"
            ).exists()
        )
        self.assertFalse(
            (
                ROOT
                / "quwoquan_app/android/app/src/profile/res/xml/beta_debug_network_security_config.xml"
            ).exists()
        )
        debug_manifest = (
            ROOT / "quwoquan_app/android/app/src/debug/AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        profile_manifest = (
            ROOT / "quwoquan_app/android/app/src/profile/AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('android:usesCleartextTraffic="false"', debug_manifest)
        self.assertIn('android:usesCleartextTraffic="false"', profile_manifest)
        self.assertNotIn(
            'android:usesCleartextTraffic="true"',
            debug_manifest + profile_manifest,
        )

    def test_android_dart_http_client_has_no_private_ca_bridge(self) -> None:
        app_bootstrap = (
            ROOT
            / "quwoquan_app/lib/runtime/shell/startup/app_bootstrap.dart"
        ).read_text(encoding="utf-8")
        main_activity = (
            ROOT
            / "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn("LocalDevHttpsTrust", app_bootstrap)
        self.assertFalse(
            (
                ROOT
                / "quwoquan_app/lib/core/platform/local_dev_https_trust_io.dart"
            ).exists()
        )
        self.assertNotIn("localEnvDebugRootCertificate", main_activity)
        self.assertNotIn("local_env_debug_root", main_activity)

    def test_image_cache_managers_use_default_security_context(self) -> None:
        image_cache_controller = (
            ROOT
            / "quwoquan_app/lib/runtime/platform/media/app_image_cache_controller.dart"
        ).read_text(encoding="utf-8")
        trusted_http_file_service = (
            ROOT
            / "quwoquan_app/lib/runtime/platform/trusted_http_file_service_io.dart"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "createTrustedHttpFileService", image_cache_controller
        )
        self.assertIn("IOClient", trusted_http_file_service)
        self.assertIn(
            "HttpClient(context: SecurityContext.defaultContext)",
            trusted_http_file_service,
        )

    def test_gamma_local_mirror_keeps_deployment_material_out_of_output(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        gamma_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/rendered"',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"',
            gamma_script,
        )
        self.assertIn(
            'public_domain_tls.py" paths',
            gamma_script,
        )
        self.assertNotIn("tls internal", gamma_script)
        self.assertIn(
            'LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/process"',
            gamma_script,
        )
        self.assertIn("startup_attempt_receipt.py", gamma_script)
        self.assertNotIn("LOCAL_GAMMA_STACK_STATUS_REPORT", gamma_script)
        self.assertNotIn("stack_status.json", gamma_script)
        self.assertIn('-v "${LOCAL_GAMMA_CADDY_DATA_VOLUME}:/data" \\', gamma_script)
        self.assertIn('-v "${LOCAL_GAMMA_CADDY_CONFIG_VOLUME}:/config" \\', gamma_script)
        self.assertIn(
            '${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}:/data',
            gamma_compose,
        )
        self.assertIn(
            '${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}:/config',
            gamma_compose,
        )
        self.assertNotIn(".qwq_output/env/gamma/runtime", gamma_compose)
        self.assertNotIn(".qwq_output/env/gamma/local/gamma-local/pki", gamma_compose)
        self.assertIn("local-gamma-caddy-data:", gamma_compose)
        self.assertIn("local-gamma-caddy-config:", gamma_compose)

    def test_gamma_notification_composition_is_explicit_and_health_gated(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        gamma_compose = (
            ROOT
            / "quwoquan_service/services/notification-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        assistant_compose = (
            ROOT
            / "quwoquan_service/services/assistant-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn('image_key="LOCAL_GAMMA_${service_key}_IMAGE"', gamma_script)
        self.assertIn("validate_local_gamma_image_composition", gamma_script)
        self.assertIn(
            'copy_service_package_config "$service"',
            gamma_script,
        )
        self.assertIn(
            "from quwoquan_ops.cli.lib.immutable_image_composition import "
            "first_party_service_names",
            gamma_script,
        )
        self.assertIn(
            "active = set(first_party_service_names(root))",
            gamma_script,
        )
        self.assertIn(
            'services_root.glob("*/deploy/compose.yaml")',
            gamma_script,
        )
        self.assertIn("if path.parents[1].name in active", gamma_script)
        self.assertNotIn('find "$ROOT/quwoquan_service/services"', gamma_script)
        self.assertIn("probe_one notification-service", gamma_script)
        self.assertIn(
            'local notification_port="${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}"',
            gamma_script,
        )
        self.assertIn(
            "-e ASSISTANT_NOTIFICATION_BASE_URL=http://notification-service:18087 \\",
            gamma_script,
        )
        self.assertIn("  notification-service:\n", gamma_compose)
        self.assertIn(
            'QWQ_COMPOSE_NOTIFICATION_PORT:-19320}:18087', gamma_compose
        )
        self.assertIn(
            "ASSISTANT_NOTIFICATION_BASE_URL: \"http://notification-service:18087\"",
            assistant_compose,
        )
        self.assertIn('NOTIFICATION_REDIS_GENERAL_DB: "1"', gamma_compose)
        self.assertIn('NOTIFICATION_REDIS_REALTIME_DB: "4"', gamma_compose)

    def test_gamma_local_search_projection_is_owned_by_release_activation(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT", gamma_script)
        self.assertNotIn("WARN: skip search backfill", gamma_script)
        self.assertNotIn("WARN: search backfill failed", gamma_script)
        self.assertNotIn("_id: profilePost", gamma_script)
        self.assertNotIn("_id: sharedPost", gamma_script)
        self.assertIn(
            "immutable release activation owns business data and search projections",
            gamma_script,
        )

    def test_local_launchers_use_canonical_output_roots_without_retired_fallbacks(self) -> None:
        beta_stack = (
            ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")
        beta_start = (
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
        ).read_text(encoding="utf-8")
        beta_stop = (
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app_stop.sh"
        ).read_text(encoding="utf-8")
        gamma_start = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        prod_sim = (
            ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
        ).read_text(encoding="utf-8")
        combined = "\n".join((beta_stack, beta_start, beta_stop, gamma_start, prod_sim))

        for script in (beta_stack, beta_start, beta_stop, gamma_start, prod_sim):
            self.assertIn('QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT', script)
            self.assertIn('QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT', script)
        self.assertNotIn(".env.beta.local", beta_stack)
        self.assertNotIn(".qwq_output/env/beta/local/beta-local", combined)
        self.assertNotIn(".qwq_output/env/gamma/local/gamma-local", combined)
        self.assertNotIn(".qwq_output/env/prod/local/prod-sim", combined)
        self.assertIn('LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"', beta_start)
        self.assertIn('REPORT="${QWQ_RUN_ROOT}/app-beta-manual-report.json"', beta_start)
        self.assertIn('BETA_MANUAL_STATE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/process"', beta_start)
        self.assertIn('--rotate-ca', beta_stop)
        self.assertIn('volume rm -f "$TLS_PROXY_DATA_VOLUME" "$TLS_PROXY_CONFIG_VOLUME"', beta_stop)
        self.assertNotIn('rm -rf "$LOG_DIR"', beta_stop)
        self.assertIn('find "$LOG_DIR" -mindepth 1 -maxdepth 1 -delete', beta_stop)

    def test_alpha_mock_public_plane_ops_event_endpoints(self) -> None:
        handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
        MockPublicPlaneHandler.ops_event_ids = set()
        MockPublicPlaneHandler.ops_events = []
        ack = handler._record_ops_events(
            {
                "events": [
                    {
                        "eventId": "evt-1",
                        "eventType": "exposure",
                        "eventName": "page.enter",
                        "occurredAt": "2026-06-04T10:50:00Z",
                        "pageName": "discovery_page",
                        "surfaceId": "discovery.home",
                    }
                ]
            }
        )
        self.assertEqual(ack["acceptedCount"], 1)
        summary = handler._build_ops_event_summary({"pageName": ["discovery_page"]})
        self.assertEqual(summary["totalCount"], 1)
        drilldown = handler._build_ops_event_drilldown({"limit": ["5"]})
        self.assertEqual(drilldown["totalCount"], 1)
        self.assertEqual(drilldown["items"][0]["eventId"], "evt-1")

    def test_alpha_mock_public_plane_ops_visit_keeps_experiments_absent(self) -> None:
        handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
        MockPublicPlaneHandler.ops_visits = []
        record = handler._record_ops_visit(
            {
                "userId": "user-1",
                "targetType": "page",
                "targetKey": "discovery_recommend",
                "sessionId": "sess-1",
            }
        )
        self.assertEqual(record["visitCount"], 1)
        stats = handler._build_ops_visit_stats(
            {
                "targetType": ["page"],
                "targetKey": ["discovery_recommend"],
            }
        )
        self.assertEqual(stats["totalVisits"], 1)
        self.assertFalse(hasattr(handler, "_resolve_experiment_assignment"))
        self.assertFalse(hasattr(handler, "_build_experiment_stats"))

    def test_alpha_mock_public_plane_serves_legal_static_package(self) -> None:
        previous = {
            "mode": MockPublicPlaneHandler.mode,
            "runtime_env": MockPublicPlaneHandler.runtime_env,
            "legal_static_root": MockPublicPlaneHandler.legal_static_root,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                "os.environ",
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                package_root = legal_static_deployment_package_dir("alpha")
                payload = legal_static.build_package(
                    "alpha",
                    output_root=package_root,
                )
            MockPublicPlaneHandler.mode = "api"
            MockPublicPlaneHandler.runtime_env = "alpha"
            MockPublicPlaneHandler.legal_static_root = str(
                Path(payload["packageDir"]) / "public"
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), MockPublicPlaneHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urllib.request.urlopen(
                    f"{base_url}/legal/user-agreement",
                    timeout=5,
                ) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("text/html", response.headers["Content-Type"])
                    self.assertIn("用户协议", body)
                    self.assertNotIn("mock route is not ready", body)
                request = urllib.request.Request(
                    f"{base_url}/legal/privacy-policy",
                    method="HEAD",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("text/html", response.headers["Content-Type"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                MockPublicPlaneHandler.mode = previous["mode"]
                MockPublicPlaneHandler.runtime_env = previous["runtime_env"]
                MockPublicPlaneHandler.legal_static_root = previous[
                    "legal_static_root"
                ]

    def test_alpha_mock_public_plane_default_legal_root_uses_deployment_workspace(self) -> None:
        previous_root = MockPublicPlaneHandler.legal_static_root
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                "os.environ",
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                package_root = legal_static_deployment_package_dir("alpha")
                legal_static.build_package(
                    "alpha",
                    output_root=package_root,
                )
            handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
            handler.runtime_env = "alpha"
            MockPublicPlaneHandler.legal_static_root = ""
            try:
                with mock.patch(
                    "quwoquan_ops.cli.lib.mock_public_plane.legal_static_deployment_package_dir",
                    return_value=package_root,
                ):
                    self.assertEqual(
                        handler._legal_root(),
                        (package_root / "current" / "public").resolve(),
                    )
                    self.assertEqual(
                        handler._resolve_legal_static_path("/legal/user-agreement"),
                        (
                            package_root
                            / "current"
                            / "public"
                            / "legal"
                            / "user-agreement"
                        ).resolve(),
                    )
            finally:
                MockPublicPlaneHandler.legal_static_root = previous_root


if __name__ == "__main__":
    unittest.main()
