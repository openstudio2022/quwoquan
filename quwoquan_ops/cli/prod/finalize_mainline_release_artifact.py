#!/usr/bin/env python3
"""把构建与发布证据归一为唯一、无版本信封的 ReleaseEvidenceManifest。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "release-evidence-manifest"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PRE_PROD_ENVIRONMENTS = ENVIRONMENTS[:-1]
STATUSES = frozenset(
    {
        "build-input",
        "component-ready",
        "candidate-ready",
        "deployable",
        "released",
        "rolled-back",
        "rollback-failed",
    }
)
APPLICATION_PLATFORMS = ("android", "ios", "web", "macos")
APPLICATION_PACKAGES = {
    environment: (
        *APPLICATION_PLATFORMS,
        *(("opsPortal",) if environment == "prod" else ()),
    )
    for environment in ENVIRONMENTS
}
REQUIRED_RELEASE_EVIDENCE = ("contractGraph", "providerEvidence", "testEvidence")
TEST_LAYERS = ("local_contract", "api_integration", "user_acceptance")
ENVIRONMENT_RECEIPT_SCHEMA = "release-environment-receipt"
ROLLOUT_RECEIPT_SCHEMA = "release-rollout-receipt"
ROLLBACK_RECEIPT_SCHEMA = "release-rollback-receipt"
ROOT_FIELDS = frozenset(
    {
        "schema",
        "candidateId",
        "status",
        "generatedAt",
        "source",
        "artifactDigest",
        "images",
        "configurationPackages",
        "applicationPackages",
        "contractGraphDigest",
        "requiredEvidence",
        "testEvidence",
        "providerEvidence",
        "environmentReceipts",
        "rolloutReceipt",
        "rollbackReceipt",
        "blockers",
        "missingEvidence",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "artifactName",
        "contractVersion",
        "imageRepositories",
        "manifestDigest",
        "registryRevision",
        "releaseFileDigests",
        "releaseFiles",
        "requiredArtifacts",
        "requiredImages",
        "schemaVersion",
        "versions",
    }
)
RECEIPT_SOURCE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "status",
        "candidateId",
        "sourceGitSha",
        "sourceTreeDigest",
        "evidenceDigest",
        "evidence",
        "verifiedAt",
    }
)
RECEIPT_DESCRIPTOR_FIELDS = RECEIPT_SOURCE_FIELDS | {"path", "digest"}
APPLICATION_PACKAGE_SCHEMA = "release-application-package"
APPLICATION_PACKAGE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "surface",
        "sourceGitSha",
        "sourceTreeDigest",
        "packageDigest",
    }
)
APPLICATION_DESCRIPTOR_FIELDS = frozenset(
    {"path", "digest", "packageDigest", "sourceRef"}
)
OCI_DIGEST_REF_PATTERN = re.compile(
    r"oci://ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}"
)
PROD_APPLICATION_SOURCE_SCHEMAS = {
    "web": "qwq.public-web.release",
    "android": "qwq.android.official-release",
    "opsPortal": "qwq.ops_portal_package",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--image-descriptors-dir", type=Path)
    parser.add_argument("--artifact-descriptors-dir", type=Path)
    parser.add_argument("--environment-receipts-dir", type=Path)
    parser.add_argument("--rollout-receipt", type=Path)
    parser.add_argument("--rollback-receipt", type=Path)
    return parser.parse_args()


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


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{label} must be a non-empty string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def _validate_relative_path(value: Any, label: str) -> str:
    relative = str(value or "").strip()
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path is unsafe")
    return path.as_posix()


def _bound_file(artifact_dir: Path, relative: str, label: str) -> Path:
    root = artifact_dir.resolve()
    candidate = artifact_dir / relative
    resolved = candidate.resolve()
    if root not in resolved.parents or candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} is missing or escapes the release evidence root")
    return candidate


def _validate_required_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("requiredEvidence must be an object")
    expected_fields = {
        "images",
        "configurationPackages",
        "applicationPackages",
        "contractGraphDigest",
        "providerEvidence",
        "testEvidence",
        "environmentReceipts",
        "rolloutReceipt",
        "rollbackReceipt",
    }
    if set(value) != expected_fields:
        raise ValueError("requiredEvidence fields are not canonical")
    images = _require_string_list(value["images"], "requiredEvidence.images")
    configuration_packages = value["configurationPackages"]
    if not isinstance(configuration_packages, dict) or set(
        configuration_packages
    ) != set(ENVIRONMENTS):
        raise ValueError("requiredEvidence.configurationPackages is not four-environment")
    for environment in ENVIRONMENTS:
        services = _require_string_list(
            configuration_packages[environment],
            f"requiredEvidence.configurationPackages.{environment}",
        )
        if services != images:
            raise ValueError(
                f"requiredEvidence.configurationPackages.{environment} service set differs"
            )
    applications = value["applicationPackages"]
    if not isinstance(applications, dict) or set(applications) != set(ENVIRONMENTS):
        raise ValueError("requiredEvidence.applicationPackages is not four-environment")
    for environment in ENVIRONMENTS:
        surfaces = _require_string_list(
            applications[environment],
            f"requiredEvidence.applicationPackages.{environment}",
        )
        if tuple(surfaces) != APPLICATION_PACKAGES[environment]:
            raise ValueError(
                f"requiredEvidence.applicationPackages.{environment} is not canonical"
            )
    layers = _require_string_list(value["testEvidence"], "requiredEvidence.testEvidence")
    if tuple(layers) != TEST_LAYERS:
        raise ValueError("requiredEvidence.testEvidence is not canonical")
    environments = _require_string_list(
        value["environmentReceipts"], "requiredEvidence.environmentReceipts"
    )
    if tuple(environments) != ENVIRONMENTS:
        raise ValueError("requiredEvidence.environmentReceipts is not canonical")
    if any(
        value[field] is not True
        for field in (
            "contractGraphDigest",
            "providerEvidence",
            "rolloutReceipt",
            "rollbackReceipt",
        )
    ):
        raise ValueError("requiredEvidence omits a mandatory release fact")
    return value


def _validate_packages(
    value: Any,
    *,
    expected: Iterable[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} set is not canonical")
    for key, descriptor in value.items():
        if not isinstance(descriptor, dict) or set(descriptor) != {"path", "digest"}:
            raise ValueError(f"{label}.{key} descriptor is not canonical")
        _validate_relative_path(descriptor.get("path"), f"{label}.{key}")
        if DIGEST_PATTERN.fullmatch(str(descriptor.get("digest") or "")) is None:
            raise ValueError(f"{label}.{key} digest is not immutable")
    return value


def _validate_configuration_packages(
    value: Any,
    *,
    required: dict[str, list[str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != set(ENVIRONMENTS):
        raise ValueError("configurationPackages must contain four autonomous environments")
    for environment in ENVIRONMENTS:
        _validate_packages(
            value[environment],
            expected=required[environment],
            label=f"configurationPackages.{environment}",
        )
    return value


def _validate_application_packages(
    value: Any,
    *,
    environment: str,
) -> dict[str, dict[str, Any]]:
    expected = set(APPLICATION_PACKAGES[environment])
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"applicationPackages.{environment} set is not canonical")
    source_refs: set[str] = set()
    for surface, descriptor in value.items():
        label = f"applicationPackages.{environment}.{surface}"
        if not isinstance(descriptor, dict) or set(descriptor) != APPLICATION_DESCRIPTOR_FIELDS:
            raise ValueError(f"{label} descriptor is not canonical")
        _validate_relative_path(descriptor.get("path"), label)
        for digest_key in ("digest", "packageDigest"):
            if DIGEST_PATTERN.fullmatch(str(descriptor.get(digest_key) or "")) is None:
                raise ValueError(f"{label}.{digest_key} is not immutable")
        source_ref = str(descriptor.get("sourceRef") or "")
        if OCI_DIGEST_REF_PATTERN.fullmatch(source_ref) is None:
            raise ValueError(f"{label}.sourceRef is not an immutable OCI reference")
        source_refs.add(source_ref)
    if len(source_refs) != 1:
        raise ValueError(
            f"applicationPackages.{environment} must use one application evidence OCI"
        )
    return value


def _validate_images(
    value: Any,
    *,
    required: list[str],
    status: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError("images set is not canonical")
    transport_tags: set[str] = set()
    for service, image in value.items():
        if not isinstance(image, dict):
            raise ValueError(f"images.{service} must be an object")
        repository = str(image.get("repository") or "").strip()
        transport_ref = str(image.get("transportRef") or "").strip()
        if not repository.startswith("ghcr.io/") or not transport_ref.startswith(
            repository + ":"
        ):
            raise ValueError(f"images.{service} transport reference is invalid")
        if transport_ref.endswith(":latest"):
            raise ValueError(f"images.{service} transport reference must not use latest")
        transport_tags.add(transport_ref[len(repository) + 1 :])
        if status == "build-input":
            if set(image) != {"repository", "transportRef"}:
                raise ValueError(f"images.{service} build input is not canonical")
            continue
        if set(image) != {
            "repository",
            "transportRef",
            "digest",
            "ref",
            "attestations",
        }:
            raise ValueError(f"images.{service} immutable descriptor is not canonical")
        digest = str(image.get("digest") or "")
        ref = str(image.get("ref") or "")
        if DIGEST_PATTERN.fullmatch(digest) is None or ref != f"{repository}@{digest}":
            raise ValueError(f"images.{service} digest reference is invalid")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or set(attestations) != {
            "spdxSbom",
            "slsaProvenance",
        }:
            raise ValueError(f"images.{service} attestations are incomplete")
        for kind in ("spdxSbom", "slsaProvenance"):
            if attestations.get(kind) != f"oci://{ref}#{kind}":
                raise ValueError(f"images.{service} {kind} reference is invalid")
    if len(transport_tags) != 1:
        raise ValueError("images must use one common transport tag")
    return value


def _forbidden_field_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_FIELDS:
                paths.append(path)
            paths.extend(_forbidden_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_forbidden_field_paths(child, f"{prefix}[{index}]"))
    return paths


def _validate_candidate_evidence(manifest: dict[str, Any]) -> None:
    applications = manifest.get("applicationPackages")
    if not isinstance(applications, dict) or set(applications) != set(ENVIRONMENTS):
        raise ValueError("applicationPackages must contain four environments")
    for environment in ENVIRONMENTS:
        _validate_application_packages(
            applications[environment], environment=environment
        )
    application_evidence_refs = {
        descriptor["sourceRef"]
        for packages in applications.values()
        for descriptor in packages.values()
    }
    if len(application_evidence_refs) != 1:
        raise ValueError("applicationPackages must use one application evidence OCI")
    if DIGEST_PATTERN.fullmatch(str(manifest.get("contractGraphDigest") or "")) is None:
        raise ValueError("contractGraphDigest is missing")
    provider = manifest.get("providerEvidence")
    if (
        not isinstance(provider, dict)
        or set(provider)
        != {"path", "digest", "status", "evidenceCount"}
        or provider.get("status") != "passed"
        or DIGEST_PATTERN.fullmatch(str(provider.get("digest") or "")) is None
        or not isinstance(provider.get("evidenceCount"), int)
        or provider["evidenceCount"] <= 0
    ):
        raise ValueError("providerEvidence is not passed and immutable")
    _validate_relative_path(provider.get("path"), "providerEvidence")
    test = manifest.get("testEvidence")
    if (
        not isinstance(test, dict)
        or set(test) != {"path", "digest", "status", "layers"}
        or test.get("status") != "passed"
        or DIGEST_PATTERN.fullmatch(str(test.get("digest") or "")) is None
    ):
        raise ValueError("testEvidence is not passed and immutable")
    _validate_relative_path(test.get("path"), "testEvidence")
    layers = test.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(TEST_LAYERS):
        raise ValueError("testEvidence layers are not canonical")
    for layer in TEST_LAYERS:
        item = layers.get(layer)
        if (
            not isinstance(item, dict)
            or set(item) != {"status", "artifactDigest"}
            or item.get("status") != "passed"
            or DIGEST_PATTERN.fullmatch(str(item.get("artifactDigest") or "")) is None
        ):
            raise ValueError(f"testEvidence layer is not immutable: {layer}")


def _validate_receipt_descriptor(
    descriptor: Any,
    *,
    manifest: dict[str, Any],
    kind: str,
    expected_environment: str,
) -> dict[str, Any]:
    if not isinstance(descriptor, dict) or set(descriptor) != RECEIPT_DESCRIPTOR_FIELDS:
        raise ValueError(f"{kind} receipt descriptor is not canonical")
    expected_schema = {
        "environment": ENVIRONMENT_RECEIPT_SCHEMA,
        "rollout": ROLLOUT_RECEIPT_SCHEMA,
        "rollback": ROLLBACK_RECEIPT_SCHEMA,
    }[kind]
    if descriptor.get("schema") != expected_schema:
        raise ValueError(f"{kind} receipt schema mismatch")
    if descriptor.get("environment") != expected_environment:
        raise ValueError(f"{kind} receipt environment mismatch")
    if kind == "rollback":
        allowed_statuses = {
            "ready",
            "not_triggered",
            "rolled_back",
            "rollback_failed",
        }
    elif kind == "rollout":
        allowed_statuses = {"passed", "failed"}
    elif expected_environment == "prod":
        allowed_statuses = {"passed", "failed"}
    else:
        allowed_statuses = {"passed"}
    if descriptor.get("status") not in allowed_statuses:
        raise ValueError(f"{kind} receipt status is invalid")
    if descriptor.get("candidateId") != manifest.get("candidateId"):
        raise ValueError(f"{kind} receipt candidateId mismatch")
    source = manifest["source"]
    if descriptor.get("sourceGitSha") != source["gitSha"]:
        raise ValueError(f"{kind} receipt source git mismatch")
    if descriptor.get("sourceTreeDigest") != source["treeDigest"]:
        raise ValueError(f"{kind} receipt source tree mismatch")
    for field in ("digest", "evidenceDigest"):
        if DIGEST_PATTERN.fullmatch(str(descriptor.get(field) or "")) is None:
            raise ValueError(f"{kind} receipt {field} is not immutable")
    evidence = descriptor.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError(f"{kind} receipt evidence projection is missing")
    expected_evidence_digest = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(evidence)
    ).hexdigest()
    if descriptor.get("evidenceDigest") != expected_evidence_digest:
        raise ValueError(f"{kind} receipt evidence projection digest mismatch")
    _validate_relative_path(descriptor.get("path"), f"{kind} receipt")
    if not str(descriptor.get("verifiedAt") or "").strip():
        raise ValueError(f"{kind} receipt verifiedAt is missing")
    return descriptor


def _validate_receipts(manifest: dict[str, Any]) -> None:
    environment_receipts = manifest.get("environmentReceipts")
    if not isinstance(environment_receipts, dict) or not set(
        environment_receipts
    ).issubset(ENVIRONMENTS):
        raise ValueError("environmentReceipts set is not canonical")
    for environment, descriptor in environment_receipts.items():
        _validate_receipt_descriptor(
            descriptor,
            manifest=manifest,
            kind="environment",
            expected_environment=environment,
        )
    rollout = manifest.get("rolloutReceipt")
    if rollout is not None:
        _validate_receipt_descriptor(
            rollout,
            manifest=manifest,
            kind="rollout",
            expected_environment="prod",
        )
    rollback = manifest.get("rollbackReceipt")
    if rollback is not None:
        _validate_receipt_descriptor(
            rollback,
            manifest=manifest,
            kind="rollback",
            expected_environment="prod",
        )


def _derive_status(manifest: dict[str, Any]) -> str:
    images = manifest["images"]
    immutable_images = all("digest" in item for item in images.values())
    candidate_complete = manifest.get("candidateId") is not None
    if not immutable_images:
        return "build-input"
    if not candidate_complete:
        return "component-ready"

    environments = set(manifest["environmentReceipts"])
    rollback = manifest.get("rollbackReceipt")
    rollout = manifest.get("rolloutReceipt")
    rollback_status = rollback.get("status") if isinstance(rollback, dict) else None
    preprod_ready = set(PRE_PROD_ENVIRONMENTS).issubset(environments)
    rollback_outcomes = {"not_triggered", "rolled_back", "rollback_failed"}
    if "prod" in environments or rollout is not None or rollback_status in rollback_outcomes:
        prod = manifest["environmentReceipts"].get("prod")
        if environments == set(ENVIRONMENTS) and isinstance(
            prod, dict
        ) and isinstance(rollout, dict):
            terminal = {
                ("passed", "passed", "not_triggered"): "released",
                ("passed", "failed", "rolled_back"): "rolled-back",
                ("failed", "failed", "rollback_failed"): "rollback-failed",
            }.get((prod.get("status"), rollout.get("status"), rollback_status))
            if terminal is not None:
                return terminal
        raise ValueError("production receipts are incomplete or out of lifecycle order")
    if preprod_ready and rollback_status == "ready":
        return "deployable"
    return "candidate-ready"


def _expected_gaps(manifest: dict[str, Any], status: str) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    if status == "build-input":
        missing.extend(
            f"images.{service}.digest"
            for service in manifest["requiredEvidence"]["images"]
            if "digest" not in manifest["images"][service]
        )
    if status in {"build-input", "component-ready"}:
        missing.extend(
            f"applicationPackages.{environment}.{surface}"
            for environment in ENVIRONMENTS
            for surface in APPLICATION_PACKAGES[environment]
        )
        missing.extend(("contractGraphDigest", "providerEvidence", "testEvidence"))
    present_environments = set(manifest.get("environmentReceipts") or {})
    missing.extend(
        f"environmentReceipts.{environment}"
        for environment in ENVIRONMENTS
        if environment not in present_environments
    )
    rollback = manifest.get("rollbackReceipt")
    rollback_status = rollback.get("status") if isinstance(rollback, dict) else None
    if rollback_status not in {
        "ready",
        "not_triggered",
        "rolled_back",
        "rollback_failed",
    }:
        missing.append("rollbackReceipt.ready")
    if manifest.get("rolloutReceipt") is None:
        missing.append("rolloutReceipt")
    if rollback_status not in {"not_triggered", "rolled_back", "rollback_failed"}:
        missing.append("rollbackReceipt.outcome")

    if status == "released":
        blockers: list[str] = []
    elif status == "rolled-back":
        blockers = ["candidate-rolled-back"]
    elif status == "rollback-failed":
        blockers = ["rollback-recovery-failed"]
    elif status == "deployable":
        blockers = ["prod-release-evidence-pending"]
    elif status == "candidate-ready":
        blockers = ["environment-qualification-evidence-pending"]
    elif status == "component-ready":
        blockers = ["whole-application-evidence-pending"]
    else:
        blockers = [
            "immutable-image-evidence-pending",
            "whole-application-evidence-pending",
        ]
    return blockers, missing


def validate_manifest(
    manifest: dict[str, Any],
    *,
    allowed_statuses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate the online canonical contract and reject every legacy envelope."""

    legacy = sorted(_forbidden_field_paths(manifest))
    if legacy:
        raise ValueError(f"legacy release evidence fields are forbidden: {legacy}")
    if set(manifest) != ROOT_FIELDS:
        missing = sorted(ROOT_FIELDS - set(manifest))
        extra = sorted(set(manifest) - ROOT_FIELDS)
        raise ValueError(
            f"release evidence manifest fields mismatch: missing={missing}, extra={extra}"
        )
    if manifest.get("schema") != SCHEMA:
        raise ValueError("release evidence manifest schema mismatch")
    status = str(manifest.get("status") or "")
    accepted = set(allowed_statuses or STATUSES)
    if status not in STATUSES or status not in accepted:
        raise ValueError(f"release evidence manifest status is invalid: {status!r}")

    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "gitSha",
        "treeDigest",
        "repository",
        "workflowRunId",
        "sourceArchiveDigest",
    }:
        raise ValueError("release evidence source is not canonical")
    if GIT_SHA_PATTERN.fullmatch(str(source.get("gitSha") or "")) is None:
        raise ValueError("release evidence source gitSha is invalid")
    if TREE_DIGEST_PATTERN.fullmatch(str(source.get("treeDigest") or "")) is None:
        raise ValueError("release evidence source treeDigest is invalid")
    if not str(source.get("repository") or "").strip() or not str(
        source.get("workflowRunId") or ""
    ).strip():
        raise ValueError("release evidence source repository or workflowRunId is missing")
    archive_digest = source.get("sourceArchiveDigest")
    if archive_digest is not None and DIGEST_PATTERN.fullmatch(
        str(archive_digest)
    ) is None:
        raise ValueError("release evidence sourceArchiveDigest is invalid")
    if not str(manifest.get("generatedAt") or "").strip():
        raise ValueError("release evidence generatedAt is missing")

    required = _validate_required_evidence(manifest.get("requiredEvidence"))
    images = _validate_images(
        manifest.get("images"),
        required=required["images"],
        status=status,
    )
    configurations = _validate_configuration_packages(
        manifest.get("configurationPackages"),
        required=required["configurationPackages"],
    )
    for environment in ENVIRONMENTS:
        if set(images) != set(configurations[environment]):
            raise ValueError(
                f"image and {environment} configuration package service sets differ"
            )

    if status in {"build-input", "component-ready"}:
        if manifest.get("applicationPackages") != {
            environment: {} for environment in ENVIRONMENTS
        }:
            raise ValueError("applicationPackages must remain empty before candidate-ready")
        if manifest.get("contractGraphDigest") is not None:
            raise ValueError("contractGraphDigest must remain empty before candidate-ready")
        if manifest.get("providerEvidence") != {} or manifest.get("testEvidence") != {}:
            raise ValueError("provider/test evidence must remain empty before candidate-ready")
    else:
        _validate_candidate_evidence(manifest)

    _validate_receipts(manifest)
    if status in {"build-input", "component-ready"} and (
        manifest["environmentReceipts"]
        or manifest["rolloutReceipt"] is not None
        or manifest["rollbackReceipt"] is not None
    ):
        raise ValueError("release receipts cannot precede candidate identity")

    derived_status = _derive_status(manifest)
    if status != derived_status:
        raise ValueError(
            f"release evidence lifecycle status mismatch: {status!r} != {derived_status!r}"
        )
    blockers = manifest.get("blockers")
    missing_evidence = manifest.get("missingEvidence")
    if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
        raise ValueError("blockers must be a string list")
    if not isinstance(missing_evidence, list) or not all(
        isinstance(item, str) for item in missing_evidence
    ):
        raise ValueError("missingEvidence must be a string list")
    expected_blockers, expected_missing = _expected_gaps(manifest, status)
    if blockers != expected_blockers or missing_evidence != expected_missing:
        raise ValueError("release evidence blockers or missingEvidence do not match lifecycle")

    expected_candidate: str | None
    try:
        expected_candidate = canonical_candidate_digest(manifest)
    except ValueError:
        expected_candidate = None
    if manifest.get("candidateId") != expected_candidate:
        raise ValueError("release evidence candidate digest mismatch")
    digest = canonical_manifest_digest(manifest)
    if manifest.get("artifactDigest") != digest:
        raise ValueError("release evidence manifest digest mismatch")
    return manifest


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
    expected_transport_ref: str,
) -> dict[str, Any]:
    if set(descriptor) != {
        "service",
        "repository",
        "transportRef",
        "digest",
        "ref",
        "attestations",
    }:
        raise ValueError(f"{service} image descriptor fields are not canonical")
    repository = str(descriptor.get("repository") or "").strip()
    transport_ref = str(descriptor.get("transportRef") or "").strip()
    digest = str(descriptor.get("digest") or "").strip()
    if repository != expected_repository:
        raise ValueError(
            f"{service} repository mismatch: {repository!r} != {expected_repository!r}"
        )
    if transport_ref != expected_transport_ref:
        raise ValueError(f"{service} transport ref mismatch")
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
        "transportRef": transport_ref,
        "digest": digest,
        "ref": expected_ref,
        "attestations": {
            "spdxSbom": str(attestations["spdxSbom"]),
            "slsaProvenance": str(attestations["slsaProvenance"]),
        },
    }


def load_release_evidence(
    artifact_dir: Path,
    descriptors_dir: Path,
) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    application_packages: dict[str, dict[str, dict[str, str]]] = {
        environment: {} for environment in ENVIRONMENTS
    }
    for descriptor_path in sorted(descriptors_dir.glob("*.json")):
        descriptor = load_json(descriptor_path)
        if set(descriptor) == {
            "applicationEnvironment",
            "applicationSurface",
            "path",
            "digest",
            "packageDigest",
            "sourceRef",
        }:
            environment = str(descriptor["applicationEnvironment"])
            surface = str(descriptor["applicationSurface"])
            if (
                environment not in ENVIRONMENTS
                or surface not in APPLICATION_PACKAGES[environment]
            ):
                raise ValueError(
                    f"unsupported application package descriptor: {environment}/{surface}"
                )
            if surface in application_packages[environment]:
                raise ValueError(
                    f"duplicate application package descriptor: {environment}/{surface}"
                )
            relative = _validate_relative_path(
                descriptor["path"],
                f"application package {environment}/{surface}",
            )
            artifact_path = _bound_file(
                artifact_dir,
                relative,
                f"application package {environment}/{surface}",
            )
            actual_digest = sha256_file(artifact_path)
            if descriptor["digest"] != actual_digest:
                raise ValueError(
                    f"application package {environment}/{surface} digest mismatch"
                )
            application_packages[environment][surface] = {
                "path": relative,
                "digest": actual_digest,
                "packageDigest": descriptor["packageDigest"],
                "sourceRef": descriptor["sourceRef"],
            }
            continue
        if set(descriptor) != {"evidenceKey", "path", "digest"}:
            raise ValueError(
                f"{descriptor_path} release evidence descriptor is not canonical"
            )
        key = str(descriptor.get("evidenceKey") or "").strip()
        relative = _validate_relative_path(
            descriptor.get("path"), f"release evidence {key or '<missing>'}"
        )
        declared_digest = str(descriptor.get("digest") or "").strip()
        if key not in REQUIRED_RELEASE_EVIDENCE:
            raise ValueError(f"unsupported release evidence key: {key!r}")
        if key in evidence:
            raise ValueError(f"duplicate release evidence descriptor: {key}")
        artifact_path = _bound_file(artifact_dir, relative, f"release evidence {key}")
        actual_digest = sha256_file(artifact_path)
        if declared_digest != actual_digest:
            raise ValueError(f"release evidence {key} digest mismatch")
        evidence[key] = {
            "path": relative,
            "digest": actual_digest,
            "payload": load_json(artifact_path),
        }
    if set(evidence) != set(REQUIRED_RELEASE_EVIDENCE):
        missing = sorted(set(REQUIRED_RELEASE_EVIDENCE) - set(evidence))
        extra = sorted(set(evidence) - set(REQUIRED_RELEASE_EVIDENCE))
        raise ValueError(
            f"release evidence descriptor set mismatch: missing={missing}, extra={extra}"
        )
    for environment in ENVIRONMENTS:
        if set(application_packages[environment]) != set(
            APPLICATION_PACKAGES[environment]
        ):
            raise ValueError(
                f"application package descriptor set mismatch: {environment}"
            )
    evidence["applicationPackages"] = application_packages
    return evidence


def _verify_configuration_packages(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    for environment, packages in manifest["configurationPackages"].items():
        for service, descriptor in packages.items():
            relative = _validate_relative_path(
                descriptor.get("path"),
                f"configurationPackages.{environment}.{service}",
            )
            path = _bound_file(
                artifact_dir,
                relative,
                f"{environment} release config for {service}",
            )
            if descriptor.get("digest") != sha256_file(path):
                raise ValueError(
                    f"{environment} release config digest mismatch for {service}"
                )


def _verify_receipt_file(
    artifact_dir: Path,
    descriptor: dict[str, Any],
    label: str,
) -> None:
    path = _bound_file(
        artifact_dir,
        _validate_relative_path(descriptor["path"], label),
        label,
    )
    if sha256_file(path) != descriptor["digest"]:
        raise ValueError(f"{label} digest mismatch")
    payload = load_json(path)
    if payload != {key: descriptor[key] for key in RECEIPT_SOURCE_FIELDS}:
        raise ValueError(f"{label} payload binding mismatch")


def _verify_receipt_evidence_files(
    artifact_dir: Path,
    descriptor: dict[str, Any],
    label: str,
) -> None:
    """Recompute every raw file binding embedded in a canonical receipt."""

    found = 0

    def visit(value: Any, breadcrumb: str) -> None:
        nonlocal found
        if isinstance(value, dict):
            if "path" in value or "digest" in value:
                if not {"path", "digest"}.issubset(value):
                    raise ValueError(f"{breadcrumb} raw evidence binding is incomplete")
                relative = _validate_relative_path(value["path"], breadcrumb)
                path = _bound_file(artifact_dir, relative, breadcrumb)
                if sha256_file(path) != value["digest"]:
                    raise ValueError(f"{breadcrumb} raw evidence digest mismatch")
                found += 1
            for key, child in value.items():
                visit(child, f"{breadcrumb}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{breadcrumb}[{index}]")

    visit(descriptor.get("evidence"), f"{label}.evidence")
    if found == 0:
        raise ValueError(f"{label} has no replayable raw evidence file binding")


def validate_application_package_evidence(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    environment: str,
    surface: str,
) -> str:
    expected_prod_schema = (
        PROD_APPLICATION_SOURCE_SCHEMAS.get(surface)
        if environment == "prod"
        else None
    )
    if expected_prod_schema is not None:
        if payload.get("schema") != expected_prod_schema:
            raise ValueError(
                f"application package schema mismatch for {environment}/{surface}"
            )
        source = manifest["source"]
        if (
            payload.get("sourceGitSha") != source["gitSha"]
            or payload.get("sourceTreeDigest") != source["treeDigest"]
        ):
            raise ValueError(
                f"application package source binding mismatch for {environment}/{surface}"
            )
    else:
        if set(payload) != APPLICATION_PACKAGE_FIELDS:
            raise ValueError(
                "application package evidence fields are not canonical: "
                f"{environment}/{surface}"
            )
        source = manifest["source"]
        if (
            payload.get("schema") != APPLICATION_PACKAGE_SCHEMA
            or payload.get("environment") != environment
            or payload.get("surface") != surface
            or payload.get("sourceGitSha") != source["gitSha"]
            or payload.get("sourceTreeDigest") != source["treeDigest"]
        ):
            raise ValueError(
                f"application package evidence binding mismatch: {environment}/{surface}"
            )
    return application_package_digest(
        payload,
        environment=environment,
        surface=surface,
    )


def validate_application_package_payload(
    payload: dict[str, Any],
    *,
    payload_root: Path,
    manifest: dict[str, Any],
    environment: str,
    surface: str,
) -> None:
    declared_digest = validate_application_package_evidence(
        payload,
        manifest=manifest,
        environment=environment,
        surface=surface,
    )
    if environment == "prod" and surface == "web":
        if sha256_tree(payload_root) != declared_digest:
            raise ValueError("prod web payload digest mismatch")
        return
    if environment == "prod" and surface == "android":
        packaged = _validate_relative_path(
            payload.get("packagedAPK"), "prod android packagedAPK"
        )
        apk = _bound_file(payload_root, packaged, "prod android APK")
        entries = sorted(payload_root.rglob("*"))
        if any(path.is_symlink() for path in entries):
            raise ValueError("prod android payload must not contain symlinks")
        files = [path for path in entries if path.is_file()]
        if files != [apk] or sha256_file(apk) != declared_digest:
            raise ValueError("prod android payload digest mismatch")
        return
    if environment == "prod" and surface == "opsPortal":
        manifest_path = _bound_file(
            payload_root, "manifest.json", "prod opsPortal manifest"
        )
        dist = payload_root / "dist"
        digests = payload.get("digests")
        if not isinstance(digests, dict):
            raise ValueError("prod opsPortal provenance digests are missing")
        if (
            sha256_file(manifest_path) != digests.get("manifest")
            or sha256_ops_portal_tree(dist) != digests.get("distTree")
            or declared_digest != digests.get("distTree")
        ):
            raise ValueError("prod opsPortal payload digest mismatch")
        return
    if sha256_tree(payload_root) != declared_digest:
        raise ValueError(
            f"application package payload digest mismatch: {environment}/{surface}"
        )


def application_package_digest(
    payload: dict[str, Any],
    *,
    environment: str,
    surface: str,
) -> str:
    if environment == "prod" and surface == "web":
        digest = "sha256:" + str(payload.get("contentSHA256") or "")
    elif environment == "prod" and surface == "android":
        digest = "sha256:" + str(payload.get("apkSHA256") or "")
    else:
        digest = str(payload.get("packageDigest") or "")
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError(
            f"application package digest is not immutable: {environment}/{surface}"
        )
    return digest


def validate_manifest_files(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    """Verify every file bound by a canonical manifest against its content digest."""

    validate_manifest(manifest)
    _verify_configuration_packages(artifact_dir, manifest)
    if manifest["status"] in {"build-input", "component-ready"}:
        return
    for environment, packages in manifest["applicationPackages"].items():
        for surface, descriptor in packages.items():
            relative = _validate_relative_path(
                descriptor.get("path"),
                f"applicationPackages.{environment}.{surface}",
            )
            path = _bound_file(
                artifact_dir,
                relative,
                f"application package {environment}/{surface}",
            )
            if sha256_file(path) != descriptor.get("digest"):
                raise ValueError(
                    f"application package digest mismatch for {environment}/{surface}"
                )
            package_digest = validate_application_package_evidence(
                load_json(path),
                manifest=manifest,
                environment=environment,
                surface=surface,
            )
            if package_digest != descriptor.get("packageDigest"):
                raise ValueError(
                    f"application package content binding mismatch for {environment}/{surface}"
                )
    contract_graph = artifact_dir / "evidence/contractGraph.json"
    if (
        contract_graph.is_symlink()
        or not contract_graph.is_file()
        or sha256_file(contract_graph) != manifest["contractGraphDigest"]
    ):
        raise ValueError("contract graph digest mismatch")
    evidence_payloads: dict[str, dict[str, Any]] = {}
    for key in ("providerEvidence", "testEvidence"):
        descriptor = manifest[key]
        relative = _validate_relative_path(descriptor.get("path"), key)
        path = _bound_file(artifact_dir, relative, key)
        if sha256_file(path) != descriptor.get("digest"):
            raise ValueError(f"{key} digest mismatch")
        evidence_payloads[key] = load_json(path)
    _verify_provider_raw_evidence(
        artifact_dir,
        evidence_payloads["providerEvidence"],
        expected_count=manifest["providerEvidence"]["evidenceCount"],
    )
    for environment, descriptor in manifest["environmentReceipts"].items():
        _verify_receipt_file(
            artifact_dir, descriptor, f"environment receipt {environment}"
        )
        _verify_receipt_evidence_files(
            artifact_dir, descriptor, f"environment receipt {environment}"
        )
    if manifest["rolloutReceipt"] is not None:
        _verify_receipt_file(artifact_dir, manifest["rolloutReceipt"], "rollout receipt")
        _verify_receipt_evidence_files(
            artifact_dir, manifest["rolloutReceipt"], "rollout receipt"
        )
    if manifest["rollbackReceipt"] is not None:
        _verify_receipt_file(
            artifact_dir, manifest["rollbackReceipt"], "rollback receipt"
        )
        _verify_receipt_evidence_files(
            artifact_dir, manifest["rollbackReceipt"], "rollback receipt"
        )


def _verify_provider_raw_evidence(
    artifact_dir: Path,
    provider_payload: dict[str, Any],
    *,
    expected_count: int,
) -> None:
    source = provider_payload.get("sourceEvidence")
    if not isinstance(source, dict) or set(source) != {"ref", "digest", "files"}:
        raise ValueError("providerEvidence sourceEvidence is not canonical")
    ref = str(source.get("ref") or "")
    digest = str(source.get("digest") or "")
    files = source.get("files")
    if (
        OCI_DIGEST_REF_PATTERN.fullmatch(ref) is None
        or DIGEST_PATTERN.fullmatch(digest) is None
        or ref != ref.rsplit("@", 1)[0] + "@" + digest
        or not isinstance(files, dict)
        or len(files) != expected_count
        or not files
    ):
        raise ValueError("providerEvidence sourceEvidence is not immutable")

    expected_paths: set[str] = set()
    prefix = "evidence/raw/provider/"
    for raw_path, raw_digest in files.items():
        if (
            not isinstance(raw_path, str)
            or not raw_path.startswith(prefix)
            or DIGEST_PATTERN.fullmatch(str(raw_digest or "")) is None
        ):
            raise ValueError("providerEvidence raw file descriptor is invalid")
        relative = _validate_relative_path(raw_path, "providerEvidence raw file")
        path = _bound_file(artifact_dir, relative, "providerEvidence raw file")
        if sha256_file(path) != raw_digest:
            raise ValueError(f"providerEvidence raw file digest mismatch: {raw_path}")
        expected_paths.add(relative)

    raw_root = artifact_dir / "evidence/raw/provider"
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise ValueError("providerEvidence raw evidence root is missing or unsafe")
    actual_paths: set[str] = set()
    for path in raw_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("providerEvidence raw evidence contains a symlink")
        if path.is_file():
            actual_paths.add(path.relative_to(artifact_dir).as_posix())
    if actual_paths != expected_paths:
        raise ValueError("providerEvidence raw evidence file set mismatch")


def _receipt_descriptor(
    *,
    artifact_dir: Path,
    source_path: Path,
    manifest: dict[str, Any],
    kind: str,
    expected_environment: str,
) -> dict[str, Any]:
    payload = load_json(source_path)
    if set(payload) != RECEIPT_SOURCE_FIELDS:
        raise ValueError(f"{kind} receipt source fields are not canonical")
    suffix = (
        expected_environment
        if kind == "environment"
        else str(payload.get("status") or "missing")
    )
    relative = Path("evidence/receipts") / kind / f"{suffix}.json"
    descriptor = {
        **payload,
        "path": relative.as_posix(),
        "digest": sha256_file(source_path),
    }
    _validate_receipt_descriptor(
        descriptor,
        manifest=manifest,
        kind=kind,
        expected_environment=expected_environment,
    )
    destination = artifact_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != source_path.read_bytes():
            raise ValueError(f"immutable {kind} receipt already differs: {suffix}")
    else:
        shutil.copyfile(source_path, destination)
    return descriptor


def _load_environment_receipts(
    *,
    artifact_dir: Path,
    receipts_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(receipts_dir.glob("*.json")):
        payload = load_json(path)
        environment = str(payload.get("environment") or "")
        if environment not in ENVIRONMENTS:
            raise ValueError(f"environment receipt has invalid environment: {environment!r}")
        if environment in result:
            raise ValueError(f"duplicate environment receipt: {environment}")
        result[environment] = _receipt_descriptor(
            artifact_dir=artifact_dir,
            source_path=path,
            manifest=manifest,
            kind="environment",
            expected_environment=environment,
        )
    if not result:
        raise ValueError("environment receipt directory contains no canonical receipts")
    return result


def _apply_candidate_evidence(
    manifest: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> None:
    manifest["applicationPackages"] = evidence["applicationPackages"]
    manifest["contractGraphDigest"] = evidence["contractGraph"]["digest"]
    provider = evidence["providerEvidence"]
    provider_payload = provider["payload"]
    manifest["providerEvidence"] = {
        "path": provider["path"],
        "digest": provider["digest"],
        "status": "passed",
        "evidenceCount": int(provider_payload.get("evidenceCount") or 0),
    }
    test = evidence["testEvidence"]
    manifest["testEvidence"] = {
        "path": test["path"],
        "digest": test["digest"],
        "status": "passed",
        "layers": {
            layer: {
                "status": test["payload"]["layers"][layer]["status"],
                "artifactDigest": test["payload"]["layers"][layer][
                    "artifactDigest"
                ],
            }
            for layer in TEST_LAYERS
        },
    }


def finalize(
    artifact_dir: Path,
    descriptors_dir: Path | None,
    artifact_descriptors_dir: Path | None = None,
    environment_receipts_dir: Path | None = None,
    rollout_receipt_path: Path | None = None,
    rollback_receipt_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = artifact_dir / "manifest.json"
    manifest = load_json(manifest_path)
    validate_manifest_files(artifact_dir, manifest)
    original_status = manifest["status"]

    operations = sum(
        value is not None
        for value in (
            descriptors_dir,
            artifact_descriptors_dir,
            environment_receipts_dir,
            rollout_receipt_path,
            rollback_receipt_path,
        )
    )
    if operations == 0:
        raise ValueError("one concrete evidence input is required")

    if descriptors_dir is not None:
        if original_status != "build-input" or operations != 1:
            raise ValueError("image evidence is only accepted from build-input")
        descriptors = load_image_descriptors(descriptors_dir)
        required = manifest["requiredEvidence"]["images"]
        if set(descriptors) != set(required):
            missing = sorted(set(required) - set(descriptors))
            extra = sorted(set(descriptors) - set(required))
            raise ValueError(
                f"image descriptor set mismatch: missing={missing}, extra={extra}"
            )
        manifest["images"] = {
            service: validate_descriptor(
                service,
                descriptors[service],
                expected_repository=str(manifest["images"][service]["repository"]),
                expected_transport_ref=str(manifest["images"][service]["transportRef"]),
            )
            for service in required
        }
    elif artifact_descriptors_dir is not None:
        if original_status != "component-ready" or operations != 1:
            raise ValueError("candidate material is only accepted from component-ready")
        _apply_candidate_evidence(
            manifest,
            load_release_evidence(artifact_dir, artifact_descriptors_dir),
        )
    else:
        if original_status not in {"candidate-ready", "deployable"}:
            raise ValueError("release receipts require a sealed candidate")
        if original_status == "deployable":
            if set(manifest["environmentReceipts"]) != set(PRE_PROD_ENVIRONMENTS):
                raise ValueError("deployable input is missing pre-prod receipts")
            if not isinstance(manifest["rollbackReceipt"], dict) or manifest[
                "rollbackReceipt"
            ].get("status") != "ready":
                raise ValueError("deployable input is missing rollback readiness")
        if environment_receipts_dir is not None:
            incoming_environments = {
                str(load_json(path).get("environment") or "")
                for path in sorted(environment_receipts_dir.glob("*.json"))
            }
            if "prod" in incoming_environments and original_status != "deployable":
                raise ValueError("prod receipt requires a previously deployable snapshot")
            incoming = _load_environment_receipts(
                artifact_dir=artifact_dir,
                receipts_dir=environment_receipts_dir,
                manifest=manifest,
            )
            for environment, descriptor in incoming.items():
                existing = manifest["environmentReceipts"].get(environment)
                if existing is not None and existing != descriptor:
                    raise ValueError(
                        f"immutable environment receipt already differs: {environment}"
                    )
                manifest["environmentReceipts"][environment] = descriptor
        if rollout_receipt_path is not None:
            if original_status != "deployable":
                raise ValueError("rollout receipt requires a previously deployable snapshot")
            manifest["rolloutReceipt"] = _receipt_descriptor(
                artifact_dir=artifact_dir,
                source_path=rollout_receipt_path,
                manifest=manifest,
                kind="rollout",
                expected_environment="prod",
            )
        if rollback_receipt_path is not None:
            rollback_payload = load_json(rollback_receipt_path)
            rollback_status = rollback_payload.get("status")
            if rollback_status in {
                "not_triggered",
                "rolled_back",
                "rollback_failed",
            } and original_status != "deployable":
                raise ValueError(
                    "completed rollback receipt requires a previously deployable snapshot"
                )
            if rollback_status == "ready" and original_status != "candidate-ready":
                raise ValueError("rollback readiness requires a candidate-ready snapshot")
            manifest["rollbackReceipt"] = _receipt_descriptor(
                artifact_dir=artifact_dir,
                source_path=rollback_receipt_path,
                manifest=manifest,
                kind="rollback",
                expected_environment="prod",
            )

    manifest["generatedAt"] = utc_now()
    manifest = seal_manifest(manifest)
    status = _derive_status(manifest)
    manifest["status"] = status
    manifest["blockers"], manifest["missingEvidence"] = _expected_gaps(
        manifest, status
    )
    manifest = seal_manifest(manifest)
    validate_manifest_files(artifact_dir, manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.md", manifest)
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
            (
                args.environment_receipts_dir.resolve()
                if args.environment_receipts_dir is not None
                else None
            ),
            args.rollout_receipt.resolve() if args.rollout_receipt is not None else None,
            (
                args.rollback_receipt.resolve()
                if args.rollback_receipt is not None
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        f"OK: {manifest['status']} release evidence "
        f"{manifest['artifactDigest']} includes {len(manifest['images'])} immutable images"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
