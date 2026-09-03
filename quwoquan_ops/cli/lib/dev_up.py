#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import active_consumer_leases
from quwoquan_ops.cli.lib.output_paths import deployment_render_dir
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports


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
    "alpha": "本地 Alpha production Remote composition + App",
    "beta": "本地 beta 栈 + App",
    "gamma": "local gamma mirror + App",
    "prod-sim": "prod-sim App 连接",
    "prod": "prod-hosted edge health + App",
}
def _configured_root(env_name: str, default_name: str) -> Path:
    configured = os.environ.get(env_name, "").strip()
    path = Path(configured).expanduser() if configured else ROOT / default_name
    if not path.is_absolute():
        path = ROOT / path
    return path


def output_root() -> Path:
    return _configured_root("QWQ_OUTPUT_ROOT", ".qwq_output")


def env_output_root(env_name: str) -> Path:
    return output_root() / "env" / runtime_env_for_dev_env(env_name)


def deployment_render_root(target_name: str) -> Path:
    """Rendered deployment input is ephemeral and must not enter .qwq_output."""
    return deployment_render_dir(
        target_name.split("-", 1)[0],
        target=target_name,
    )


def env_cache_target_root(env_name: str, target_name: str) -> Path:
    return env_output_root(env_name) / "local" / target_name / "cache"


def observability_run_root(env_name: str) -> Path:
    configured = os.environ.get("QWQ_OBSERVABILITY_RUN_ROOT", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else ROOT / path
    from quwoquan_ops.cli.lib.local_run import resolve_local_run

    runtime_env = runtime_env_for_dev_env(env_name)
    target = {
        "alpha": "alpha-local",
        "beta": "beta-local",
        "gamma": "gamma-local",
        "prod": "prod-sim",
    }[runtime_env]
    return resolve_local_run(
        env=runtime_env,
        target=target,
        action="status",
        root=output_root(),
    ).observability_root


def observability_runtime_logs_root(env_name: str) -> Path:
    return observability_run_root(env_name) / "logs" / "service"


def run_root(env_name: str) -> Path:
    configured = os.environ.get("QWQ_RUN_ROOT", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else ROOT / path
    from quwoquan_ops.cli.lib.local_run import resolve_local_run

    runtime_env = runtime_env_for_dev_env(env_name)
    target = {
        "alpha": "alpha-local",
        "beta": "beta-local",
        "gamma": "gamma-local",
        "prod": "prod-sim",
    }[runtime_env]
    return resolve_local_run(
        env=runtime_env,
        target=target,
        action="status",
        root=output_root(),
    ).run_root


def target_local_root(target_name: str) -> Path:
    env_name = runtime_env_for_dev_env(target_name.split("-", 1)[0])
    return env_output_root(env_name) / "local" / target_name


def target_process_root(env_name: str, target_name: str) -> Path:
    return env_output_root(env_name) / "local" / target_name / "process"


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
    """Extract one explainable top-level JSON array from noisy Flutter stdout."""

    decoder = json.JSONDecoder()
    candidates: list[tuple[int, int]] = []
    for start, character in enumerate(output):
        if character != "[":
            continue
        try:
            value, consumed = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            candidates.append((start, start + consumed))
    maximal = [
        candidate
        for candidate in candidates
        if not any(
            other != candidate
            and other[0] <= candidate[0]
            and other[1] >= candidate[1]
            for other in candidates
        )
    ]
    if not maximal:
        raise ValueError("flutter devices output missing JSON array")
    if len(maximal) != 1:
        raise ValueError("flutter devices output contains ambiguous JSON arrays")
    start, end = maximal[0]
    return output[start:end]


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
    flutter_executable: str | Path = "flutter",
) -> list[dict[str, Any]]:
    executable = str(flutter_executable).strip()
    if not executable:
        raise RuntimeError("GATE_BLOCK: Flutter device discovery executable is empty.")
    try:
        result = subprocess.run(
            [executable, "devices", "--machine"],
            cwd=str(app_dir),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise RuntimeError(
            f"flutter devices --machine could not start: {error}"
        ) from error
    if result.returncode != 0:
        raise RuntimeError(
            "flutter devices --machine failed:\n"
            + summarize_output((result.stdout or "") + (result.stderr or ""))
        )
    try:
        raw_devices = json.loads(extract_json_array(result.stdout or ""))
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(
            f"flutter devices --machine returned an invalid inventory: {error}"
        ) from error
    if not isinstance(raw_devices, list):
        raise RuntimeError(
            "flutter devices --machine returned a non-array inventory"
        )
    devices: list[dict[str, Any]] = []
    for raw in raw_devices:
        if not isinstance(raw, dict):
            raise RuntimeError(
                "flutter devices --machine inventory contains a non-object device"
            )
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


def select_device(
    devices: list[dict[str, Any]],
    *,
    device_id: str = "",
    label: str = "[dev-up]",
) -> str:
    """Resolve an explicit exact id or delegate interactive choice to ``pick_device``."""

    explicit = device_id.strip()
    if device_id and not explicit:
        raise RuntimeError("GATE_BLOCK: Flutter device id is empty after trimming.")
    if explicit:
        for device in devices:
            candidate = str(device.get("id") or "").strip()
            if candidate == explicit:
                return candidate
        raise RuntimeError(
            f"GATE_BLOCK: Flutter mobile device {explicit!r} is not visible; "
            "rerun device discovery or choose a connected iOS/Android device."
        )
    return pick_device(devices, label=label)


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
        for device in devices:
            candidate = str(device.get("id") or "").strip()
            if choice == candidate:
                return candidate
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
    if target == "ios":
        return "ios-simulator" if emulator else "ios-physical"
    if target in {"darwin", "macos"} or device_norm == "macos":
        return "macos"
    return "unknown"


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
    gateway_base_url = str(public_bases["api"]).rstrip("/")
    if device_kind == "web":
        gateway_base_url = f"{str(public_bases['publicWeb']).rstrip('/')}/api"
    return {
        "target": target_name,
        "gatewayBaseUrl": gateway_base_url,
        "legalBaseUrl": str(public_bases["legal"]).rstrip("/"),
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
    app_mode: str = "content-live",
    launch_receipt: Path | None = None,
    launch_log_ref: Path | None = None,
    artifact_manifest: Path | None = None,
    launcher_handoff: Path | None = None,
    candidate_digest: str = "",
    artifact_manifest_digest: str = "",
    launcher_handoff_digest: str = "",
) -> list[str]:
    del topology
    command = [
        "bash",
        "quwoquan_app/scripts/device/run_app_instance.sh",
        "--env",
        runtime_env_for_dev_env(env_name),
        "--target",
        app_target_for_env(env_name),
        "--device-id",
        device_id,
        "--mode",
        app_mode,
        "--instance-namespace",
        f"{env_name}-dev-up",
        "--service-mode",
        f"{env_name}-dev-up",
    ]
    if rollout_mode:
        command.extend(["--rollout-mode", rollout_mode])
    if launch_receipt is not None:
        command.extend(["--launch-receipt", str(launch_receipt)])
    if launch_log_ref is not None:
        command.extend(["--launch-log-ref", str(launch_log_ref)])
    release_values = (
        artifact_manifest,
        launcher_handoff,
        candidate_digest,
        artifact_manifest_digest,
        launcher_handoff_digest,
    )
    if any(value is not None and value != "" for value in release_values):
        if artifact_manifest is None or launcher_handoff is None or not all(
            (candidate_digest, artifact_manifest_digest, launcher_handoff_digest)
        ):
            raise ValueError("prod-sim candidate launch bundle is incomplete")
        command.extend(
            [
                "--artifact-manifest",
                str(artifact_manifest),
                "--launcher-handoff",
                str(launcher_handoff),
                "--candidate-digest",
                candidate_digest,
                "--artifact-manifest-digest",
                artifact_manifest_digest,
                "--launcher-handoff-digest",
                launcher_handoff_digest,
            ]
        )
    return command


def launch_app(
    env_name: str,
    device_id: str,
    *,
    topology: dict[str, Any] | None = None,
    rollout_mode: str = "",
    log_path: Path | None = None,
    startup_wait_seconds: float = 900,
    artifact_manifest: Path | None = None,
    launcher_handoff: Path | None = None,
    candidate_digest: str = "",
    artifact_manifest_digest: str = "",
    launcher_handoff_digest: str = "",
) -> subprocess.Popen[str]:
    from quwoquan_ops.cli.lib.app_launch_attempt import wait_for_app_launch_attempt

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
    if (
        str(target.get("backend", "")).strip() == "local"
        and str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ):
        command_env["QWQ_IOS_SIMULATOR_UDID"] = device_id
    if target_name == "prod-sim" and device_kind != "android_emulator":
        raise RuntimeError(
            "APP.LAUNCH.platform_unsupported: prod-sim exact Release supports only "
            "an Android emulator"
        )
    # device trust 由委托链内的 canonical run.sh 以真实 consumer lease 安装；
    # 这里不再用 fabricated lease 预装一份平行 trust 回执。
    launch_log = log_path or (
        observability_runtime_logs_root(env_name) / f"{env_name}-app-launch.log"
    )
    launch_receipt = launch_log.with_suffix(".receipt.json")
    command = build_start_app_command(
        env_name,
        device_id,
        topology=manifest,
        rollout_mode=rollout_mode,
        app_mode=("release-artifact" if target_name == "prod-sim" else "content-live"),
        launch_receipt=launch_receipt,
        launch_log_ref=launch_log,
        artifact_manifest=artifact_manifest,
        launcher_handoff=launcher_handoff,
        candidate_digest=candidate_digest,
        artifact_manifest_digest=artifact_manifest_digest,
        launcher_handoff_digest=launcher_handoff_digest,
    )
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
    if target_name == "prod-sim":
        deadline = time.monotonic() + startup_wait_seconds
        while not launch_receipt.exists():
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(
                    "APP.LAUNCH.receipt_absent: prod-sim launcher exited before "
                    f"creating its receipt (exit={return_code})"
                )
            if time.monotonic() >= deadline:
                process.terminate()
                raise RuntimeError(
                    f"APP.LAUNCH.receipt_absent: {launch_receipt}"
                )
            time.sleep(0.05)

    def process_watchdog() -> None:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                "APP.LAUNCH.launch_failed: App launcher exited before a terminal "
                f"receipt (exit={return_code})"
            )

    try:
        attempt = wait_for_app_launch_attempt(
            launch_receipt,
            timeout_seconds=startup_wait_seconds,
            poll_seconds=0.05 if target_name == "prod-sim" else 0.2,
            watchdog=process_watchdog if target_name == "prod-sim" else None,
            watchdog_interval_seconds=0.05,
        )
    except (RuntimeError, TimeoutError) as error:
        if process.poll() is None:
            process.terminate()
        raise RuntimeError(str(error)) from error
    if attempt["status"] != "launched":
        output = launch_log.read_text(encoding="utf-8") if launch_log.exists() else ""
        blocker = str(attempt.get("firstBlocker") or "APP.LAUNCH.launch_failed")
        raise RuntimeError(
            f"{blocker}: App launch did not reach launched "
            f"(status={attempt['status']}, "
            f"configurationState={attempt['configurationState']}, "
            f"runtimeHealthStatus={attempt['runtimeHealthStatus']}):\n"
            + summarize_output(output)
        )
    if target_name == "prod-sim":
        expected_identity = {
            "candidateDigest": candidate_digest,
            "artifactManifestDigest": artifact_manifest_digest,
            "launcherHandoffDigest": launcher_handoff_digest,
            "runtimeHealthStatus": "healthy",
            "configurationState": "complete",
        }
        mismatches = [
            field
            for field, expected in expected_identity.items()
            if attempt.get(field) != expected
        ]
        terminal_fields = (
            "startupTerminalAttemptId",
            "startupTerminalEvidenceDigest",
            "startupTerminalEvidenceRef",
        )
        if mismatches or any(not str(attempt.get(field) or "") for field in terminal_fields):
            raise RuntimeError(
                "APP.LAUNCH.receipt_invalid: prod-sim receipt is not candidate-bound "
                f"and healthy; mismatched={sorted(mismatches)}"
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
    manifest = topology or load_environment_topology()
    local_targets = sorted(
        {
            target
            for target in DEV_UP_APP_TARGETS.values()
            if target and target != "prod-hosted"
        }
    )
    for other_target in local_targets:
        if other_target == target_name:
            continue
        for lease in active_consumer_leases(other_target, adb_path=adb):
            if str(lease.get("device") or "").strip() == device_id:
                raise RuntimeError(
                    "GATE_BLOCK: Android device has an active consumer lease for "
                    f"{other_target}; release that app session before switching to {target_name}."
                )

    canonical_ports: set[int] = set()
    for local_target in local_targets:
        try:
            candidate = get_target(manifest, local_target)
        except (KeyError, ValueError):
            continue
        profile_name = str(candidate.get("portProfile") or "").strip()
        if profile_name:
            canonical_ports.update(
                int(port)
                for port in profile_ports(load_port_manifest(), profile_name).values()
            )
    desired_ports = set(ports)
    listed_before = subprocess.run(
        [adb, "-s", device_id, "reverse", "--list"],
        text=True,
        capture_output=True,
        check=False,
    )
    if listed_before.returncode != 0:
        detail = (listed_before.stderr or listed_before.stdout or "").strip()
        raise RuntimeError(
            f"GATE_BLOCK: cannot inspect existing adb reverse mappings for {device_id}: "
            f"{detail or 'unknown adb failure'}"
        )
    existing_ports = _same_port_adb_reverse_mappings(listed_before.stdout)
    stale_ports = sorted((existing_ports & canonical_ports) - desired_ports)
    for port in stale_ports:
        removed = subprocess.run(
            [adb, "-s", device_id, "reverse", "--remove", f"tcp:{port}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if removed.returncode != 0:
            detail = (removed.stderr or removed.stdout or "").strip()
            raise RuntimeError(
                f"GATE_BLOCK: cannot remove stale adb reverse tcp:{port} for {device_id}: "
                f"{detail or 'unknown adb failure'}"
            )
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
    listed = subprocess.run(
        [adb, "-s", device_id, "reverse", "--list"],
        text=True,
        capture_output=True,
        check=False,
    )
    if listed.returncode != 0:
        detail = (listed.stderr or listed.stdout or "").strip()
        raise RuntimeError(
            f"GATE_BLOCK: cannot verify adb reverse for {device_id}: {detail or 'unknown adb failure'}"
        )
    missing = [
        port
        for port in ports
        if not any(
            line.split().count(f"tcp:{port}") >= 2
            for line in listed.stdout.splitlines()
        )
    ]
    if missing:
        raise RuntimeError(
            "GATE_BLOCK: adb reverse verification is incomplete for "
            f"{device_id}; missing ports={','.join(str(port) for port in missing)}"
        )
    remaining_stale = sorted(
        (_same_port_adb_reverse_mappings(listed.stdout) & canonical_ports)
        - desired_ports
    )
    if remaining_stale:
        raise RuntimeError(
            "GATE_BLOCK: stale cross-target adb reverse mappings remain for "
            f"{device_id}: {','.join(str(port) for port in remaining_stale)}"
        )
    return ports


def _same_port_adb_reverse_mappings(output: str) -> set[int]:
    ports: set[int] = set()
    for line in output.splitlines():
        endpoints = [part for part in line.split() if part.startswith("tcp:")]
        if len(endpoints) < 2 or endpoints[-2] != endpoints[-1]:
            continue
        try:
            ports.add(int(endpoints[-1].removeprefix("tcp:")))
        except ValueError:
            continue
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shared helpers for stackctl dev-up flows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-devices")
    _add_device_args(list_parser)
    list_parser.add_argument("--output", default="")

    pick_parser = subparsers.add_parser("pick-device")
    _add_device_args(pick_parser)
    pick_parser.add_argument("--device-id", default="")
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
