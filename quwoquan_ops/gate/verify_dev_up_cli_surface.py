#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.dev_up import (
    deployment_render_root,
    env_cache_target_root,
    observability_runtime_logs_root,
    resolve_app_endpoint_overrides,
    run_root,
    target_process_root,
)
from quwoquan_ops.cli.lib.output_paths import certificate_export_dir
from quwoquan_ops.cli.lib.environment_topology import load_environment_topology

STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    issues: list[str] = []

    up_help = run(["python3", str(STACKCTL), "up", "--help"])
    if up_help.returncode != 0:
        issues.append("stackctl up --help failed")
        help_stdout = up_help.stdout + up_help.stderr
    else:
        help_stdout = up_help.stdout

    if "--env" not in help_stdout:
        issues.append("stackctl up --help must expose --env")
    if "--gateway-base-url" in help_stdout:
        issues.append("stackctl up must not expose --gateway-base-url to users")

    conflict = run(["python3", str(STACKCTL), "up", "--env", "beta", "--target", "beta-local", "--skip-app"])
    if conflict.returncode == 0 or "provide exactly one of --env or --target" not in (conflict.stdout + conflict.stderr):
        issues.append("stackctl up must reject simultaneous --env and --target")

    missing = run(["python3", str(STACKCTL), "up", "--skip-app"])
    missing_output = missing.stdout + missing.stderr
    if missing.returncode == 0 or "dev-up environment is missing" not in missing_output:
        issues.append("stackctl up must prompt or fail clearly when env selector is missing")

    topology = load_environment_topology()
    alpha_android = resolve_app_endpoint_overrides("alpha", "android_physical", topology=topology)
    if alpha_android["gatewayBaseUrl"] != "https://localhost:17000":
        issues.append("alpha android local device must map gateway to plain localhost HTTPS transport")
    if alpha_android.get("legalBaseUrl") != "https://localhost:17000/legal":
        issues.append("alpha android local device must map legal-static to gateway /legal")
    if alpha_android["mediaImageBaseUrl"] != "https://localhost:17100":
        issues.append("alpha android local device must map media to plain localhost HTTPS transport")
    beta_android = resolve_app_endpoint_overrides("beta", "android_emulator", topology=topology)
    if beta_android["gatewayBaseUrl"] != "https://beta-api.localhost:18000":
        issues.append("beta android local device must map gateway to distinct localhost HTTPS transport")
    if beta_android.get("legalBaseUrl") != "https://beta-api.localhost:18000/legal":
        issues.append("beta android local device must map legal-static to gateway /legal")
    if beta_android["mediaImageBaseUrl"] != "https://beta-image.localhost:18100":
        issues.append("beta android local device must map media to beta media port")
    gamma_android = resolve_app_endpoint_overrides("gamma", "android_physical", topology=topology)
    if gamma_android["gatewayBaseUrl"] != "https://gamma-api.localhost:19000":
        issues.append("gamma android local device must map gateway to local-gamma loopback transport")
    if gamma_android.get("legalBaseUrl") != "https://gamma-api.localhost:19000/legal":
        issues.append("gamma android local device must map legal-static to gateway /legal")
    if gamma_android["mediaImageBaseUrl"] != "https://gamma-image.localhost:19100":
        issues.append("gamma android local device must map media to local-gamma media port")
    prod_sim_android = resolve_app_endpoint_overrides("prod-sim", "android_physical", topology=topology)
    if prod_sim_android["gatewayBaseUrl"] != "https://prod-api.localhost:20000":
        issues.append("prod-sim android local device must map gateway to prod-sim loopback transport")
    if prod_sim_android.get("legalBaseUrl") != "https://prod-api.localhost:20000/legal":
        issues.append("prod-sim android local device must map legal-static to prod-sim gateway /legal")
    if prod_sim_android["mediaImageBaseUrl"] != "https://prod-image.localhost:20100":
        issues.append("prod-sim android local device must map media to prod-sim media port")
    prod_hosted = resolve_app_endpoint_overrides("prod", "android_physical", topology=topology)
    if prod_hosted["gatewayBaseUrl"] != "https://api.quwoquan.com":
        issues.append("prod android launch must keep canonical api.quwoquan.com gateway")
    if prod_hosted.get("legalBaseUrl") != "https://quwoquan.com/legal":
        issues.append("prod android launch must keep canonical legal base")
    if prod_hosted["mediaImageBaseUrl"] != "https://cdn.quwoquan.com":
        issues.append("prod android launch must keep canonical cdn.quwoquan.com media image base")
    if prod_hosted.get("mediaUploadBaseUrl") != "https://upload.quwoquan.com":
        issues.append("prod android launch must keep canonical upload.quwoquan.com media upload base")
    gamma_web = resolve_app_endpoint_overrides("gamma", "web", topology=topology)
    if gamma_web["gatewayBaseUrl"] != "https://gamma-api.quwoquan-env.test:19000":
        issues.append("gamma web must map gateway to secure gamma env domain")
    if gamma_web.get("legalBaseUrl") != "https://gamma-api.quwoquan-env.test:19000/legal":
        issues.append("gamma web must map legal-static to gateway /legal")

    build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
        encoding="utf-8"
    )
    alpha_run = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    beta_manual = (
        ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
    ).read_text(encoding="utf-8")
    beta_stack = (
        ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
    ).read_text(encoding="utf-8")
    beta_stop = (
        ROOT / "quwoquan_app/scripts/device/stop_app_beta_manual.sh"
    ).read_text(encoding="utf-8")
    app_instance_launcher = (
        ROOT / "quwoquan_app/scripts/device/start_app_instance.sh"
    ).read_text(encoding="utf-8")
    legal_document_page = (
        ROOT / "quwoquan_app/lib/ui/user/pages/legal_document_page.dart"
    ).read_text(encoding="utf-8")
    legal_document_remote = (
        ROOT / "quwoquan_app/lib/cloud/remote/user/legal_document_remote.dart"
    ).read_text(encoding="utf-8")
    mock_public_plane = (
        ROOT / "quwoquan_ops/cli/lib/mock_public_plane.py"
    ).read_text(encoding="utf-8")
    local_gamma_caddyfile = (
        ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
    ).read_text(encoding="utf-8")
    prod_plane_renderer = (
        ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
    ).read_text(encoding="utf-8")
    gamma_script = (
        ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    gamma_compose = (
        ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
    ).read_text(encoding="utf-8")
    gamma_notification_compose = (
        ROOT
        / "quwoquan_service/services/notification-service/deploy/compose.yaml"
    ).read_text(encoding="utf-8")
    prod_sim = (
        ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
    ).read_text(encoding="utf-8")

    expected_default_paths = {
        deployment_render_root("gamma-local"):
            Path.home() / ".cache/quwoquan/deploy/gamma-local/rendered",
        env_cache_target_root("gamma", "gamma-local"):
            ROOT / ".qwq_output/env/gamma/local/gamma-local/cache",
        target_process_root("gamma", "gamma-local"):
            ROOT / ".qwq_output/env/gamma/local/gamma-local/process",
        certificate_export_dir("gamma-local"):
            Path.home() / ".cache/quwoquan/deploy/gamma-local/certificates",
    }
    for actual, expected in expected_default_paths.items():
        if actual != expected:
            issues.append(f"split runtime path mismatch: expected {expected}, got {actual}")
    gamma_observability_logs = observability_runtime_logs_root("gamma")
    if gamma_observability_logs.parts[-2:] != ("logs", "service"):
        issues.append(f"gamma observability logs must use logs/service: {gamma_observability_logs}")
    if "current" in gamma_observability_logs.parts or "current" in run_root("gamma").parts:
        issues.append("local run paths must use an immutable runId, never current")

    if "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED" not in build_gradle:
        issues.append("android debug build must require explicit local CA when launcher marks it required")
    if (
        'File(deploymentWorkRoot, "alpha-local/certificates/root.crt")'
        not in build_gradle
    ):
        issues.append(
            "android alpha debug CA must use the same root.crt that signs the alpha TLS proxy leaf"
        )
    if "alpha-local/certificates/tls/ca/root.crt" in build_gradle:
        issues.append(
            "android alpha debug CA must not use the retired tls/ca/root.crt path"
        )
    if (
        "verifyAndroidLocalAlphaCaSource" not in build_gradle
        or "packaged local_env_debug_root.crt must exactly equal" not in build_gradle
    ):
        issues.append(
            "android alpha build must verify the packaged raw CA equals the TLS proxy signing root"
        )
    if "tasks.withType<FlutterTask>()" not in build_gradle:
        issues.append("android debug build must patch FlutterTask dart-defines for plain flutter run")
    if "alphaLocalTransportDartDefineKeys" not in build_gradle:
        issues.append(
            "android alpha plain flutter run must declare transport dart-define keys for force overwrite"
        )
    if "shouldForceTransport" not in build_gradle:
        issues.append(
            "android alpha plain flutter run must force-overwrite gateway/media localhost dart-defines"
        )
    if "existingKeys.add(key)" in build_gradle and "shouldForceTransport" not in build_gradle:
        issues.append(
            "android alpha mergeAlphaLocalDartDefines must not remain fill-only for transport URLs"
        )
    if 'loadRuntimePackageDartDefines("alpha")' not in build_gradle:
        issues.append("plain android flutter run must derive alpha endpoints from the app runtime package")
    if "alphaLocalTransportDartDefineKeys.forEach" not in build_gradle:
        issues.append("plain android flutter run must project every alpha transport endpoint")
    if "rewriteAlphaLocalTransport(getValue(key))" not in build_gradle:
        issues.append("plain android flutter run must rewrite alpha transport hosts to localhost")
    duplicate_alpha_transport_urls = (
        "https://localhost:17000",
        "https://localhost:17100",
    )
    if any(url in build_gradle for url in duplicate_alpha_transport_urls):
        issues.append(
            "plain android flutter run must not duplicate alpha ports outside the runtime package"
        )
    if "prepareAndroidLocalAlphaStack" not in build_gradle:
        issues.append("plain android flutter run must prepare alpha local stack before debug resource generation")
    if 'environment("QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP", "skip")' not in build_gradle:
        issues.append("plain android flutter run must start alpha stack in HTTPS localhost transport mode")
    if "prepareAndroidLocalAdbReverse" not in build_gradle or '"reverse",' not in build_gradle:
        issues.append("plain android flutter run must prepare adb reverse for local gateway/media ports")
    android_debug_network = (
        ROOT / "quwoquan_app/android/app/src/debug/res/xml/beta_debug_network_security_config.xml"
    ).read_text(encoding="utf-8")
    android_profile_network = (
        ROOT / "quwoquan_app/android/app/src/profile/res/xml/beta_debug_network_security_config.xml"
    ).read_text(encoding="utf-8")
    android_debug_manifest = (
        ROOT / "quwoquan_app/android/app/src/debug/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    android_profile_manifest = (
        ROOT / "quwoquan_app/android/app/src/profile/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    app_bootstrap = (ROOT / "quwoquan_app/lib/app_bootstrap.dart").read_text(
        encoding="utf-8"
    )
    platform_local_https_trust = (
        ROOT / "quwoquan_app/lib/core/platform/local_dev_https_trust_io.dart"
    ).read_text(encoding="utf-8")
    main_activity = (
        ROOT / "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
    ).read_text(encoding="utf-8")
    if 'cleartextTrafficPermitted="true"' in android_debug_network + android_profile_network:
        issues.append("android local network security config must not permit cleartext HTTP")
    if 'android:usesCleartextTraffic="true"' in android_debug_manifest + android_profile_manifest:
        issues.append("android debug/profile manifests must not permit cleartext HTTP")
    if "LocalDevHttpsTrust.installForCurrentRuntime()" not in app_bootstrap:
        issues.append("app bootstrap must install Dart local HTTPS trust before media/cache clients start")
    if "_installLocalDevHttpsTrustAfterFirstFrame" in app_bootstrap:
        issues.append("app bootstrap must not defer Dart local HTTPS trust until after the first frame")
    if "source: 'local_dev_https_trust'" in app_bootstrap:
        issues.append(
            "app bootstrap must fail-fast on local HTTPS trust install errors (no swallow/log-only)"
        )
    if (
        "_installLocalDevHttpsTrustBeforeMediaClients()" not in app_bootstrap
        or "authNetworkPrerequisites:" not in app_bootstrap
    ):
        issues.append("app bootstrap must pass local HTTPS trust as auth network prerequisites before media clients")
    image_cache_controller = (
        ROOT / "quwoquan_app/lib/core/media/app_image_cache_controller.dart"
    ).read_text(encoding="utf-8")
    trusted_http_file_service = (
        ROOT / "quwoquan_app/lib/core/platform/trusted_http_file_service_io.dart"
    ).read_text(encoding="utf-8")
    if "createTrustedHttpFileService" not in image_cache_controller:
        issues.append(
            "App image cache managers must use the platform trusted HTTP file-service factory"
        )
    if "IOClient" not in trusted_http_file_service:
        issues.append(
            "Native trusted HTTP file service must use package:http IOClient"
        )
    if (
        "HttpClient(context: SecurityContext.defaultContext)"
        not in trusted_http_file_service
    ):
        issues.append(
            "Native trusted HTTP file service must bind HttpClient to SecurityContext.defaultContext"
        )
    if (
        "SecurityContext.defaultContext.setTrustedCertificatesBytes"
        not in platform_local_https_trust
    ):
        issues.append("Dart local HTTPS trust must add the packaged CA to SecurityContext.defaultContext")
    if "appRuntimeEnv == 'prod'" in platform_local_https_trust:
        issues.append(
            "Dart local HTTPS trust must not hardcode APP_RUNTIME_ENV==prod; use runtime bases plane"
        )
    if "isLocalHttpsTransportBase" not in platform_local_https_trust:
        issues.append(
            "Dart local HTTPS trust must decide install from local HTTPS transport bases"
        )
    if "placeholderSubjectMarker" not in platform_local_https_trust:
        issues.append("Dart local HTTPS trust must reject placeholder local CA certificates")
    if "badCertificateCallback" in platform_local_https_trust:
        issues.append("Dart local HTTPS trust must not bypass certificate validation")
    if "localEnvDebugRootCertificate" not in main_activity:
        issues.append("Android MainActivity must expose packaged local_env_debug_root to Dart HttpClient")
    if "export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1" not in alpha_run:
        issues.append("alpha run.sh must require Android local debug CA when preparing local device launch")
    if "--legal-base-url" not in alpha_run:
        issues.append("alpha run.sh must pass legal-static base URL with app env dart-defines")
    if "export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1" not in beta_manual:
        issues.append("beta manual launcher must require Android local debug CA for Android devices")
    if (
        "prepare_android_local_tls" not in app_instance_launcher
        or "enable_android_adb_reverse" not in app_instance_launcher
        or "local_target_android_debug_ca_cert" not in app_instance_launcher
    ):
        issues.append(
            "shared app-instance launcher must derive Android adb reverse and local CA from dev_up topology helpers"
        )
    alpha_script = (ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh").read_text(
        encoding="utf-8"
    )
    if 'TLS_ROOT_CERT="$TLS_CA_DIR/root.crt"' not in alpha_script:
        issues.append(
            "alpha TLS proxy must expose alpha-local/certificates/root.crt as its signing root"
        )
    if "quwoquan_ops/cli/lib/tls_reverse_proxy.py" not in alpha_script:
        issues.append("alpha local stack must use repo-owned TLS reverse proxy")
    if "quwoquan_ops/cli/legal_static.py\" package --env alpha" not in alpha_script:
        issues.append("alpha local stack must build legal-static before serving /legal")
    if '"/legal/user-agreement"' not in alpha_script:
        issues.append("alpha local stack must health-check legal-static stable URL")
    if "stop_alpha_reserved_listeners" not in alpha_script or "lsof -nP -tiTCP" not in alpha_script:
        issues.append("alpha local stack must clear repo-owned stale listeners on reserved ports before startup")
    if "docker.io/library/caddy" in alpha_script:
        issues.append("alpha local stack must not depend on external Caddy image for flutter run")
    if "ensure_public_hosts_mapping" not in alpha_script:
        issues.append("alpha local stack must manage quwoquan-env.test loopback DNS before app launch")
    if "security add-trusted-cert" not in alpha_script:
        issues.append("alpha local stack must trust the local root CA for host/iOS simulator HTTPS")
    if "macos_login_keychain_trust_is_current" not in alpha_script:
        issues.append("alpha local stack must idempotently skip repeated macOS login keychain trust writes")
    if "QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST" not in alpha_script:
        issues.append("alpha local stack must allow skipping macOS login keychain trust for iOS simulator builds")
    if (
        "quwoquan_ops/cli/lib/local_target_tls.py" not in alpha_script
        or "install-ios-simulator-ca" not in alpha_script
        or "--simulator-udid" not in alpha_script
    ):
        issues.append(
            "alpha local stack must delegate explicit Simulator CA installation to local_target_tls.py"
        )
    if "IP.2 = 10.0.2.2" not in alpha_script:
        issues.append("alpha local TLS certificate must include Android emulator host 10.0.2.2 as an IP SAN")
    if "--resolve" in alpha_script:
        issues.append("alpha local stack health checks must use real public DNS, not curl --resolve")
    if "curl -k" in alpha_script:
        issues.append("alpha local stack health checks must not bypass TLS trust with curl -k")
    ios_project = (
        ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
    ).read_text(encoding="utf-8")
    ios_prepare_alpha = (
        ROOT / "quwoquan_app/scripts/ios/prepare_alpha_local_https.sh"
    ).read_text(encoding="utf-8")
    if "Prepare Alpha HTTPS Local Plane" not in ios_project:
        issues.append("plain iOS flutter run must prepare alpha HTTPS local plane before Flutter build")
    if "../scripts/ios/prepare_alpha_local_https.sh" not in ios_project:
        issues.append("iOS Runner project must call the alpha HTTPS prepare script")
    if "QWQ_IOS_LOCAL_AUTO_PREPARE" not in ios_prepare_alpha:
        issues.append("iOS alpha prepare script must expose an explicit opt-out")
    if "start_alpha_mock_stack.sh\" up" not in ios_prepare_alpha:
        issues.append("iOS alpha prepare script must start the alpha HTTPS stack")
    if "QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST=skip" not in ios_prepare_alpha:
        issues.append("iOS alpha prepare script must skip macOS login keychain trust to avoid repeated password prompts")
    if "legal_static_deployment_package_dir(self.runtime_env)" not in mock_public_plane:
        issues.append("alpha mock public plane must resolve legal-static deployment packages through output_paths")
    if "utf8.decode(response.bodyBytes)" not in legal_document_remote:
        issues.append("legal document page must decode response bytes as UTF-8")
    if "loadHtmlString(html, baseUrl: uri.toString())" not in legal_document_page:
        issues.append("legal document page must render the explicitly decoded HTML string")
    if "loadRequest(uri)" in legal_document_page:
        issues.append("legal document page must not regress to charset-dependent WebView loadRequest")
    if 'legal_static_deployment_package_dir("beta")' not in beta_manual:
        issues.append("beta manual stack must mount the canonical legal-static deployment package")
    if 'stackctl.py" package --env beta --kind legal-static' not in beta_manual:
        issues.append("beta manual stack must package legal-static before starting its TLS gateway")
    if 'handle /legal/manifest.json {' not in beta_manual or 'handle /legal/* {' not in beta_manual:
        issues.append("beta TLS gateway must serve legal manifest and documents before proxying business routes")
    if '-v "$BETA_LEGAL_STATIC_ROOT:/srv/legal:ro"' not in beta_manual:
        issues.append("beta TLS gateway must mount legal-static under /srv/legal")
    if '--legal-base-url "$GATEWAY_BASE_URL/legal"' not in beta_manual:
        issues.append("beta app launch must inject its TLS gateway legal-static base URL")
    if (
        "beta_manual_verify_legal_document" not in beta_manual
        or '"趣我圈用户协议"' not in beta_manual
        or '"趣我圈隐私政策"' not in beta_manual
    ):
        issues.append("beta manual startup must verify UTF-8 agreement and privacy-policy content")
    if 'legal_static_deployment_package_dir(' not in prod_sim or '"prod"' not in prod_sim:
        issues.append("prod-sim must mount the canonical prod legal-static deployment package")
    if 'stackctl.py" package --env prod --kind legal-static' not in prod_sim:
        issues.append("prod-sim must gate startup on a valid prod legal-static package")
    if 'handle /legal/manifest.json {' not in prod_sim or 'handle /legal/* {' not in prod_sim:
        issues.append("prod-sim TLS gateway must serve legal manifest and documents before proxying business routes")
    if '-v "$PROD_SIM_LEGAL_STATIC_ROOT:/srv/legal:ro"' not in prod_sim:
        issues.append("prod-sim TLS gateway must mount legal-static under /srv/legal")
    if (
        "verify_https_legal_document" not in prod_sim
        or '"趣我圈用户协议"' not in prod_sim
        or '"趣我圈隐私政策"' not in prod_sim
    ):
        issues.append("prod-sim startup must verify UTF-8 agreement and privacy-policy content")
    for label, source in {"gamma Caddyfile": local_gamma_caddyfile}.items():
        if "@api_user path /auth* /owner* /user* /me /me/*" not in source:
            issues.append(f"{label} must route auth and owner APIs to user-service")
        if "@pub_user path /auth* /owner* /user* /me /me/*" not in source:
            issues.append(f"{label} must expose auth and owner APIs on the public gateway")
        if 'handle /legal/manifest.json {' not in source:
            issues.append(f"{label} must preserve JSON content type for the legal manifest")
        if 'Content-Type "text/html; charset=utf-8"' not in source:
            issues.append(f"{label} must declare UTF-8 for extensionless legal documents")
    if prod_plane_renderer.count('handle /legal/manifest.json {') != 2:
        issues.append("prod renderer must preserve JSON content type for both legal route surfaces")
    if prod_plane_renderer.count('Content-Type "text/html; charset=utf-8"') != 2:
        issues.append("prod renderer must declare UTF-8 for both extensionless legal route surfaces")
    if prod_plane_renderer.count(
        "@api_user path /auth* /owner* /user* /me /me/*"
    ) != 1 or prod_plane_renderer.count(
        "@pub_user path /auth* /owner* /user* /me /me/*"
    ) != 1:
        issues.append("prod renderer must route auth and owner APIs to user-service on both gateway surfaces")
    if 'LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/gamma-local/rendered"' not in gamma_script:
        issues.append("gamma rendered deployment config must use the system deployment work root")
    if 'LOCAL_GAMMA_CADDYFILE="$ROOT/quwoquan_ops/environments/gamma/local/Caddyfile"' not in gamma_script:
        issues.append("gamma launcher must mount the single Ops-owned Caddyfile source")
    if "prepare_caddyfile" in gamma_script or "MEDIA_ORIGIN_BASE_URL" in gamma_script:
        issues.append("gamma launcher must not generate a second Caddyfile or launch a media origin")
    if 'handle /healthz {\n\t\trespond "ok" 200\n\t}' not in local_gamma_caddyfile:
        issues.append("gamma media edge must expose a direct /healthz endpoint")
    if 'LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/gamma/local/gamma-local/process"' not in gamma_script:
        issues.append("gamma pid/env/status must live under output local/process")
    for marker, message in (
        (
            'export LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE=',
            "gamma launcher must resolve the Notification image explicitly",
        ),
        (
            'notification-service \\\n',
            "gamma launcher must include Notification in the autonomous package scan",
        ),
        (
            'local notification_port="${LOCAL_GAMMA_NOTIFICATION_PORT:-19320}"',
            "gamma readiness must probe Notification directly",
        ),
        (
            '-e ASSISTANT_NOTIFICATION_BASE_URL=http://notification-service:18087 \\',
            "gamma podman composition must bind Assistant to Notification",
        ),
    ):
        if marker not in gamma_script:
            issues.append(message)
    if "  notification-service:\n" not in gamma_notification_compose:
        issues.append("Notification autonomous compose fragment is missing")
    if 'QWQ_COMPOSE_NOTIFICATION_PORT:-19320}:18087' not in gamma_notification_compose:
        issues.append("Notification compose fragment must publish the canonical port")
    if 'LOCAL_GAMMA_CADDY_DATA_VOLUME="${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}"' not in gamma_script:
        issues.append("gamma Caddy certificate state must use its named deployment volume")
    if '/data/caddy/pki/authorities/local/root.crt' not in gamma_script:
        issues.append("gamma launcher must export the public root CA into the deployment work root")
    if '${LOCAL_GAMMA_CADDY_DATA_VOLUME:-local-gamma-caddy-data}:/data' not in gamma_compose:
        issues.append("gamma compose must bind Caddy data to a named volume")
    if '${LOCAL_GAMMA_CADDY_CONFIG_VOLUME:-local-gamma-caddy-config}:/config' not in gamma_compose:
        issues.append("gamma compose must bind Caddy config to a named volume")
    if ".qwq_output/env/gamma/runtime" in gamma_compose or ".qwq_output/env/gamma/local/gamma-local/pki" in gamma_compose:
        issues.append("gamma compose must not place deployment config or certificates under output")
    if "QWQ_STATE_ROOT" in gamma_script or ".qwq_state" in gamma_script:
        issues.append("gamma launcher must not use a second state root")

    launcher_sources = {
        "beta stack": beta_stack,
        "beta manual start": beta_manual,
        "beta manual stop": beta_stop,
        "gamma mirror": gamma_script,
        "prod-sim": prod_sim,
    }
    for label, source in launcher_sources.items():
        if 'QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT' not in source:
            issues.append(f"{label} must default QWQ_OUTPUT_ROOT to repository .qwq_output")
        if 'QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT' not in source:
            issues.append(f"{label} must default QWQ_OUTPUT_ROOT to repository .qwq_output")
    if ".env.beta.local" in beta_stack:
        issues.append("beta stack must not write the repository-root .env.beta.local")
    combined_launchers = "\n".join(launcher_sources.values())
    for retired_path in (".qwq_state", "QWQ_STATE_ROOT", ".qwq_output/env/gamma/runtime"):
        if retired_path in combined_launchers:
            issues.append(f"local launchers must not retain retired path fallback: {retired_path}")
    if 'LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"' not in beta_manual:
        issues.append("beta runtime logs must use QWQ_OBSERVABILITY_RUN_ROOT/logs/service")
    if 'REPORT="${QWQ_RUN_ROOT}/app-beta-manual-report.json"' not in beta_manual:
        issues.append("beta report must use QWQ_RUN_ROOT")
    if 'BETA_MANUAL_STATE_DIR="${QWQ_OUTPUT_ROOT}/env/beta/local/beta-local/process"' not in beta_manual:
        issues.append("beta pid/env state must use QWQ_OUTPUT_ROOT local/process")
    if "--rotate-ca" not in beta_stop or 'volume rm -f "$TLS_PROXY_DATA_VOLUME" "$TLS_PROXY_CONFIG_VOLUME"' not in beta_stop:
        issues.append("beta CA rotation must be an explicit stop action")
    if 'rm -rf "$LOG_DIR"' in beta_stop:
        issues.append("beta --purge-logs must not recursively remove a directory that can contain PKI")
    if 'find "$LOG_DIR" -mindepth 1 -maxdepth 1 -delete' not in beta_stop:
        issues.append("beta --purge-logs must delete runtime log entries only")

    if issues:
        print("[verify_dev_up_cli_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_dev_up_cli_surface] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
