#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.common import run
from agent_ops.deploy.lib.environment_topology import get_target, load_environment_topology
from agent_ops.deploy.lib.port_manifest import load_port_manifest, profile_ports


DEFAULT_APP_DIR = ROOT / "quwoquan_app"
DEV_UP_ENVS = ("alpha", "beta", "gamma", "prod", "prod-sim")
DEV_UP_STACK_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod-sim": "prod-sim",
    "prod": "",
}
DEV_UP_APP_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod-sim": "prod-sim",
    "prod": "prod-hosted",
}
WEB_DEVICE_IDS = {"chrome", "web-server", "edge", "firefox"}
DEV_UP_ENV_DESCRIPTIONS = {
    "alpha": "本地 mock 栈 + App",
    "beta": "本地 beta 栈 + App",
    "gamma": "local gamma mirror + App",
    "prod-sim": "prod-sim App 连接",
    "prod": "prod-hosted edge health + App",
}
ANDROID_LOCAL_LOOPBACK_SUFFIX = ".localhost"
ANDROID_LOCAL_DEBUG_CA_ENV = "QWQ_ANDROID_LOCAL_ENV_CA_PATH"
ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV = "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED"
ANDROID_LOCAL_DEBUG_CA_PATHS = {
    "alpha-local": ROOT / "state" / "local" / "alpha_stack" / "caddy-data" / "caddy" / "pki" / "authorities" / "local" / "root.crt",
    "beta-local": ROOT / "state" / "local" / "app_beta_manual" / "caddy-data" / "caddy" / "pki" / "authorities" / "local" / "root.crt",
    "gamma-local": ROOT / "state" / "local" / "gamma" / "caddy-data" / "caddy" / "pki" / "authorities" / "local" / "root.crt",
    "prod-sim": ROOT / "state" / "local" / "prod_sim_stack" / "caddy-data" / "caddy" / "pki" / "authorities" / "local" / "root.crt",
}


def summarize_output(output: str, *, max_lines: int = 80) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def extract_json_array(output: str) -> str:
    start = output.find("[")
    end = output.rfind("]")
    if start < 0 or end < start:
        raise ValueError("flutter devices output missing JSON array")
    return output[start : end + 1]


def app_target_for_env(env_name: str) -> str:
    target_name = DEV_UP_APP_TARGETS.get(env_name, "")
    if not target_name:
        raise KeyError(f"unsupported dev-up env: {env_name}")
    return target_name


def runtime_env_for_dev_env(env_name: str) -> str:
    return "prod" if env_name == "prod-sim" else env_name


def device_category(device: dict[str, Any]) -> str:
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target == "ios" or target.startswith("android"):
        return "mobile"
    if target.startswith("web"):
        return "web"
    if target in {"darwin", "macos", "linux", "windows"}:
        return "desktop"
    return ""


def discover_flutter_devices(
    app_dir: Path = DEFAULT_APP_DIR,
    *,
    include_mobile: bool = True,
    include_web: bool = True,
    include_desktop: bool = False,
) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["flutter", "devices", "--machine"],
        cwd=str(app_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "flutter devices --machine failed:\n"
            + summarize_output((result.stdout or "") + (result.stderr or ""))
        )
    raw_devices = json.loads(extract_json_array(result.stdout or ""))
    devices: list[dict[str, Any]] = []
    for raw in raw_devices:
        if not bool(raw.get("isSupported", True)):
            continue
        device_id = str(raw.get("id", "")).strip()
        if not device_id:
            continue
        device = {
            "id": device_id,
            "name": str(raw.get("name", "")),
            "targetPlatform": str(raw.get("targetPlatform", "")),
            "sdk": str(raw.get("sdk", "")),
            "emulator": bool(raw.get("emulator", False)),
            "ephemeral": bool(raw.get("ephemeral", False)),
        }
        category = device_category(device)
        if category == "mobile" and not include_mobile:
            continue
        if category == "web" and not include_web:
            continue
        if category == "desktop" and not include_desktop:
            continue
        if category not in {"mobile", "web", "desktop"}:
            continue
        device["category"] = category
        devices.append(device)
    return devices


def build_device_report(devices: list[dict[str, Any]]) -> dict[str, Any]:
    android = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).lower().startswith("android")
    ]
    ios = [
        device for device in devices if str(device.get("targetPlatform", "")).lower() == "ios"
    ]
    web = [
        device for device in devices if str(device.get("targetPlatform", "")).lower().startswith("web")
    ]
    desktop = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).lower() in {"darwin", "macos", "linux", "windows"}
    ]
    platforms: list[str] = []
    if android:
        platforms.append("android")
    if ios:
        platforms.append("ios")
    if web:
        platforms.append("web")
    if desktop:
        platforms.append("desktop")
    return {
        "deviceCount": len(devices),
        "mobileCount": len(android) + len(ios),
        "webCount": len(web),
        "desktopCount": len(desktop),
        "platforms": platforms,
        "android": android,
        "ios": ios,
        "web": web,
        "desktop": desktop,
        "devices": devices,
    }


def resolve_device_id(
    *,
    app_dir: Path = DEFAULT_APP_DIR,
    include_mobile: bool = True,
    include_web: bool = True,
    include_desktop: bool = False,
    label: str = "[dev-up]",
) -> str:
    devices = discover_flutter_devices(
        app_dir,
        include_mobile=include_mobile,
        include_web=include_web,
        include_desktop=include_desktop,
    )
    return pick_device(devices, label=label)


def describe_dev_up_env(env_name: str) -> str:
    return DEV_UP_ENV_DESCRIPTIONS.get(env_name, env_name)


def pick_dev_up_env(
    envs: tuple[str, ...] = DEV_UP_ENVS,
    *,
    label: str = "[dev-up]",
) -> str:
    if not envs:
        raise RuntimeError("GATE_BLOCK: no dev-up environment is available.")
    if len(envs) == 1:
        return envs[0]
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        options = "\n".join(
            f"  - {env_name}: {describe_dev_up_env(env_name)}"
            for env_name in envs
        )
        raise RuntimeError(
            "GATE_BLOCK: dev-up environment is missing; rerun in a TTY to choose interactively or pass --env <name>.\n"
            + options
        )
    print(f"{label} no environment selected; pick one:", file=sys.stderr)
    for idx, env_name in enumerate(envs, 1):
        print(
            f"  [{idx}] {env_name}: {describe_dev_up_env(env_name)}",
            file=sys.stderr,
        )
    while True:
        print(f"Select environment [1-{len(envs)}]: ", end="", file=sys.stderr, flush=True)
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("GATE_BLOCK: no environment selection received; rerun with --env <name>.")
        choice = line.strip()
        if choice in envs:
            return choice
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(envs):
                return envs[index - 1]
        print(f"  invalid selection: {choice!r}", file=sys.stderr)


def pick_device(devices: list[dict[str, Any]], *, label: str = "[dev-up]") -> str:
    if not devices:
        raise RuntimeError("GATE_BLOCK: no Flutter device is visible for app launch.")
    if len(devices) == 1:
        return str(devices[0].get("id") or "").strip()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        options = "\n".join(
            f"  - {device.get('name', '')} ({device.get('id', '')}, {device.get('targetPlatform', '')})"
            for device in devices
        )
        raise RuntimeError(
            "GATE_BLOCK: multiple Flutter devices visible; rerun with --device-id <id>.\n"
            + options
        )
    print(f"{label} multiple Flutter devices visible; pick one:", file=sys.stderr)
    for idx, device in enumerate(devices, 1):
        print(
            f"  [{idx}] {device.get('name', '')} ({device.get('id', '')}, {device.get('targetPlatform', '')})",
            file=sys.stderr,
        )
    while True:
        print(f"Select device [1-{len(devices)}]: ", end="", file=sys.stderr, flush=True)
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("GATE_BLOCK: no selection received; rerun with --device-id <id>.")
        choice = line.strip()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(devices):
                return str(devices[index - 1].get("id") or "").strip()
        print(f"  invalid selection: {choice!r}", file=sys.stderr)


def find_device(
    device_id: str,
    *,
    app_dir: Path = DEFAULT_APP_DIR,
    include_mobile: bool = True,
    include_web: bool = True,
    include_desktop: bool = False,
) -> dict[str, Any] | None:
    for device in discover_flutter_devices(
        app_dir,
        include_mobile=include_mobile,
        include_web=include_web,
        include_desktop=include_desktop,
    ):
        if str(device.get("id", "")).strip() == device_id:
            return device
    return None


def detect_device_kind(
    device_id: str,
    *,
    target_platform: str = "",
    emulator: bool | None = None,
) -> str:
    target = target_platform.strip().lower()
    device_norm = device_id.strip().lower()
    if target.startswith("web") or device_norm in WEB_DEVICE_IDS:
        return "web"
    if target.startswith("android"):
        if emulator or device_norm.startswith("emulator-") or "android sdk" in device_id:
            return "android_emulator"
        if shutil.which("adb"):
            probe = subprocess.run(
                ["adb", "-s", device_id, "get-state"],
                text=True,
                capture_output=True,
                check=False,
            )
            if probe.returncode == 0:
                return "android_physical"
        return "android_physical"
    return "ios_or_macos"


def resolve_app_endpoint_overrides(
    env_name: str,
    device_kind: str,
    *,
    topology: dict[str, Any] | None = None,
) -> dict[str, str]:
    manifest = topology or load_environment_topology()
    target_name = app_target_for_env(env_name)
    target = get_target(manifest, target_name)
    public_bases = dict(target.get("publicBases") or {})
    if str(target.get("backend", "")).strip() == "local" and device_kind.startswith("android"):
        # alpha's repo-owned TLS plane is port-routed. Pure localhost is the
        # only portable Android physical-device target with adb reverse.
        collapse_to_localhost = env_name == "alpha"
        public_bases = {
            key: _rewrite_android_local_base(
                str(value),
                collapse_to_localhost=collapse_to_localhost,
            )
            for key, value in public_bases.items()
        }
    return {
        "target": target_name,
        "gatewayBaseUrl": str(public_bases["api"]).rstrip("/"),
        "mediaAvatarBaseUrl": str(public_bases["mediaAvatar"]).rstrip("/"),
        "mediaImageBaseUrl": str(public_bases["mediaImage"]).rstrip("/"),
        "mediaVideoBaseUrl": str(public_bases["mediaVideo"]).rstrip("/"),
        "mediaUploadBaseUrl": str(public_bases["mediaUpload"]).rstrip("/"),
    }


def build_start_app_command(
    env_name: str,
    device_id: str,
    *,
    topology: dict[str, Any] | None = None,
    rollout_mode: str = "",
) -> list[str]:
    manifest = topology or load_environment_topology()
    device = find_device(device_id, app_dir=DEFAULT_APP_DIR, include_desktop=False) or {}
    device_kind = detect_device_kind(
        device_id,
        target_platform=str(device.get("targetPlatform", "")),
        emulator=bool(device.get("emulator", False)) if device else None,
    )
    overrides = resolve_app_endpoint_overrides(env_name, device_kind, topology=manifest)
    command = [
        "bash",
        "quwoquan_app/scripts/device/start_app_instance.sh",
        "--env",
        runtime_env_for_dev_env(env_name),
        "--device-id",
        device_id,
        "--gateway-base-url",
        overrides["gatewayBaseUrl"],
        "--media-avatar-base-url",
        overrides["mediaAvatarBaseUrl"],
        "--media-image-base-url",
        overrides["mediaImageBaseUrl"],
        "--media-video-base-url",
        overrides["mediaVideoBaseUrl"],
        "--media-upload-base-url",
        overrides["mediaUploadBaseUrl"],
        "--instance-namespace",
        f"{env_name}-dev-up",
        "--service-mode",
        f"{env_name}-dev-up",
    ]
    if rollout_mode:
        command.extend(["--rollout-mode", rollout_mode])
    return command


def launch_app(
    env_name: str,
    device_id: str,
    *,
    topology: dict[str, Any] | None = None,
    rollout_mode: str = "",
    log_path: Path | None = None,
    startup_wait_seconds: float = 1.5,
) -> subprocess.Popen[str]:
    manifest = topology or load_environment_topology()
    target_name = app_target_for_env(env_name)
    target = get_target(manifest, target_name)
    device = find_device(device_id, app_dir=DEFAULT_APP_DIR, include_desktop=False) or {}
    device_kind = detect_device_kind(
        device_id,
        target_platform=str(device.get("targetPlatform", "")),
        emulator=bool(device.get("emulator", False)) if device else None,
    )
    command_env = os.environ.copy()
    if str(target.get("backend", "")).strip() == "local" and device_kind.startswith("android"):
        enable_android_adb_reverse(device_id, target_name, topology=manifest)
        command_env[ANDROID_LOCAL_DEBUG_CA_ENV] = str(
            local_target_android_debug_ca_cert(target_name)
        )
        command_env[ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV] = "1"
    command = build_start_app_command(
        env_name,
        device_id,
        topology=manifest,
        rollout_mode=rollout_mode,
    )
    launch_log = log_path or (ROOT / "artifacts" / "stackctl" / runtime_env_for_dev_env(env_name) / "app-launch.log")
    launch_log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = launch_log.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=command_env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    if startup_wait_seconds > 0:
        time.sleep(startup_wait_seconds)
    if process.poll() is not None:
        output = launch_log.read_text(encoding="utf-8") if launch_log.exists() else ""
        raise RuntimeError(
            "app launch exited before reaching steady state:\n"
            + summarize_output(output)
        )
    return process


def enable_android_adb_reverse(
    device_id: str,
    target_name: str,
    *,
    topology: dict[str, Any] | None = None,
) -> list[int]:
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("GATE_BLOCK: adb not found in PATH; cannot prepare Android physical device reverse tunnel.")
    ports = local_target_ports(target_name, topology=topology)
    for port in ports:
        probe = subprocess.run(
            [adb, "-s", device_id, "reverse", f"tcp:{port}", f"tcp:{port}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            detail = (probe.stderr or probe.stdout or "").strip()
            raise RuntimeError(
                f"GATE_BLOCK: adb reverse tcp:{port} failed for {device_id}: {detail or 'unknown adb failure'}"
            )
    return ports


def local_target_ports(
    target_name: str,
    *,
    topology: dict[str, Any] | None = None,
) -> list[int]:
    manifest = topology or load_environment_topology()
    target = get_target(manifest, target_name)
    if str(target.get("backend", "")).strip() != "local":
        return []
    ports: set[int] = set()
    for url in list((target.get("publicBases") or {}).values()) + list(
        (target.get("origins") or {}).values()
    ):
        parsed = urllib.parse.urlparse(url)
        if parsed.port:
            ports.add(parsed.port)
    profile_name = str(target.get("portProfile") or "").strip()
    if profile_name:
        for port in profile_ports(load_port_manifest(), profile_name).values():
            ports.add(int(port))
    return sorted(ports)


def local_target_android_debug_ca_cert(target_name: str) -> Path:
    cert_path = ANDROID_LOCAL_DEBUG_CA_PATHS.get(target_name)
    if cert_path is None:
        raise RuntimeError(
            f"GATE_BLOCK: local Android debug CA path is undefined for target {target_name}"
        )
    if not cert_path.is_file():
        raise RuntimeError(
            f"GATE_BLOCK: local Android debug CA certificate missing for {target_name}: {cert_path}"
        )
    return cert_path


def _android_local_loopback_host(host: str, *, collapse_to_localhost: bool = False) -> str:
    if collapse_to_localhost:
        return "localhost"
    if host == "127.0.0.1":
        return "localhost"
    if host == "localhost" or host.endswith(ANDROID_LOCAL_LOOPBACK_SUFFIX):
        return host
    suffix = ".quwoquan-env.test"
    if host.endswith(suffix):
        return host[: -len(suffix)] + ANDROID_LOCAL_LOOPBACK_SUFFIX
    return host


def _rewrite_android_local_base(url: str, *, collapse_to_localhost: bool = False) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return url
    host = _android_local_loopback_host(
        parsed.hostname,
        collapse_to_localhost=collapse_to_localhost,
    )
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _rewrite_localhost_base(url: str, host: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return url
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shared helpers for stackctl dev-up flows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-devices")
    _add_device_args(list_parser)
    list_parser.add_argument("--output", default="")

    pick_parser = subparsers.add_parser("pick-device")
    _add_device_args(pick_parser)
    return parser


def _add_device_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-dir", default=str(DEFAULT_APP_DIR))
    parser.add_argument("--mobile-only", action="store_true")
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--include-desktop", action="store_true")


def _discover_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    include_mobile = not args.web_only
    include_web = not args.mobile_only
    return discover_flutter_devices(
        Path(args.app_dir),
        include_mobile=include_mobile,
        include_web=include_web,
        include_desktop=args.include_desktop,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "list-devices":
            payload = json.dumps(build_device_report(_discover_from_args(args)), ensure_ascii=False, indent=2) + "\n"
            if args.output:
                output_path = Path(args.output)
                if not output_path.is_absolute():
                    output_path = ROOT / output_path
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(payload, encoding="utf-8")
            sys.stdout.write(payload)
            return 0
        if args.command == "pick-device":
            device_id = pick_device(
                _discover_from_args(args),
                label="[dev-up]",
            )
            print(device_id)
            return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
