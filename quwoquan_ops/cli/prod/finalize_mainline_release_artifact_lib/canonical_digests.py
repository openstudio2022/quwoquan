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
    DISTRIBUTION_EVIDENCE_PATHS,
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
    # 身份摘要只吃组件内容 digest。repository/transportRef/ref/attestations 属于
    # OCI 运输与 provenance 通道，保留在 manifest 里但不得进入组合身份（DEC-006），
    # 否则同一 bytes 换仓库或换 tag 会伪造出新候选。
    projected_images: dict[str, Any] = {}
    for owner, descriptor in sorted(images.items()):
        if (
            not isinstance(descriptor, dict)
            or DIGEST_PATTERN.fullmatch(str(descriptor.get("digest") or "")) is None
        ):
            raise ValueError(
                f"environment image material is not immutable: {environment}/{owner}"
            )
        projected_images[owner] = {"digest": descriptor["digest"]}
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
    """Project deployable software/config only; qualification is separate."""

    source = payload.get("source")
    artifacts = payload.get("environmentArtifacts")
    applications = payload.get("applicationPackages")
    portal = payload.get("opsPortal")
    contract_graph = payload.get("contractGraphDigest")
    release_train_id = payload.get("releaseTrainId")
    if not isinstance(source, dict) or not isinstance(artifacts, dict):
        raise ValueError("release composition source or environment artifacts are incomplete")
    if set(artifacts) != set(ENVIRONMENTS):
        raise ValueError("release composition environment artifact material is incomplete")
    if not isinstance(applications, dict) or set(applications) != set(APPLICATION_PACKAGES):
        raise ValueError("release composition App build product material is incomplete")
    if not isinstance(portal, dict) or DIGEST_PATTERN.fullmatch(str(portal.get("packageDigest") or "")) is None:
        raise ValueError("release composition Ops Portal material is incomplete")
    if DIGEST_PATTERN.fullmatch(str(contract_graph or "")) is None:
        raise ValueError("release composition contract graph material is incomplete")
    if DIGEST_PATTERN.fullmatch(str(release_train_id or "")) is None:
        raise ValueError("release composition train identity is incomplete")

    projected_artifacts: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        projection = _environment_artifact_projection(payload, environment)
        artifact = artifacts[environment]
        environment_digest = artifact.get("environmentArtifactDigest")
        if environment_digest != canonical_environment_artifact_digest(payload, environment):
            raise ValueError(f"environment artifact digest is incomplete: {environment}")
        projected_artifacts[environment] = {**projection, "environmentArtifactDigest": environment_digest}

    projected_applications = {
        product: {"digest": descriptor.get("digest"), "packageDigest": descriptor.get("packageDigest")}
        for product, descriptor in sorted(applications.items()) if isinstance(descriptor, dict)
    }
    if len(projected_applications) != len(APPLICATION_PACKAGES):
        raise ValueError("release composition App material is invalid")
    for product, descriptor in projected_applications.items():
        if any(DIGEST_PATTERN.fullmatch(str(descriptor.get(field) or "")) is None for field in ("digest", "packageDigest")):
            raise ValueError(f"release composition App material is not immutable: {product}")
    return {
        "schema": SCHEMA, "releaseTrainId": release_train_id,
        "source": {"gitSha": source.get("gitSha"), "treeDigest": source.get("treeDigest"), "repository": source.get("repository")},
        "environmentArtifacts": projected_artifacts, "applicationPackages": projected_applications,
        "opsPortal": {"packageDigest": portal.get("packageDigest")},
        "contractGraphDigest": contract_graph,
    }


def _evidence_projection(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload.get("providerEvidence")
    tests = payload.get("testEvidence")
    distributions = {key: payload.get(key) for key in DISTRIBUTION_EVIDENCE_PATHS}
    if not isinstance(provider, dict) or not isinstance(tests, dict):
        raise ValueError("qualification evidence is incomplete")
    if any(not isinstance(value, dict) or DIGEST_PATTERN.fullmatch(str(value.get("digest") or "")) is None for value in distributions.values()):
        raise ValueError("distribution qualification evidence is incomplete")
    if DIGEST_PATTERN.fullmatch(str(provider.get("digest") or "")) is None or DIGEST_PATTERN.fullmatch(str(tests.get("digest") or "")) is None:
        raise ValueError("Provider/test qualification evidence is incomplete")
    return {
        "schema": SCHEMA, "releaseCompositionId": payload.get("releaseCompositionId"),
        "distributionEvidence": {key: {"digest": value["digest"]} for key, value in sorted(distributions.items())},
        "providerEvidence": {"digest": provider.get("digest"), "status": provider.get("status")},
        "testEvidence": {"digest": tests.get("digest"), "status": tests.get("status"), "layers": tests.get("layers")},
    }


def canonical_release_composition_id(payload: dict[str, Any]) -> str:
    projection = _candidate_projection(payload)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(projection)).hexdigest()


def canonical_evidence_set_digest(payload: dict[str, Any]) -> str:
    projection = _evidence_projection(payload)
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
                and payload.get("releaseCompositionId") is not None
            ):
                raise ValueError(
                    "environment artifact identity changed across lifecycle snapshots: "
                    f"{environment}"
                )
            artifact["environmentArtifactDigest"] = environment_digest
            artifacts[environment] = artifact

    try:
        composition_id: str | None = canonical_release_composition_id(sealed)
    except ValueError:
        composition_id = None
    existing_composition = payload.get("releaseCompositionId")
    if existing_composition not in {None, composition_id}:
        raise ValueError("release composition identity changed across lifecycle snapshots")
    sealed["releaseCompositionId"] = composition_id
    try:
        evidence_set_digest: str | None = canonical_evidence_set_digest(sealed)
    except ValueError:
        evidence_set_digest = None
    sealed["evidenceSetDigest"] = evidence_set_digest
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
        f"- `releaseCompositionId`: `{manifest['releaseCompositionId']}`",
        f"- `evidenceSetDigest`: `{manifest['evidenceSetDigest']}`",
        f"- `artifactDigest`: `{manifest['artifactDigest']}`",
        f"- `environmentArtifacts`: `{len(manifest['environmentArtifacts'])}`",
        f"- `immutableImages`: `{immutable_images}`",
        f"- `environmentReceipts`: `{len(manifest['environmentReceipts'])}`",
        f"- `blockers`: `{len(manifest['blockers'])}`",
        f"- `missingEvidence`: `{len(manifest['missingEvidence'])}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
