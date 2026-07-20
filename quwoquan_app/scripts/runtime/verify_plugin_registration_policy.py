#!/usr/bin/env python3
"""Keep eager/deferred Android plugin registration policy synchronized."""

from __future__ import annotations

import json
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[2]
POLICY = APP / "configs/plugin_registration_policy.json"
PATCH = APP / "scripts/patch_android_plugin_registrant.sh"
REGISTRY = APP / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupDeferredPluginRegistry.java"
GENERATED = APP / "android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java"


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    patch = PATCH.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    generated = GENERATED.read_text(encoding="utf-8")
    failures: list[str] = []
    # Flutter 在 iOS/Web build 与 pub get 时会重生 Android registrant。延迟插件是否
    # 被剥离由 Android Javac 前的 patch + registry 双重约束，不以工作树瞬时产物判定。
    for class_name in policy.get("eagerRuntime", []):
        if class_name in patch:
            failures.append(f"eagerRuntime: patch wrongly defers {class_name}")
        if class_name in registry:
            failures.append(f"eagerRuntime: registry wrongly defers {class_name}")
        if f"new {class_name}()" not in generated:
            failures.append(f"eagerRuntime: generated registration missing {class_name}")

    for group, classes in policy.items():
        if group == "eagerRuntime":
            continue
        for class_name in classes:
            if class_name not in patch:
                failures.append(f"{group}: patch missing {class_name}")
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
