#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.dev_up import resolve_app_endpoint_overrides
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
    if prod_hosted["gatewayBaseUrl"] != "https://118.31.239.122:19000":
        issues.append("prod android launch must keep hosted gateway address")
    if prod_hosted.get("legalBaseUrl") != "https://quwoquan.com/legal":
        issues.append("prod android launch must keep canonical legal base")
    if prod_hosted["mediaImageBaseUrl"] != "https://118.31.239.122:19100":
        issues.append("prod android launch must keep hosted media address")
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
    gamma_script = (
        ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    gamma_compose = (
        ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
    ).read_text(encoding="utf-8")

    if "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED" not in build_gradle:
        issues.append("android debug build must require explicit local CA when launcher marks it required")
    if "tasks.withType<FlutterTask>()" not in build_gradle:
        issues.append("android debug build must patch FlutterTask dart-defines for plain flutter run")
    if '"CLOUD_GATEWAY_BASE_URL" to "https://localhost:17000"' not in build_gradle:
        issues.append("plain android flutter run must default alpha gateway to localhost HTTPS transport")
    if '"APP_LEGAL_BASE_URL" to "https://localhost:17000/legal"' not in build_gradle:
        issues.append("plain android flutter run must default alpha legal-static to gateway /legal")
    if '"MEDIA_IMAGE_CDN_BASE_URL" to "https://localhost:17100"' not in build_gradle:
        issues.append("plain android flutter run must default alpha media to localhost HTTPS transport")
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
    local_https_trust = (
        ROOT / "quwoquan_app/lib/cloud/runtime/local_dev_https_trust_io.dart"
    ).read_text(encoding="utf-8")
    platform_local_https_trust = (
        ROOT / "quwoquan_app/lib/core/platform/local_dev_https_trust_io.dart"
    ).read_text(encoding="utf-8")
    local_https_trust_sources = local_https_trust + "\n" + platform_local_https_trust
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
    if (
        "_installLocalDevHttpsTrustBeforeMediaClients()" not in app_bootstrap
        or "startupPrerequisites: startupPrerequisites" not in app_bootstrap
    ):
        issues.append("app bootstrap must pass local HTTPS trust as startup prerequisites before media clients")
    if (
        "SecurityContext.defaultContext.setTrustedCertificatesBytes"
        not in local_https_trust_sources
    ):
        issues.append("Dart local HTTPS trust must add the packaged CA to SecurityContext.defaultContext")
    if "badCertificateCallback" in local_https_trust_sources:
        issues.append("Dart local HTTPS trust must not bypass certificate validation")
    if "localEnvDebugRootCertificate" not in main_activity:
        issues.append("Android MainActivity must expose packaged local_env_debug_root to Dart HttpClient")
    if "export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1" not in alpha_run:
        issues.append("alpha run.sh must require Android local debug CA when preparing local device launch")
    if "--legal-base-url" not in alpha_run:
        issues.append("alpha run.sh must pass legal-static base URL with app env dart-defines")
    if "export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1" not in beta_manual:
        issues.append("beta manual launcher must require Android local debug CA for Android devices")
    alpha_script = (ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh").read_text(
        encoding="utf-8"
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
    if "simctl keychain booted add-root-cert" not in alpha_script:
        issues.append("alpha local stack must install the local root CA into booted iOS simulators")
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
    if 'LOCAL_GAMMA_CADDY_DATA_ROOT="${LOCAL_GAMMA_CADDY_DATA_ROOT:-${LOCAL_GAMMA_LOCAL_ROOT}/caddy/data}"' not in gamma_script:
        issues.append("gamma local mirror must expose host-readable caddy data root")
    if 'LOCAL_GAMMA_CADDY_CONFIG_ROOT="${LOCAL_GAMMA_CADDY_CONFIG_ROOT:-${LOCAL_GAMMA_LOCAL_ROOT}/caddy/config}"' not in gamma_script:
        issues.append("gamma local mirror must expose host-readable caddy config root")
    if '${LOCAL_GAMMA_CADDY_DATA_ROOT:-../../../.qwq_output/local/gamma-local/caddy/data}:/data' not in gamma_compose:
        issues.append("gamma compose must bind caddy data to .qwq_output/local path")
    if '${LOCAL_GAMMA_CADDY_CONFIG_ROOT:-../../../.qwq_output/local/gamma-local/caddy/config}:/config' not in gamma_compose:
        issues.append("gamma compose must bind caddy config to .qwq_output/local path")
    if "local-gamma-caddy/data:/data" in gamma_compose or "local-gamma-caddy/config:/config" in gamma_compose:
        issues.append("gamma compose must not hide caddy CA inside named volumes")

    if issues:
        print("[verify_dev_up_cli_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_dev_up_cli_surface] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
