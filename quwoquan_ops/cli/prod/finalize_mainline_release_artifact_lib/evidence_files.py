"""镜像/应用包描述符加载与文件级发布证据摘要复核（逐字搬移自入口）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGE_FIELDS,
    APPLICATION_PACKAGE_SCHEMA,
    APPLICATION_PACKAGES,
    DIGEST_PATTERN,
    ENVIRONMENTS,
    OCI_DIGEST_REF_PATTERN,
    PROD_APPLICATION_SOURCE_SCHEMAS,
    RECEIPT_SOURCE_FIELDS,
    REQUIRED_RELEASE_EVIDENCE,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
    load_json,
    sha256_file,
    sha256_ops_portal_tree,
    sha256_tree,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.manifest_validation import (
    _bound_file,
    _validate_relative_path,
    validate_manifest,
)


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
