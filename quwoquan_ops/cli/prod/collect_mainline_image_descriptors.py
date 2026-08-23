#!/usr/bin/env python3
"""Resolve four-environment GHCR tags into immutable image descriptors."""

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
    ENVIRONMENTS,
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


def collect(
    manifest: dict[str, Any], output_dir: Path
) -> dict[str, dict[str, dict[str, Any]]]:
    validate_manifest(manifest, allowed_statuses={"build-input"})
    artifacts = manifest["environmentArtifacts"]
    required = manifest["requiredEvidence"]["environmentArtifacts"]

    inputs: list[tuple[str, str, str, str]] = []
    for environment in ENVIRONMENTS:
        images = artifacts[environment]["images"]
        for owner in required[environment]:
            image = images[owner]
            repository = str(image.get("repository") or "").strip()
            transport_ref = str(image.get("transportRef") or "").strip()
            if not repository.startswith("ghcr.io/"):
                raise ValueError(
                    f"release image repository is not GHCR: {environment}/{owner}"
                )
            if not transport_ref.startswith(repository + ":") or transport_ref.endswith(
                ":latest"
            ):
                raise ValueError(
                    f"release image transport ref is not fixed: {environment}/{owner}"
                )
            inputs.append((environment, str(owner), repository, transport_ref))

    source = manifest.get("source")
    source_repository = (
        str(source.get("repository") or "") if isinstance(source, dict) else ""
    )

    def resolve_and_verify(
        environment: str,
        owner: str,
        repository: str,
        transport_ref: str,
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
            "environment": environment,
            "runtimeImageOwner": owner,
            "repository": repository,
            "transportRef": transport_ref,
            "digest": digest,
            "ref": ref,
            "attestations": {
                "spdxSbom": f"oci://{ref}#spdxSbom",
                "slsaProvenance": f"oci://{ref}#slsaProvenance",
            },
        }

    descriptors: dict[tuple[str, str], dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, max(1, len(inputs))),
        thread_name_prefix="release-image-descriptor",
    ) as executor:
        futures = {
            executor.submit(resolve_and_verify, *item): (item[0], item[1])
            for item in inputs
        }
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                descriptors[key] = future.result()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                environment, owner = key
                raise RuntimeError(
                    "release image descriptor collection failed for "
                    f"{environment}/{owner}: {error}"
                ) from error

    output_dir.mkdir(parents=True, exist_ok=True)
    ordered: dict[str, dict[str, dict[str, Any]]] = {}
    # DEC-005 信任域裁决：alpha/beta/gamma 必须复用同一 nonprod digest，
    # prod 属于独立信任域（编译期 Provider binding 不同），digest 必须分叉。
    nonprod_digests: dict[str, str] = {}
    prod_digests: dict[str, str] = {}
    for environment in ENVIRONMENTS:
        ordered[environment] = {}
        environment_dir = output_dir / environment
        environment_dir.mkdir(parents=True, exist_ok=True)
        for owner in required[environment]:
            descriptor = descriptors[(environment, owner)]
            digest = str(descriptor["digest"])
            if environment == "prod":
                prod_digests[str(owner)] = digest
            else:
                previous = nonprod_digests.setdefault(str(owner), digest)
                if previous != digest:
                    raise ValueError(
                        "nonprod release images must share one digest per owner: "
                        f"{owner} diverges at {environment}"
                    )
            environment_dir.joinpath(f"{owner}.json").write_text(
                json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            ordered[environment][owner] = descriptor
    for owner, digest in prod_digests.items():
        if nonprod_digests.get(owner) == digest:
            raise ValueError(
                "prod release images must not reuse the nonprod trust-domain "
                f"digest: {owner}"
            )
    return ordered


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
                "environments": {
                    environment: sorted(images)
                    for environment, images in descriptors.items()
                },
                "count": sum(len(images) for images in descriptors.values()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
