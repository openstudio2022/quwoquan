#!/usr/bin/env python3
"""Build component-ready runtime packages from the canonical launch handoff.

This script never emits runtime readiness.  It retains each environment's
artifact under the report directory so later launcher evidence cannot silently
refer to an artifact overwritten by the next matrix build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PLATFORMS = ("android", "ios", "web")
TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
ARTIFACTS = {
    "android": APP_DIR / "build/app/outputs/flutter-apk/app-debug.apk",
    "ios": APP_DIR / "build/ios/iphonesimulator/Runner.app",
    "web": APP_DIR / "build/web",
}
SPEC_REFS = (
    (
        "specs/feature-tree/runtime/runtime-client-foundation/"
        "cold-start-performance/spec.md#gwt-004"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-001"
    ),
)


def _handoff(environment: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "python3",
            "scripts/device/build_launcher_handoff.py",
            "--env",
            environment,
            "--target",
            TARGETS[environment],
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
    paths = [path] if path.is_file() else sorted(
        item for item in path.rglob("*") if item.is_file()
    )
    for item in paths:
        relative = item.name if path.is_file() else item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _retain_artifact(
    artifact: Path,
    *,
    report_dir: Path,
    environment: str,
    platform: str,
) -> Path:
    destination = report_dir / "artifacts" / environment / platform / artifact.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"retained artifact already exists: {destination}")
    if artifact.is_dir():
        shutil.copytree(artifact, destination, symlinks=True)
    else:
        shutil.copy2(artifact, destination)
    return destination


def _build_command(platform: str, handoff: dict[str, Any]) -> list[str]:
    command = ["flutter", "build"]
    if platform == "android":
        command.extend(["apk", "--debug"])
    elif platform == "ios":
        command.extend(["ios", "--simulator", "--debug"])
    else:
        command.extend(["web", "--debug"])
    command.extend(["--target", str(handoff["entrypoint"])])
    command.extend(
        f"--dart-define={key}={value}"
        for key, value in dict(handoff["dartDefines"]).items()
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
    parser.add_argument(
        "--environment",
        action="append",
        choices=ENVIRONMENTS,
        default=[],
    )
    parser.add_argument("--ios-simulator-id", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--baseline-id", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--release-digest", default="")
    args = parser.parse_args()

    platforms = tuple(dict.fromkeys(args.platform or PLATFORMS))
    environments = tuple(dict.fromkeys(args.environment or ENVIRONMENTS))

    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_root = (
        Path(args.output_root)
        if args.output_root
        else ROOT / ".qwq_output/env/repo/runs/startup_environment_build_matrix"
    )
    report_dir = output_root / stamp
    report_dir.mkdir(parents=True, exist_ok=True)
    builds: list[dict[str, Any]] = []

    for environment in environments:
        handoff = _handoff(environment)
        for platform in platforms:
            command = _build_command(platform, handoff)
            process_env = dict(os.environ)
            process_env["QWQ_APP_RUNTIME_ENV"] = environment
            process_env["QWQ_LAUNCH_TARGET"] = str(handoff["target"])
            process_env["QWQ_APP_BUILD_CONTEXT"] = "package-only"
            process_env["QWQ_DART_DEFINES_DIGEST"] = str(
                handoff["dartDefinesDigest"]
            )
            process_env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
                handoff["runtimeConfigDigest"]
            )
            process_env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
                handoff["effectiveLaunchManifestDigest"]
            )
            process_env["QWQ_APP_RECOVERY_BASE_URL"] = str(
                handoff["recoveryBaseUrl"]
            )
            process_env["QWQ_APP_PUBLIC_WEB_URL"] = str(
                handoff["publicWebBaseUrl"]
            )
            process_env["QWQ_APP_DOWNLOAD_BASE_URL"] = str(
                handoff["appDownloadBaseUrl"]
            )
            if platform == "ios" and args.ios_simulator_id:
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
            if artifact.is_dir():
                succeeded = result.returncode == 0 and any(
                    item.is_file() for item in artifact.rglob("*")
                )
            retained_artifact: Path | None = None
            if succeeded:
                retained_artifact = _retain_artifact(
                    artifact,
                    report_dir=report_dir,
                    environment=environment,
                    platform=platform,
                )
            builds.append(
                {
                    "caseId": f"component-build:{environment}:{platform}",
                    "kind": "component_readiness",
                    "required": True,
                    "runtimeEnv": environment,
                    "runtimeTarget": handoff["target"],
                    "platform": platform,
                    "entrypoint": handoff["entrypoint"],
                    "dartDefinesDigest": handoff["dartDefinesDigest"],
                    "runtimeConfigDigest": handoff["runtimeConfigDigest"],
                    "effectiveLaunchManifestDigest": handoff[
                        "effectiveLaunchManifestDigest"
                    ],
                    "buildContext": "package-only",
                    "exitCode": result.returncode,
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                    "artifact": str(retained_artifact or artifact),
                    "artifactSha256": (
                        _sha256(retained_artifact) if retained_artifact else ""
                    ),
                    "status": "component_ready" if succeeded else "failed",
                    "specRefs": list(SPEC_REFS),
                }
            )

    failed = sum(build["status"] == "failed" for build in builds)
    report = {
        "schema": "qwq.startup-environment-component-build",
        "status": "component_ready" if failed == 0 else "failed",
        "required": len(builds),
        "executed": len(builds),
        "skipped": 0,
        "failed": failed,
        "baselineId": args.baseline_id,
        "releaseId": args.release_id,
        "releaseDigest": args.release_digest,
        "specRefs": list(SPEC_REFS),
        "environments": list(environments),
        "platforms": list(platforms),
        "builds": builds,
    }
    report_path = report_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "component_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
