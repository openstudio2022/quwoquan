"""镜像/应用包描述符加载与文件级发布证据摘要复核（逐字搬移自入口）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quwoquan_ops.ci.render_release_application_package import validate_package
from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    APPLICATION_SOURCE_DESCRIPTOR_FIELDS,
    DIGEST_PATTERN,
    DISTRIBUTION_EVIDENCE_PATHS,
    ENVIRONMENTS,
    OCI_DIGEST_REF_PATTERN,
    OPS_PORTAL_SOURCE_DESCRIPTOR_FIELDS,
    OPTIONAL_RELEASE_EVIDENCE,
    RECEIPT_SOURCE_FIELDS,
    REQUIRED_RELEASE_EVIDENCE,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
    load_json,
    sha256_file,
    sha256_tree,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.manifest_validation import (
    _bound_file,
    _validate_relative_path,
    validate_manifest,
)


def load_image_descriptors(
    directory: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    descriptors: dict[str, dict[str, dict[str, Any]]] = {
        environment: {} for environment in ENVIRONMENTS
    }
    for path in sorted(directory.glob("*/*.json")):
        descriptor = load_json(path)
        environment = str(descriptor.get("environment") or "").strip()
        owner = str(descriptor.get("runtimeImageOwner") or "").strip()
        if environment not in ENVIRONMENTS or not owner:
            raise ValueError(f"{path} missing environment/runtimeImageOwner")
        if path.parent.name != environment:
            raise ValueError(f"{path} descriptor path environment mismatch")
        if owner in descriptors[environment]:
            raise ValueError(
                f"duplicate image descriptor for {environment}/{owner}"
            )
        descriptors[environment][owner] = descriptor
    return descriptors


def validate_descriptor(
    environment: str,
    owner: str,
    descriptor: dict[str, Any],
    *,
    expected_repository: str,
    expected_transport_ref: str,
) -> dict[str, Any]:
    label = f"{environment}/{owner}"
    if set(descriptor) != {
        "environment",
        "runtimeImageOwner",
        "repository",
        "transportRef",
        "digest",
        "ref",
        "attestations",
    }:
        raise ValueError(f"{label} image descriptor fields are not canonical")
    if (
        descriptor.get("environment") != environment
        or descriptor.get("runtimeImageOwner") != owner
    ):
        raise ValueError(f"{label} image descriptor identity mismatch")
    repository = str(descriptor.get("repository") or "").strip()
    transport_ref = str(descriptor.get("transportRef") or "").strip()
    digest = str(descriptor.get("digest") or "").strip()
    if repository != expected_repository:
        raise ValueError(
            f"{label} repository mismatch: {repository!r} != {expected_repository!r}"
        )
    if transport_ref != expected_transport_ref:
        raise ValueError(f"{label} transport ref mismatch")
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{label} missing immutable OCI digest")
    expected_ref = f"{repository}@{digest}"
    if str(descriptor.get("ref") or "") != expected_ref:
        raise ValueError(f"{label} digest ref mismatch")
    attestations = descriptor.get("attestations")
    if not isinstance(attestations, dict):
        raise ValueError(f"{label} missing attestations")
    for attestation_type in ("spdxSbom", "slsaProvenance"):
        value = str(attestations.get(attestation_type) or "").strip()
        if value != f"oci://{expected_ref}#{attestation_type}":
            raise ValueError(f"{label} missing {attestation_type} attestation reference")
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
    application_packages: dict[str, dict[str, str]] = {}
    ops_portal: dict[str, str] | None = None
    for descriptor_path in sorted(descriptors_dir.glob("*.json")):
        descriptor = load_json(descriptor_path)
        if set(descriptor) == APPLICATION_SOURCE_DESCRIPTOR_FIELDS:
            build_product_id = str(descriptor.get("buildProductId") or "")
            if build_product_id not in APPLICATION_PACKAGES:
                raise ValueError(
                    f"unsupported App build product descriptor: {build_product_id}"
                )
            if build_product_id in application_packages:
                raise ValueError(
                    f"duplicate App build product descriptor: {build_product_id}"
                )
            relative = _validate_relative_path(
                descriptor["path"], f"application package {build_product_id}"
            )
            artifact_path = _bound_file(
                artifact_dir, relative, f"application package {build_product_id}"
            )
            actual_digest = sha256_file(artifact_path)
            if descriptor["digest"] != actual_digest:
                raise ValueError(
                    f"application package {build_product_id} digest mismatch"
                )
            application_packages[build_product_id] = {
                "path": relative,
                "digest": actual_digest,
                "packageDigest": descriptor["packageDigest"],
                "sourceRef": descriptor["sourceRef"],
            }
            continue
        key = str(descriptor.get("evidenceKey") or "").strip()
        if key == "opsPortal":
            if set(descriptor) != OPS_PORTAL_SOURCE_DESCRIPTOR_FIELDS:
                raise ValueError("opsPortal evidence descriptor is not canonical")
            if ops_portal is not None:
                raise ValueError("duplicate opsPortal evidence descriptor")
            relative = _validate_relative_path(descriptor["path"], "opsPortal evidence")
            artifact_path = _bound_file(artifact_dir, relative, "opsPortal evidence")
            actual_digest = sha256_file(artifact_path)
            if descriptor["digest"] != actual_digest:
                raise ValueError("opsPortal evidence digest mismatch")
            ops_portal = {
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
        relative = _validate_relative_path(
            descriptor.get("path"), f"release evidence {key or '<missing>'}"
        )
        declared_digest = str(descriptor.get("digest") or "").strip()
        if key not in (*REQUIRED_RELEASE_EVIDENCE, *OPTIONAL_RELEASE_EVIDENCE):
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
    missing = sorted(set(REQUIRED_RELEASE_EVIDENCE) - set(evidence))
    extra = sorted(
        set(evidence)
        - set(REQUIRED_RELEASE_EVIDENCE)
        - set(OPTIONAL_RELEASE_EVIDENCE)
    )
    if missing or extra:
        raise ValueError(
            f"release evidence descriptor set mismatch: missing={missing}, extra={extra}"
        )
    if set(application_packages) != set(APPLICATION_PACKAGES):
        missing = sorted(set(APPLICATION_PACKAGES) - set(application_packages))
        extra = sorted(set(application_packages) - set(APPLICATION_PACKAGES))
        raise ValueError(
            f"App build product descriptor set mismatch: missing={missing}, extra={extra}"
        )
    if ops_portal is None:
        raise ValueError("opsPortal evidence descriptor is missing")
    evidence["applicationPackages"] = application_packages
    evidence["opsPortal"] = ops_portal
    return evidence


def _verify_configuration_packages(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    for environment, artifact in manifest["environmentArtifacts"].items():
        packages = artifact["configurationPackages"]
        for service, descriptor in packages.items():
            relative = _validate_relative_path(
                descriptor.get("path"),
                f"environmentArtifacts.{environment}.configurationPackages.{service}",
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

    evidence = descriptor.get("evidence")
    if evidence is None and isinstance(descriptor.get("path"), str):
        relative = _validate_relative_path(descriptor["path"], label)
        payload = load_json(_bound_file(artifact_dir, relative, label))
        evidence = payload.get("evidence")
    visit(evidence, f"{label}.evidence")
    if found == 0:
        raise ValueError(f"{label} has no replayable raw evidence file binding")


def validate_application_package_evidence(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    build_product_id: str,
) -> str:
    source = manifest["source"]
    validate_package(
        payload,
        build_product_id=build_product_id,
        source_git_sha=str(source["gitSha"]),
        source_tree_digest=str(source["treeDigest"]),
    )
    return application_package_digest(payload)


def validate_application_package_payload(
    payload: dict[str, Any],
    *,
    payload_root: Path,
    manifest: dict[str, Any],
    build_product_id: str,
) -> None:
    declared_digest = validate_application_package_evidence(
        payload,
        manifest=manifest,
        build_product_id=build_product_id,
    )
    if sha256_tree(payload_root) != declared_digest:
        raise ValueError(
            f"application package payload digest mismatch: {build_product_id}"
        )


def application_package_digest(payload: dict[str, Any]) -> str:
    digest = str(payload.get("packageDigest") or "")
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError("application package digest is not immutable")
    return digest


def validate_manifest_files(artifact_dir: Path, manifest: dict[str, Any]) -> None:
    """Verify every file bound by a canonical manifest against its content digest."""

    validate_manifest(manifest)
    _verify_configuration_packages(artifact_dir, manifest)
    if manifest["status"] in {"build-input", "component-ready"}:
        return
    for build_product_id, descriptor in manifest["applicationPackages"].items():
        relative = _validate_relative_path(
            descriptor.get("path"),
            f"applicationPackages.{build_product_id}",
        )
        path = _bound_file(
            artifact_dir,
            relative,
            f"application package {build_product_id}",
        )
        if sha256_file(path) != descriptor.get("digest"):
            raise ValueError(
                f"application package digest mismatch for {build_product_id}"
            )
        package_digest = validate_application_package_evidence(
            load_json(path),
            manifest=manifest,
            build_product_id=build_product_id,
        )
        if package_digest != descriptor.get("packageDigest"):
            raise ValueError(
                f"application package content binding mismatch for {build_product_id}"
            )
    for evidence_key, canonical_path in DISTRIBUTION_EVIDENCE_PATHS.items():
        descriptor = manifest[evidence_key]
        path = _bound_file(artifact_dir, canonical_path, evidence_key)
        if descriptor.get("path") != canonical_path:
            raise ValueError(f"{evidence_key} path is not canonical")
        if sha256_file(path) != descriptor.get("digest"):
            raise ValueError(f"{evidence_key} digest mismatch")
    ops_portal = manifest["opsPortal"]
    relative = _validate_relative_path(ops_portal.get("path"), "opsPortal")
    path = _bound_file(artifact_dir, relative, "opsPortal")
    if sha256_file(path) != ops_portal.get("digest"):
        raise ValueError("opsPortal evidence digest mismatch")
    payload = load_json(path)
    if payload.get("packageDigest") != ops_portal.get("packageDigest"):
        raise ValueError("opsPortal package digest mismatch")
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
    _verify_receipt_evidence_files(
        artifact_dir,
        manifest["testEvidence"],
        "test evidence",
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
    readiness_count = expected_required_cell_count_from_readiness(
        provider_payload.get("readiness")
    )
    if (
        expected_count != readiness_count
        or provider_payload.get("evidenceCount") != readiness_count
    ):
        raise ValueError(
            "providerEvidence manifest count does not match its dynamically "
            "validated required cell set"
        )
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
