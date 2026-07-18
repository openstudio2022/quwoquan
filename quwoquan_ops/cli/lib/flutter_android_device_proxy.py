from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Sequence


ANDROID_DEVICE_INVENTORY_ENV = "QWQ_PATROL_ANDROID_DEVICE_INVENTORY"
REAL_FLUTTER_ENV = "QWQ_PATROL_REAL_FLUTTER"


def _is_machine_device_inventory(args: Sequence[str]) -> bool:
    return "devices" in args and "--machine" in args


def _is_verbose_doctor(args: Sequence[str]) -> bool:
    return "doctor" in args and "--verbose" in args


def _print_java_version() -> int:
    javac = shutil.which("javac")
    if javac is None:
        raise RuntimeError("javac is required for Android Patrol compatibility checks")
    result = subprocess.run(
        [javac, "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or not output.startswith("javac "):
        raise RuntimeError("javac --version failed")
    version = output.split(maxsplit=1)[1]
    sys.stdout.write(f"[OK] Android toolchain \u2022 Java version {version}\n")
    return 0


def _load_device_inventory() -> list[dict[str, object]]:
    raw = os.environ.get(ANDROID_DEVICE_INVENTORY_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{ANDROID_DEVICE_INVENTORY_ENV} is required")
    payload = json.loads(raw)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Android Patrol device inventory must be a non-empty list")
    for index, device in enumerate(payload):
        if not isinstance(device, dict):
            raise RuntimeError(f"Android Patrol device {index} must be an object")
        required = ("id", "name", "targetPlatform", "emulator")
        if any(key not in device for key in required):
            raise RuntimeError(f"Android Patrol device {index} is incomplete")
        target = str(device["targetPlatform"])
        if not target.startswith("android-"):
            raise RuntimeError(
                f"Android Patrol device {index} has invalid targetPlatform {target!r}"
            )
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _is_machine_device_inventory(args):
        json.dump(_load_device_inventory(), sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if _is_verbose_doctor(args):
        return _print_java_version()

    real_flutter = os.environ.get(REAL_FLUTTER_ENV, "").strip()
    if not real_flutter or not os.path.isabs(real_flutter):
        raise RuntimeError(f"{REAL_FLUTTER_ENV} must be an absolute executable path")
    os.execv(real_flutter, [real_flutter, *args])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
