#!/usr/bin/env python3
"""Materialize a Service Pipeline release bundle from an immutable OCI image."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ref")
    source.add_argument("--source-sha")
    parser.add_argument("--repository", default="")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def fetch(ref: str, output_dir: Path) -> dict[str, str]:
    if IMMUTABLE_REF.fullmatch(ref) is None or "/release-artifact@" not in ref:
        raise ValueError("release artifact must be a GHCR release-artifact digest ref")
    pull = run(["docker", "pull", ref])
    if pull.returncode != 0:
        raise RuntimeError(
            f"release artifact pull failed: {pull.stderr.strip() or pull.stdout.strip()}"
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
        create = run(["docker", "create", ref])
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


def discover(repository: str, source_sha: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("release artifact source SHA is invalid")
    normalized = repository.strip("/").lower()
    if re.fullmatch(r"[a-z0-9._-]+/[a-z0-9._-]+", normalized) is None:
        raise ValueError("release artifact repository is invalid")
    tag_ref = f"ghcr.io/{normalized}/release-artifact:sha-{source_sha}"
    pull = run(["docker", "pull", tag_ref])
    if pull.returncode != 0:
        raise RuntimeError(
            f"release artifact discovery pull failed: "
            f"{pull.stderr.strip() or pull.stdout.strip()}"
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
            else discover(args.repository, args.source_sha.strip())
        )
        report = fetch(ref, args.output_dir.resolve())
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
