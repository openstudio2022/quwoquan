#!/usr/bin/env python3
"""阻断共享可写 App identity 状态与缺失的 flavor 选择。

触发范围：App identity metadata/codegen、Android/iOS 原生配置、Flutter 启动入口。
阻断条件：退役共享状态仍存在、运行时入口消费它、默认 Alpha 或显式 flavor 选择缺失。
修复方式：删除共享状态，恢复静态 flavor/scheme，运行 `make codegen-app-identity` 后重跑
`make verify-app-identity-state-isolation` 与 `make verify-app-identity`。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[4]


def _read_required(path: Path, root: Path, issues: list[str]) -> str:
    if not path.is_file():
        issues.append(f"required App identity input is missing: {path.relative_to(root)}")
        return ""
    return path.read_text(encoding="utf-8")


def collect_issues(root: Path) -> list[str]:
    app = root / "quwoquan_app"
    issues: list[str] = []
    forbidden = (
        app / "ios/Flutter/QWQEnvironment.xcconfig",
        app / "scripts/ios/write_environment_xcconfig.sh",
    )
    for path in forbidden:
        if path.exists():
            issues.append(
                f"shared mutable App identity state must not exist: {path.relative_to(root)}"
            )

    scanned_paths = (
        app / "run.sh",
        app / "scripts/device/run_app_instance.sh",
        app / "scripts/device/verify_ios_hot_restart.py",
        app / "scripts/device/build_startup_environment_matrix.py",
        app / "scripts/ios/build_prepare_dart_defines.sh",
    )
    sources: dict[Path, str] = {}
    for path in scanned_paths:
        source = _read_required(path, root, issues)
        sources[path] = source
        if "write_environment_xcconfig" in source or "QWQEnvironment.xcconfig" in source:
            issues.append(
                f"runtime path mutates or consumes retired identity state: {path.relative_to(root)}"
            )

    launcher = sources[app / "run.sh"]
    if '--flavor "$QWQ_APP_RUNTIME_ENV"' not in launcher:
        issues.append("run.sh must select the canonical Flutter flavor")

    app_instance = sources[app / "scripts/device/run_app_instance.sh"]
    if '"--flavor",' not in app_instance:
        issues.append("run_app_instance.sh must select an explicit Flutter flavor")

    runner_scheme = app / "ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme"
    if runner_scheme.exists():
        issues.append("unflavored shared Runner scheme must not remain selectable")

    pubspec = _read_required(app / "pubspec.yaml", root, issues)
    if "  default-flavor: alpha\n" not in pubspec:
        issues.append("pubspec.yaml must make alpha the deterministic default flavor")

    identity_source = _read_required(
        app / "android/app/app_identity.generated.json", root, issues
    )
    if identity_source:
        try:
            identity = json.loads(identity_source)
        except json.JSONDecodeError as error:
            issues.append(f"generated App identity document is invalid: {error}")
        else:
            if identity.get("environments") != ["alpha", "beta", "gamma", "prod"]:
                issues.append("generated App identity environment matrix is incomplete")

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    issues = collect_issues(args.repo_root.resolve())
    if issues:
        print("[verify_app_identity_state_isolation] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_app_identity_state_isolation] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
