#!/usr/bin/env python3
"""Generate / refresh native launch-screen assets.

Canonical welcome-final-frame pixels come from Flutter:

  flutter test --no-pub tool/generate_native_launch_welcome_final_test.dart

That Dart tool writes a same-source transparent brand cluster plus adaptive
gradient resources. Android 12+ uses the static app icon configured by v31
styles; native code never owns motion, replay, hints, or Flutter progress.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image


APP_DIR = Path(__file__).resolve().parents[2]
ANDROID_RES = APP_DIR / "android" / "app" / "src" / "main" / "res"
IOS_LAUNCH_IMAGESET = (
    APP_DIR / "ios" / "Runner" / "Assets.xcassets" / "LaunchImage.imageset"
)
IOS_LAUNCH_TRANSITION_IMAGESET = (
    APP_DIR
    / "ios"
    / "Runner"
    / "Assets.xcassets"
    / "LaunchTransitionBackground.imageset"
)
MASTER = APP_DIR / "assets" / "brand" / "launch_welcome_final_master.png"
ANDROID_FINAL = ANDROID_RES / "drawable-nodpi" / "launch_welcome_final.png"

BRAND_BLUE = (10, 132, 255, 255)
WELCOME_GRADIENT_START = (20, 145, 255, 255)
WELCOME_GRADIENT_END = (21, 84, 209, 255)


def vertical_gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    img = Image.new("RGBA", size)
    pixels = img.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        if t < 0.48:
            k = t / 0.48
            c0, c1 = WELCOME_GRADIENT_START, BRAND_BLUE
        else:
            k = (t - 0.48) / 0.52
            c0, c1 = BRAND_BLUE, WELCOME_GRADIENT_END
        color = tuple(round(c0[i] + (c1[i] - c0[i]) * k) for i in range(4))
        for x in range(width):
            pixels[x, y] = color
    return img


def run_flutter_final_frame_export() -> None:
    result = subprocess.run(
        [
            "flutter",
            "test",
            "--no-pub",
            "tool/generate_native_launch_welcome_final_test.dart",
        ],
        cwd=APP_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def ensure_fallback_assets() -> None:
    """Only used if Flutter export did not produce the master bitmap."""
    if MASTER.exists() and ANDROID_FINAL.exists():
        return
    print(
        "WARN: Flutter master missing; writing gradient-only fallback "
        "(re-run with Flutter export for branded final frame).",
        file=sys.stderr,
    )
    ANDROID_FINAL.parent.mkdir(parents=True, exist_ok=True)
    vertical_gradient((1179, 2556)).save(ANDROID_FINAL)
    IOS_LAUNCH_IMAGESET.mkdir(parents=True, exist_ok=True)
    IOS_LAUNCH_TRANSITION_IMAGESET.mkdir(parents=True, exist_ok=True)
    sizes = {
        "LaunchTransitionBackground.png": (1, 3),
        "LaunchTransitionBackground@2x.png": (2, 6),
        "LaunchTransitionBackground@3x.png": (3, 9),
    }
    for filename, size in sizes.items():
        img = vertical_gradient(size)
        img.save(IOS_LAUNCH_TRANSITION_IMAGESET / filename)
        img.save(IOS_LAUNCH_IMAGESET / filename.replace("LaunchTransitionBackground", "LaunchImage"))


def main() -> None:
    run_flutter_final_frame_export()
    if not MASTER.exists() or not ANDROID_FINAL.exists():
        ensure_fallback_assets()
    print(f"OK: native launch final frame at {ANDROID_FINAL}")


if __name__ == "__main__":
    main()
