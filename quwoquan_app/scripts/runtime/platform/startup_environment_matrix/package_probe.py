"""component readiness 探针：runtime/iOS defines 与 launcher handoff。"""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .context import APP_DIR, REQUIRED_RUNTIME_FIELDS, RUNTIME_TARGETS


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=APP_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _runtime_package(environment: str) -> dict[str, str]:
    target = RUNTIME_TARGETS[environment]
    result = _run(
        "python3",
        "scripts/env/print_app_env_dart_defines.py",
        "--env",
        environment,
        "--target",
        target,
        "--launch-policy",
        "test_live",
        "--format",
        "json",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    package = json.loads(result.stdout)
    runtime = package.get("runtime")
    if not isinstance(runtime, dict):
        raise RuntimeError(f"{environment}: runtime package has no runtime section")
    return runtime


def _ios_compile_defines(environment: str) -> dict[str, str]:
    """跑一次真实 Xcode 前置，回读它交给编译器的 define 集合。

    endpoint 已改为安装后激活，Runner.app 里只放 profile trust envelope。所以
    这里要的是「编译输入里还剩什么」，而不是过去那份扁平 endpoint define。
    """

    with tempfile.TemporaryDirectory() as staging:
        artifact_root = Path(staging).resolve()
        trust_path = artifact_root / "runtime-config-trust.json"
        handoff = _launcher_handoff(
            environment,
            trust_output=str(trust_path),
        )
        process_env = dict(os.environ)
        process_env["QWQ_APP_BUILD_PROFILE"] = str(handoff["buildProfile"])
        process_env["CONFIGURATION"] = _xcode_configuration(str(handoff["buildProfile"]))
        process_env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(trust_path)
        process_env["TARGET_BUILD_DIR"] = str(artifact_root / "build")
        process_env["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
        process_env.pop("DART_DEFINES", None)
        process_env.pop("QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH", None)
        result = _run(
            "bash",
            "scripts/ios/build_prepare_dart_defines.sh",
            env=process_env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        export_line = next(
            line
            for line in result.stdout.splitlines()
            if line.startswith("export DART_DEFINES=")
        )
    assignment = shlex.split(export_line.removeprefix("export "))[0]
    encoded = assignment.split("=", 1)[1]
    values: dict[str, str] = {}
    if encoded == "__QWQ_COMPILE_ONLY__":
        return values
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _xcode_configuration(build_profile: str) -> str:
    if build_profile == "nonprod":
        return "Debug-nonprod"
    if build_profile == "prod":
        return "Release-prod"
    raise RuntimeError(f"unsupported iOS build profile: {build_profile}")


def _launcher_handoff(
    environment: str,
    target: str | None = None,
    trust_output: str = "",
) -> dict[str, Any]:
    argv = [
        "python3",
        "scripts/device/build_launcher_handoff.py",
        "--env",
        environment,
        "--target",
        target or RUNTIME_TARGETS[environment],
        "--launch-mode",
        "matrix_verify",
    ]
    if trust_output:
        argv.extend(("--runtime-config-trust-output", trust_output))
    result = _run(*argv)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _validate_runtime_package(environment: str, runtime: dict[str, str]) -> list[str]:
    issues = [
        f"{environment}: runtime package missing {field}"
        for field in sorted(REQUIRED_RUNTIME_FIELDS)
        if not str(runtime.get(field, "")).strip()
    ]
    if runtime.get("appRuntimeEnv") != environment:
        issues.append(f"{environment}: runtime package appRuntimeEnv mismatch")
    return issues


def _validate_compile_defines(environment: str, values: dict[str, str]) -> list[str]:
    """编译输入必须一项 runtime 配置都不带：endpoint 只走安装后激活。

    探针不带 `DART_DEFINES` 进入前置脚本，因此这里唯一可接受的结果就是空集；
    禁令闭集由 `scripts/ios/build_prepare_dart_defines.sh` 独家拥有，不复制。
    """

    return [
        f"{environment}: compile define leaks runtime configuration {key}"
        for key in sorted(values)
    ]
