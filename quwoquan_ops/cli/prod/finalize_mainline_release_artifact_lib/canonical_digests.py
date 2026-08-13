"""ReleaseEvidenceManifest 规范字节序列化、摘要与封存（逐字搬移自入口）。"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    DIGEST_PATTERN,
    ENVIRONMENTS,
    SCHEMA,
)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Return the canonical full-snapshot projection used by artifactDigest."""

    canonical = dict(payload)
    canonical.pop("artifactDigest", None)
    return _canonical_json_bytes(canonical)


def canonical_manifest_digest(payload: dict[str, Any]) -> str:
    """Digest the complete manifest snapshot, excluding only artifactDigest itself."""

    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _candidate_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Project immutable candidate material; release receipts are intentionally absent."""

    source = payload.get("source")
    images = payload.get("images")
    configurations = payload.get("configurationPackages")
    applications = payload.get("applicationPackages")
    provider = payload.get("providerEvidence")
    test = payload.get("testEvidence")
    contract_graph = payload.get("contractGraphDigest")
    if not isinstance(source, dict) or not isinstance(images, dict):
        raise ValueError("candidate material source or images are incomplete")
    if not isinstance(configurations, dict) or set(configurations) != set(ENVIRONMENTS):
        raise ValueError("candidate configuration material is incomplete")
    if not isinstance(applications, dict) or set(applications) != set(ENVIRONMENTS):
        raise ValueError("candidate application material is incomplete")
    if not isinstance(provider, dict) or not isinstance(test, dict):
        raise ValueError("candidate qualification material is incomplete")
    if DIGEST_PATTERN.fullmatch(str(contract_graph or "")) is None:
        raise ValueError("candidate contract graph material is incomplete")

    projected_images: dict[str, Any] = {}
    for service, descriptor in sorted(images.items()):
        if not isinstance(descriptor, dict) or not {
            "repository",
            "digest",
            "ref",
            "attestations",
        }.issubset(descriptor):
            raise ValueError(f"candidate image material is incomplete: {service}")
        projected_images[service] = {
            "repository": descriptor["repository"],
            "digest": descriptor["digest"],
            "ref": descriptor["ref"],
            "attestations": descriptor["attestations"],
        }

    projected_configurations: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        packages = configurations.get(environment)
        if not isinstance(packages, dict) or not packages:
            raise ValueError(
                f"candidate configuration material is incomplete: {environment}"
            )
        projected_configurations[environment] = {
            service: {"digest": descriptor.get("digest")}
            for service, descriptor in sorted(packages.items())
            if isinstance(descriptor, dict)
        }
        if len(projected_configurations[environment]) != len(packages):
            raise ValueError(
                f"candidate configuration material is invalid: {environment}"
            )

    projected_applications: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        packages = applications.get(environment)
        if not isinstance(packages, dict) or set(packages) != set(
            APPLICATION_PACKAGES[environment]
        ):
            raise ValueError(
                f"candidate application material is incomplete: {environment}"
            )
        projected_applications[environment] = {
            surface: {
                "digest": descriptor.get("digest"),
                "packageDigest": descriptor.get("packageDigest"),
                "sourceRef": descriptor.get("sourceRef"),
            }
            for surface, descriptor in sorted(packages.items())
            if isinstance(descriptor, dict)
        }
        if len(projected_applications[environment]) != len(packages):
            raise ValueError(
                f"candidate application material is invalid: {environment}"
            )

    return {
        "schema": SCHEMA,
        "source": {
            "gitSha": source.get("gitSha"),
            "treeDigest": source.get("treeDigest"),
            "repository": source.get("repository"),
        },
        "images": projected_images,
        "configurationPackages": projected_configurations,
        "applicationPackages": projected_applications,
        "contractGraphDigest": contract_graph,
        "providerEvidence": {"digest": provider.get("digest")},
        "testEvidence": {
            "digest": test.get("digest"),
            "layers": test.get("layers"),
        },
    }


def canonical_candidate_digest(payload: dict[str, Any]) -> str:
    projection = _candidate_projection(payload)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def seal_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Seal one lifecycle snapshot without allowing candidate identity drift."""

    sealed = dict(payload)
    sealed.pop("artifactDigest", None)
    try:
        candidate_digest: str | None = canonical_candidate_digest(sealed)
    except ValueError:
        candidate_digest = None
    existing_candidate = payload.get("candidateId")
    if existing_candidate not in {None, candidate_digest}:
        raise ValueError("release candidate identity changed across lifecycle snapshots")
    sealed["candidateId"] = candidate_digest
    sealed["artifactDigest"] = canonical_manifest_digest(sealed)
    return sealed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"application payload tree is missing or unsafe: {root}")
    entries = sorted(root.rglob("*"))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f"application payload tree contains symlink: {unsafe}")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f"application payload tree is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def sha256_ops_portal_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Ops Portal payload tree is missing or unsafe: {root}")
    entries = sorted(root.rglob("*"))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f"Ops Portal payload tree contains symlink: {unsafe}")
    files = [path for path in entries if path.is_file()]
    if not files:
        raise ValueError(f"Ops Portal payload tree is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def write_summary(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "## Release Evidence Manifest",
        "",
        f"- `status`: `{manifest['status']}`",
        f"- `candidateId`: `{manifest['candidateId']}`",
        f"- `artifactDigest`: `{manifest['artifactDigest']}`",
        f"- `immutableImages`: `{len(manifest['images'])}`",
        f"- `environmentReceipts`: `{len(manifest['environmentReceipts'])}`",
        f"- `blockers`: `{len(manifest['blockers'])}`",
        f"- `missingEvidence`: `{len(manifest['missingEvidence'])}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
