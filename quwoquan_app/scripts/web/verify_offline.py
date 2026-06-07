"""Verify Web offline resources (fonts, bootstrap, lib scan)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from _common.paths import APP_ROOT, LIB_DIR, WEB_DIR
from _common.subprocess_util import run_checked
from fonts.gate import gate_verify


def _scan_lib_forbidden() -> list[str]:
    errors: list[str] = []
    patterns = (
        (re.compile(r"import\s+['\"]package:google_fonts/"), "google_fonts import"),
        (re.compile(r"fonts\.gstatic\.com"), "fonts.gstatic.com literal"),
        (re.compile(r"fonts\.googleapis\.com"), "fonts.googleapis.com literal"),
    )
    for path in sorted(LIB_DIR.rglob("*.dart")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(APP_ROOT)
        for pattern, label in patterns:
            if pattern.search(text):
                errors.append(f"{rel}: forbidden {label}")
    return errors


def _verify_bootstrap() -> list[str]:
    bootstrap = WEB_DIR / "flutter_bootstrap.js"
    if not bootstrap.is_file():
        return ["missing web/flutter_bootstrap.js"]
    text = bootstrap.read_text(encoding="utf-8")
    if "canvasKitBaseUrl" not in text:
        return ["web/flutter_bootstrap.js missing canvasKitBaseUrl"]
    return []


def verify_offline(*, build: bool = False, build_mode: str = "debug") -> None:
    print("[qwq-app web verify-offline] fonts: running")
    gate_verify()
    print("[qwq-app web verify-offline] fonts: OK")

    bootstrap_errors = _verify_bootstrap()
    if bootstrap_errors:
        print("[qwq-app web verify-offline] bootstrap: FAIL")
        for err in bootstrap_errors:
            print(f"  - {err}")
        raise SystemExit(1)
    print("[qwq-app web verify-offline] bootstrap: OK canvasKitBaseUrl=canvaskit/")

    lib_errors = _scan_lib_forbidden()
    if lib_errors:
        print("[qwq-app web verify-offline] lib-scan: FAIL")
        for err in lib_errors:
            print(f"  - {err}")
        raise SystemExit(1)
    print("[qwq-app web verify-offline] lib-scan: OK")

    if build:
        print(f"[qwq-app web verify-offline] build: flutter web --no-web-resources-cdn ({build_mode})")
        run_checked(
            [
                "flutter",
                "build",
                "web",
                "--no-web-resources-cdn",
                f"--{build_mode}",
                "-t",
                "lib/main.dart",
            ],
            cwd=APP_ROOT,
        )
        print("[qwq-app web verify-offline] build: OK")
    else:
        print("[qwq-app web verify-offline] build: SKIPPED")

    print("[qwq-app web verify-offline] DONE")
