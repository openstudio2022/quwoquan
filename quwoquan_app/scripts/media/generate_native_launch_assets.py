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
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[2]
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
    missing = [str(path.relative_to(APP_DIR)) for path in required if not path.is_file()]
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
