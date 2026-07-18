from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli.lib.dev_up import (
    ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
    app_target_for_env,
    deployment_render_root,
    env_cache_target_root,
    observability_runtime_logs_root,
    pick_dev_up_env,
    resolve_app_endpoint_overrides,
    run_root,
    runtime_env_for_dev_env,
    target_process_root,
)
from quwoquan_ops.cli.lib.output_paths import certificate_export_dir
from quwoquan_ops.cli.lib.environment_topology import load_environment_topology
from quwoquan_ops.cli.lib.local_media_origin import LocalMediaOriginHandler
from quwoquan_ops.cli.lib.mock_public_plane import MockPublicPlaneHandler
from quwoquan_ops.cli.stackctl import _health_checks_for_target, _seeded_media_surface_tier_command

ROOT = Path(__file__).resolve().parents[4]
_ASSISTANT_BETA_GATEWAY_PATH = (
    ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance"
    / "service_ops"
    / "assistant-service"
    / "smoke"
    / "dev_assistant_beta_gateway.py"
)
_ASSISTANT_BETA_GATEWAY_SPEC = importlib.util.spec_from_file_location(
    "assistant_beta_gateway",
    _ASSISTANT_BETA_GATEWAY_PATH,
)
if _ASSISTANT_BETA_GATEWAY_SPEC is None or _ASSISTANT_BETA_GATEWAY_SPEC.loader is None:
    raise RuntimeError(f"cannot load assistant beta gateway: {_ASSISTANT_BETA_GATEWAY_PATH}")
_ASSISTANT_BETA_GATEWAY_MODULE = importlib.util.module_from_spec(
    _ASSISTANT_BETA_GATEWAY_SPEC
)
_ASSISTANT_BETA_GATEWAY_SPEC.loader.exec_module(_ASSISTANT_BETA_GATEWAY_MODULE)
AssistantBetaGateway = _ASSISTANT_BETA_GATEWAY_MODULE.AssistantBetaGateway
app_message_unread_count = _ASSISTANT_BETA_GATEWAY_MODULE.app_message_unread_count


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpTest(unittest.TestCase):
    def test_alpha_android_physical_uses_plain_localhost_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "alpha",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://localhost:17000",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://localhost:17000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://localhost:17100",
        )

    def test_beta_android_emulator_uses_local_loopback_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_emulator",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("beta"), "beta-local")
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://beta-api.localhost:18000",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://beta-api.localhost:18000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://beta-image.localhost:18100",
        )

    def test_beta_android_physical_uses_local_loopback_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://beta-api.localhost:18000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://beta-image.localhost:18100",
        )

    def test_android_local_envs_use_manifest_ports_without_emulator_host(self) -> None:
        topology = load_environment_topology()
        cases = {
            "alpha": (
                "https://localhost:17000",
                "https://localhost:17000/legal",
                "https://localhost:17100",
            ),
            "beta": (
                "https://beta-api.localhost:18000",
                "https://beta-api.localhost:18000/legal",
                "https://beta-image.localhost:18100",
            ),
            "gamma": (
                "https://gamma-api.localhost:19000",
                "https://gamma-api.localhost:19000/legal",
                "https://gamma-image.localhost:19100",
            ),
            "prod-sim": (
                "https://prod-api.localhost:20000",
                "https://prod-api.localhost:20000/legal",
                "https://prod-image.localhost:20100",
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
        self.assertEqual(overrides["mediaImageBaseUrl"], "https://cdn.quwoquan.com")
        self.assertEqual(overrides["mediaUploadBaseUrl"], "https://upload.quwoquan.com")
        self.assertNotIn("118.31.239.122", "\n".join(overrides.values()))
        self.assertNotIn("10.0.2.2", "\n".join(overrides.values()))

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
            "https://gamma-api.quwoquan-env.test:19000",
        )
        self.assertEqual(
            overrides["legalBaseUrl"],
            "https://gamma-api.quwoquan-env.test:19000/legal",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://gamma-image.quwoquan-env.test:19100",
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
                    deploy_root / "gamma-local/rendered",
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
                    deploy_root / "gamma-local/certificates",
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

    def test_local_media_origin_resolves_conversation_avatar_alias(self) -> None:
        handler = LocalMediaOriginHandler.__new__(LocalMediaOriginHandler)
        # alpha / prod-sim 启用 alias 时才会解析占位会话头像。
        handler.conversation_avatar_alias_enabled = True
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_002/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        )
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_006/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png",
        )
        self.assertIsNone(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png"
            ),
        )
        self.assertIsNone(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_11/v1/mock.png"
            ),
        )
        self.assertIsNone(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_12/v1/mock.png"
            ),
        )
        self.assertIsNone(handler._resolve_alias("/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"))

    def test_local_media_origin_alias_disabled_by_default(self) -> None:
        handler = LocalMediaOriginHandler.__new__(LocalMediaOriginHandler)
        # gamma-local 默认关闭 alias：会话占位路径不再被改写。
        self.assertIsNone(
            handler._resolve_alias("/media/avatar/conversation/conv_002/v1/mock.png")
        )
        self.assertIsNone(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png"
            )
        )

    def test_local_media_origin_supports_byte_range_probe(self) -> None:
        self.assertEqual(
            LocalMediaOriginHandler._parse_byte_range("bytes=0-1", 1128375),
            (0, 1),
        )

    def test_stackctl_media_health_checks_include_video_range(self) -> None:
        topology = load_environment_topology()
        checks = _health_checks_for_target(topology, "alpha-local", "media")
        video_check = next(
            item
            for item in checks
            if item["name"] == "media-public-content-video-primary"
        )
        self.assertEqual(video_check["headers"], {"Range": "bytes=0-1"})
        self.assertEqual(video_check["expectedStatus"], 206)
        self.assertEqual(video_check["expectedContentTypePrefix"], "video/")
        self.assertIn(
            "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4",
            video_check["url"],
        )

    def test_stackctl_t4_blocks_on_full_seeded_media_surface(self) -> None:
        for env_name in ("alpha", "beta", "gamma"):
            with self.subTest(env_name=env_name):
                command = _seeded_media_surface_tier_command(env_name, f"{env_name}-local")
                self.assertIsNotNone(command)
                assert command is not None
                argv = command["argv"]
                self.assertEqual(command["name"], "seeded-media-surface")
                self.assertIn("quwoquan_ops/gate/verify_alpha_media_fixture_surface.py", argv)
                self.assertIn("--avatar-base-url", argv)
                self.assertIn(f"https://{env_name}-avatar.quwoquan-env.test", " ".join(argv))
                self.assertIn("--media-base-url", argv)
                self.assertIn(f"https://{env_name}-image.quwoquan-env.test", " ".join(argv))
                self.assertIn("--video-base-url", argv)
                self.assertIn(f"https://{env_name}-video.quwoquan-env.test", " ".join(argv))

    def test_alpha_local_checks_current_app_group_avatar_contract(self) -> None:
        script = (
            ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png",
            script,
        )
        self.assertIn(
            "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png",
            script,
        )

    def test_beta_manual_uses_range_aware_media_origin(self) -> None:
        script = (ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("quwoquan_ops/cli/lib/local_media_origin.py", script)
        self.assertIn("beta_manual_wait_http_range_ok", script)
        self.assertNotIn("python3 -m http.server", script)

    def test_android_local_debug_ca_is_required_for_supported_launchers(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        alpha_run = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
            "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED",
        )
        self.assertIn(ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV, build_gradle)
        self.assertIn("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1", alpha_run)
        self.assertIn("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1", beta_manual)

    def test_plain_android_flutter_run_is_env_package_backed(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        alpha_script = (
            ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("tasks.withType<FlutterTask>()", build_gradle)
        self.assertIn('"APP_RUNTIME_ENV" to "alpha"', build_gradle)
        self.assertIn(
            '"CLOUD_GATEWAY_BASE_URL" to "https://localhost:17000"',
            build_gradle,
        )
        self.assertIn(
            '"APP_LEGAL_BASE_URL" to "https://localhost:17000/legal"',
            build_gradle,
        )
        self.assertIn(
            '"MEDIA_IMAGE_CDN_BASE_URL" to "https://localhost:17100"',
            build_gradle,
        )
        self.assertIn("prepareAndroidLocalAlphaStack", build_gradle)
        self.assertIn(
            'environment("QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP", "skip")',
            build_gradle,
        )
        self.assertIn("prepareAndroidLocalAdbReverse", build_gradle)
        self.assertIn("android.adbExecutable", build_gradle)
        self.assertIn('"reverse",', build_gradle)
        self.assertIn("quwoquan_ops/cli/lib/tls_reverse_proxy.py", alpha_script)
        self.assertIn("ensure_public_hosts_mapping", alpha_script)
        self.assertIn("security add-trusted-cert", alpha_script)
        self.assertIn("macos_login_keychain_trust_is_current", alpha_script)
        self.assertIn("QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST", alpha_script)
        self.assertIn("install-ios-simulator-ca", alpha_script)
        self.assertIn("--simulator-udid", alpha_script)
        self.assertNotIn("simctl keychain booted add-root-cert", alpha_script)
        self.assertIn("IP.2 = 10.0.2.2", alpha_script)
        self.assertNotIn("--resolve", alpha_script)
        self.assertNotIn("curl -k", alpha_script)
        self.assertNotIn("docker.io/library/caddy", alpha_script)

    def test_start_app_instance_accepts_legal_base_url_override(self) -> None:
        script = (
            ROOT / "quwoquan_app/scripts/device/start_app_instance.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--legal-base-url", script)
        self.assertIn("APP_LEGAL_BASE_URL", script)

    def test_app_env_defines_derive_legal_base_from_gateway_override(self) -> None:
        script = ROOT / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"
        result = subprocess.run(
            [
                "python3",
                str(script),
                "--env",
                "alpha",
                "--format",
                "json",
                "--gateway-base-url",
                "https://localhost:17000",
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        defines = json.loads(result.stdout)
        self.assertEqual(
            defines["APP_LEGAL_BASE_URL"],
            "https://localhost:17000/legal",
        )

    def test_prod_app_env_defines_keep_canonical_legal_base(self) -> None:
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
                "https://118.31.239.122:19000",
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        defines = json.loads(result.stdout)
        self.assertEqual(
            defines["APP_LEGAL_BASE_URL"],
            "https://quwoquan.com/legal",
        )

    def test_plain_ios_flutter_run_prepares_alpha_https_stack(self) -> None:
        project = (
            ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
        ).read_text(encoding="utf-8")
        prepare_script = (
            ROOT / "quwoquan_app/scripts/ios/prepare_alpha_local_https.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("Prepare Alpha HTTPS Local Plane", project)
        self.assertIn("../scripts/ios/prepare_alpha_local_https.sh", project)
        self.assertIn("QWQ_IOS_LOCAL_AUTO_PREPARE", prepare_script)
        self.assertIn("APP_RUNTIME_ENV=", prepare_script)
        self.assertIn("start_alpha_mock_stack.sh\" up", prepare_script)
        self.assertIn("QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST=skip", prepare_script)

    def test_android_local_network_security_forbids_cleartext(self) -> None:
        debug_config = (
            ROOT
            / "quwoquan_app/android/app/src/debug/res/xml/beta_debug_network_security_config.xml"
        ).read_text(encoding="utf-8")
        profile_config = (
            ROOT
            / "quwoquan_app/android/app/src/profile/res/xml/beta_debug_network_security_config.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('cleartextTrafficPermitted="false"', debug_config)
        self.assertIn('cleartextTrafficPermitted="false"', profile_config)
        self.assertNotIn('cleartextTrafficPermitted="true"', debug_config)
        self.assertNotIn('cleartextTrafficPermitted="true"', profile_config)
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

    def test_android_dart_http_client_trusts_packaged_local_ca(self) -> None:
        app_bootstrap = (ROOT / "quwoquan_app/lib/app_bootstrap.dart").read_text(
            encoding="utf-8"
        )
        local_https_trust = (
            ROOT / "quwoquan_app/lib/core/platform/local_dev_https_trust_io.dart"
        ).read_text(encoding="utf-8")
        main_activity = (
            ROOT
            / "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
        ).read_text(encoding="utf-8")
        self.assertIn("LocalDevHttpsTrust.installForCurrentRuntime()", app_bootstrap)
        self.assertIn("_installLocalDevHttpsTrustBeforeMediaClients()", app_bootstrap)
        self.assertIn("startupPrerequisites: startupPrerequisites", app_bootstrap)
        self.assertNotIn("_installLocalDevHttpsTrustAfterFirstFrame", app_bootstrap)
        self.assertIn(
            "SecurityContext.defaultContext.setTrustedCertificatesBytes",
            local_https_trust,
        )
        self.assertNotIn("badCertificateCallback", local_https_trust)
        self.assertIn("localEnvDebugRootCertificate", main_activity)
        self.assertIn("local_env_debug_root", main_activity)

    def test_image_cache_managers_use_default_security_context(self) -> None:
        image_cache_controller = (
            ROOT
            / "quwoquan_app/lib/core/media/app_image_cache_controller.dart"
        ).read_text(encoding="utf-8")
        trusted_http_file_service = (
            ROOT
            / "quwoquan_app/lib/core/platform/trusted_http_file_service_io.dart"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "createTrustedHttpFileService", image_cache_controller
        )
        self.assertIn("IOClient", trusted_http_file_service)
        self.assertIn(
            "HttpClient(context: SecurityContext.defaultContext)",
            trusted_http_file_service,
        )

    def test_alpha_local_clears_repo_owned_stale_reserved_port_listeners(self) -> None:
        alpha_script = (
            ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("stop_alpha_reserved_listeners", alpha_script)
        self.assertIn("stop_repo_listener_on_port", alpha_script)
        self.assertIn('lsof -nP -tiTCP:"$port" -sTCP:LISTEN', alpha_script)
        self.assertIn("quwoquan_ops/cli/lib/mock_public_plane.py", alpha_script)
        self.assertIn("quwoquan_ops/cli/lib/tls_reverse_proxy.py", alpha_script)

    def test_gamma_local_mirror_keeps_deployment_material_out_of_output(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        gamma_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/rendered"',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"',
            gamma_script,
        )
        self.assertIn(
            '/data/caddy/pki/authorities/local/root.crt',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_CONFIG_ROOT="${LOCAL_GAMMA_DEPLOY_RENDER_ROOT}/config-root"',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/process"',
            gamma_script,
        )
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
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'export LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE=', gamma_script
        )
        self.assertIn(
            "copy_service_package_config notification-service notification-service",
            gamma_script,
        )
        self.assertIn("  notification-service\n)", gamma_script)
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
            'LOCAL_GAMMA_NOTIFICATION_PORT:-19320}:18087', gamma_compose
        )
        self.assertIn(
            "ASSISTANT_NOTIFICATION_BASE_URL: \"http://notification-service:18087\"",
            gamma_compose,
        )

    def test_gamma_local_search_backfill_blocks_incomplete_read_model(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("--request-timeout \"$LOCAL_GAMMA_SEARCH_BACKFILL_REQUEST_TIMEOUT\"", gamma_script)
        self.assertIn(
            "gamma startup is blocked because /search would be incomplete",
            gamma_script,
        )
        self.assertNotIn("WARN: skip search backfill", gamma_script)
        self.assertNotIn("WARN: search backfill failed", gamma_script)
        self.assertIn("_id: profilePost", gamma_script)
        self.assertIn("_id: sharedPost", gamma_script)

    def test_local_launchers_use_canonical_output_roots_without_retired_fallbacks(self) -> None:
        beta_stack = (
            ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")
        beta_start = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        beta_stop = (
            ROOT / "quwoquan_app/scripts/device/stop_app_beta_manual.sh"
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

    def test_alpha_mock_public_plane_ops_visit_and_experiment_endpoints(self) -> None:
        handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
        MockPublicPlaneHandler.ops_visits = []
        MockPublicPlaneHandler.ops_experiment_assignments = {}
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
        assignment = handler._resolve_experiment_assignment("discovery_feed_v3", "user-1")
        self.assertEqual(assignment["experimentId"], "discovery_feed_v3")
        experiment_stats = handler._build_experiment_stats("discovery_feed_v3")
        self.assertEqual(experiment_stats["assignedSubjects"], 1)

    def test_alpha_mock_public_plane_serves_legal_static_package(self) -> None:
        previous = {
            "mode": MockPublicPlaneHandler.mode,
            "runtime_env": MockPublicPlaneHandler.runtime_env,
            "legal_static_root": MockPublicPlaneHandler.legal_static_root,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = legal_static.build_package("alpha", output_root=Path(tmp_dir))
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

    def test_alpha_mock_public_plane_default_legal_root_uses_output_layout(self) -> None:
        previous_root = MockPublicPlaneHandler.legal_static_root
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            payload = legal_static.build_package("alpha", output_root=output_root)
            package_root = Path(payload["packageDir"]).parent
            handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
            handler.runtime_env = "alpha"
            MockPublicPlaneHandler.legal_static_root = ""
            try:
                with mock.patch(
                    "quwoquan_ops.cli.lib.mock_public_plane.legal_static_release_dir",
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

    def test_beta_gateway_notification_fixture_family(self) -> None:
        handler = AssistantBetaGateway.__new__(AssistantBetaGateway)
        listing = handler._fixture_response("/app-messages")
        self.assertIsInstance(listing, dict)
        self.assertGreaterEqual(listing["unreadCount"], 0)
        unread = handler._fixture_response("/app-messages/unread-count")
        self.assertEqual(unread["unreadCount"], listing["unreadCount"])
        aggregate = handler._fixture_response("/notifications/unread-count")
        self.assertEqual(aggregate["unreadCount"], listing["unreadCount"])
        first_message = listing["items"][0]
        message_id = first_message["messageId"]
        detail = handler._fixture_response(f"/app-messages/{message_id}")
        self.assertEqual(detail["messageId"], message_id)
        read = handler._fixture_response(f"/app-messages/{message_id}/read")
        self.assertTrue(read["read"])

    def test_beta_gateway_unread_count_falls_back_to_message_scan(self) -> None:
        notification = {
            "appMessages": [
                {"messageId": "a", "read": False},
                {"messageId": "b", "read": True},
                {"messageId": "c", "read": False},
            ]
        }
        self.assertEqual(app_message_unread_count(notification), 2)

    def test_beta_gateway_intersection_fixture_family(self) -> None:
        handler = AssistantBetaGateway.__new__(AssistantBetaGateway)
        summary = handler._fixture_response("/content/intersections/summary")
        self.assertGreater(summary["totalCount"], 0)
        listing = handler._fixture_response("/content/intersections", "dimension=interest&limit=5")
        self.assertTrue(all(item["dimension"] == "interest" for item in listing["items"]))
        feed = handler._fixture_response(
            "/content/feed/intersections",
            "channel=recommend&limit=2",
        )
        self.assertEqual(len(feed["items"]), 2)
        self.assertEqual(
            handler._fixture_response("/content/intersections/visit"),
            {"accepted": True},
        )
        self.assertEqual(
            handler._fixture_response("/content/intersections/exposure"),
            {"accepted": True},
        )


if __name__ == "__main__":
    unittest.main()
