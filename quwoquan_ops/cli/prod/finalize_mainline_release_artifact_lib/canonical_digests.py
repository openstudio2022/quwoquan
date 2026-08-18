"""ReleaseEvidenceManifest 规范字节序列化、摘要与封存。"""

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
    canonical = dict(payload)
    canonical.pop("artifactDigest", None)
    return _canonical_json_bytes(canonical)


def canonical_manifest_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _environment_artifact_projection(
    payload: dict[str, Any], environment: str
) -> dict[str, Any]:
    artifacts = payload.get("environmentArtifacts")
    artifact = artifacts.get(environment) if isinstance(artifacts, dict) else None
    if not isinstance(artifact, dict) or artifact.get("environment") != environment:
        raise ValueError(f"environment artifact is incomplete: {environment}")
    images = artifact.get("images")
    configurations = artifact.get("configurationPackages")
    if not isinstance(images, dict) or not images:
        raise ValueError(f"environment image material is incomplete: {environment}")
    if not isinstance(configurations, dict) or not configurations:
        raise ValueError(
            f"environment configuration material is incomplete: {environment}"
        )
    projected_images: dict[str, Any] = {}
    for owner, descriptor in sorted(images.items()):
        if not isinstance(descriptor, dict) or not {
            "repository",
            "transportRef",
        }.issubset(descriptor):
            raise ValueError(
                f"environment image material is incomplete: {environment}/{owner}"
            )
        projected = {
            "repository": descriptor["repository"],
            "transportRef": descriptor["transportRef"],
        }
        if {"digest", "ref", "attestations"}.issubset(descriptor):
            projected.update(
                {
                    "digest": descriptor["digest"],
                    "ref": descriptor["ref"],
                    "attestations": descriptor["attestations"],
                }
            )
        projected_images[owner] = projected
    projected_configurations = {
        service: {"digest": descriptor.get("digest")}
        for service, descriptor in sorted(configurations.items())
        if isinstance(descriptor, dict)
    }
    if len(projected_configurations) != len(configurations):
        raise ValueError(
            f"environment configuration material is invalid: {environment}"
        )
    return {
        "environment": environment,
        "images": projected_images,
        "configurationPackages": projected_configurations,
    }


def canonical_environment_artifact_digest(
    payload: dict[str, Any], environment: str
) -> str:
    projection = _environment_artifact_projection(payload, environment)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def canonical_release_train_digest(payload: dict[str, Any]) -> str:
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("release train source is incomplete")
    projection = {
        "schema": SCHEMA,
        "source": {
            "gitSha": source.get("gitSha"),
            "treeDigest": source.get("treeDigest"),
            "repository": source.get("repository"),
        },
    }
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def _candidate_projection(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source")
    artifacts = payload.get("environmentArtifacts")
    applications = payload.get("applicationPackages")
    provider = payload.get("providerEvidence")
    test = payload.get("testEvidence")
    contract_graph = payload.get("contractGraphDigest")
    release_train_id = payload.get("releaseTrainId")
    if not isinstance(source, dict) or not isinstance(artifacts, dict):
        raise ValueError("candidate source or environment artifacts are incomplete")
    if set(artifacts) != set(ENVIRONMENTS):
        raise ValueError("candidate environment artifact material is incomplete")
    if not isinstance(applications, dict) or set(applications) != set(ENVIRONMENTS):
        raise ValueError("candidate application material is incomplete")
    if not isinstance(provider, dict) or not isinstance(test, dict):
        raise ValueError("candidate qualification material is incomplete")
    if DIGEST_PATTERN.fullmatch(str(contract_graph or "")) is None:
        raise ValueError("candidate contract graph material is incomplete")
    if DIGEST_PATTERN.fullmatch(str(release_train_id or "")) is None:
        raise ValueError("candidate release train identity is incomplete")

    projected_artifacts: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        projection = _environment_artifact_projection(payload, environment)
        artifact = artifacts[environment]
        environment_digest = artifact.get("environmentArtifactDigest")
        if environment_digest != canonical_environment_artifact_digest(
            payload, environment
        ):
            raise ValueError(
                f"environment artifact digest is incomplete: {environment}"
            )
        projected_artifacts[environment] = {
            **projection,
            "environmentArtifactDigest": environment_digest,
        }

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
        "releaseTrainId": release_train_id,
        "source": {
            "gitSha": source.get("gitSha"),
            "treeDigest": source.get("treeDigest"),
            "repository": source.get("repository"),
        },
        "environmentArtifacts": projected_artifacts,
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
    sealed = dict(payload)
    sealed.pop("artifactDigest", None)
    release_train_id = canonical_release_train_digest(sealed)
    existing_release_train = payload.get("releaseTrainId")
    if existing_release_train not in {None, release_train_id}:
        raise ValueError("release train identity changed across lifecycle snapshots")
    sealed["releaseTrainId"] = release_train_id

    raw_artifacts = sealed.get("environmentArtifacts")
    if isinstance(raw_artifacts, dict):
        artifacts = {
            environment: dict(artifact)
            if isinstance(artifact, dict)
            else artifact
            for environment, artifact in raw_artifacts.items()
        }
        sealed["environmentArtifacts"] = artifacts
        for environment in ENVIRONMENTS:
            artifact = artifacts.get(environment)
            if not isinstance(artifact, dict):
                continue
            artifact = dict(artifact)
            try:
                environment_digest: str | None = canonical_environment_artifact_digest(
                    sealed, environment
                )
            except ValueError:
                environment_digest = None
            existing_digest = artifact.get("environmentArtifactDigest")
            immutable_images = isinstance(artifact.get("images"), dict) and all(
                isinstance(descriptor, dict) and "digest" in descriptor
                for descriptor in artifact["images"].values()
            )
            if (
                immutable_images
                and existing_digest not in {None, environment_digest}
                and payload.get("candidateId") is not None
            ):
                raise ValueError(
                    "environment artifact identity changed across lifecycle snapshots: "
                    f"{environment}"
                )
            artifact["environmentArtifactDigest"] = environment_digest
            artifacts[environment] = artifact

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
    immutable_images = sum(
        len(artifact["images"])
        for artifact in manifest["environmentArtifacts"].values()
    )
    lines = [
        "## Release Evidence Manifest",
        "",
        f"- `status`: `{manifest['status']}`",
        f"- `releaseTrainId`: `{manifest['releaseTrainId']}`",
        f"- `candidateId`: `{manifest['candidateId']}`",
        f"- `artifactDigest`: `{manifest['artifactDigest']}`",
        f"- `environmentArtifacts`: `{len(manifest['environmentArtifacts'])}`",
        f"- `immutableImages`: `{immutable_images}`",
        f"- `environmentReceipts`: `{len(manifest['environmentReceipts'])}`",
        f"- `blockers`: `{len(manifest['blockers'])}`",
        f"- `missingEvidence`: `{len(manifest['missingEvidence'])}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
