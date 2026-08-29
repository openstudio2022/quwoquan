#!/usr/bin/env python3
"""Ratchet gate: keep platform branching out of the business layer (rule 14).

Capability-first means business / UI code must NOT ask "which platform am I on"
or talk to native channels directly. It must consume `PlatformCapabilities`
(via platformCapabilitiesProvider) and the anti-corruption gateways.

This gate scans quwoquan_app/lib (excluding the platform ACL itself) for:
  - bare platform discrimination:  `Platform.isAndroid/isIOS/isMacOS/...`,
    `Platform.operatingSystem`, `kIsWeb`
  - raw native channels:           `MethodChannel(` / `EventChannel(` /
    `BasicMessageChannel(`
  - page-private width breakpoints: `MediaQuery...width > <num>` / `.width >= <num>`
    style hard-coded layout breakpoints (must use AppSpacing breakpoints).
  - platform SDK imports:          LiveKit / CallKit / native video SDKs

Every occurrence outside the platform anti-corruption layer fails. There is no
tracked baseline or allowlist.
"""

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

import re

ROOT = REPO_ROOT
APP_LIB = ROOT / "quwoquan_app" / "lib"
# The anti-corruption layer is the ONLY place allowed to do these. It spans two
# prefixes while the cross-cutting migration runs: `core/platform/` is where the
# layer sits today, `runtime/platform/` is the target derived by
# `quwoquan_ops/gate/object_path_map.py` for every one of those files. Files
# arrive at the target one by one, so both must resolve to the same boundary.
EXEMPT_PREFIXES = ("core/platform/", "runtime/platform/")

CHECKS: list[tuple[str, re.Pattern[str]]] = [
    (
        "platform_branch",
        re.compile(
            r"\bPlatform\s*\.\s*(isAndroid|isIOS|isMacOS|isWindows|isLinux|isFuchsia|operatingSystem)\b"
        ),
    ),
    ("kIsWeb", re.compile(r"\bkIsWeb\b")),
    (
        "raw_channel",
        re.compile(r"\b(MethodChannel|EventChannel|BasicMessageChannel)\s*\("),
    ),
    (
        "private_breakpoint",
        re.compile(r"\.width\s*(?:>=|>|<=|<)\s*\d{2,4}(?:\.\d+)?"),
    ),
    (
        # 裸变量断点（如 `width >= 430` / `maxWidth < 360`）同样是第二套断点；
        # 必须使用 AppSpacing.* breakpoint token。只匹配屏幕/视口宽度语义变量，
        # 元素级宽度阶梯（tileWidth 等）不属于断点治理范围。
        "private_breakpoint_bare",
        re.compile(
            r"\b(?:width|maxWidth|minWidth|screenWidth|viewportWidth|"
            r"availableWidth)\s*(?:>=|>|<=|<)\s*\d{2,4}(?:\.\d+)?\b"
        ),
    ),
    (
        "platform_sdk_import",
        re.compile(
            r"package:(?:livekit_client|flutter_callkit_incoming|video_thumbnail)/"
        ),
    ),
]

# 体验分叉检查（R-XP1）：业务层禁止用 AppPlatform 比较做体验分支；
# 平台标识仅允许装配（runtime/di、runtime/shell/startup）与 observability
# wire 投影（platformWireName）。
APP_PLATFORM_COMPARE = re.compile(r"[=!]=\s*AppPlatform\.")
ASSEMBLY_PREFIXES = (
    "runtime/di/",
    "runtime/shell/startup/",
)


def _scan() -> set[tuple[str, str]]:
    hits: set[tuple[str, str]] = set()
    for path in APP_LIB.rglob("*.dart"):
        rel = path.relative_to(APP_LIB).as_posix()
        if any(rel.startswith(p) for p in EXEMPT_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for kind, rx in CHECKS:
            if rx.search(text):
                hits.add((rel, kind))
        if not any(rel.startswith(p) for p in ASSEMBLY_PREFIXES):
            if APP_PLATFORM_COMPARE.search(text):
                hits.add((rel, "app_platform_experience_branch"))
    return hits


def main() -> int:
    hits = _scan()
    if hits:
        print(
            "verify_lib_platform_check_isolation: BLOCK: platform branching leaked into business layer",
            file=sys.stderr,
        )
        for path, kind in sorted(hits):
            print(f"  hit: {path}: {kind}", file=sys.stderr)
        print(
            "  Use PlatformCapabilities (platformCapabilitiesProvider), the native "
            "bridge, or AppSpacing breakpoints instead.",
            file=sys.stderr,
        )
        return 1

    print("verify_lib_platform_check_isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
