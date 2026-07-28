#!/usr/bin/env python3
"""把构建输出摘要封装为可部署、可复核的不可变发布清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from quwoquan_ops.cli.prod.collect_release_artifact_descriptors import (
        ARTIFACT_SCHEMAS,
    )
except ModuleNotFoundError:  # Direct CLI execution sets sys.path to this directory.
    from collect_release_artifact_descriptors import ARTIFACT_SCHEMAS


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
REQUIRED_RELEASE_ARTIFACTS = (
    "publicWeb",
    "androidOfficialRelease",
    "opsPortal",
    "contractGraph",
    "providerBindings",
    "testEvidence",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--image-descriptors-dir", type=Path)
    parser.add_argument("--artifact-descriptors-dir", type=Path)
    return parser.parse_args()


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def load_image_descriptors(directory: Path) -> dict[str, dict[str, Any]]:
    descriptors: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        descriptor = load_json(path)
        service = str(descriptor.get("service") or "").strip()
        if not service:
            raise ValueError(f"{path} missing service")
        if service in descriptors:
            raise ValueError(f"duplicate image descriptor for {service}")
        descriptors[service] = descriptor
    return descriptors


def validate_descriptor(
    service: str,
    descriptor: dict[str, Any],
    *,
    expected_repository: str,
    expected_tag: str,
) -> dict[str, Any]:
    repository = str(descriptor.get("repository") or "").strip()
    tag = str(descriptor.get("tag") or "").strip()
    digest = str(descriptor.get("digest") or "").strip()
    if repository != expected_repository:
        raise ValueError(
            f"{service} repository mismatch: {repository!r} != {expected_repository!r}"
        )
    if tag != expected_tag:
        raise ValueError(f"{service} tag mismatch: {tag!r} != {expected_tag!r}")
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{service} missing immutable OCI digest")
    expected_ref = f"{repository}@{digest}"
    if str(descriptor.get("ref") or "") != expected_ref:
        raise ValueError(f"{service} digest ref mismatch")
    attestations = descriptor.get("attestations")
    if not isinstance(attestations, dict):
        raise ValueError(f"{service} missing attestations")
    for attestation_type in ("spdxSbom", "slsaProvenance"):
        value = str(attestations.get(attestation_type) or "").strip()
        if value != f"oci://{expected_ref}#{attestation_type}":
            raise ValueError(f"{service} missing {attestation_type} attestation reference")
    return {
        "repository": repository,
        "tag": tag,
        "digest": digest,
        "ref": expected_ref,
        "attestations": attestations,
    }


def load_release_artifacts(
    artifact_dir: Path,
    descriptors_dir: Path,
) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for descriptor_path in sorted(descriptors_dir.glob("*.json")):
        descriptor = load_json(descriptor_path)
        artifact_id = str(descriptor.get("artifactId") or "").strip()
        schema = str(descriptor.get("schema") or "").strip()
        relative = str(descriptor.get("path") or "").strip()
        declared_digest = str(descriptor.get("sha256") or "").strip()
        if artifact_id not in REQUIRED_RELEASE_ARTIFACTS:
            raise ValueError(f"unsupported release artifact id: {artifact_id!r}")
        if artifact_id in artifacts:
            raise ValueError(f"duplicate release artifact descriptor: {artifact_id}")
        expected_schema = ARTIFACT_SCHEMAS[artifact_id]
        if schema != expected_schema:
            raise ValueError(
                f"release artifact {artifact_id} schema mismatch: "
                f"{schema!r} != {expected_schema!r}"
            )
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise ValueError(f"release artifact {artifact_id} path is unsafe")
        artifact_path = (artifact_dir / relative_path).resolve()
        if artifact_dir.resolve() not in artifact_path.parents:
            raise ValueError(f"release artifact {artifact_id} escapes artifact root")
        if not artifact_path.is_file():
            raise ValueError(f"release artifact {artifact_id} is missing: {relative}")
        actual_digest = sha256_file(artifact_path)
        if declared_digest != actual_digest:
            raise ValueError(f"release artifact {artifact_id} digest mismatch")
        digest_field = (
            "manifestSHA256"
            if artifact_id in {"publicWeb", "androidOfficialRelease"}
            else "contentSHA256"
        )
        artifacts[artifact_id] = {
            "schema": schema,
            "path": relative_path.as_posix(),
            digest_field: actual_digest,
        }
    if set(artifacts) != set(REQUIRED_RELEASE_ARTIFACTS):
        missing = sorted(set(REQUIRED_RELEASE_ARTIFACTS) - set(artifacts))
        extra = sorted(set(artifacts) - set(REQUIRED_RELEASE_ARTIFACTS))
        raise ValueError(
            f"release artifact descriptor set mismatch: missing={missing}, extra={extra}"
        )
    return artifacts


def finalize(
    artifact_dir: Path,
    descriptors_dir: Path | None,
    artifact_descriptors_dir: Path | None = None,
) -> dict[str, Any]:
    manifest_path = artifact_dir / "manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "mainline-release-artifact":
        raise ValueError("release artifact schema mismatch")

    required = manifest.get("requiredImages")
    repositories = manifest.get("imageRepositories")
    versions = manifest.get("versions")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ValueError("requiredImages must be a string list")
    if not isinstance(repositories, dict) or not isinstance(versions, dict):
        raise ValueError("release artifact is missing image repositories or versions")
    image_version = str(versions.get("imageVersion") or "").strip()
    if not image_version:
        raise ValueError("release artifact is missing imageVersion")

    if descriptors_dir is None:
        if artifact_descriptors_dir is None or manifest.get("status") != "component-ready":
            raise ValueError(
                "existing image descriptors may only be reused while attaching "
                "whole-app artifacts to a component-ready manifest"
            )
        existing_images = manifest.get("images")
        if not isinstance(existing_images, dict):
            raise ValueError("component-ready manifest is missing immutable images")
        descriptors = existing_images
    else:
        descriptors = load_image_descriptors(descriptors_dir)
    required_set = set(required)
    if set(descriptors) != required_set:
        missing = sorted(required_set - set(descriptors))
        extra = sorted(set(descriptors) - required_set)
        raise ValueError(f"image descriptor set mismatch: missing={missing}, extra={extra}")

    images = {
        service: validate_descriptor(
            service,
            descriptors[service],
            expected_repository=str(repositories.get(service) or ""),
            expected_tag=image_version,
        )
        for service in required
    }

    release_files = manifest.get("releaseFiles")
    release_digests = manifest.get("releaseFileDigests")
    if not isinstance(release_files, dict) or not isinstance(release_digests, dict):
        raise ValueError("release artifact is missing config file digests")
    for service, relative in release_files.items():
        path = artifact_dir / str(relative)
        if not path.is_file():
            raise ValueError(f"release config missing for {service}: {relative}")
        if release_digests.get(service) != sha256_file(path):
            raise ValueError(f"release config digest mismatch for {service}")

    manifest["images"] = images
    if artifact_descriptors_dir is None:
        manifest.pop("requiredArtifacts", None)
        manifest.pop("artifacts", None)
        manifest["status"] = "component-ready"
    else:
        manifest["requiredArtifacts"] = list(REQUIRED_RELEASE_ARTIFACTS)
        manifest["artifacts"] = load_release_artifacts(
            artifact_dir,
            artifact_descriptors_dir,
        )
        manifest["status"] = "deployable"
    manifest.pop("manifestDigest", None)
    manifest["manifestDigest"] = (
        "sha256:" + hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    args = parse_args()
    try:
        manifest = finalize(
            args.artifact_dir.resolve(),
            (
                args.image_descriptors_dir.resolve()
                if args.image_descriptors_dir is not None
                else None
            ),
            (
                args.artifact_descriptors_dir.resolve()
                if args.artifact_descriptors_dir is not None
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        f"OK: {manifest['status']} release artifact "
        f"{manifest['manifestDigest']} includes {len(manifest['images'])} immutable images"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
