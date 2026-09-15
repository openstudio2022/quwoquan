#!/usr/bin/env python3
"""验证静态身份矩阵及消费者单轨，阻断共享可写 App identity 状态。

Debug/Profile 使用 canonical 环境身份，Release 使用信任域身份；Prod 不可调试。
AST 校验命令与 resolver、内容源和缓存键的接线，不执行被检查的启动脚本。
此源码门不证明真实编译、安装或设备启动；生成物正确性另由 verify-app-identity 验证。
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


def _contains(node: ast.AST, code: str) -> bool:
    """比较语法节点而非文本：注释、字符串中的伪接线不算代码。"""
    expected = ast.parse(code).body[0]
    if isinstance(expected, ast.Expr):
        expected = expected.value
    shape = ast.dump(expected, include_attributes=False)
    return any(ast.dump(child, include_attributes=False) == shape for child in ast.walk(node))


def _function(node: ast.AST, name: str) -> ast.AST:
    matches = [child for child in ast.walk(node)
               if isinstance(child, ast.FunctionDef) and child.name == name]
    return matches[0] if len(matches) == 1 else ast.Module(body=[], type_ignores=[])


def _flavor_values(node: ast.AST) -> list[str]:
    values = []
    for child in ast.walk(node):
        if isinstance(child, (ast.List, ast.Tuple)):
            for index, item in enumerate(child.elts):
                if isinstance(item, ast.Constant) and item.value == "--flavor":
                    values.append(ast.unparse(child.elts[index + 1]) if index + 1 < len(child.elts) else "")
    return values


def _executor_uses_canonical_identity(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    identity = _function(tree, "build_identity")
    required = (
        "from quwoquan_ops.cli.lib.app_identity import resolve_app_identity",
        'identity = resolve_app_identity(platform=platform, environment=str(handoff["environment"]), build_profile=str(handoff["buildProfile"]), build_mode="debug")',
        'expected = contract["content_source_entrypoints"][contract["content_source_policy"][identity.environment]]',
        'if identity.application_id != self.application_id:\n    raise CanonicalExecutorError("application id conflicts with canonical build identity")',
        'if self.entrypoint != expected:\n    raise CanonicalExecutorError("entrypoint conflicts with canonical environment content source")',
        "return identity",
    )
    if not all(_contains(identity, code) for code in required):
        return False
    if not _contains(tree, "driver.launch_handoff = handoff"):
        return False
    for name in ("AndroidPlatformDriver", "IOSSimulatorPlatformDriver", "IOSPhysicalPlatformDriver"):
        classes = [child for child in tree.body if isinstance(child, ast.ClassDef) and child.name == name]
        if len(classes) != 1:
            return False
        command = _function(classes[0], "build_command")
        if _flavor_values(command) != ["self.build_identity().flavor"]:
            return False
        # 真正返回的构建命令必须消费这个表达式，不能只放在未使用列表里。
        returns = [child for child in ast.walk(command) if isinstance(child, ast.Return)]
        if len(returns) != 1 or _flavor_values(returns[0]) != ["self.build_identity().flavor"]:
            return False
    return True


def _matrix_uses_canonical_identity(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    identity = _function(tree, "_build_identity")
    required = (
        "from quwoquan_ops.cli.lib.app_identity import resolve_app_identity",
        'mode = str(handoff.get("buildMode") or ("release" if handoff["environment"] == "prod" else "debug"))',
        'return resolve_app_identity(platform=platform, environment=str(handoff["environment"]), build_profile=str(handoff["buildProfile"]), build_mode=mode)',
    )
    command = _function(tree, "_build_command")
    key = _function(tree, "_build_key")
    compile_env = _function(tree, "_compile_environment")
    keys = [node.value for node in ast.walk(_function(tree, "main"))
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "key" for target in node.targets)]
    if not keys or any(ast.unparse(value) != "_build_key(platform, handoff)" for value in keys):
        return False
    return (all(_contains(identity, code) for code in required)
            and _flavor_values(command) == ["identity.flavor"]
            and _contains(command, "identity = _build_identity(platform, handoff)")
            and _contains(command, 'expected = contract["content_source_entrypoints"][contract["content_source_policy"][handoff["environment"]]]')
            and _contains(command, 'if handoff["entrypoint"] != expected:\n    raise ValueError("entrypoint conflicts with canonical environment content source")')
            and _contains(command, 'command.extend(["apk" if platform == "android" else "ios", "--" + identity.build_mode, "--flavor", identity.flavor])')
            and _contains(command, "return command")
            and _contains(key, "identity = _build_identity(platform, handoff)")
            and _contains(key, 'selector = f"{identity.flavor}/{identity.build_mode}"')
            and _contains(key, 'return selector + ":" + str(handoff["entrypoint"]), platform')
            and _contains(compile_env, 'if build_profile_for_environment(runtime_environment) != build_profile:\n    raise ValueError("compile environment/build profile mismatch")')
            and _contains(_function(tree, "main"), "key = _build_key(platform, handoff)")
            and _contains(_function(tree, "main"), "existing = compiled.get(key)")
            and _contains(_function(tree, "main"), 'process_env = _compile_environment(build_profile=str(handoff["buildProfile"]), platform=platform, runtime_environment=environment, ios_simulator_id=args.ios_simulator_id)'))


def _ios_uses_canonical_configuration(source: str) -> bool:
    # 只解析 shell 中独立的 Python heredoc，不 eval shell、不运行启动器。
    for block in source.split("<<'PY'\n")[1:]:
        try:
            tree = ast.parse(block.split("\nPY\n", 1)[0])
        except SyntaxError:
            continue
        if all(_contains(tree, code) for code in (
            "from quwoquan_ops.cli.lib.app_identity import resolve_ios_configuration",
            "identity = resolve_ios_configuration(sys.argv[1])",
            'key + "=" + shlex.quote(value)',
        )):
            fields = [node for node in ast.walk(tree) if isinstance(node, ast.Dict)]
            required = {"BUILD_PROFILE": "identity.build_profile", "BUILD_MODE": "identity.build_mode",
                        "BUILD_ENVIRONMENT": "identity.environment or ''", "EXPECTED_BUNDLE_ID": "identity.application_id"}
            return any({key.value: ast.unparse(value) for key, value in zip(node.keys, node.values)
                        if isinstance(key, ast.Constant)} == required for node in fields)
    return False



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
    if not _executor_uses_canonical_identity(executor):
        issues.append("canonical executor drivers must bind flavor, profile and source through canonical identity")

    app_instance = sources[app / "scripts/device/run_app_instance.sh"]
    if 'bash "$APP_DIR/run.sh"' not in app_instance or "flutter run" in app_instance:
        issues.append(
            "run_app_instance.sh must delegate non-Prod flavor selection to run.sh"
        )

    matrix = sources[app / "scripts/device/build_startup_environment_matrix.py"]
    if not _matrix_uses_canonical_identity(matrix):
        issues.append("startup matrix must bind canonical flavor, mode, source and isolated cache key")
    prepare = sources[app / "scripts/ios/build_prepare_dart_defines.sh"]
    if not _ios_uses_canonical_configuration(prepare):
        issues.append("iOS configuration must resolve canonical profile, environment and bundle identity")

    schemes = app / "ios/Runner.xcodeproj/xcshareddata/xcschemes"
    if (schemes / "Runner.xcscheme").exists():
        issues.append("unflavored shared Runner scheme must not remain selectable")
    for environment in ("alpha", "beta", "gamma"):
        if not (schemes / f"{environment}.xcscheme").exists():
            issues.append(f"canonical development environment scheme is missing: {environment}")

    _read_required(app / "pubspec.yaml", root, issues)

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
                    "nonprod/release",
                    "prod/release",
                    "alpha/debug",
                    "alpha/profile",
                    "beta/debug",
                    "beta/profile",
                    "gamma/debug",
                    "gamma/profile",
                }
                if set(identities) != expected_keys:
                    issues.append(
                        f"generated {platform} identity keys must match canonical release/development targets"
                    )
                if any(key.startswith("prod/") and key != "prod/release" for key in identities):
                    issues.append(f"generated {platform} identity must not expose Prod Debug/Profile")
                for key, value in identities.items():
                    if key.endswith(("/debug", "/profile")) and value.get("promotable") is not False:
                        issues.append(f"generated {platform} development identity must be non-promotable: {key}")

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
