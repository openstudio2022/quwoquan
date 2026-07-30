#!/usr/bin/env python3
"""Resolve pushed GHCR tags into immutable image descriptors.

The Service Pipeline uses this after every image matrix entry has completed.  It
rebuilds no image and stores no credential; Docker/Buildx owns registry auth.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.registry_transport import run_with_bounded_retry
from quwoquan_ops.cli.prod.oci_supply_chain import verify_oci_supply_chain
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    validate_manifest,
    validate_manifest_files,
)


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release input manifest must be an object")
    manifest = validate_manifest(payload, allowed_statuses={"build-input"})
    validate_manifest_files(path.parent, manifest)
    return manifest


def resolve_registry_digest(ref: str) -> str:
    argv = ["docker", "buildx", "imagetools", "inspect", ref]
    result = run_with_bounded_retry(
        lambda: subprocess.run(
            argv,
            text=True,
            capture_output=True,
            check=False,
        )
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
    validate_manifest(manifest, allowed_statuses={"build-input"})
    required = manifest["requiredEvidence"]["images"]
    images = manifest["images"]

    inputs: list[tuple[str, str, str]] = []
    for service in required:
        image = images[service]
        repository = str(image.get("repository") or "").strip()
        transport_ref = str(image.get("transportRef") or "").strip()
        if not repository.startswith("ghcr.io/"):
            raise ValueError(f"release image repository is not GHCR: {service}")
        if not transport_ref.startswith(repository + ":") or transport_ref.endswith(
            ":latest"
        ):
            raise ValueError(f"release image transport ref is not fixed: {service}")
        inputs.append((str(service), repository, transport_ref))

    source = manifest.get("source")
    source_repository = (
        str(source.get("repository") or "") if isinstance(source, dict) else ""
    )

    def resolve_and_verify(
        service: str, repository: str, transport_ref: str
    ) -> dict[str, Any]:
        digest = resolve_registry_digest(transport_ref)
        ref = f"{repository}@{digest}"
        verify_oci_supply_chain(
            ref,
            repository=source_repository,
            signer_workflow=(
                f"{source_repository}/.github/workflows/service_pipeline.yml"
            ),
        )
        return {
            "service": service,
            "repository": repository,
            "transportRef": transport_ref,
            "digest": digest,
            "ref": ref,
            "attestations": {
                "spdxSbom": f"oci://{ref}#spdxSbom",
                "slsaProvenance": f"oci://{ref}#slsaProvenance",
            },
        }

    descriptors: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, max(1, len(inputs))),
        thread_name_prefix="release-image-descriptor",
    ) as executor:
        futures = {
            executor.submit(resolve_and_verify, *item): item[0] for item in inputs
        }
        for future in concurrent.futures.as_completed(futures):
            service = futures[future]
            try:
                descriptors[service] = future.result()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                raise RuntimeError(
                    f"release image descriptor collection failed for {service}: {error}"
                ) from error

    output_dir.mkdir(parents=True, exist_ok=True)
    ordered_descriptors: dict[str, dict[str, Any]] = {}
    for service in required:
        descriptor = descriptors[service]
        output_dir.joinpath(f"{service}.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        ordered_descriptors[service] = descriptor
    return ordered_descriptors


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
