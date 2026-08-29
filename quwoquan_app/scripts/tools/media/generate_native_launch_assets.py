#!/usr/bin/env python3
"""Generate / refresh native launch-screen assets.

Owner: App media/launch tooling (manual generator under tools/media).
Input: Flutter welcome-final-frame export via
  flutter test --no-pub tool/generate_native_launch_welcome_final_test.dart
Output: native Android launch drawable assets under android/.../res.
Write behavior: overwrites generated launch PNG resources only.

Android 12+ uses the static app icon configured by v31 styles; native code
never owns motion, replay, hints, or Flutter progress.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT


APP_DIR = APP_ROOT
ANDROID_RES = APP_DIR / "android" / "app" / "src" / "main" / "res"
MASTER = APP_DIR / "assets" / "brand" / "launch_welcome_final_master.png"
ANDROID_FINAL = ANDROID_RES / "drawable-nodpi" / "launch_welcome_final.png"
RESPONSIVE_WIDTHS = (360, 393, 430)


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


def require_flutter_outputs() -> None:
    required = [MASTER, ANDROID_FINAL]
    for width in RESPONSIVE_WIDTHS:
        root = ANDROID_RES / f"drawable-sw{width}dp-nodpi"
        required.extend(
            [
                root / "launch_brand_cluster.png",
                root / "launch_brand_footer.png",
            ]
        )
    missing = [
        str(path.relative_to(APP_DIR))
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise SystemExit(
            "FAIL: Flutter welcome export did not produce canonical native assets: "
            + ", ".join(missing)
        )


def main() -> None:
    run_flutter_final_frame_export()
    require_flutter_outputs()
    print(f"OK: native launch final frame at {ANDROID_FINAL}")


if __name__ == "__main__":
    main()
