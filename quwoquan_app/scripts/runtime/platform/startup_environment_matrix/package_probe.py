"""component readiness 探针：runtime/iOS defines 与 launcher handoff。"""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
from typing import Any

from .context import APP_DIR, REQUIRED_DEFINES, RUNTIME_TARGETS


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=APP_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _runtime_defines(environment: str) -> dict[str, str]:
    result = _run(
        "python3",
        "scripts/env/print_app_env_dart_defines.py",
        "--env",
        environment,
        "--format",
        "json",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _ios_defines(environment: str) -> dict[str, str]:
    process_env = dict(os.environ)
    handoff = _launcher_handoff(environment)
    process_env["QWQ_APP_RUNTIME_ENV"] = environment
    process_env["QWQ_APP_LAUNCH_MODE"] = str(handoff["launchMode"])
    process_env["QWQ_LAUNCH_TARGET"] = str(handoff["target"])
    process_env["QWQ_DART_DEFINES_DIGEST"] = str(handoff["dartDefinesDigest"])
    process_env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
        handoff["runtimeConfigDigest"]
    )
    process_env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
        handoff["effectiveLaunchManifestDigest"]
    )
    process_env.pop("DART_DEFINES", None)
    result = _run("bash", "scripts/ios/build_prepare_dart_defines.sh", env=process_env)
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
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _launcher_handoff(
    environment: str,
    target: str | None = None,
) -> dict[str, Any]:
    result = _run(
        "python3",
        "scripts/device/build_launcher_handoff.py",
        "--env",
        environment,
        "--target",
        target or RUNTIME_TARGETS[environment],
        "--launch-mode",
        "matrix_verify",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _validate_defines(environment: str, values: dict[str, str]) -> list[str]:
    issues = [
        f"{environment}: missing {key}"
        for key in sorted(REQUIRED_DEFINES)
        if not values.get(key, "").strip()
    ]
    if values.get("APP_RUNTIME_ENV") != environment:
        issues.append(f"{environment}: APP_RUNTIME_ENV mismatch")
    return issues
