#!/usr/bin/env python3
"""Build all runtime environment packages with the shared Dart define source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PLATFORMS = ("android", "ios", "web")
ARTIFACTS = {
    "android": APP_DIR / "build/app/outputs/flutter-apk/app-debug.apk",
    "ios": APP_DIR / "build/ios/iphonesimulator/Runner.app/Runner",
    "web": APP_DIR / "build/web/main.dart.js",
}


def _defines(environment: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "python3",
            "scripts/env/print_app_env_dart_defines.py",
            "--env",
            environment,
            "--format",
            "json",
            "--launch-mode",
            "matrix_build",
        ],
        cwd=APP_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_command(platform: str, defines: dict[str, str]) -> list[str]:
    command = ["flutter", "build"]
    if platform == "android":
        command.extend(["apk", "--debug"])
    elif platform == "ios":
        command.extend(["ios", "--simulator", "--debug"])
    else:
        command.extend(["web", "--debug"])
    command.extend(
        f"--dart-define={key}={value}" for key, value in defines.items()
    )
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform",
        action="append",
        choices=PLATFORMS,
        default=[],
    )
    parser.add_argument("--ios-simulator-id", default="")
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()

    platforms = tuple(dict.fromkeys(args.platform or PLATFORMS))
    if "ios" in platforms and not args.ios_simulator_id:
        raise ValueError("--ios-simulator-id is required for the iOS matrix")

    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_root = (
        Path(args.output_root)
        if args.output_root
        else ROOT / ".qwq_output/env/repo/runs/startup_environment_build_matrix"
    )
    report_dir = output_root / stamp
    report_dir.mkdir(parents=True, exist_ok=True)
    builds: list[dict[str, Any]] = []

    for environment in ENVIRONMENTS:
        defines = _defines(environment)
        for platform in platforms:
            command = _build_command(platform, defines)
            process_env = dict(os.environ)
            process_env["QWQ_APP_RUNTIME_ENV"] = environment
            if platform == "ios":
                process_env["QWQ_IOS_SIMULATOR_UDID"] = args.ios_simulator_id
            started = time.monotonic()
            result = subprocess.run(
                command,
                cwd=APP_DIR,
                env=process_env,
                check=False,
            )
            artifact = ARTIFACTS[platform]
            succeeded = result.returncode == 0 and artifact.is_file()
            builds.append(
                {
                    "runtimeEnv": environment,
                    "platform": platform,
                    "exitCode": result.returncode,
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                    "artifact": str(artifact),
                    "artifactSha256": _sha256(artifact) if succeeded else "",
                    "status": "passed" if succeeded else "failed",
                }
            )

    report = {
        "schema": "startup-environment-build-matrix",
        "status": (
            "passed"
            if all(build["status"] == "passed" for build in builds)
            else "failed"
        ),
        "environments": list(ENVIRONMENTS),
        "platforms": list(platforms),
        "builds": builds,
    }
    report_path = report_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
