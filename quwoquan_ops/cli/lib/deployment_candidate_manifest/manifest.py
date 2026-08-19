"""deployment candidate manifest 的写入、加载与全量校验（逐字迁自原单文件）。

``validate_packaged_graphql_read_registry``、``deployment_candidate_dir`` 与三个
deployment package 目录解析函数经包属性（``_pkg.``）消费，保持测试对包属性
monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg
from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest

from .candidate_fs import (
    _UnsafeCandidatePath,
    _read_candidate_bytes,
    _read_candidate_object,
    _sha256_candidate_file,
    _sha256_json,
)
from .candidate_staging import (
    _atomic_write_candidate_file,
    _validate_candidate_payload_tree,
)
from .constants import (
    _DIGEST,
    _RELEASE_BINDING_FIELDS,
    CANDIDATE_MANIFEST_SCHEMA,
    CANDIDATE_VALIDATION_PURPOSES,
    ROOT,
    RUNTIME_CANDIDATE_TYPE,
    SPEC_REFS,
)
from .environment_artifact import (
    build_environment_artifact,
    validate_environment_artifact,
)
from .log_sink_package import (
    load_observability_log_sink_package,
    validate_observability_log_sink_package,
)
from .provider_runtime_package import (
    _validate_candidate_provider_oci_binding,
    load_provider_runtime_package,
    validate_packaged_provider_runtime,
)
from .release_binding import (
    _release_binding,
    canonical_contract_graph_digest,
    release_input_classification,
    validate_release_attestations,
)


def _prod_hosted_release_package_identity(
    candidate_root: Path,
    *,
    expected_services: list[str] | tuple[str, ...] | set[str],
    expected_source_revision: str,
) -> dict[str, Any]:
    """Reconstruct hosted release identity from candidate-owned service packages."""

    services = sorted(str(service or "").strip() for service in expected_services)
    if (
        not services
        or len(services) != len(set(services))
        or any(re.fullmatch(r"[a-z][a-z0-9-]*", service) is None for service in services)
    ):
        raise ValueError("deployment candidate hosted service closure is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", expected_source_revision) is None:
        raise ValueError("deployment candidate hosted source revision is invalid")

    release_identity: dict[str, str] | None = None
    configuration_versions: dict[str, str] = {}
    for service in services:
        provenance_ref = f"packages/services/{service}/provenance.json"
        try:
            provenance = _read_candidate_object(
                candidate_root,
                provenance_ref,
                label=f"hosted service package provenance: {service}",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                f"deployment candidate hosted service package is unsafe: {service}"
            ) from exc
        digests = provenance.get("digests")
        release_evidence = provenance.get("releaseEvidence")
        if (
            provenance.get("schema") != "qwq.service_package"
            or provenance.get("service") != service
            or provenance.get("environment") != "prod"
            or provenance.get("gitRevision") != expected_source_revision
            or not isinstance(digests, dict)
            or not isinstance(release_evidence, dict)
            or set(release_evidence)
            != {
                "manifest",
                "evidenceFileDigest",
                "artifactDigest",
                "candidateId",
                "verifiedConfigDigest",
            }
        ):
            raise ValueError(
                f"deployment candidate hosted release evidence fields mismatch: {service}"
            )
        config_version = str(provenance.get("configVersion") or "")
        packaged_config_digest = str(digests.get("config") or "")
        verified_config_digest = str(
            release_evidence.get("verifiedConfigDigest") or ""
        )
        actual_config_digest = _sha256_candidate_file(
            candidate_root,
            f"packages/services/{service}/config/config.yaml",
            label=f"hosted service runtime configuration: {service}",
        )
        if (
            _DIGEST.fullmatch(config_version) is None
            or packaged_config_digest != actual_config_digest
            or verified_config_digest != actual_config_digest
        ):
            raise ValueError(
                f"deployment candidate hosted configuration identity drifted: {service}"
            )
        current_release_identity = {
            "manifestDigest": str(release_evidence.get("evidenceFileDigest") or ""),
            "artifactDigest": str(release_evidence.get("artifactDigest") or ""),
            "candidateId": str(release_evidence.get("candidateId") or ""),
            "sourceRevision": expected_source_revision,
        }
        if (
            not str(release_evidence.get("manifest") or "").strip()
            or any(
                _DIGEST.fullmatch(current_release_identity[field]) is None
                for field in ("manifestDigest", "artifactDigest", "candidateId")
            )
        ):
            raise ValueError(
                f"deployment candidate hosted release evidence is invalid: {service}"
            )
        if release_identity is None:
            release_identity = current_release_identity
        elif current_release_identity != release_identity:
            raise ValueError("deployment candidate hosted release evidence drifted")
        configuration_versions[service] = config_version

    if release_identity is None:
        raise ValueError("deployment candidate hosted release evidence is missing")
    return {
        "hostedRelease": release_identity,
        "configurationDigest": _sha256_json(configuration_versions),
    }


def _materialize_prod_hosted_oci_manifest(
    env_name: str,
    target_name: str,
    *,
    provider_runtime: Mapping[str, Any],
    candidate_root: Path,
    package_snapshot: Mapping[str, object],
    materialized_release_evidence: Mapping[str, str],
    source_root: Path = ROOT,
) -> tuple[Path, dict[str, Any]]:
    """Project canonical Service Pipeline image descriptors into the candidate."""

    from quwoquan_ops.cli import stackctl as _stackctl

    if env_name != "prod" or target_name != "prod-hosted":
        raise ValueError("hosted OCI manifest supports only prod/prod-hosted")
    unsealed_composition = provider_runtime.get("composition")
    if (
        not isinstance(unsealed_composition, Mapping)
        or provider_runtime.get("images") != {}
    ):
        raise ValueError("prod-hosted Provider runtime package is not unsealed")
    artifact_root_value = os.environ.get(
        "QWQ_PROD_RELEASE_ARTIFACT_ROOT", ""
    ).strip()
    if not artifact_root_value:
        raise FileNotFoundError("prod-hosted release artifact root is required")
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = _stackctl.ROOT / artifact_root
    artifact_root = artifact_root.resolve()
    release_manifest_path = artifact_root / "manifest.json"
    if release_manifest_path.is_symlink() or not release_manifest_path.is_file():
        raise FileNotFoundError(
            "prod-hosted release artifact manifest is missing or unsafe: "
            f"{release_manifest_path}"
        )
    try:
        release_manifest = json.loads(
            release_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"prod-hosted release artifact manifest is unreadable: {exc}"
        ) from exc
    if not isinstance(release_manifest, dict):
        raise ValueError("prod-hosted release artifact manifest must be an object")
    _stackctl.finalize_mainline_release_artifact.validate_manifest(
        release_manifest,
        allowed_statuses={"deployable", "released"},
    )
    _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
        artifact_root,
        release_manifest,
    )

    source = release_manifest.get("source")
    source_revision = str(package_snapshot.get("sourceRevision") or "")
    release_source_revision = (
        str(source.get("gitSha") or "") if isinstance(source, Mapping) else ""
    )
    if release_source_revision != source_revision:
        raise ValueError(
            "prod-hosted release evidence source revision differs from package inputs"
        )
    release_identity = {
        "candidateId": str(release_manifest.get("candidateId") or ""),
        "artifactDigest": str(release_manifest.get("artifactDigest") or ""),
        "sourceGitSha": release_source_revision,
        "sourceTreeDigest": (
            str(source.get("treeDigest") or "") if isinstance(source, Mapping) else ""
        ),
    }
    if dict(materialized_release_evidence) != release_identity:
        raise ValueError("prod-hosted release evidence identity drifted during package")

    required_evidence = release_manifest.get("requiredEvidence")
    required_images = (
        required_evidence.get("images")
        if isinstance(required_evidence, Mapping)
        else None
    )
    release_images = release_manifest.get("images")
    canonical_services = tuple(_stackctl.first_party_service_names(source_root))
    if (
        not isinstance(required_images, list)
        or not isinstance(release_images, dict)
        or set(required_images) != set(canonical_services)
        or set(release_images) != set(canonical_services)
    ):
        raise ValueError("prod-hosted release image owner closure is invalid")
    images: dict[str, dict[str, str]] = {}
    first_party_refs: dict[str, str] = {}
    for service in sorted(canonical_services):
        descriptor = release_images.get(service)
        if not isinstance(descriptor, Mapping):
            raise ValueError(f"prod-hosted release image is invalid: {service}")
        ref = str(descriptor.get("ref") or "")
        digest = str(descriptor.get("digest") or "")
        if (
            re.fullmatch(
                r"ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}", ref
            )
            is None
            or ref.rpartition("@")[2] != digest
        ):
            raise ValueError(f"prod-hosted release image is invalid: {service}")
        first_party_refs[service] = ref
        images[service] = {"ref": ref, "imageDigest": digest}

    sealed_provider_runtime = _stackctl.seal_provider_runtime_package_images(
        env_name,
        target_name,
        candidate_root,
        {},
    )
    if sealed_provider_runtime.get("composition") != unsealed_composition:
        raise ValueError("prod-hosted Provider runtime composition drifted while sealing")
    hosted_identity = _prod_hosted_release_package_identity(
        candidate_root,
        expected_services=canonical_services,
        expected_source_revision=source_revision,
    )
    release_manifest_digest = (
        "sha256:" + hashlib.sha256(release_manifest_path.read_bytes()).hexdigest()
    )
    expected_hosted_release = hosted_identity["hostedRelease"]
    if expected_hosted_release != {
        "manifestDigest": release_manifest_digest,
        "artifactDigest": release_identity["artifactDigest"],
        "candidateId": release_identity["candidateId"],
        "sourceRevision": source_revision,
    }:
        raise ValueError("prod-hosted packaged release evidence identity drifted")
    build_input = {
        "firstPartyImageVersion": immutable_image_digest(first_party_refs),
        "providerRuntimeDigest": unsealed_composition.get(
            "runtimeCompositionDigest"
        ),
        "providerImageRefs": {},
        "hostedRelease": expected_hosted_release,
    }
    manifest = {
        "schema": _stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "configurationDigest": hosted_identity["configurationDigest"],
        "buildInputDigest": _sha256_json(build_input),
        "imageDigest": _sha256_json(images),
        "images": images,
    }
    manifest_path = (
        _stackctl.runtime_shared_deployment_package_dir(
            env_name,
            target=target_name,
        )
        / "oci-images.json"
    )
    _stackctl.write_json(manifest_path, manifest)
    return manifest_path, manifest


def _validate_prod_hosted_oci_binding(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Bind prod-hosted to Service Pipeline images, never local Docker output."""

    if candidate.get("target") != "prod-hosted":
        return
    oci = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/oci-images.json",
        label="package OCI image manifest",
    )
    images = oci.get("images")
    provider_runtime = candidate.get("providerRuntime")
    provider_images = (
        provider_runtime.get("images")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if (
        not isinstance(images, dict)
        or not images
        or not isinstance(provider_images, dict)
        or provider_images
        or not isinstance(composition, Mapping)
    ):
        raise ValueError(
            "deployment candidate prod-hosted image closure is invalid"
        )

    first_party_refs: dict[str, str] = {}
    for role, descriptor in sorted(images.items()):
        if not isinstance(descriptor, Mapping) or set(descriptor) != {
            "ref",
            "imageDigest",
        }:
            raise ValueError(
                f"deployment candidate hosted image is invalid: {role}"
            )
        ref = str(descriptor.get("ref") or "")
        digest = str(descriptor.get("imageDigest") or "")
        if (
            re.fullmatch(
                r"ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}",
                ref,
            )
            is None
            or ref.rpartition("@")[2] != digest
        ):
            raise ValueError(
                f"deployment candidate hosted image is invalid: {role}"
            )
        first_party_refs[str(role)] = ref

    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    service_packages = fingerprint.get("servicePackages")
    if (
        not isinstance(service_packages, list)
        or any(not isinstance(service, str) for service in service_packages)
        or set(service_packages) != set(first_party_refs)
    ):
        raise ValueError(
            "deployment candidate hosted image/service role closure mismatch"
        )
    hosted_identity = _prod_hosted_release_package_identity(
        candidate_root,
        expected_services=service_packages,
        expected_source_revision=str(candidate.get("sourceRevision") or ""),
    )
    if oci.get("configurationDigest") != hosted_identity["configurationDigest"]:
        raise ValueError("deployment candidate hosted configuration identity drifted")
    expected_build_input = _sha256_json(
        {
            "firstPartyImageVersion": immutable_image_digest(first_party_refs),
            "providerRuntimeDigest": composition.get("runtimeCompositionDigest"),
            "providerImageRefs": {},
            "hostedRelease": hosted_identity["hostedRelease"],
        }
    )
    if oci.get("buildInputDigest") != expected_build_input:
        raise ValueError(
            "deployment candidate hosted buildInputDigest closure mismatch"
        )


def _validate_prod_hosted_release_evidence_currentness(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Recheck the exact hosted release source when package selects/reuses a candidate."""

    if candidate.get("target") != "prod-hosted":
        return
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    service_packages = fingerprint.get("servicePackages")
    if not isinstance(service_packages, list) or any(
        not isinstance(service, str) for service in service_packages
    ):
        raise ValueError("prod-hosted package service closure is invalid")
    packaged_identity = _prod_hosted_release_package_identity(
        candidate_root,
        expected_services=service_packages,
        expected_source_revision=str(candidate.get("sourceRevision") or ""),
    )["hostedRelease"]

    from quwoquan_ops.cli import stackctl as _stackctl

    artifact_root_value = os.environ.get(
        "QWQ_PROD_RELEASE_ARTIFACT_ROOT", ""
    ).strip()
    if not artifact_root_value:
        raise FileNotFoundError("prod-hosted release artifact root is required")
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = _stackctl.ROOT / artifact_root
    artifact_root = artifact_root.resolve()
    release_manifest_path = artifact_root / "manifest.json"
    if release_manifest_path.is_symlink() or not release_manifest_path.is_file():
        raise FileNotFoundError(
            "prod-hosted release artifact manifest is missing or unsafe: "
            f"{release_manifest_path}"
        )
    try:
        release_manifest = json.loads(
            release_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"prod-hosted release artifact manifest is unreadable: {exc}"
        ) from exc
    if not isinstance(release_manifest, dict):
        raise ValueError("prod-hosted release artifact manifest must be an object")
    _stackctl.finalize_mainline_release_artifact.validate_manifest(
        release_manifest,
        allowed_statuses={"deployable", "released"},
    )
    _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
        artifact_root,
        release_manifest,
    )
    source = release_manifest.get("source")
    release_source_revision = (
        str(source.get("gitSha") or "") if isinstance(source, Mapping) else ""
    )
    current_identity = {
        "manifestDigest": "sha256:"
        + hashlib.sha256(release_manifest_path.read_bytes()).hexdigest(),
        "artifactDigest": str(release_manifest.get("artifactDigest") or ""),
        "candidateId": str(release_manifest.get("candidateId") or ""),
        "sourceRevision": release_source_revision,
    }
    if current_identity != packaged_identity:
        raise ValueError("prod-hosted release evidence currentness drifted")

    required_evidence = release_manifest.get("requiredEvidence")
    required_images = (
        required_evidence.get("images")
        if isinstance(required_evidence, Mapping)
        else None
    )
    release_images = release_manifest.get("images")
    oci = _read_candidate_object(
        candidate_root,
        "packages/runtime-shared/oci-images.json",
        label="package OCI image manifest",
    )
    packaged_images = oci.get("images")
    if (
        not isinstance(required_images, list)
        or set(required_images) != set(service_packages)
        or not isinstance(release_images, dict)
        or not isinstance(packaged_images, dict)
        or set(release_images) != set(service_packages)
        or {
            service: {
                "ref": str(descriptor.get("ref") or ""),
                "imageDigest": str(descriptor.get("digest") or ""),
            }
            for service, descriptor in release_images.items()
            if isinstance(descriptor, Mapping)
        }
        != packaged_images
    ):
        raise ValueError("prod-hosted release image evidence currentness drifted")


def write_candidate_manifest(
    env_name: str,
    target_name: str,
    *,
    package_snapshot: dict[str, object],
    candidate_type: str = RUNTIME_CANDIDATE_TYPE,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
) -> Path:
    """Write the only candidate manifest after every package digest is sealed."""

    app_dir = _pkg.app_deployment_package_dir(env_name, target=target_name)
    candidate_root = app_dir.parent.parent
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    app_report = _read_candidate_object(
        candidate_root,
        "packages/app/report.json",
        label="App package report",
    )
    environment_runtime_ref = "packages/app/environment_runtime.yaml"
    environment_runtime = _read_candidate_object(
        candidate_root,
        environment_runtime_ref,
        label="packaged environment runtime",
    )
    runtime_schema_version = str(environment_runtime.get("schema") or "").strip()
    if (
        not runtime_schema_version
        or re.fullmatch(r"[a-z][a-z0-9-]*", runtime_schema_version) is None
        or environment_runtime.get("environment") != env_name
        or environment_runtime.get("target") != target_name
    ):
        raise ValueError("packaged environment runtime identity mismatch")
    package_content = fingerprint.get("packageContent")
    deployment_inputs = fingerprint.get("deploymentInputs")
    if not isinstance(package_content, dict) or not isinstance(deployment_inputs, dict):
        raise TypeError("package fingerprint digest bindings are missing")

    shared_dir = _pkg.runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if shared_dir != candidate_root / "packages/runtime-shared":
        raise ValueError("runtime-shared package root escaped the candidate")
    try:
        oci = _read_candidate_object(
            candidate_root,
            "packages/runtime-shared/oci-images.json",
            label="package OCI image manifest",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("full candidate has no safe package-bound OCI manifest") from exc
    include_services = bool(fingerprint.get("includeServices"))
    if (
        candidate_type != RUNTIME_CANDIDATE_TYPE
        or fingerprint.get("candidateType") != RUNTIME_CANDIDATE_TYPE
        or not include_services
    ):
        raise ValueError("runtime candidate must be a full service package")
    legal_static_root = _pkg.legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static_root != candidate_root / "packages/legal-static":
        raise ValueError("legal-static package root escaped the candidate")
    for relative in (
        "packages/legal-static/current/release_metadata.json",
        "packages/legal-static/current/checksums.json",
        "packages/legal-static/current/public/legal/manifest.json",
    ):
        try:
            _read_candidate_bytes(
                candidate_root,
                relative,
                label="deployment candidate legal-static package",
            )
        except _UnsafeCandidatePath as exc:
            raise ValueError(
                "deployment candidate has no complete safe legal-static package"
            ) from exc
    release = validate_release_attestations(
        release_attestation,
        rollback_release_attestation,
    )
    release_classification = release_input_classification(release)
    contract_graph_digest = canonical_contract_graph_digest()
    if (
        fingerprint.get("releaseInputClassification") != release_classification
        or fingerprint.get("contractGraphDigest") != contract_graph_digest
    ):
        raise ValueError("package fingerprint release identity drifted")
    graphql_read_registry = _pkg.validate_packaged_graphql_read_registry(
        repo_root=ROOT,
        candidate_root=candidate_root,
        expected_environment=env_name,
        expected_target=target_name,
        expected_candidate_digest=str(package_snapshot["baselineId"]),
        expected_descriptor=fingerprint.get("graphqlReadRegistry"),
    )

    environment_runtime_digest = _sha256_candidate_file(
        candidate_root,
        environment_runtime_ref,
        label="packaged environment runtime",
    )
    provider_runtime = load_provider_runtime_package(
        env_name,
        target_name,
        candidate_root,
    )
    payload = {
        "schema": CANDIDATE_MANIFEST_SCHEMA,
        "candidateType": candidate_type,
        "environment": env_name,
        "target": target_name,
        "baselineId": package_snapshot["baselineId"],
        "sourceRevision": package_snapshot["sourceRevision"],
        "workspaceDigest": deployment_inputs.get("digest"),
        "workspaceStatusDigest": package_snapshot["workspaceStatusDigest"],
        "packageDigest": package_content.get("digest"),
        "buildInputDigest": oci.get("buildInputDigest") if oci else None,
        "imageDigest": oci.get("imageDigest") if oci else None,
        "configurationDigest": oci.get("configurationDigest") if oci else None,
        "runtimeSchemaVersion": runtime_schema_version,
        "runtimeConfigDigest": app_report.get("runtimeConfigDigest"),
        "environmentRuntimeDigest": environment_runtime_digest,
        "observabilityLogSink": load_observability_log_sink_package(
            env_name,
            target_name,
            candidate_root,
        ),
        "providerRuntime": provider_runtime,
        "release": release,
        "releaseInputClassification": release_classification,
        "contractGraphDigest": contract_graph_digest,
        "graphqlReadRegistry": graphql_read_registry,
        "specRefs": list(SPEC_REFS),
    }
    payload["environmentArtifact"] = build_environment_artifact(
        environment=env_name,
        target=target_name,
        baseline_id=payload["baselineId"],
        source_revision=payload["sourceRevision"],
        workspace_status_digest=payload["workspaceStatusDigest"],
        workspace_digest=payload["workspaceDigest"],
        package_digest=payload["packageDigest"],
        image_build_input_digest=payload["buildInputDigest"],
        image_set_digest=payload["imageDigest"],
        service_configuration_digest=payload["configurationDigest"],
        app_runtime_digest=payload["runtimeConfigDigest"],
        environment_runtime_digest=payload["environmentRuntimeDigest"],
        provider_runtime=provider_runtime,
        contract_graph_digest=payload["contractGraphDigest"],
        environment_runtime=environment_runtime,
        fingerprint=fingerprint,
        candidate_root=candidate_root,
    )
    validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=True,
        candidate_root=candidate_root,
    )
    path = _atomic_write_candidate_file(
        candidate_root,
        "manifest.json",
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
        label="deployment candidate manifest",
    )
    return path


def validate_candidate_manifest(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    require_full: bool,
    candidate_root: Path | None = None,
    purpose: str = "currentness",
    currentness_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if candidate_root is None:
        raise ValueError(
            "runnable deployment candidate validation requires candidate_root"
        )
    if purpose not in CANDIDATE_VALIDATION_PURPOSES:
        raise ValueError("deployment candidate validation purpose is invalid")
    try:
        _validate_candidate_payload_tree(candidate_root)
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate payload tree is unsafe") from exc
    required = {
        "schema",
        "candidateType",
        "environment",
        "target",
        "baselineId",
        "sourceRevision",
        "workspaceDigest",
        "workspaceStatusDigest",
        "packageDigest",
        "buildInputDigest",
        "imageDigest",
        "configurationDigest",
        "runtimeSchemaVersion",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "observabilityLogSink",
        "providerRuntime",
        "release",
        "releaseInputClassification",
        "contractGraphDigest",
        "graphqlReadRegistry",
        "specRefs",
        "environmentArtifact",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("deployment candidate manifest fields mismatch")
    if payload.get("schema") != CANDIDATE_MANIFEST_SCHEMA:
        raise ValueError("deployment candidate manifest schema mismatch")
    if payload.get("candidateType") != RUNTIME_CANDIDATE_TYPE:
        raise ValueError("deployment candidate type mismatch")
    if (
        payload.get("environment") != expected_environment
        or payload.get("target") != expected_target
    ):
        raise ValueError("deployment candidate manifest target identity mismatch")
    if re.fullmatch(r"[0-9a-f]{40}", str(payload.get("sourceRevision") or "")) is None:
        raise ValueError("deployment candidate sourceRevision is invalid")
    if (
        re.fullmatch(
            r"[a-z][a-z0-9-]*",
            str(payload.get("runtimeSchemaVersion") or ""),
        )
        is None
    ):
        raise ValueError("deployment candidate runtimeSchemaVersion is invalid")
    for field in (
        "baselineId",
        "workspaceDigest",
        "workspaceStatusDigest",
        "packageDigest",
        "configurationDigest",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "contractGraphDigest",
    ):
        if _DIGEST.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"deployment candidate {field} is invalid")
    if payload.get("specRefs") != list(SPEC_REFS):
        raise ValueError("deployment candidate specRefs mismatch")
    if not require_full:
        raise ValueError("runtime deployment candidate cannot be loaded as App-only")
    for field in ("buildInputDigest", "imageDigest"):
        if _DIGEST.fullmatch(str(payload.get(field) or "")) is None:
            raise ValueError(f"full deployment candidate {field} is invalid")
    validate_observability_log_sink_package(
        payload.get("observabilityLogSink"),
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
    )
    validate_packaged_provider_runtime(
        payload.get("providerRuntime"),
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
        require_current_contracts=purpose == "currentness",
    )
    _validate_candidate_app_runtime_binding(
        payload,
        candidate_root=candidate_root,
    )
    _validate_candidate_provider_oci_binding(
        payload,
        candidate_root=candidate_root,
    )
    _validate_prod_hosted_oci_binding(
        payload,
        candidate_root=candidate_root,
    )
    release = payload.get("release")
    if not isinstance(release, dict) or set(release) != {"candidate", "rollback"}:
        raise ValueError("full deployment candidate release binding mismatch")
    for label in ("candidate", "rollback"):
        binding = release.get(label)
        if not isinstance(binding, dict) or set(binding) != _RELEASE_BINDING_FIELDS:
            raise ValueError(f"deployment candidate {label} release fields mismatch")
        if not str(binding.get("releaseId") or ""):
            raise ValueError(f"deployment candidate {label} releaseId is invalid")
        for field in ("releaseDigest", "attestationDigest"):
            if _DIGEST.fullmatch(str(binding.get(field) or "")) is None:
                raise ValueError(f"deployment candidate {label} {field} is invalid")
        attestation_ref = binding.get("attestationRef")
        if not isinstance(attestation_ref, str) or not attestation_ref.strip():
            raise ValueError(
                f"deployment candidate {label} attestationRef is invalid"
            )
    expected_classification = release_input_classification(release)
    if payload.get("releaseInputClassification") != expected_classification:
        raise ValueError("deployment candidate release input classification drifted")
    if (
        purpose == "currentness"
        and payload.get("contractGraphDigest") != canonical_contract_graph_digest()
    ):
        raise ValueError("deployment candidate ContractGraph bytes drifted")
    validate_environment_artifact(
        payload.get("environmentArtifact"),
        candidate=payload,
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
    )
    graphql_read_registry = _pkg.validate_packaged_graphql_read_registry(
        repo_root=ROOT,
        candidate_root=candidate_root,
        expected_environment=expected_environment,
        expected_target=expected_target,
        expected_candidate_digest=str(payload.get("baselineId") or ""),
        expected_descriptor=payload.get("graphqlReadRegistry"),
        purpose=purpose,
        currentness_timeout_seconds=currentness_timeout_seconds,
    )
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    if (
        fingerprint.get("releaseInputClassification") != expected_classification
        or fingerprint.get("contractGraphDigest") != payload.get("contractGraphDigest")
        or fingerprint.get("graphqlReadRegistry") != graphql_read_registry
    ):
        raise ValueError("package fingerprint release identity drifted")
    if purpose == "currentness":
        for label in ("candidate", "rollback"):
            binding = release[label]
            current = _release_binding(binding["attestationRef"], label=label)
            if current != binding:
                raise ValueError(f"{label} release attestation bytes drifted")
    return payload


def _validate_candidate_app_runtime_binding(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> None:
    """Cross-bind the App runtime config without conflating service config."""

    try:
        app_report = _read_candidate_object(
            candidate_root,
            "packages/app/report.json",
            label="App package report",
        )
    except _UnsafeCandidatePath as exc:
        raise ValueError("deployment candidate App package report is unsafe") from exc
    if (
        _DIGEST.fullmatch(str(app_report.get("runtimeConfigDigest") or "")) is None
        or app_report.get("runtimeConfigDigest")
        != candidate.get("runtimeConfigDigest")
    ):
        raise ValueError("deployment candidate App runtime identity drifted")


def load_candidate_manifest(
    env_name: str,
    target_name: str,
    baseline_id: str,
    *,
    require_full: bool,
    purpose: str = "self_verify",
    currentness_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    candidate_root = _pkg.deployment_candidate_dir(target_name, baseline_id)
    payload = _read_candidate_object(
        candidate_root,
        "manifest.json",
        label="deployment candidate manifest",
    )
    return validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=require_full,
        candidate_root=candidate_root,
        purpose=purpose,
        currentness_timeout_seconds=currentness_timeout_seconds,
    )
