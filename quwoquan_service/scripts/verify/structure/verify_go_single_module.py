#!/usr/bin/env python3
"""阻断 quwoquan_service 下嵌套 Go module 回归。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

SERVICE_ROOT = repository_root() / "quwoquan_service"
ROOT_MODULE = SERVICE_ROOT / "go.mod"
ROOT_SUM = SERVICE_ROOT / "go.sum"

#: `.qwq_output/` 是被 gitignore 的可重建运行输出，GOMODCACHE/GOPATH 重定向到这里之后
#: 里面全是第三方依赖自带的 go.mod/go.sum/go.work。它们不是「源码树里的嵌套 module」，
#: 把它们算进来会让本门禁在任何跑过 go build 的机器上恒红。
DISPOSABLE_DIRS = {".qwq_output", ".git"}


def _source_files(pattern: str) -> list[Path]:
    """在 service 源码树里查找 `pattern`，跳过可丢弃输出目录。"""
    return [
        path
        for path in SERVICE_ROOT.rglob(pattern)
        if not DISPOSABLE_DIRS.intersection(path.relative_to(SERVICE_ROOT).parts)
    ]


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
        for path in _source_files("go.mod")
        if path != ROOT_MODULE
    )
    if nested:
        failures.append("nested go.mod files are forbidden: " + ", ".join(nested))

    nested_sums = sorted(
        path.relative_to(SERVICE_ROOT).as_posix()
        for path in _source_files("go.sum")
        if path != ROOT_SUM
    )
    if nested_sums:
        failures.append("nested go.sum files are forbidden: " + ", ".join(nested_sums))

    workspaces = sorted(
        path.relative_to(SERVICE_ROOT).as_posix()
        for path in _source_files("go.work")
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
