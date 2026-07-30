#!/usr/bin/env python3
"""Materialize a generic immutable GHCR evidence bundle from ``/evidence``."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--require-file", action="append", default=[])
    return parser.parse_args()


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def materialize(
    ref: str, expected_digest: str, output_dir: Path, required_files: list[str]
) -> None:
    if IMMUTABLE_REF.fullmatch(ref) is None:
        raise ValueError("evidence ref must be an immutable GHCR digest ref")
    if DIGEST.fullmatch(expected_digest) is None or ref.rsplit("@", 1)[1] != expected_digest:
        raise ValueError("evidence ref does not match its expected OCI digest")
    pull = _run(["docker", "pull", "--platform", "linux/amd64", ref])
    if pull.returncode != 0:
        raise RuntimeError(pull.stderr.strip() or "evidence OCI pull failed")
    inspect = _run(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref]
    )
    if inspect.returncode != 0 or ref not in json.loads(inspect.stdout):
        raise RuntimeError("pulled evidence OCI digest does not match requested ref")
    create = _run(["docker", "create", "--platform", "linux/amd64", ref])
    if create.returncode != 0:
        raise RuntimeError(create.stderr.strip() or "evidence OCI create failed")
    container_id = create.stdout.strip()
    try:
        with tempfile.TemporaryDirectory(prefix="qwq-evidence-oci-") as temporary:
            staged = Path(temporary) / "evidence"
            staged.mkdir()
            copy = _run(["docker", "cp", f"{container_id}:/evidence/.", str(staged)])
            if copy.returncode != 0:
                raise RuntimeError(copy.stderr.strip() or "evidence OCI extraction failed")
            for relative in required_files:
                path = staged / relative
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f"evidence OCI required file is missing: {relative}")
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged, output_dir)
    finally:
        _run(["docker", "rm", "-f", container_id])


def main() -> int:
    args = parse_args()
    try:
        materialize(args.ref, args.expected_digest, args.output_dir, args.require_file)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"materialize_evidence_oci: FAIL: {error}")
        return 2
    print(f"materialize_evidence_oci: OK: {args.ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
