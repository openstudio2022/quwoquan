#!/usr/bin/env python3
from __future__ import annotations

import re
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
    summarize_output,
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


def source_section(source: str, start: str, end: str) -> str | None:
    start_index = source.find(start)
    if start_index < 0:
        return None
    content_start = start_index + len(start)
    end_index = source.find(end, content_start)
    if end_index < 0:
        return None
    return source[content_start:end_index]


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
    if alpha_android["gatewayBaseUrl"] != "https://api.alpha.quwoquan.com:17000":
        issues.append("alpha Android must keep the canonical public API authority")
    if alpha_android.get("legalBaseUrl") != "https://alpha.quwoquan.com:17000/legal":
        issues.append("alpha Android must keep the canonical public legal authority")
    if alpha_android["mediaImageBaseUrl"] != "https://cdn.alpha.quwoquan.com:17100/media/image":
        issues.append("alpha Android must keep the canonical public CDN role path")
    beta_android = resolve_app_endpoint_overrides("beta", "android_emulator", topology=topology)
    if beta_android["gatewayBaseUrl"] != "https://api.beta.quwoquan.com:18000":
        issues.append("beta Android must keep the canonical public API authority")
    if beta_android.get("legalBaseUrl") != "https://beta.quwoquan.com:18000/legal":
        issues.append("beta Android must keep the canonical public legal authority")
    if beta_android["mediaImageBaseUrl"] != "https://cdn.beta.quwoquan.com:18100/media/image":
        issues.append("beta Android must keep the canonical public CDN role path")
    gamma_android = resolve_app_endpoint_overrides("gamma", "android_physical", topology=topology)
    if gamma_android["gatewayBaseUrl"] != "https://api.gamma.quwoquan.com:19000":
        issues.append("gamma Android must keep the canonical public API authority")
    if gamma_android.get("legalBaseUrl") != "https://gamma.quwoquan.com:19000/legal":
        issues.append("gamma Android must keep the canonical public legal authority")
    if gamma_android["mediaImageBaseUrl"] != "https://cdn.gamma.quwoquan.com:19100/media/image":
        issues.append("gamma Android must keep the canonical public CDN role path")
    prod_sim_android = resolve_app_endpoint_overrides("prod-sim", "android_physical", topology=topology)
    if prod_sim_android["gatewayBaseUrl"] != "https://api.sim.quwoquan.com:20000":
        issues.append("prod-sim Android must keep the canonical public API authority")
    if prod_sim_android.get("legalBaseUrl") != "https://sim.quwoquan.com:20000/legal":
        issues.append("prod-sim Android must keep the canonical public legal authority")
    if prod_sim_android["mediaImageBaseUrl"] != "https://cdn.sim.quwoquan.com:20100/media/image":
        issues.append("prod-sim Android must keep the canonical public CDN role path")
    prod_hosted = resolve_app_endpoint_overrides("prod", "android_physical", topology=topology)
    if prod_hosted["gatewayBaseUrl"] != "https://api.quwoquan.com":
        issues.append("prod android launch must keep canonical api.quwoquan.com gateway")
    if prod_hosted.get("legalBaseUrl") != "https://quwoquan.com/legal":
        issues.append("prod android launch must keep canonical legal base")
    if prod_hosted["mediaImageBaseUrl"] != "https://cdn.quwoquan.com/media/image":
        issues.append("prod android launch must keep canonical cdn.quwoquan.com media image base")
    if prod_hosted.get("mediaUploadBaseUrl") != "https://upload.quwoquan.com":
        issues.append("prod android launch must keep canonical upload.quwoquan.com media upload base")
    gamma_web = resolve_app_endpoint_overrides("gamma", "web", topology=topology)
    if gamma_web["gatewayBaseUrl"] != "https://gamma.quwoquan.com:19000/api":
        issues.append("gamma web must use the public origin same-origin /api proxy")
    if gamma_web.get("legalBaseUrl") != "https://gamma.quwoquan.com:19000/legal":
        issues.append("gamma web must keep canonical public legal authority")

    build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
        encoding="utf-8"
    )
    alpha_run = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    beta_manual = (
        ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
    ).read_text(encoding="utf-8")
    beta_stack = (
        ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
    ).read_text(encoding="utf-8")
    alpha_content_release = (
        ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py"
    ).read_text(encoding="utf-8")
    beta_stop = (
        ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app_stop.sh"
    ).read_text(encoding="utf-8")
    app_instance_launcher = (
        ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
    ).read_text(encoding="utf-8")
    legal_document_page = (
        ROOT / "quwoquan_app/lib/runtime/shell/legal/legal_document_page.dart"
    ).read_text(encoding="utf-8")
    legal_document_remote = (
        ROOT / "quwoquan_app/lib/runtime/shell/legal/legal_document_remote.dart"
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
    for label, source in {
        "alpha content release": alpha_content_release,
        "beta manual": beta_manual,
        "gamma Caddyfile": local_gamma_caddyfile,
        "prod-sim": prod_sim,
    }.items():
        if "path /api/*" not in source or "uri @web_api strip_prefix /api" not in source:
            issues.append(f"{label} must route browser API calls through same-origin /api")

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

    for token in (
        "QWQ_ANDROID_LOCAL_ENV_CA",
        "local_env_debug_root",
        "verifyAndroidLocalAlphaCaSource",
    ):
        if token in build_gradle:
            issues.append(f"android build must use system public CA only; retired token: {token}")
    if "tasks.withType<FlutterTask>()" not in build_gradle:
        issues.append("android debug build must patch FlutterTask dart-defines for plain flutter run")
    if "verifyAndroidLocalLauncherContract" not in build_gradle:
        issues.append(
            "android debug/profile must fail-closed unless start_app_instance/run.sh leases the device"
        )
    if "requireCompleteRuntimeDartDefines" not in build_gradle:
        issues.append(
            "android FlutterTask must require complete runtime dart-defines from the canonical launcher"
        )
    if 'runtimeEnvironment in setOf("alpha", "beta", "gamma", "prod")' not in build_gradle:
        issues.append(
            "android debug/profile launcher contract must accept all four QWQ_APP_RUNTIME_ENV values"
        )
    if "QWQ_CONSUMER_LEASE_ACQUIRED" not in build_gradle or "QWQ_ANDROID_LOCAL_PORTS" not in build_gradle:
        issues.append(
            "android debug/profile must require consumer lease and adb reverse ports from the launcher"
        )
    for retired in (
        "alphaLocalTransportDartDefineKeys",
        "shouldForceTransport",
        "mergeAlphaLocalDartDefines",
        "prepareAndroidLocalAlphaStack",
        "prepareAndroidLocalAdbReverse",
        'loadRuntimePackageDartDefines("alpha")',
    ):
        if retired in build_gradle:
            issues.append(
                "android debug build must not auto-assemble alpha transport for bare flutter run; "
                f"retired helper still present: {retired}"
            )
    duplicate_alpha_transport_urls = (
        "https://localhost:17000",
        "https://localhost:17100",
    )
    if any(url in build_gradle for url in duplicate_alpha_transport_urls):
        issues.append(
            "android debug build must not hardcode alpha localhost transport URLs"
        )
    android_debug_manifest = (
        ROOT / "quwoquan_app/android/app/src/debug/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    android_profile_manifest = (
        ROOT / "quwoquan_app/android/app/src/profile/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    main_activity = (
        ROOT / "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
    ).read_text(encoding="utf-8")
    if 'android:usesCleartextTraffic="true"' in android_debug_manifest + android_profile_manifest:
        issues.append("android debug/profile manifests must not permit cleartext HTTP")
    image_cache_controller = (
        ROOT
        / "quwoquan_app/lib/runtime/platform/media/app_image_cache_controller.dart"
    ).read_text(encoding="utf-8")
    trusted_http_file_service = (
        ROOT / "quwoquan_app/lib/runtime/platform/trusted_http_file_service_io.dart"
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
    if "localEnvDebugRootCertificate" in main_activity:
        issues.append("Android MainActivity must not expose a private trust root")
    if "--legal-base-url" not in alpha_run:
        issues.append("alpha run.sh must pass legal-static base URL with app env dart-defines")
    if (
        "prepare_android_reverse" not in app_instance_launcher
        or "enable_android_adb_reverse" not in app_instance_launcher
    ):
        issues.append(
            "shared app-instance launcher must prepare adb reverse without rewriting authorities"
        )
    alpha_script = (ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py").read_text(
        encoding="utf-8"
    )
    if 'certificate_export_dir(TARGET) / "root.crt"' in alpha_script:
        issues.append("alpha Remote content-release must not export a private Caddy root")
    if (
        "legal_static_deployment_package_dir" not in alpha_script
        or "Alpha legal-static package is incomplete" not in alpha_script
    ):
        issues.append(
            "alpha Remote content-release must fail closed on an incomplete legal-static package"
        )
    if '"  handle /legal/* {"' not in alpha_script:
        issues.append("alpha local stack must health-check legal-static stable URL")
    if "quwoquan_cloud_mock" in alpha_script or "test_fixtures" in alpha_script:
        issues.append("alpha Remote content-release must not reference App mocks or fixtures")
    ios_project = (
        ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
    ).read_text(encoding="utf-8")
    ios_prepare_defines = (
        ROOT / "quwoquan_app/scripts/ios/build_prepare_dart_defines.sh"
    ).read_text(encoding="utf-8")
    stackctl_source = STACKCTL.read_text(encoding="utf-8")
    # stackctl 域拆分后的契约位置：provider-conformance CLI 面与 gamma 包装载
    # 分别迁至 commands/provider_conformance_domain.py 与 commands/package_shared.py。
    conformance_domain_source = (
        ROOT / "quwoquan_ops" / "cli" / "commands" / "provider_conformance_domain.py"
    ).read_text(encoding="utf-8")
    package_shared_source = (
        ROOT / "quwoquan_ops" / "cli" / "commands" / "package_shared.py"
    ).read_text(encoding="utf-8")
    if (
        "Prepare Alpha HTTPS Local Plane" in ios_project
        or "Bundle Local HTTPS Trust Root" in ios_project
    ):
        issues.append("iOS project must rely on system public CA without trust injection phases")
    for retired in (
        "DIRECT_ALPHA_HANDOFF",
        "xcode-direct-alpha",
    ):
        if retired in ios_prepare_defines:
            issues.append(
                "iOS Xcode phase must not synthesize a bare flutter run fallback; "
                f"retired token: {retired}"
            )
    launch_policy_contract = run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            (
                "quwoquan_ops.tests.local_contract.environment."
                "test_local_runtime_consumer_lease__local_contract_test."
                "LocalRuntimeConsumerLeaseTest."
                "test_launcher_warning_policy_reaches_flutter_run_without_runtime_lease"
            ),
            (
                "quwoquan_ops.tests.local_contract.environment."
                "test_local_runtime_consumer_lease__local_contract_test."
                "LocalRuntimeConsumerLeaseTest."
                "test_launcher_hard_safety_blocker_stops_before_flutter_run"
            ),
        ]
    )
    if launch_policy_contract.returncode != 0:
        issues.append(
            "canonical launcher must continue on test_live readiness warnings and "
            "stop on hard safety blockers: "
            + summarize_output(
                launch_policy_contract.stdout + launch_policy_contract.stderr,
                max_lines=12,
            )
        )
    ios_policy_contract = run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            (
                "quwoquan_app.test.local_contract.runtime."
                "ios_runtime_dart_defines__direct_debug__local_contract_test."
                "IosRuntimeDartDefinesContractTest."
                "test_direct_ios_debug_selects_canonical_nonprod_handoff"
            ),
            (
                "quwoquan_app.test.local_contract.runtime."
                "ios_runtime_dart_defines__direct_debug__local_contract_test."
                "IosRuntimeDartDefinesContractTest."
                "test_direct_ios_debug_reports_the_first_hard_safety_blocker"
            ),
        ]
    )
    if ios_policy_contract.returncode != 0:
        issues.append(
            "iOS direct Debug must continue on test_live readiness warnings and "
            "stop on hard safety blockers: "
            + summarize_output(
                ios_policy_contract.stdout + ios_policy_contract.stderr,
                max_lines=12,
            )
        )
    if "use ./run.sh -d <device>" not in ios_prepare_defines:
        issues.append(
            "iOS bare build failure must point to the canonical run.sh launcher"
        )
    if (
        "PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS"
        not in stackctl_source + conformance_domain_source
    ):
        issues.append(
            "stackctl must keep provider-conformance argparse choices local (no eager PyYAML import)"
        )
    if "def _provider_conformance_runner(" not in conformance_domain_source:
        issues.append(
            "stackctl must lazy-import provider_conformance_runner for Xcode/alpha up"
        )
    if "utf8.decode(response.bodyBytes)" not in legal_document_remote:
        issues.append("legal document page must decode response bytes as UTF-8")
    if "loadHtmlString(html, baseUrl: uri.toString())" not in legal_document_page:
        issues.append("legal document page must render the explicitly decoded HTML string")
    if "loadRequest(uri)" in legal_document_page:
        issues.append("legal document page must not regress to charset-dependent WebView loadRequest")
    if 'legal_static_deployment_package_dir("beta")' not in beta_manual:
        issues.append("beta manual stack must mount the canonical legal-static deployment package")
    if "GATE_BLOCK: beta legal-static package is missing user-agreement" not in beta_manual:
        issues.append(
            "beta manual stack must fail closed on an incomplete legal-static package before starting its TLS gateway"
        )
    if 'handle /legal/manifest.json {' not in beta_manual or 'handle /legal/* {' not in beta_manual:
        issues.append("beta TLS gateway must serve legal manifest and documents before proxying business routes")
    if '-v "$BETA_LEGAL_STATIC_ROOT:/srv/legal:ro"' not in beta_manual:
        issues.append("beta TLS gateway must mount legal-static under /srv/legal")
    if "start_app_instance.sh" in beta_manual:
        issues.append(
            "beta environment assembly must not launch App; release-bound App execution is a separate matrix stage"
        )
    if (
        "beta_manual_verify_legal_document" not in beta_manual
        or '"趣我圈用户协议"' not in beta_manual
        or '"趣我圈隐私政策"' not in beta_manual
    ):
        issues.append("beta manual startup must verify UTF-8 agreement and privacy-policy content")
    if 'legal_static_deployment_package_dir(' not in prod_sim or '"prod"' not in prod_sim:
        issues.append("prod-sim must mount the canonical prod legal-static deployment package")
    if "[prod-sim] FAIL: legal-static package missing user-agreement" not in prod_sim:
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
    first_party_direct_proxy = re.compile(
        r"reverse_proxy\s+(?:assistant|chat|circle|content|entity|integration|"
        r"notification|platform-ops|product-ops|recommendation|rtc|search|tag|user)-service(?::\d+)?\b"
    )
    for label, source in {
        "gamma Caddyfile": local_gamma_caddyfile,
        "prod renderer": prod_plane_renderer,
    }.items():
        edge_snippet = source_section(source, "(business_api_edge) {", "\n}\n")
        if source.count("(business_api_edge) {") != 1 or edge_snippet is None:
            issues.append(f"{label} must define exactly one business api-edge ingress")
        else:
            if (
                "reverse_proxy api-edge:18079" not in edge_snippet
                or "header_up X-Edge-Client-IP {remote_host}" not in edge_snippet
            ):
                issues.append(
                    f"{label} business ingress must proxy only to api-edge and overwrite the edge client identity"
                )
        business_proxy_source = source
        if label == "gamma Caddyfile":
            public_web_seo = source_section(
                source,
                "\thandle @public_web_seo {",
                "\n\t}",
            )
            if public_web_seo is not None:
                business_proxy_source = business_proxy_source.replace(
                    public_web_seo,
                    "",
                    1,
                )
        if first_party_direct_proxy.search(business_proxy_source):
            issues.append(
                f"{label} must not duplicate operation ownership by proxying directly to a first-party service"
            )
        if "@api_user" in source or "@pub_user" in source:
            issues.append(
                f"{label} must not retain path-owned user-service ingress matchers"
            )

    gamma_public_gateway = source_section(
        local_gamma_caddyfile,
        "https://{$QWQ_PUBLIC_API_HOST}",
        "\n\nhttps://{$QWQ_PUBLIC_RTC_HOST}",
    )
    if (
        gamma_public_gateway is None
        or "uri @web_api strip_prefix /api" not in gamma_public_gateway
        or "handle {\n\t\timport business_api_edge\n\t}" not in gamma_public_gateway
    ):
        issues.append(
            "gamma public API/Web gateway must send its complete business fallback through api-edge"
        )
    gamma_direct_http = source_section(local_gamma_caddyfile, "\n:80 {", "\n}")
    if (
        gamma_direct_http is None
        or "handle {\n\t\timport business_api_edge\n\t}" not in gamma_direct_http
    ):
        issues.append(
            "gamma direct HTTP gateway must send its complete business fallback through api-edge"
        )

    prod_api_gateway = source_section(
        prod_plane_renderer,
        "api.sim.quwoquan.com {",
        "\n\nops.sim.quwoquan.com {",
    )
    if (
        prod_api_gateway is None
        or "\\thandle {\n\\t\\timport business_api_edge\n\\t}"
        not in prod_api_gateway
    ):
        issues.append(
            "prod API gateway template must send its complete business fallback through api-edge"
        )
    prod_web_gateway = source_section(
        prod_plane_renderer, 'web_site = f"""', '"""'
    )
    if prod_web_gateway is not None:
        prod_web_gateway = prod_web_gateway.replace("{{", "{").replace("}}", "}")
    if (
        prod_web_gateway is None
        or "\\thandle_path /api/* {\n\\t\\timport business_api_edge\n\\t}"
        not in prod_web_gateway
        or "\\thandle /ops/app-recovery/version {\n\\t\\timport business_api_edge\n\\t}"
        not in prod_web_gateway
    ):
        issues.append(
            "prod public-Web business routes must enter through the same api-edge ingress"
        )

    for label, source in {"gamma Caddyfile": local_gamma_caddyfile}.items():
        if 'handle /legal/manifest.json {' not in source:
            issues.append(f"{label} must preserve JSON content type for the legal manifest")
        if 'Content-Type "text/html; charset=utf-8"' not in source:
            issues.append(f"{label} must declare UTF-8 for extensionless legal documents")
    if prod_plane_renderer.count('handle /legal/manifest.json {') != 3:
        issues.append("prod renderer must preserve JSON content type for all legal route surfaces")
    prod_legal_blocks = re.findall(
        r"handle /legal/\* \{.*?\n\\t\}",
        prod_plane_renderer,
        re.DOTALL,
    )
    if len(prod_legal_blocks) != 3 or any(
        'Content-Type "text/html; charset=utf-8"' not in block
        for block in prod_legal_blocks
    ):
        issues.append("prod renderer must declare UTF-8 for all extensionless legal route surfaces")
    if 'LOCAL_GAMMA_DEPLOY_RENDER_ROOT="${QWQ_DEPLOY_WORK_ROOT}/${QWQ_LOCAL_RELEASE_TARGET}/rendered"' not in gamma_script:
        issues.append(
            "local release rendered deployment config must use the target-scoped system deployment work root"
        )
    if (
        'LOCAL_GAMMA_CADDYFILE="${LOCAL_GAMMA_RUNTIME_SHARED_ROOT}/Caddyfile"'
        not in gamma_script
        or '"quwoquan_ops" / "environments" / "gamma" / "local" / "Caddyfile"'
        not in package_shared_source
    ):
        issues.append(
            "gamma launcher must mount the package copy of the single Ops-owned Caddyfile"
        )
    if "prepare_caddyfile" in gamma_script or "MEDIA_ORIGIN_BASE_URL" in gamma_script:
        issues.append("gamma launcher must not generate a second Caddyfile or launch a media origin")
    if 'handle /healthz {\n\t\trespond "ok" 200\n\t}' not in local_gamma_caddyfile:
        issues.append("gamma media edge must expose a direct /healthz endpoint")
    if 'LOCAL_GAMMA_PROCESS_ROOT="${QWQ_OUTPUT_ROOT}/env/${QWQ_LOCAL_RELEASE_ENV}/local/${QWQ_LOCAL_RELEASE_TARGET}/process"' not in gamma_script:
        issues.append(
            "local release runtime state must use the environment/target-scoped output process root"
        )
    if "startup_attempt_receipt.py" not in gamma_script:
        issues.append("local release runtime must write the canonical startup attempt receipt")
    if "LOCAL_GAMMA_STACK_STATUS_REPORT" in gamma_script or "stack_status.json" in gamma_script:
        issues.append("local release runtime must not write a second stack status receipt")
    gamma_service_compose_files = sorted(
        (ROOT / "quwoquan_service/services").glob("*/deploy/compose.yaml")
    )
    gamma_discovered_services = {
        compose_path.parents[1].name for compose_path in gamma_service_compose_files
    }
    # Full-workload packaging must use the same active-service roster as the
    # immutable image composition.  A raw ``find`` used to include retired
    # service directories and made Gamma depend on stale Compose fragments;
    # the launcher now derives the intersection explicitly through
    # ``first_party_service_names``.
    for scanner_marker in (
        "from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names",
        "active = set(first_party_service_names(root))",
        'services_root.glob("*/deploy/compose.yaml")',
        "if path.parents[1].name in active",
    ):
        if scanner_marker not in gamma_script:
            issues.append(
                "gamma full workload must derive first-party services from canonical "
                f"service compose files: missing {scanner_marker}"
            )
    if 'find "$ROOT/quwoquan_service/services"' in gamma_script:
        issues.append(
            "gamma full workload must not scan retired service Compose fragments "
            "outside the canonical active-service roster"
        )
    if "notification-service" not in gamma_discovered_services:
        issues.append(
            "gamma canonical service compose scan must derive notification-service"
        )
    for marker, message in (
        (
            'image_key="LOCAL_GAMMA_${service_key}_IMAGE"',
            "gamma launcher must resolve every discovered first-party image explicitly",
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
    if "/data/caddy/pki/authorities/local/root.crt" in gamma_script:
        issues.append("gamma launcher must not export a private Caddy root CA")
    if (
        "QWQ_PUBLIC_TLS_CERT_FILE" not in gamma_script
        or "QWQ_PUBLIC_TLS_KEY_FILE" not in gamma_script
        or "QWQ_PUBLIC_TLS_CERT_FILE" not in gamma_compose
        or "QWQ_PUBLIC_TLS_KEY_FILE" not in gamma_compose
    ):
        issues.append("gamma launcher and compose must mount canonical target certificates")
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
    if (
        "quwoquan_ops/cli/stackctl.py" not in beta_stack
        or "--target beta-local" not in beta_stack
        or "go run" in beta_stack
        or "start_app_beta_manual.sh" in beta_stack
        or "docker compose" in beta_stack
    ):
        issues.append(
            "beta compatibility entry must be a stackctl-only beta-local adapter"
        )
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
