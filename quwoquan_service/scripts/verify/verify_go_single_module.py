#!/usr/bin/env python3
"""阻断 quwoquan_service 下嵌套 Go module 回归。"""

from __future__ import annotations

from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]
ROOT_MODULE = SERVICE_ROOT / "go.mod"
ROOT_SUM = SERVICE_ROOT / "go.sum"


def main() -> int:
    failures: list[str] = []
    if not ROOT_MODULE.is_file():
        failures.append(f"missing root module: {ROOT_MODULE}")
    else:
        module_line = ROOT_MODULE.read_text(encoding="utf-8").splitlines()[0].strip()
        if module_line != "module quwoquan_service":
            failures.append(
                f"{ROOT_MODULE}: expected 'module quwoquan_service', got {module_line!r}"
            )

    nested = sorted(
        path.relative_to(SERVICE_ROOT).as_posix()
        for path in SERVICE_ROOT.rglob("go.mod")
        if path != ROOT_MODULE
    )
    if nested:
        failures.append("nested go.mod files are forbidden: " + ", ".join(nested))

    nested_sums = sorted(
        path.relative_to(SERVICE_ROOT).as_posix()
        for path in SERVICE_ROOT.rglob("go.sum")
        if path != ROOT_SUM
    )
    if nested_sums:
        failures.append("nested go.sum files are forbidden: " + ", ".join(nested_sums))

    workspaces = sorted(
        path.relative_to(SERVICE_ROOT).as_posix()
        for path in SERVICE_ROOT.rglob("go.work")
    )
    if workspaces:
        failures.append("go.work files are forbidden in the single-module tree: " + ", ".join(workspaces))

    if failures:
        for failure in failures:
            print(f"[verify] FAIL: {failure}")
        return 1

    print("[verify] OK: quwoquan_service uses one root Go module")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
