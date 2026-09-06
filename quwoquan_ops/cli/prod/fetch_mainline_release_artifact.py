#!/usr/bin/env python3
"""Materialize a Service Pipeline release bundle from an immutable OCI image."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.registry_transport import run_with_bounded_retry
from quwoquan_ops.ci.release_evidence_reader import (
    STATUSES,
    validate_historical_release_snapshot,
)


IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
FETCHABLE_STATUSES = STATUSES - {"build-input"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize an exact release-artifact digest for non-promotable "
            "prevalidation or historical inspection"
        )
    )
    parser.add_argument("--ref", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--platform",
        choices=("linux/amd64",),
        default="linux/amd64",
    )
    return parser.parse_args()


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def pull(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return run_with_bounded_retry(lambda: run(argv))


def fetch(
    ref: str,
    output_dir: Path,
    *,
    platform: str = "linux/amd64",
) -> dict[str, str]:
    if IMMUTABLE_REF.fullmatch(ref) is None or "/release-artifact@" not in ref:
        raise ValueError("release artifact must be a GHCR release-artifact digest ref")
    if platform != "linux/amd64":
        raise ValueError("release artifact platform must be linux/amd64")
    pull_result = pull(["docker", "pull", "--platform", platform, ref])
    if pull_result.returncode != 0:
        raise RuntimeError(
            "release artifact pull failed after 3 bounded attempts: "
            f"{pull_result.stderr.strip() or pull_result.stdout.strip()}"
        )
    inspect = run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref]
    )
    if inspect.returncode != 0:
        raise RuntimeError("release artifact digest inspection failed")
    repo_digests = json.loads(inspect.stdout)
    if ref not in repo_digests:
        raise RuntimeError("pulled release artifact digest does not match requested ref")

    with tempfile.TemporaryDirectory(prefix="qwq-release-artifact-") as temporary:
        create = run(["docker", "create", "--platform", platform, ref])
        if create.returncode != 0:
            raise RuntimeError(
                f"release artifact container creation failed: "
                f"{create.stderr.strip() or create.stdout.strip()}"
            )
        container_id = create.stdout.strip()
        try:
            staged = Path(temporary) / "release"
            staged.mkdir()
            copy = run(["docker", "cp", f"{container_id}:/release/.", str(staged)])
            if copy.returncode != 0:
                raise RuntimeError(
                    f"release artifact extraction failed: "
                    f"{copy.stderr.strip() or copy.stdout.strip()}"
                )
            manifest_path = staged / "manifest.json"
            if not manifest_path.is_file():
                raise RuntimeError("release artifact does not contain manifest.json")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest root must be an object")
                validate_historical_release_snapshot(
                    manifest,
                    artifact_dir=staged,
                    allowed_statuses=FETCHABLE_STATUSES,
                )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    f"release artifact contains invalid canonical evidence: {error}"
                ) from error
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged, output_dir)
        finally:
            run(["docker", "rm", "-f", container_id])
    return {
        "ref": ref,
        "manifest": str(output_dir / "manifest.json"),
        "candidateId": str(manifest["candidateId"]),
        "artifactDigest": str(manifest["artifactDigest"]),
    }


def main() -> int:
    args = parse_args()
    try:
        report = fetch(
            args.ref.strip(),
            args.output_dir.resolve(),
            platform=args.platform,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
