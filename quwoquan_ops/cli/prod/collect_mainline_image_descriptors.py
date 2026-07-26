#!/usr/bin/env python3
"""Resolve pushed GHCR tags into immutable image descriptors.

The Service Pipeline uses this after every image matrix entry has completed.  It
rebuilds no image and stores no credential; Docker/Buildx owns registry auth.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "build-input":
        raise ValueError("release input manifest is invalid")
    return payload


def resolve_registry_digest(ref: str) -> str:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"registry digest lookup failed for {ref}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "digest":
            digest = value.strip()
            if DIGEST_PATTERN.fullmatch(digest):
                return digest
    raise RuntimeError(f"registry digest lookup returned no immutable digest: {ref}")


def collect(manifest: dict[str, Any], output_dir: Path) -> dict[str, dict[str, Any]]:
    required = manifest.get("requiredImages")
    repositories = manifest.get("imageRepositories")
    versions = manifest.get("versions")
    if (
        not isinstance(required, list)
        or not all(isinstance(item, str) and item for item in required)
        or not isinstance(repositories, dict)
        or not isinstance(versions, dict)
    ):
        raise ValueError("release input image set is incomplete")
    image_version = str(versions.get("imageVersion") or "").strip()
    if not image_version or image_version == "latest":
        raise ValueError("release input image version is not immutable")

    output_dir.mkdir(parents=True, exist_ok=True)
    descriptors: dict[str, dict[str, Any]] = {}
    for service in required:
        repository = str(repositories.get(service) or "").strip()
        if not repository.startswith("ghcr.io/"):
            raise ValueError(f"release image repository is not GHCR: {service}")
        tag_ref = f"{repository}:{image_version}"
        digest = resolve_registry_digest(tag_ref)
        ref = f"{repository}@{digest}"
        descriptor = {
            "service": service,
            "repository": repository,
            "tag": image_version,
            "digest": digest,
            "ref": ref,
            "attestations": {
                "spdxSbom": f"oci://{ref}#spdxSbom",
                "slsaProvenance": f"oci://{ref}#slsaProvenance",
            },
            "buildDurationSeconds": 0,
        }
        output_dir.joinpath(f"{service}.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        descriptors[service] = descriptor
    return descriptors


def main() -> int:
    args = parse_args()
    try:
        descriptors = collect(load_manifest(args.manifest), args.output_dir)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "services": sorted(descriptors),
                "count": len(descriptors),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
