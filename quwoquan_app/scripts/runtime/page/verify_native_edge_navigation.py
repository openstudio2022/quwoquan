#!/usr/bin/env python3

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

from pathlib import Path


REPO = REPO_ROOT
APP_ROUTER = REPO / "quwoquan_app/lib/runtime/di/navigation/app_router.dart"
POLICY = REPO / "quwoquan_app/lib/runtime/shell/navigation/native_back_navigation.dart"
SPEC = REPO / "specs/feature-tree/runtime/native-edge-gesture-navigation/spec.md"
STORY = (
    REPO
    / "specs/feature-tree/runtime/native-edge-gesture-navigation/global-route-edge-pop-contract/spec.md"
)


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: native edge navigation: {message}")


def main() -> None:
    for path in (APP_ROUTER, POLICY, SPEC, STORY):
        if not path.exists():
            fail(f"missing required file: {path.relative_to(REPO)}")

    router = APP_ROUTER.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")

    if "native_back_navigation.dart" not in router:
        fail("app_router.dart must import the native navigation anti-corruption layer")
    if "builder: (context, state)" in router:
        fail("ordinary GoRoute.builder bypasses AppRoutePageFactory")
    if "MaterialPage<" in router:
        fail("app_router.dart must not construct bare MaterialPage for app routes")
    if router.count("appRoutePage<") < 30:
        fail("ordinary app routes must be built through appRoutePage")

    required_policy_symbols = (
        "abstract class NativeBackNavigationPolicy",
        "class IosNativeBackNavigationPolicy",
        "class AndroidNativeBackNavigationPolicy",
        "class AppNativeBackScope",
        "abstract class AppBackGuard",
    )
    for symbol in required_policy_symbols:
        if symbol not in policy:
            fail(f"missing policy symbol: {symbol}")

    if "global-route-edge-pop-contract" not in spec:
        fail("capability spec must include global-route-edge-pop-contract")

    print("PASS: native edge navigation static contract")


if __name__ == "__main__":
    main()
