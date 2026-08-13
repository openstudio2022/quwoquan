"""Android 侧证据：设备属性、launcher 解析、任务栈、Gate→Main 顺序与 APK 定位。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .context import (
    APP_DIR,
    DEFAULT_ANDROID_APK,
    DEFAULT_ANDROID_APK_DIR,
    DEFAULT_ANDROID_APK_METADATA,
)
from .execution import run


def read_android_device_abi(device: str) -> str:
    abi = run(
        ["adb", "-s", device, "shell", "getprop", "ro.product.cpu.abi"],
        timeout=15,
    ).stdout.strip()
    if not abi:
        raise RuntimeError(f"Unable to resolve Android ABI for device {device}")
    return abi


def android_device_kind(device: str) -> str:
    qemu = run(
        ["adb", "-s", device, "shell", "getprop", "ro.kernel.qemu"],
        check=False,
        timeout=15,
    ).stdout.strip()
    return "simulator" if qemu == "1" else "true_device"


def normalize_android_component(component: str, package: str) -> str:
    value = component.strip()
    if "/" not in value:
        return value
    component_package, activity = value.split("/", 1)
    if activity.startswith("."):
        activity = f"{component_package}{activity}"
    return f"{component_package}/{activity}"


def parse_android_launcher_resolution(
    raw: str,
    *,
    package: str,
    expected_activity: str,
) -> dict[str, Any]:
    components = [
        line.strip()
        for line in raw.splitlines()
        if "/" in line and not line.lstrip().startswith(("priority=", "match="))
    ]
    resolved = components[-1] if components else ""
    return {
        "resolvedActivity": resolved,
        "matchesExpectedGate": (
            normalize_android_component(resolved, package)
            == normalize_android_component(expected_activity, package)
        ),
    }


def parse_android_task_snapshot(
    raw: str,
    *,
    package: str,
    main_activity: str,
) -> dict[str, Any]:
    expected = normalize_android_component(main_activity, package)
    history_components = re.findall(
        r"Hist #\d+:\s+ActivityRecord\{[^}]*\s+u\d+\s+([^\s}]+)",
        raw,
    )
    normalized_history = [
        normalize_android_component(component, package)
        for component in history_components
    ]
    main_instances = sum(component == expected for component in normalized_history)
    return {
        "historyComponents": normalized_history,
        "mainActivityInstances": main_instances,
        "singleMainTask": main_instances == 1,
    }


def android_gate_main_order_evidence(log: str) -> dict[str, Any]:
    static_frame_indexes = [
        match.start()
        for event in (
            "android_gate_static_frame_drawn",
            "android_gate_static_frame_draw_timeout",
        )
        for match in re.finditer(re.escape(event), log)
    ]
    focus_indexes = [
        match.start()
        for match in re.finditer("android_gate_window_focus_confirmed", log)
    ]
    focus_released_indexes = [
        match.start()
        for match in re.finditer("android_gate_window_focus_released", log)
    ]
    handoff_indexes = [
        match.start()
        for match in re.finditer("android_gate_main_handoff", log)
    ]
    main_indexes = [
        match.start()
        for match in re.finditer("android_activity_on_create", log)
    ]
    event_counts = {
        "staticFrameReady": len(static_frame_indexes),
        "windowFocusConfirmed": len(focus_indexes),
        "windowFocusReleased": len(focus_released_indexes),
        "mainHandoff": len(handoff_indexes),
        "mainActivityCreate": len(main_indexes),
    }
    unique_attempt = all(count == 1 for count in event_counts.values())
    ordered = bool(
        unique_attempt
        and static_frame_indexes[0] < handoff_indexes[0]
        and focus_indexes[0]
        < focus_released_indexes[0]
        < handoff_indexes[0]
        < main_indexes[0]
    )
    return {
        "eventCounts": event_counts,
        "uniqueAttemptLog": unique_attempt,
        "ordered": ordered,
    }


def android_gate_main_order_observed(log: str) -> bool:
    return bool(android_gate_main_order_evidence(log)["ordered"])


def android_log_after_baseline(
    baseline: str,
    current: str,
) -> tuple[str, bool]:
    baseline_lines = baseline.splitlines()
    current_lines = current.splitlines()
    if not baseline_lines:
        return current, True
    if current_lines[: len(baseline_lines)] != baseline_lines:
        return current, False
    return "\n".join(current_lines[len(baseline_lines) :]), True


def android_package_anr_evidence(log: str, package: str) -> dict[str, Any]:
    package_token = re.compile(
        rf"(?<![A-Za-z0-9_.]){re.escape(package)}(?![A-Za-z0-9_.])"
    )
    signals: list[str] = []
    matched_line_count = 0
    for line in log.splitlines():
        if package_token.search(line) is None:
            continue
        line_signals = []
        if re.search(r"\bam_anr\s*:", line):
            line_signals.append("am_anr")
        if re.search(rf"\bANR in\s+{re.escape(package)}(?![A-Za-z0-9_.])", line):
            line_signals.append("anr_in_package")
        if "Input dispatching timed out" in line:
            line_signals.append("input_dispatch_timeout")
        if not line_signals:
            continue
        matched_line_count += 1
        for signal in line_signals:
            if signal not in signals:
                signals.append(signal)
    return {
        "detected": bool(signals),
        "signals": signals,
        "matchedLineCount": matched_line_count,
    }


def android_fresh_startup_log_evidence(
    *,
    baseline: str,
    current: str,
    package: str,
) -> dict[str, Any]:
    observation_log, baseline_applied = android_log_after_baseline(
        baseline,
        current,
    )
    order = android_gate_main_order_evidence(observation_log)
    anr = android_package_anr_evidence(observation_log, package)
    return {
        "observationLog": observation_log,
        "baselineApplied": baseline_applied,
        "baselineLineCount": len(baseline.splitlines()),
        "observationLineCount": len(observation_log.splitlines()),
        "startupAttemptLogUnique": order["uniqueAttemptLog"],
        "gateEventCounts": order["eventCounts"],
        "gateMainOrderObserved": order["ordered"],
        "androidAnrDetected": anr["detected"],
        "androidAnrSignals": anr["signals"],
        "androidAnrMatchedLineCount": anr["matchedLineCount"],
        "passed": bool(
            baseline_applied
            and order["uniqueAttemptLog"]
            and order["ordered"]
            and not anr["detected"]
        ),
    }


def resolve_android_launch_resource_profile(device: str) -> str:
    size_output = run(
        ["adb", "-s", device, "shell", "wm", "size"],
        check=False,
        timeout=15,
    ).stdout
    density_output = run(
        ["adb", "-s", device, "shell", "wm", "density"],
        check=False,
        timeout=15,
    ).stdout
    size_matches = re.findall(r"(?:Override|Physical) size:\s*(\d+)x(\d+)", size_output)
    density_matches = re.findall(
        r"(?:Override|Physical) density:\s*(\d+)",
        density_output,
    )
    if not size_matches or not density_matches:
        return "default"
    width_px, height_px = (int(value) for value in size_matches[-1])
    density_dpi = int(density_matches[-1])
    if density_dpi <= 0:
        return "default"
    smallest_width_dp = min(width_px, height_px) * 160 / density_dpi
    supported = [
        width for width in (360, 393, 430) if width <= smallest_width_dp + 0.5
    ]
    return f"sw{max(supported)}dp" if supported else "default"


def native_launch_visual_provenance(profile: str) -> dict[str, Any]:
    resource_root = APP_DIR / "android/app/src/main/res"
    qualifier = "" if profile == "default" else f"-{profile}"
    image_qualifier = "-nodpi" if profile == "default" else f"-{profile}-nodpi"
    files = [
        APP_DIR / "tool/generate_native_launch_welcome_final_test.dart",
        APP_DIR / "lib/runtime/shell/welcome/welcome_brand_cluster.dart",
        resource_root / f"drawable{qualifier}/launch_background.xml",
        resource_root / f"drawable{image_qualifier}/launch_brand_cluster.png",
        resource_root / f"drawable{image_qualifier}/launch_brand_footer.png",
    ]
    missing = [str(path.relative_to(APP_DIR)) for path in files if not path.is_file()]
    digest = hashlib.sha256()
    if not missing:
        for path in files:
            relative = str(path.relative_to(APP_DIR))
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    launch_xml = files[2].read_text(encoding="utf-8") if files[2].is_file() else ""
    return {
        "profile": profile,
        "sourceDigest": digest.hexdigest() if not missing else "",
        "sourceFiles": [str(path.relative_to(APP_DIR)) for path in files],
        "missingFiles": missing,
        "contractVerified": (
            not missing
            and "Generated by generate_native_launch_welcome_final_test.dart"
            in launch_xml
        ),
    }


def resolve_android_apk(apk: Path, device: str) -> Path:
    if apk.exists():
        return apk

    default_apk_requested = (
        apk.resolve(strict=False) == DEFAULT_ANDROID_APK.resolve(strict=False)
    )
    if default_apk_requested:
        abi = read_android_device_abi(device)
        if DEFAULT_ANDROID_APK_METADATA.exists():
            metadata = json.loads(
                DEFAULT_ANDROID_APK_METADATA.read_text(encoding="utf-8")
            )
            for element in metadata.get("elements", []):
                filters = {
                    item.get("filterType"): item.get("value")
                    for item in element.get("filters", [])
                }
                if filters.get("ABI") != abi:
                    continue
                output_file = element.get("outputFile")
                if not output_file:
                    continue
                for base_dir in (
                    DEFAULT_ANDROID_APK_DIR,
                    DEFAULT_ANDROID_APK_METADATA.parent,
                ):
                    candidate = base_dir / output_file
                    if candidate.exists():
                        return candidate

        candidate = DEFAULT_ANDROID_APK_DIR / f"app-{abi}-debug.apk"
        if candidate.exists():
            return candidate

        available = ", ".join(
            path.name for path in sorted(DEFAULT_ANDROID_APK_DIR.glob("app-*-debug.apk"))
        )
        raise FileNotFoundError(
            "Android install requested but default app-debug.apk was not found; "
            f"device ABI is {abi}, available split APKs: {available or 'none'}"
        )

    raise FileNotFoundError(f"Android install requested but APK was not found: {apk}")
