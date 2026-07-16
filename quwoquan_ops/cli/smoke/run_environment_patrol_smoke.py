#!/usr/bin/env python3
"""Run page-level Patrol smoke tests for one environment target."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.cli.lib.dev_up import (
    ANDROID_LOCAL_DEBUG_CA_ENV,
    ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
    local_target_android_debug_ca_cert,
)
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli


APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "device-matrix" / "environment-smoke" / "report.json"
DEFAULT_TARGET = "test/user_acceptance/patrol/environment/basic_viability__user_acceptance_test.dart"
IOS_SDK_VERSION_PATTERN = re.compile(r"iOS[- ](\d+)(?:[-._](\d+))?")
XCODE_IOS_SIMULATOR_SDK_PATTERN = re.compile(
    r"-sdk\s+iphonesimulator(\d+)(?:\.(\d+))?"
)
XCODE_GLOBAL_PRODUCTS_DIR = Path.home() / "Library" / "Developer" / "Xcode" / "XcodeDerivedData" / "Build" / "Products"
PATROL_IOS_PRODUCTS_DIR = APP_DIR / "build" / "ios_integ" / "Build" / "Products"
LOCAL_TARGETS = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
LOCAL_ENVIRONMENT_ALIAS_TARGETS = {"local-gamma": "gamma-local"}
PUBLIC_TEST_SUFFIX = ".quwoquan-env.test"
LOCALHOST_SUFFIX = ".localhost"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _runtime_env_for_alias(alias: str) -> str:
    normalized = alias.strip().lower()
    if normalized in {"prod", "prod-sim", "prod-hosted"}:
        return "prod"
    if "gamma" in normalized:
        return "gamma"
    if "beta" in normalized:
        return "beta"
    return "alpha"


def _data_source_for_runtime(runtime_env: str) -> str:
    return "mock" if runtime_env == "alpha" else "remote"


def _local_target_for_environment_alias(env_name: str) -> str:
    """Resolve a public environment alias to its concrete local deployment target."""
    normalized = env_name.strip().lower()
    return LOCAL_ENVIRONMENT_ALIAS_TARGETS.get(normalized, normalized)


def _uses_runtime_anonymous_session(args: argparse.Namespace) -> bool:
    return args.env_name.strip().lower() == "local-gamma"


def _is_local_target(env_name: str) -> bool:
    return _local_target_for_environment_alias(env_name) in LOCAL_TARGETS


def _device_uses_local_loopback(device: dict[str, Any]) -> bool:
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android"):
        return True
    return target == "ios" and bool(device.get("emulator", False))


def _rewrite_local_loopback_base(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme or not parsed.hostname:
        return url
    host = parsed.hostname
    if host == "127.0.0.1":
        host = "localhost"
    elif host.endswith(PUBLIC_TEST_SUFFIX):
        host = host[: -len(PUBLIC_TEST_SUFFIX)] + LOCALHOST_SUFFIX
    elif host == "localhost" or host.endswith(LOCALHOST_SUFFIX):
        host = host
    else:
        return url
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _effective_base_urls_for_device(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, str]:
    gateway_base_url = args.gateway_base_url.strip()
    product_ops_base_url = args.product_ops_base_url.strip()
    media_base_url = args.media_base_url.strip()
    if _is_local_target(args.env_name) and _device_uses_local_loopback(device):
        gateway_base_url = _rewrite_local_loopback_base(gateway_base_url)
        product_ops_base_url = _rewrite_local_loopback_base(product_ops_base_url)
        media_base_url = _rewrite_local_loopback_base(media_base_url)
    return {
        "gatewayBaseUrl": gateway_base_url,
        "productOpsBaseUrl": product_ops_base_url,
        "mediaBaseUrl": media_base_url,
    }


def _resolved_owner_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_owner_id", "") or "").strip()


def _resolved_sub_account_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_sub_account_id", "") or "").strip()


def _local_debug_ca_path(env_name: str) -> Path | None:
    try:
        return local_target_android_debug_ca_cert(
            _local_target_for_environment_alias(env_name)
        )
    except RuntimeError:
        return None


def _install_booted_simulator_root_ca(cert_path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "keychain", "booted", "add-root-cert", str(cert_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "skipped",
            "reason": "xcrun unavailable",
            "certPath": str(cert_path),
        }
    output = summarize_output((result.stdout or "") + (result.stderr or ""))
    return {
        "status": "attempted" if result.returncode == 0 else "best_effort_failed",
        "exitCode": result.returncode,
        "certPath": str(cert_path),
        "outputSummary": output,
    }


def _device_command_env(args: argparse.Namespace, device: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    cert_path = _local_debug_ca_path(args.env_name)
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android") and cert_path is not None:
        env[ANDROID_LOCAL_DEBUG_CA_ENV] = str(cert_path)
        env[ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV] = "1"
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--env-name", "--environment-alias", dest="env_name", default="local-gamma")
    parser.add_argument("--runtime-env", default="")
    parser.add_argument("--api-contract-env", default="")
    parser.add_argument("--data-source", choices=("mock", "remote"), default="")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--test-auth-token", default=os.environ.get("TEST_AUTH_TOKEN", "").strip())
    parser.add_argument(
        "--test-refresh-token",
        default=os.environ.get("TEST_REFRESH_TOKEN", "").strip(),
    )
    parser.add_argument(
        "--release-uat-cases",
        default="",
        help="Gamma data-release 生成的 app_uat_cases.json；只用于两省实体主页真实消费验证",
    )
    parser.add_argument(
        "--current-owner-id",
        default=os.environ.get("APP_CURRENT_OWNER_ID", "").strip(),
    )
    parser.add_argument(
        "--current-sub-account-id",
        default=os.environ.get("APP_CURRENT_SUB_ACCOUNT_ID", "").strip(),
    )
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _load_release_uat_cases_b64(path_value: str) -> str:
    """Validate a runtime-only Gamma UAT manifest before injecting it into Patrol."""
    path = Path(path_value).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release UAT cases unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("release UAT cases must be an object")
    allowed = {
        "schemaVersion",
        "environment",
        "releaseId",
        "runId",
        "importerReportRef",
        "generatedAt",
        "cases",
    }
    if set(payload) != allowed:
        raise ValueError("release UAT cases has an invalid field set")
    if payload.get("schemaVersion") != "quwoquan_data.gamma_app_uat_case_manifest/1":
        raise ValueError("release UAT cases schemaVersion is invalid")
    if payload.get("environment") != "gamma":
        raise ValueError("release UAT cases must target gamma")
    for field in ("releaseId", "runId", "importerReportRef", "generatedAt"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"release UAT cases {field} is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("release UAT cases must contain at least one case")
    entity_refs: set[str] = set()
    homepage_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {"entityRef", "homepageId", "title"}:
            raise ValueError(f"release UAT case {index} has an invalid field set")
        entity_ref = case.get("entityRef")
        homepage_id = case.get("homepageId")
        title = case.get("title")
        if not all(isinstance(value, str) and value.strip() for value in (entity_ref, homepage_id, title)):
            raise ValueError(f"release UAT case {index} has invalid values")
        if entity_ref in entity_refs or homepage_id in homepage_ids:
            raise ValueError(f"release UAT case {index} duplicates entity or homepage identity")
        entity_refs.add(entity_ref)
        homepage_ids.add(homepage_id)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _redact_command(command: list[str]) -> list[str]:
    secret_defines = {
        "--dart-define=TEST_AUTH_TOKEN=": "--dart-define=TEST_AUTH_TOKEN=<redacted>",
        "--dart-define=TEST_REFRESH_TOKEN=": "--dart-define=TEST_REFRESH_TOKEN=<redacted>",
    }
    redacted: list[str] = []
    for item in command:
        if item.startswith("--dart-define-from-file="):
            replacement = "--dart-define-from-file=<ephemeral-secret-file>"
        else:
            replacement = next(
                (
                    placeholder
                    for prefix, placeholder in secret_defines.items()
                    if item.startswith(prefix)
                ),
                item,
            )
        redacted.append(replacement)
    return redacted


def _redact_text(output: str, secret_values: tuple[str, ...]) -> str:
    redacted = output
    for value in secret_values:
        if value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def summarize_output(output: str, *, max_lines: int = 120) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    log_path: Path | None = None,
    secret_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output, _ = process.communicate(timeout=timeout_seconds)
        output = output or ""
        exit_code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                output, _ = process.communicate(timeout=10)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    pass
                output = ""
        else:
            output = ""
        exit_code = 124
        timed_out = True
    redacted_output = _redact_text(output, secret_values)
    result = {
        "command": _redact_command(command),
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(redacted_output),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(redacted_output, encoding="utf-8")
        result["logPath"] = repo_relative(log_path)
    return result


def ios_sdk_version(device: dict[str, Any]) -> tuple[int, int] | None:
    sdk = str(device.get("sdk", "")).strip()
    match = IOS_SDK_VERSION_PATTERN.search(sdk)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor)


def xcode_ios_simulator_sdk_version() -> tuple[int, int]:
    result = subprocess.run(
        ["xcodebuild", "-showsdks"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("xcodebuild -showsdks failed")
    versions = [
        (int(match.group(1)), int(match.group(2) or 0))
        for match in XCODE_IOS_SIMULATOR_SDK_PATTERN.finditer(result.stdout)
    ]
    if not versions:
        raise RuntimeError("Xcode reports no iOS Simulator SDK")
    return max(versions)


def _select_compatible_ios_devices(
    devices: list[dict[str, Any]],
    *,
    simulator_sdk_version: tuple[int, int],
) -> list[dict[str, Any]]:
    simulators = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ]
    compatible_versions = [
        version
        for device in simulators
        for version in [ios_sdk_version(device)]
        if version is not None and version <= simulator_sdk_version
    ]
    if simulators and not compatible_versions:
        requested = ", ".join(
            sorted({str(device.get("sdk", "")).strip() for device in simulators})
        )
        supported = f"{simulator_sdk_version[0]}.{simulator_sdk_version[1]}"
        raise RuntimeError(
            f"no discovered iOS simulator runtime is compatible with Xcode SDK {supported}: {requested}"
        )
    if not compatible_versions:
        return devices
    selected_version = max(compatible_versions)
    selected = [
        device
        for device in devices
        if not (
            str(device.get("targetPlatform", "")).strip().lower() == "ios"
            and bool(device.get("emulator", False))
        )
        or ios_sdk_version(device) == selected_version
    ]
    patrol_keys: set[tuple[tuple[int, int] | None, str]] = set()
    for device in selected:
        if str(device.get("targetPlatform", "")).strip().lower() != "ios":
            continue
        key = (ios_sdk_version(device), str(device.get("name", "")).strip())
        if key in patrol_keys:
            raise RuntimeError(
                "Patrol cannot select duplicate iOS devices with the same runtime and name: "
                f"{key[1]} iOS {key[0]}"
            )
        patrol_keys.add(key)
    return selected


def discover_devices(platform: str, device_ids: list[str]) -> list[dict[str, Any]]:
    payload = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "quwoquan_app" / "scripts" / "device" / "discover_flutter_mobile_devices.py"),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if payload.returncode != 0:
        raise RuntimeError(
            "discover_flutter_mobile_devices.py failed:\n"
            + summarize_output((payload.stdout or "") + (payload.stderr or ""))
        )
    data = json.loads(payload.stdout)
    devices = list(data.get("devices") or [])
    allowed_ids = {item for item in device_ids if item}
    selected: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        if allowed_ids and device_id not in allowed_ids:
            continue
        if platform == "android" and not target.startswith("android"):
            continue
        if platform == "ios" and target != "ios":
            continue
        if platform == "all" and target != "ios" and not target.startswith("android"):
            continue
        selected.append(device)
    if not allowed_ids and platform in ("ios", "all"):
        selected = _select_compatible_ios_devices(
            selected,
            simulator_sdk_version=xcode_ios_simulator_sdk_version(),
        )
    return selected


def _prepare_execution_session(args: argparse.Namespace) -> str:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    data_source = args.data_source.strip() or _data_source_for_runtime(runtime_env)
    if _uses_runtime_anonymous_session(args):
        supplied = {
            "test_auth_token": args.test_auth_token,
            "test_refresh_token": args.test_refresh_token,
            "current_owner_id": _resolved_owner_id(args),
            "current_sub_account_id": _resolved_sub_account_id(args),
        }
        if any(str(value).strip() for value in supplied.values()):
            raise ValueError(
                "local-gamma Patrol must use device-runtime anonymous login; "
                "do not inject auth tokens or actor identities"
            )
        return "gamma_local_anonymous_runtime"
    if runtime_env == "alpha" and data_source == "mock":
        args.test_auth_token = args.test_auth_token.strip() or "alpha-contract-fixture-access"
        args.test_refresh_token = (
            args.test_refresh_token.strip() or "alpha-contract-fixture-refresh"
        )
        args.current_owner_id = (
            _resolved_owner_id(args) or "fixture_user_current_owner"
        )
        args.current_sub_account_id = (
            _resolved_sub_account_id(args) or "fixture_user_current"
        )
        return "alpha_contract_fixture"
    return "provided_remote_session"


def _create_patrol_secret_define_file(args: argparse.Namespace) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="qwq-patrol-secrets-", suffix=".json")
    path = Path(raw_path)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "TEST_AUTH_TOKEN": args.test_auth_token.strip(),
                    "TEST_REFRESH_TOKEN": args.test_refresh_token.strip(),
                },
                handle,
                ensure_ascii=False,
            )
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def patrol_command(
    device: dict[str, Any],
    args: argparse.Namespace,
    patrol_executable: str,
    *,
    dart_define_file: Path | None,
) -> list[str]:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    data_source = args.data_source.strip() or _data_source_for_runtime(runtime_env)
    base_urls = _effective_base_urls_for_device(args, device)
    gateway_base_url = base_urls["gatewayBaseUrl"]
    product_ops_base_url = base_urls["productOpsBaseUrl"]
    media_base_url = base_urls["mediaBaseUrl"]
    current_owner_id = _resolved_owner_id(args)
    current_sub_account_id = _resolved_sub_account_id(args)
    command = [
        patrol_executable,
        "test",
        "-t",
        args.target,
        "-d",
        str(device["id"]),
        "--dart-define=RUN_T4_PATROL=true",
        f"--dart-define=APP_RUNTIME_ENV={runtime_env}",
        f"--dart-define=APP_DATA_SOURCE={data_source}",
        f"--dart-define=API_CONTRACT_ENV={api_contract_env}",
        f"--dart-define=CLOUD_GATEWAY_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
    ]
    if _uses_runtime_anonymous_session(args):
        command.append("--dart-define=QWQ_PATROL_SESSION_MODE=local_gamma_anonymous")
    else:
        if dart_define_file is None:
            raise ValueError("remote Patrol session requires a private Dart define file")
        command.extend(
            [
                f"--dart-define-from-file={dart_define_file}",
                f"--dart-define=APP_CURRENT_OWNER_ID={current_owner_id}",
                f"--dart-define=APP_CURRENT_SUB_ACCOUNT_ID={current_sub_account_id}",
                f"--dart-define=APP_CURRENT_USER_ID={current_sub_account_id}",
            ]
        )
    if str(device.get("targetPlatform", "")).strip().lower() == "ios":
        sdk_version = ios_sdk_version(device)
        if sdk_version is not None:
            command.append(f"--ios={sdk_version[0]}.{sdk_version[1]}")
    if media_base_url:
        command.extend(
            [
                f"--dart-define=MEDIA_AVATAR_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_IMAGE_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_VIDEO_CDN_BASE_URL={media_base_url}",
                f"--dart-define=MEDIA_UPLOAD_BASE_URL={media_base_url}",
            ]
        )
    release_uat_cases_b64 = str(getattr(args, "release_uat_cases_b64", "") or "")
    if release_uat_cases_b64:
        command.append(f"--dart-define=QWQ_TWO_PROVINCE_UAT_CASES_B64={release_uat_cases_b64}")
    return command


def _output_evidence_ref(path: Path) -> str:
    """Expose runtime output references relative to QWQ_OUTPUT_ROOT, not repo root."""
    relative = repo_relative(path)
    prefix = ".qwq_output/"
    return relative[len(prefix) :] if relative.startswith(prefix) else relative


def ensure_patrol_ios_products_bridge() -> None:
    """Bridge Patrol's expected ios_integ products path to Xcode 26 global products."""
    patrol_products = PATROL_IOS_PRODUCTS_DIR
    patrol_products.parent.mkdir(parents=True, exist_ok=True)
    if patrol_products.is_symlink():
        try:
            if patrol_products.resolve() == XCODE_GLOBAL_PRODUCTS_DIR.resolve():
                return
        except FileNotFoundError:
            patrol_products.unlink()
    elif patrol_products.exists():
        return
    patrol_products.symlink_to(XCODE_GLOBAL_PRODUCTS_DIR)


def dry_run_devices(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_ids = args.device_id or ["dry-run-device"]
    devices = []
    for device_id in raw_ids:
        target_platform = "ios" if args.platform == "ios" else "android-arm64"
        if args.platform == "all":
            target_platform = "ios"
        devices.append(
            {
                "id": device_id,
                "name": "Dry Run Device",
                "targetPlatform": target_platform,
                "sdk": "dry-run",
                "emulator": True,
                "screenClass": "phone",
            }
        )
    return devices


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _missing_required_args(args: argparse.Namespace) -> list[str]:
    required = [
        ("gateway_base_url", args.gateway_base_url),
        ("product_ops_base_url", args.product_ops_base_url),
    ]
    if not _uses_runtime_anonymous_session(args):
        required.extend(
            [
                ("test_auth_token", args.test_auth_token),
                ("test_refresh_token", args.test_refresh_token),
                ("current_owner_id", _resolved_owner_id(args)),
                ("current_sub_account_id", _resolved_sub_account_id(args)),
            ]
        )
    return [name for name, value in required if not str(value).strip()]


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    data_source = args.data_source.strip() or _data_source_for_runtime(runtime_env)
    report: dict[str, Any] = {
        "suiteId": "environment_page_smoke",
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "environmentAlias": args.env_name,
        "runtimeEnv": runtime_env,
        "apiContractEnv": api_contract_env,
        "dataSource": data_source,
        "target": args.target,
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "mediaBaseUrl": args.media_base_url,
        "currentOwnerId": _resolved_owner_id(args),
        "currentSubAccountId": _resolved_sub_account_id(args),
        "sessionSource": "",
        "releaseUatCasesPath": "",
        "devices": [],
        "runs": [],
        "failureReason": "",
        "deviceInventoryPath": "",
        "evidenceRoot": "",
    }
    if not args.dry_run:
        try:
            report["sessionSource"] = _prepare_execution_session(args)
        except Exception as exc:  # noqa: BLE001
            report["status"] = "gate_block"
            report["failureReason"] = str(exc)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        report["currentOwnerId"] = _resolved_owner_id(args)
        report["currentSubAccountId"] = _resolved_sub_account_id(args)
    else:
        report["sessionSource"] = "dry_run"
    patrol_resolution = resolve_patrol_cli()
    patrol_executable = patrol_resolution.executable or "patrol"
    report["patrolCli"] = patrol_resolution.as_report(required=not args.dry_run)

    if args.release_uat_cases:
        try:
            args.release_uat_cases_b64 = _load_release_uat_cases_b64(args.release_uat_cases)
        except ValueError as exc:
            report["status"] = "gate_block"
            report["failureReason"] = str(exc)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        report["releaseUatCasesPath"] = _output_evidence_ref(Path(args.release_uat_cases).expanduser())
    else:
        args.release_uat_cases_b64 = ""

    if not args.dry_run:
        if patrol_resolution.executable is None:
            report["status"] = "gate_block"
            report["failureReason"] = patrol_resolution.error
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        missing = _missing_required_args(args)
        if missing:
            report["status"] = "gate_block"
            report["failureReason"] = f"missing required args: {', '.join(missing)}"
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2

    try:
        devices = dry_run_devices(args) if args.dry_run else discover_devices(args.platform, args.device_id)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureReason"] = str(exc)
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 1

    if not devices:
        report["status"] = "gate_block"
        report["failureReason"] = "no mobile Flutter devices available on self-hosted Mac runner"
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2

    report["devices"] = devices
    evidence_root = report_path.parent / "runs"
    report["evidenceRoot"] = repo_relative(evidence_root)
    report["deviceInventoryPath"] = write_discovered_devices_snapshot(
        report_path.parent / "discovered_devices.json",
        devices,
        suite="environment-page-smoke",
        requested_environments=[args.env_name],
        extra={
            "target": args.target,
            "runtimeEnv": runtime_env,
            "platform": args.platform,
            "reportPath": repo_relative(report_path),
        },
    )
    failed = False
    for device in devices:
        run_dir = evidence_root / sanitize_device_id(str(device.get("id", "")))
        run_dir.mkdir(parents=True, exist_ok=True)
        device_manifest_path = write_device_manifest(
            run_dir / "device.json",
            device,
            env_name=args.env_name,
            suite="environment-page-smoke",
            extra={"target": args.target, "runtimeEnv": runtime_env},
        )
        if str(device.get("targetPlatform", "")).lower() == "ios":
            ensure_patrol_ios_products_bridge()
        tls_trust = {"status": "skipped", "reason": "not-required"}
        if (
            _is_local_target(args.env_name)
            and str(device.get("targetPlatform", "")).lower() == "ios"
            and bool(device.get("emulator", False))
        ):
            cert_path = _local_debug_ca_path(args.env_name)
            if cert_path is None:
                tls_trust = {
                    "status": "missing",
                    "reason": f"local debug root CA missing for {args.env_name}",
                }
            else:
                tls_trust = _install_booted_simulator_root_ca(cert_path)
        secret_define_path: Path | None = None
        if args.dry_run:
            secret_define_path = run_dir / "dry-run-patrol-secrets.json"
        elif not _uses_runtime_anonymous_session(args):
            secret_define_path = _create_patrol_secret_define_file(args)
        command = patrol_command(
            device,
            args,
            patrol_executable,
            dart_define_file=secret_define_path,
        )
        command_env = _device_command_env(args, device)
        command_path = write_json(
            run_dir / "command.json",
            {
                "capturedAt": utc_now(),
                "target": args.target,
                "deviceId": device["id"],
                "command": _redact_command(command),
                "environment": {
                    "QWQ_ANDROID_LOCAL_ENV_CA_PATH": command_env.get(ANDROID_LOCAL_DEBUG_CA_ENV, ""),
                    "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED": command_env.get(ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV, ""),
                },
            },
        )
        before_screenshot = capture_device_screenshot(device, run_dir / "before.png")
        print(
            f"[environment-page-smoke] run {args.env_name} on "
            f"{device['name']} ({device['id']}, {device['targetPlatform']})",
            flush=True,
        )
        if args.dry_run:
            log_path = run_dir / "patrol.log"
            log_path.write_text("dry-run\n", encoding="utf-8")
            result = {
                "command": _redact_command(command),
                "cwd": str(APP_DIR),
                "exitCode": 0,
                "timedOut": False,
                "durationMs": 0,
                "outputSummary": "dry-run",
                "logPath": repo_relative(log_path),
            }
        else:
            try:
                result = run_command(
                    command,
                    cwd=APP_DIR,
                    env=command_env,
                    timeout_seconds=args.timeout_seconds,
                    log_path=run_dir / "patrol.log",
                    secret_values=(
                        args.test_auth_token.strip(),
                        args.test_refresh_token.strip(),
                    ),
                )
            finally:
                if secret_define_path is not None:
                    secret_define_path.unlink(missing_ok=True)
        after_screenshot = (
            capture_device_screenshot(device, run_dir / "after.png")
            if result["exitCode"] == 0 and not args.dry_run
            else {"status": "skipped", "reason": "command failed"}
        )
        failure_screenshot = (
            capture_device_screenshot(device, run_dir / "failure.png")
            if result["exitCode"] != 0 and not args.dry_run
            else {"status": "skipped", "reason": "command passed"}
        )
        result["device"] = device
        result["evidence"] = {
            "runDirectory": repo_relative(run_dir),
            "deviceManifestPath": device_manifest_path,
            "commandPath": command_path,
            "rawLogPath": result.get("logPath", ""),
            "beforeScreenshot": before_screenshot,
            "afterScreenshot": after_screenshot,
            "failureScreenshot": failure_screenshot,
            "localTlsTrust": tls_trust,
        }
        report["runs"].append(result)
        failed = failed or result["exitCode"] != 0

    report["status"] = "failed" if failed else "passed"
    if failed:
        report["failureReason"] = "one or more Patrol runs failed"
    report["endedAt"] = utc_now()
    write_report(report_path, report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
