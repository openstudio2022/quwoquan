#!/usr/bin/env python3
"""阻断共享可写 App identity 状态与退役环境 flavor。

触发范围：App identity metadata/codegen、Android/iOS 原生配置、Flutter 启动入口。
阻断条件：退役共享状态或环境 flavor 仍存在、启动入口未选择 buildProfile、生成矩阵缺失。
修复方式：删除共享状态和环境 flavor，恢复 nonprod/prod 静态 flavor/scheme，运行
`make codegen-app-identity` 后重跑两道 App identity 门禁。
"""

from __future__ import annotations

import argparse
import ast
import json
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

from _common.paths import REPO_ROOT

DEFAULT_ROOT = REPO_ROOT


def _read_required(path: Path, root: Path, issues: list[str]) -> str:
    if not path.is_file():
        issues.append(f"required App identity input is missing: {path.relative_to(root)}")
        return ""
    return path.read_text(encoding="utf-8")


def _executor_nonprod_build_drivers(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    expected = {
        "AndroidPlatformDriver",
        "IOSSimulatorPlatformDriver",
        "IOSPhysicalPlatformDriver",
    }
    compliant: set[str] = set()
    for class_node in tree.body:
        if not isinstance(class_node, ast.ClassDef) or class_node.name not in expected:
            continue
        profiles: set[str] = set()
        for method in class_node.body:
            if not isinstance(method, ast.FunctionDef) or method.name != "build_command":
                continue
            for child in ast.walk(method):
                if not isinstance(child, (ast.List, ast.Tuple)):
                    continue
                values = [
                    item.value
                    for item in child.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
                for index, value in enumerate(values[:-1]):
                    if value == "--flavor":
                        profiles.add(values[index + 1])
        if profiles == {"nonprod"}:
            compliant.add(class_node.name)
    return compliant


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
        app / "scripts/device/run_app_instance.py",
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
    # 单轨检查只看行为行：注释里的提及不构成第二条 flavor 选择轨。
    launcher_behavior = "\n".join(
        line
        for line in launcher.splitlines()
        if not line.lstrip().startswith("#")
    )
    executor_path = app / "scripts/device/run_app_instance.py"
    executor = sources[executor_path]
    if str(executor_path.relative_to(app)) not in launcher_behavior:
        issues.append("run.sh must delegate buildProfile selection to canonical executor")
    if "flutter run" in launcher_behavior or "--flavor" in launcher_behavior:
        issues.append("run.sh must not own a second Flutter buildProfile selection")
    if '--flavor "$QWQ_APP_RUNTIME_ENV"' in launcher_behavior:
        issues.append("run.sh must not select flavor from the runtime environment")
    if _executor_nonprod_build_drivers(executor) != {
        "AndroidPlatformDriver",
        "IOSSimulatorPlatformDriver",
        "IOSPhysicalPlatformDriver",
    }:
        issues.append(
            "canonical executor Android/iOS build drivers must select only nonprod"
        )

    app_instance = sources[app / "scripts/device/run_app_instance.sh"]
    if 'bash "$APP_DIR/run.sh"' not in app_instance or "flutter run" in app_instance:
        issues.append(
            "run_app_instance.sh must delegate non-Prod flavor selection to run.sh"
        )

    matrix = sources[app / "scripts/device/build_startup_environment_matrix.py"]
    if "--flavor" in matrix:
        if '"--flavor", str(handoff["environment"])' in matrix:
            issues.append(
                "startup matrix must not select flavor from the runtime environment"
            )
        if '"--flavor", str(handoff["buildProfile"])' not in matrix:
            issues.append(
                "startup matrix must select flavor from the handoff buildProfile"
            )

    schemes = app / "ios/Runner.xcodeproj/xcshareddata/xcschemes"
    if (schemes / "Runner.xcscheme").exists():
        issues.append("unflavored shared Runner scheme must not remain selectable")
    for environment in ("alpha", "beta", "gamma"):
        if (schemes / f"{environment}.xcscheme").exists():
            issues.append(f"retired environment scheme must not exist: {environment}")

    pubspec = _read_required(app / "pubspec.yaml", root, issues)
    if "  default-flavor: nonprod\n" not in pubspec:
        issues.append("pubspec.yaml must make nonprod the deterministic default flavor")

    identity_source = _read_required(
        app / "android/app/app_identity.generated.json", root, issues
    )
    if identity_source:
        try:
            identity = json.loads(identity_source)
        except json.JSONDecodeError as error:
            issues.append(f"generated App identity document is invalid: {error}")
        else:
            if identity.get("buildProfiles") != ["nonprod", "prod"]:
                issues.append("generated App identity buildProfile matrix is incomplete")
            expected_profiles = {
                "alpha": "nonprod",
                "beta": "nonprod",
                "gamma": "nonprod",
                "prod": "prod",
            }
            if identity.get("environmentProfiles") != expected_profiles:
                issues.append("generated App identity environmentProfiles mapping is incomplete")
            for platform in ("android", "ios"):
                identities = (identity.get("identities") or {}).get(platform) or {}
                expected_keys = {
                    f"{profile}/{mode}"
                    for profile in ("nonprod", "prod")
                    for mode in ("debug", "profile", "release")
                }
                if set(identities) != expected_keys:
                    issues.append(
                        f"generated {platform} identity keys must be buildProfile/buildMode"
                    )

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
