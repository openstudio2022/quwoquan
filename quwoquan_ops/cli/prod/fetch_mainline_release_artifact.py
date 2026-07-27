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


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.registry_transport import run_with_bounded_retry


IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ref")
    source.add_argument("--source-sha")
    parser.add_argument("--repository", default="")
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
            if not staged.joinpath("manifest.json").is_file():
                raise RuntimeError("release artifact does not contain manifest.json")
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged, output_dir)
        finally:
            run(["docker", "rm", "-f", container_id])
    return {"ref": ref, "manifest": str(output_dir / "manifest.json")}


def discover(
    repository: str,
    source_sha: str,
    *,
    platform: str = "linux/amd64",
) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("release artifact source SHA is invalid")
    normalized = repository.strip("/").lower()
    if re.fullmatch(r"[a-z0-9._-]+/[a-z0-9._-]+", normalized) is None:
        raise ValueError("release artifact repository is invalid")
    tag_ref = f"ghcr.io/{normalized}/release-artifact:sha-{source_sha}"
    if platform != "linux/amd64":
        raise ValueError("release artifact platform must be linux/amd64")
    pull_result = pull(["docker", "pull", "--platform", platform, tag_ref])
    if pull_result.returncode != 0:
        raise RuntimeError(
            "release artifact discovery pull failed after 3 bounded attempts: "
            f"{pull_result.stderr.strip() or pull_result.stdout.strip()}"
        )
    inspect = run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag_ref]
    )
    if inspect.returncode != 0:
        raise RuntimeError("release artifact discovery digest inspection failed")
    for item in json.loads(inspect.stdout):
        if IMMUTABLE_REF.fullmatch(str(item)) and "/release-artifact@" in item:
            return str(item)
    raise RuntimeError("release artifact discovery returned no immutable digest")


def main() -> int:
    args = parse_args()
    try:
        ref = (
            args.ref.strip()
            if args.ref
            else discover(
                args.repository,
                args.source_sha.strip(),
                platform=args.platform,
            )
        )
        report = fetch(
            ref,
            args.output_dir.resolve(),
            platform=args.platform,
        )
        if args.source_sha:
            manifest = json.loads(
                Path(report["manifest"]).read_text(encoding="utf-8")
            )
            source = manifest.get("source") or {}
            if source.get("gitSha") != args.source_sha:
                raise RuntimeError(
                    "release artifact source SHA does not match discovery tag"
                )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
