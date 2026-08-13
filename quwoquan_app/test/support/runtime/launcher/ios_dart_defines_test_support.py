# iOS dart defines 契约套件的共享常量与构造 helper。
#
# 由 1000 行硬顶拆分自
# quwoquan_app/test/local_contract/runtime/ios_runtime_dart_defines__local_contract_test.py，
# 供 ios_runtime_dart_defines__local_contract_test.py 与
# ios_runtime_dart_defines__direct_debug__local_contract_test.py 共用；
# 常量与函数体逐字保留原实现。

import base64
import json
import shlex
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[4]
for _support_path in (
    str(APP_DIR / "scripts/runtime/platform"),
    str(APP_DIR / "scripts/device"),
    str(APP_DIR / "test/support/runtime/launcher"),
):
    if _support_path not in sys.path:
        sys.path.insert(0, _support_path)

import build_launcher_handoff as launcher
from launcher_package_fixture import build_test_handoff


SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
BUILD_WRAPPER = APP_DIR / "scripts/ios/build_xcode_backend.sh"
CANONICAL_LAUNCHER = APP_DIR / "run.sh"
STACKCTL_PYTHON_RESOLVER = APP_DIR / "scripts/ios/build_resolve_stackctl_python.sh"
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
REQUIRED_KEYS = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
    "APP_LAUNCH_POLICY",
    "CONTENT_BINDING_STATE",
}


def _build_handoff(
    environment: str,
    *,
    launch_mode: str = "xcode_build",
) -> dict[str, object]:
    extra_arguments: list[str] = []
    if environment == "prod":
        extra_arguments.extend(
            [
                "--content-release-id",
                f"release-{environment}",
                "--content-manifest-digest",
                "sha256:" + "1" * 64,
                "--content-readiness-receipt-digest",
                "sha256:" + "2" * 64,
            ]
        )
    return build_test_handoff(
        launcher,
        environment,
        RUNTIME_TARGETS[environment],
        launch_mode=launch_mode,
        extra_arguments=tuple(extra_arguments),
    )


def _apply_handoff_identity(
    env: dict[str, str],
    environment: str,
    *,
    launch_mode: str = "xcode_build",
    runtime_python: Path,
) -> dict[str, object]:
    handoff = _build_handoff(environment, launch_mode=launch_mode)
    env["QWQ_IOS_STACKCTL_PYTHON"] = str(runtime_python)
    env["QWQ_TEST_LAUNCHER_DEFINES_JSON"] = json.dumps(
        handoff["dartDefines"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    env["QWQ_APP_LAUNCH_MODE"] = launch_mode
    env["QWQ_APP_LAUNCH_POLICY"] = str(handoff["launchPolicy"])
    env["QWQ_LAUNCH_TARGET"] = str(handoff["target"])
    env["QWQ_DART_DEFINES_DIGEST"] = str(handoff["dartDefinesDigest"])
    env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
        handoff["runtimeConfigDigest"]
    )
    env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
        handoff["effectiveLaunchManifestDigest"]
    )
    for environment_key, handoff_key in (
        ("QWQ_CONTENT_RELEASE_ID", "contentReleaseId"),
        ("QWQ_CONTENT_MANIFEST_DIGEST", "contentManifestDigest"),
        (
            "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
            "contentReadinessReceiptDigest",
        ),
    ):
        value = str(handoff.get(handoff_key) or "")
        if value:
            env[environment_key] = value
    return handoff


def _decode_export(stdout: str) -> dict[str, str]:
    line = next(
        item for item in stdout.splitlines() if item.startswith("export DART_DEFINES=")
    )
    assignment = shlex.split(line.removeprefix("export "))[0]
    encoded = assignment.split("=", 1)[1]
    values: dict[str, str] = {}
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _encode_defines(defines: dict[str, object]) -> str:
    return ",".join(
        base64.b64encode(f"{key}={value}".encode()).decode()
        for key, value in sorted(defines.items())
    )


def _bound_test_live_handoff() -> dict[str, object]:
    return build_test_handoff(
        launcher,
        "alpha",
        "alpha-local",
        launch_mode="environment_patrol_smoke",
        extra_arguments=(
            "--content-release-id",
            "travel-research-test",
            "--content-manifest-digest",
            "sha256:" + "1" * 64,
            "--content-readiness-receipt-digest",
            "sha256:" + "2" * 64,
        ),
    )


def _write_preflight_python(directory: Path) -> Path:
    executable = directory / "preflight-python"
    preflight = json.dumps(
        {
            "status": "warning",
            "warnings": [
                "target startup status is not running: stopped",
                "api-edge is not ready: network_error",
            ],
        }
    )
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "for argument in \"$@\"; do\n"
        "  if [[ \"$argument\" == \"app-debug-preflight\" ]]; then\n"
        f"    printf '%s\\n' {shlex.quote(preflight)}\n"
        "    exit 0\n"
        "  fi\n"
        "  if [[ \"$argument\" == */build_launcher_handoff.py ]]; then\n"
        "    printf '%s\\n' \"${QWQ_TEST_LAUNCHER_HANDOFF_JSON:?}\"\n"
        "    exit 0\n"
        "  fi\n"
        "  if [[ \"$argument\" == */print_app_env_dart_defines.py ]]; then\n"
        "    printf '%s\\n' \"${QWQ_TEST_LAUNCHER_DEFINES_JSON:?}\"\n"
        "    exit 0\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _install_direct_handoff(
    environment: dict[str, str],
    runtime_environment: str,
) -> None:
    handoff = build_test_handoff(
        launcher,
        runtime_environment,
        RUNTIME_TARGETS[runtime_environment],
        launch_mode="direct_flutter_run",
    )
    environment["QWQ_TEST_LAUNCHER_HANDOFF_JSON"] = json.dumps(
        handoff,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    environment["QWQ_TEST_LAUNCHER_DEFINES_JSON"] = json.dumps(
        handoff["dartDefines"],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _write_hard_blocked_preflight_python(directory: Path) -> Path:
    executable = directory / "blocked-preflight-python"
    preflight = json.dumps(
        {
            "status": "gate_block",
            "details": [
                "api endpoint escapes the selected alpha namespace",
            ],
        }
    )
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "for argument in \"$@\"; do\n"
        "  if [[ \"$argument\" == \"app-debug-preflight\" ]]; then\n"
        f"    printf '%s\\n' {shlex.quote(preflight)}\n"
        "    exit 2\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable
