"""Canonical App coverage runner policy and deterministic runtime identity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

import quwoquan_ops.gate.canonical_coverage as cc
from quwoquan_app.scripts._common.flutter_test_selection import declares_serial_tests

from .constants import CoverageError, _tail


APP_COVERAGE_RUNTIME_ENV = "alpha"
APP_COVERAGE_LAUNCH_POLICY = "test_live"
APP_COVERAGE_CONCURRENCY = "4"
APP_COVERAGE_SERIAL_CONCURRENCY = "1"
APP_COVERAGE_TIMEOUT_SECONDS = "1800"
# A transient failure reruns the red canonical shard on the next collection.
# Retrying inside one shard would execute business tests twice and blur the
# exact-once phase contract; the guarded runner still deletes stale lcov before
# every attempt for its non-coverage callers that keep the default retry policy.
APP_COVERAGE_MAX_ATTEMPTS = "1"
APP_FLUTTER_TEST_RUNNER = Path("scripts/env/run_flutter_test_guarded.py")
APP_RUNTIME_DEFINE_RESOLVER = Path("scripts/env/print_app_env_dart_defines.py")
APP_TEST_SELECTION_POLICY = Path("scripts/_common/flutter_test_selection.py")

# These caller-owned variables may narrow the test set or change the resolved
# runtime package. Canonical coverage owns both decisions and therefore removes
# every ambient value before launching the guarded runner.
APP_COVERAGE_CLEARED_ENV_KEYS = (
    "APP_LEGAL_BASE_URL",
    "APP_ROLLOUT_MODE",
    "FLUTTER_TEST_CONCURRENCY",
    "FLUTTER_TEST_SERIAL_MODE",
    "FLUTTER_TEST_SHARD_INDEX",
    "FLUTTER_TEST_TOTAL_SHARDS",
    "LOCAL_GAMMA_GATEWAY_BASE_URL",
    "LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL",
    "LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL",
    "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL",
    "LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL",
    "LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL",
    "QWQ_APP_LAUNCH_MODE",
    "QWQ_DEPLOY_TARGET",
)


def canonical_app_coverage_environment(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the exact environment used by App coverage subprocesses."""

    environment = dict(os.environ if base is None else base)
    for key in APP_COVERAGE_CLEARED_ENV_KEYS:
        environment.pop(key, None)
    environment.update(
        {
            "FLUTTER_TEST_GUARD_MAX_ATTEMPTS": APP_COVERAGE_MAX_ATTEMPTS,
            "FLUTTER_TEST_GUARD_TIMEOUT_SECONDS": APP_COVERAGE_TIMEOUT_SECONDS,
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_APP_RUNTIME_ENV": APP_COVERAGE_RUNTIME_ENV,
        }
    )
    return environment


def app_runtime_define_command(*, output_format: str) -> list[str]:
    if output_format not in {"args", "json"}:
        raise CoverageError(f"unsupported App runtime define format: {output_format}")
    return [
        sys.executable,
        str(cc.APP_ROOT / APP_RUNTIME_DEFINE_RESOLVER),
        "--env",
        APP_COVERAGE_RUNTIME_ENV,
        "--launch-policy",
        APP_COVERAGE_LAUNCH_POLICY,
        "--format",
        output_format,
    ]


def resolved_app_runtime_defines() -> dict[str, str]:
    """Resolve and validate the exact Dart-define vector used for coverage."""

    command = app_runtime_define_command(output_format="json")
    completed = subprocess.run(
        command,
        cwd=cc.APP_ROOT,
        env=canonical_app_coverage_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise CoverageError(
            "App coverage runtime define resolution failed "
            f"(exit={completed.returncode}): {_tail(completed.stderr)}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise CoverageError("App coverage runtime defines are not JSON") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        raise CoverageError("App coverage runtime defines must be string-only object")
    if payload.get("APP_RUNTIME_ENV") != APP_COVERAGE_RUNTIME_ENV:
        raise CoverageError("App coverage runtime environment is not canonical alpha")
    if payload.get("APP_LAUNCH_POLICY") != APP_COVERAGE_LAUNCH_POLICY:
        raise CoverageError("App coverage launch policy is not canonical test_live")
    public_origin = payload.get("PUBLIC_WEB_BASE_URL", "")
    if not public_origin.startswith("https://"):
        raise CoverageError("App coverage public Web origin must be explicit HTTPS")
    return dict(sorted(payload.items()))


def guarded_app_coverage_command(
    destination: Path,
    test_files: Sequence[str],
    *,
    serial_phase: bool,
) -> list[str]:
    """Build one phase of the canonical App coverage shard argv."""

    tag_arguments = ["--tags", "serial"] if serial_phase else ["--exclude-tags", "serial"]
    concurrency = (
        APP_COVERAGE_SERIAL_CONCURRENCY
        if serial_phase
        else APP_COVERAGE_CONCURRENCY
    )

    return [
        sys.executable,
        str(cc.APP_ROOT / APP_FLUTTER_TEST_RUNNER),
        "--coverage",
        "--branch-coverage",
        f"--coverage-path={destination}",
        "--reporter=compact",
        f"--dart-define=APP_RUNTIME_ENV={APP_COVERAGE_RUNTIME_ENV}",
        f"--concurrency={concurrency}",
        *tag_arguments,
        *test_files,
    ]


def serial_app_test_files(test_files: Sequence[str]) -> tuple[str, ...]:
    """Select serial-bearing files with the same predicate as the App runner."""

    return tuple(
        test_file
        for test_file in test_files
        if declares_serial_tests(cc.APP_ROOT / test_file)
    )


def app_coverage_policy_identity() -> dict[str, object]:
    """Stable scope identity; no host paths or ambient values are serialized."""

    return {
        "runner": APP_FLUTTER_TEST_RUNNER.as_posix(),
        "runtimeResolver": APP_RUNTIME_DEFINE_RESOLVER.as_posix(),
        "testSelectionPolicy": APP_TEST_SELECTION_POLICY.as_posix(),
        "runtimeEnvironment": APP_COVERAGE_RUNTIME_ENV,
        "launchPolicy": APP_COVERAGE_LAUNCH_POLICY,
        "concurrency": APP_COVERAGE_CONCURRENCY,
        "serialConcurrency": APP_COVERAGE_SERIAL_CONCURRENCY,
        "phases": ["exclude-serial", "serial-only"],
        "timeoutSeconds": APP_COVERAGE_TIMEOUT_SECONDS,
        "maxAttempts": APP_COVERAGE_MAX_ATTEMPTS,
        "clearedEnvironmentKeys": list(APP_COVERAGE_CLEARED_ENV_KEYS),
        "resolvedDartDefines": resolved_app_runtime_defines(),
    }
