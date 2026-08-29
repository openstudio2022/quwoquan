#!/usr/bin/env python3
"""Keep eager/deferred Android plugin registration policy synchronized."""

from __future__ import annotations


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

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import json
import sys
from pathlib import Path


APP = APP_ROOT
POLICY = APP / "configs/plugin_registration_policy.json"
LEGACY_PATCH = APP / "scripts/patch_android_plugin_registrant.sh"
EAGER = APP / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupEagerPluginRegistry.java"
REGISTRY = APP / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupDeferredPluginRegistry.java"
GENERATED = APP / "android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java"
MAIN_ACTIVITY = APP / "android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    eager = EAGER.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    generated = GENERATED.read_text(encoding="utf-8")
    main_activity = MAIN_ACTIVITY.read_text(encoding="utf-8")
    failures: list[str] = []
    if LEGACY_PATCH.exists():
        failures.append("legacy GeneratedPluginRegistrant patch script must not exist")
    if "StartupEagerPluginRegistry.registerWith(flutterEngine)" not in main_activity:
        failures.append("MainActivity does not use the app-owned eager registry")
    if "super.configureFlutterEngine(flutterEngine)" in main_activity:
        failures.append("MainActivity still invokes GeneratedPluginRegistrant through super")

    for class_name in policy.get("eagerRuntime", []):
        if class_name not in eager:
            failures.append(f"eagerRuntime: eager registry missing {class_name}")
        if class_name in registry:
            failures.append(f"eagerRuntime: registry wrongly defers {class_name}")
        if f"new {class_name}()" not in generated:
            failures.append(f"eagerRuntime: generated registration missing {class_name}")

    for group, classes in policy.items():
        if group == "eagerRuntime":
            continue
        for class_name in classes:
            if class_name in eager:
                failures.append(f"{group}: eager registry wrongly includes {class_name}")
            if class_name not in registry:
                failures.append(f"{group}: registry missing {class_name}")
    if failures:
        print("FAIL: plugin registration policy drift")
        print("\n".join(failures))
        return 1
    print("PASS: plugin registration policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
