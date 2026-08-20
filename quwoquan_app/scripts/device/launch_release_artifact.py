#!/usr/bin/env python3
"""Install and launch one exact Android Release artifact on prod-sim."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    transition_app_launch_attempt,
)

IOS_SIMULATOR_RELEASE_BLOCKER = (
    "APP.LAUNCH.ios_release_simulator_unsupported: Flutter iOS simulator "
    "supports Debug only; use an iphoneos Release artifact on an authorized "
    "registered device instead"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--platform", required=True, choices=("android", "ios"))
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--log-ref", default="")
    return parser


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    elif path.is_dir():
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(child.stat().st_size.to_bytes(8, "big"))
            with child.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
    else:
        raise ValueError(f"artifact is missing: {path}")
    return "sha256:" + digest.hexdigest()


def _load_inputs(manifest_path: Path, platform: str) -> tuple[dict[str, Any], Path]:
    if platform == "ios":
        raise ValueError(IOS_SIMULATOR_RELEASE_BLOCKER)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "app-artifact-manifest"
        or manifest.get("environment") != "prod"
        or manifest.get("platform") != platform
        or manifest.get("buildMode") != "release"
        or manifest.get("distributionClass") != "simulator"
        or manifest.get("promotable") is not False
    ):
        raise ValueError(
            "APP.LAUNCH.prod_artifact_invalid: prod-sim requires an exact "
            "non-promotable simulator Release manifest"
        )
    receipt_path = manifest_path.with_name("build-receipt.json")
    build_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if Path(str(build_receipt.get("manifestPath") or "")).resolve() != manifest_path.resolve():
        raise ValueError("APP.LAUNCH.prod_artifact_invalid: build receipt manifest mismatch")
    artifact = Path(str(build_receipt.get("artifactPath") or "")).resolve()
    if _digest(artifact) != manifest.get("artifactDigest"):
        raise ValueError("APP.LAUNCH.prod_artifact_invalid: artifact digest mismatch")
    return manifest, artifact


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True)


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest, artifact = _load_inputs(args.manifest.resolve(), args.platform)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    create_app_launch_attempt(
        args.receipt,
        environment="prod",
        target="prod-sim",
        platform=args.platform,
        build_mode="release",
        run_mode="release-artifact",
        device_id=args.device,
        artifact_digest=str(manifest["artifactDigest"]),
        launch_digest=str(manifest["launchManifestDigest"]),
        log_refs=[args.log_ref] if args.log_ref else [],
        non_promotable=True,
    )
    transition_app_launch_attempt(args.receipt, "compiling")
    transition_app_launch_attempt(args.receipt, "compiled")
    transition_app_launch_attempt(args.receipt, "installing")
    if args.platform == "android":
        install = _run(["adb", "-s", args.device, "install", "-r", str(artifact)])
    else:
        install = _run(["xcrun", "simctl", "install", args.device, str(artifact)])
    if install.returncode != 0:
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.install_failed",
        )
        return install.returncode
    transition_app_launch_attempt(args.receipt, "installed")
    transition_app_launch_attempt(args.receipt, "launching")
    application_id = str(manifest["applicationId"])
    if args.platform == "android":
        launch = _run(
            [
                "adb",
                "-s",
                args.device,
                "shell",
                "monkey",
                "-p",
                application_id,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ]
        )
    else:
        launch = _run(["xcrun", "simctl", "launch", args.device, application_id])
    if launch.returncode != 0:
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.launch_failed",
        )
        return launch.returncode
    transition_app_launch_attempt(args.receipt, "launched")
    print(json.dumps({"receipt": str(args.receipt), "artifact": str(artifact)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
