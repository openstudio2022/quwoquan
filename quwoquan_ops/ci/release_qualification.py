#!/usr/bin/env python3
"""Explicit RC qualification request, build-once material and final aggregation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OCI = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@(sha256:[0-9a-f]{64})$")
_RC = re.compile(
    r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)-rc\.([1-9][0-9]*)$"
)
_ALLOCATION_SCHEMA = "quwoquan_ops.artifact_build_number_allocation.v1"
_HOSTED_ALLOCATION_PROVIDER = "github_actions_workflow_run_number"
_PROD_BUNDLE_PATHS = (
    "quwoquan_ops/environments/prod",
    "quwoquan_ops/external/coturn/base",
    "quwoquan_ops/external/coturn/environments/prod",
    "quwoquan_ops/external/livekit/base",
    "quwoquan_ops/external/livekit/environments/prod",
    "quwoquan_ops/observability/monitoring/docker-compose.prod.yml",
    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
    "quwoquan_ops/cli/prod/render_prod_plane_stack_lib",
    ":(glob)quwoquan_service/services/*/config/schema.yaml",
    ":(glob)quwoquan_service/services/*/environments/prod/config.yaml",
    ":(glob)quwoquan_service/services/*/deploy/**",
    ":(glob)quwoquan_service/services/*/environments/prod/deploy/**",
    "quwoquan_service/control-plane/platform-ops/deploy/base",
    "quwoquan_service/control-plane/platform-ops/environments/prod/deploy",
)
_PROD_BUNDLE_SCHEMA = "quwoquan_ops.prod_runtime_config_deployment_bundle.v1"


class ReleaseQualificationError(ValueError):
    pass


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(value: Mapping[str, Any] | Path | bytes) -> str:
    raw = (
        value.read_bytes()
        if isinstance(value, Path)
        else value
        if isinstance(value, bytes)
        else canonical_bytes(value)
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        raise ReleaseQualificationError(f"{field} is invalid")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA.fullmatch(text) is None:
        raise ReleaseQualificationError(f"{field} is not an exact Git SHA")
    return text


def _digest(value: object, field: str) -> str:
    text = _text(value, field)
    if _DIGEST.fullmatch(text) is None:
        raise ReleaseQualificationError(f"{field} is not an exact digest")
    return text


def _oci(value: object, field: str) -> tuple[str, str]:
    text = _text(value, field)
    match = _OCI.fullmatch(text)
    if match is None:
        raise ReleaseQualificationError(f"{field} is not an exact GHCR OCI ref")
    return text, match.group(1)


def _exact_path(root: Path, value: object, field: str) -> tuple[Path, dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise ReleaseQualificationError(f"{field} must contain ref and digest")
    ref = _text(value.get("ref"), f"{field}.ref")
    relative = PurePosixPath(ref)
    if (
        relative.is_absolute()
        or relative.as_posix() != ref
        or "\\" in ref
        or any(part in {"", ".", "..", "latest", "current"} for part in relative.parts)
    ):
        raise ReleaseQualificationError(f"{field}.ref is mutable or unsafe")
    expected = _digest(value.get("digest"), f"{field}.digest")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ReleaseQualificationError(f"{field}.ref traverses symlink")
    if not path.is_file() or digest(path) != expected:
        raise ReleaseQualificationError(f"{field} exact bytes drifted")
    return path, {"ref": ref, "digest": expected}


def _exact(root: Path, value: object, field: str) -> tuple[dict[str, Any], dict[str, str]]:
    path, normalized = _exact_path(root, value, field)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseQualificationError(f"{field} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ReleaseQualificationError(f"{field} must be an object")
    return payload, normalized


def _validate_hosted_allocation(
    *,
    allocation: Mapping[str, Any],
    request: Mapping[str, Any],
    request_exact: Mapping[str, str],
    artifact_build_number: int,
) -> None:
    authority = allocation.get("hostedAuthority")
    if (
        allocation.get("schema") != _ALLOCATION_SCHEMA
        or allocation.get("requestId") != request.get("requestId")
        or allocation.get("qualificationRequest") != request_exact
        or allocation.get("artifactBuildNumber") != artifact_build_number
        or allocation.get("predecessor") is not None
        or not isinstance(authority, Mapping)
        or set(authority) != {"provider", "runId", "runNumber"}
        or authority.get("provider") != _HOSTED_ALLOCATION_PROVIDER
        or authority.get("runNumber") != artifact_build_number
    ):
        raise ReleaseQualificationError(
            "hosted artifact build-number allocation drifted"
        )
    _text(authority.get("runId"), "artifactBuildNumberAllocation.hostedAuthority.runId")
    allocation_id = _digest(
        allocation.get("allocationId"), "artifactBuildNumberAllocation.allocationId"
    )
    if digest(
        {key: value for key, value in allocation.items() if key != "allocationId"}
    ) != allocation_id:
        raise ReleaseQualificationError(
            "hosted artifact build-number allocation identity drifted"
        )


def _write(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ReleaseQualificationError(
                f"create-once conflict: {path.name}"
            ) from exc
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def create_qualification_request(
    *,
    root: Path,
    rc_tag_admission_ref: Mapping[str, str],
    main_source_seal_ref: Mapping[str, str],
    integration_qualification_ref: Mapping[str, str],
    requested_by_ref: Mapping[str, str],
    requested_at: str,
) -> Path:
    root = root.resolve()
    tag, tag_exact = _exact(root, rc_tag_admission_ref, "rcTagAdmission")
    seal, seal_exact = _exact(root, main_source_seal_ref, "mainSourceSeal")
    integration, integration_exact = _exact(
        root, integration_qualification_ref, "integrationQualification"
    )
    authority, authority_exact = _exact(root, requested_by_ref, "requestAuthority")
    tag_name = _text(tag.get("tagName"), "tagName")
    if _RC.fullmatch(tag_name) is None or tag.get("decision") != "admitted":
        raise ReleaseQualificationError("qualification requires admitted RC tag")
    source = _sha(tag.get("peeledCommit"), "peeledCommit")
    source_tree = _sha(tag.get("sourceTree"), "sourceTree")
    source_head = _sha(seal.get("sourceHeadSha"), "mainSourceSeal.sourceHeadSha")
    if (
        seal.get("schema") != "quwoquan_ops.main_source_seal.v1"
        or seal.get("mainSha") != source
        or seal.get("mainTree") != source_tree
    ):
        raise ReleaseQualificationError("MainSourceSeal drifted")
    if (
        integration.get("schema")
        != "quwoquan_ops.integration_qualification_fact.v1"
        or integration.get("decision") != "qualified"
        or integration.get("devHead") != source_head
        or integration.get("devTree") != source_tree
    ):
        raise ReleaseQualificationError("IntegrationQualificationFact drifted")
    if (
        authority.get("status") != "approved"
        or authority.get("sourceGitSha") != source
        or authority.get("tagName") not in {None, tag_name}
    ):
        raise ReleaseQualificationError("qualification request authority is invalid")
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.release_qualification_request.v1",
        "rcTagAdmission": tag_exact,
        "mainSourceSeal": seal_exact,
        "integrationQualification": integration_exact,
        "requestAuthority": authority_exact,
        "tagName": tag_name,
        "sourceGitSha": source,
        "sourceTree": source_tree,
        "requestedAt": _text(requested_at, "requestedAt"),
    }
    body["requestId"] = digest(body)
    return _write(
        root / "release-qualification/requests" / f"{body['requestId']}.json",
        body,
    )


def _normalize_artifacts(
    artifacts: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping) or set(artifact) != {
            "platform",
            "ociRef",
            "digest",
        }:
            raise ReleaseQualificationError("artifact shape is invalid")
        platform = _text(artifact.get("platform"), f"artifacts[{index}].platform")
        oci, oci_digest = _oci(artifact.get("ociRef"), f"artifacts[{index}].ociRef")
        exact_digest = _digest(artifact.get("digest"), f"artifacts[{index}].digest")
        if oci_digest != exact_digest or platform in seen:
            raise ReleaseQualificationError(
                "artifact must be unique exact OCI digest"
            )
        seen.add(platform)
        normalized.append(
            {"platform": platform, "ociRef": oci, "digest": exact_digest}
        )
    if seen != {"android", "ios", "service", "web"}:
        raise ReleaseQualificationError("material platforms are incomplete")
    return sorted(normalized, key=lambda item: item["platform"])


def create_candidate_material_manifest(
    *,
    root: Path,
    request_ref: Mapping[str, str],
    artifact_build_number: int,
    product_version_manifest_ref: Mapping[str, str],
    artifacts: Sequence[Mapping[str, str]],
    sbom_ref: Mapping[str, str],
    provenance_ref: Mapping[str, str],
    signing_ref: Mapping[str, str],
    created_at: str,
    artifact_build_number_allocation_ref: Mapping[str, str],
    factory_outputs: Mapping[str, Any] | None = None,
) -> Path:
    root = root.resolve()
    request, request_exact = _exact(root, request_ref, "qualificationRequest")
    if request.get("schema") != "quwoquan_ops.release_qualification_request.v1":
        raise ReleaseQualificationError("request schema drifted")
    if type(artifact_build_number) is not int or artifact_build_number < 1:
        raise ReleaseQualificationError("artifactBuildNumber must be positive")
    _, version_exact = _exact_path(
        root, product_version_manifest_ref, "productVersionManifest"
    )
    allocation, allocation_exact = _exact(
        root,
        artifact_build_number_allocation_ref,
        "artifactBuildNumberAllocation",
    )
    _validate_hosted_allocation(
        allocation=allocation,
        request=request,
        request_exact=request_exact,
        artifact_build_number=artifact_build_number,
    )
    support: dict[str, dict[str, str]] = {}
    for name, exact in (
        ("sbom", sbom_ref),
        ("provenance", provenance_ref),
        ("signing", signing_ref),
    ):
        _, support[name] = _exact(root, exact, name)
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "qualificationRequest": request_exact,
        "sourceGitSha": request["sourceGitSha"],
        "sourceTree": request["sourceTree"],
        "tagName": request["tagName"],
        "artifactBuildNumber": artifact_build_number,
        "artifactBuildNumberAllocation": allocation_exact,
        "productVersionManifest": version_exact,
        "artifacts": _normalize_artifacts(artifacts),
        **support,
        "factoryOutputs": dict(factory_outputs or {}),
        "buildPolicy": "build_sign_attest_once",
        "createdAt": _text(created_at, "createdAt"),
    }
    body["materialId"] = digest(body)
    return _write(
        root / "release-qualification/materials" / f"{body['materialId']}.json",
        body,
    )


def build_prod_runtime_config_deployment_bundle(
    repository_root: Path,
) -> dict[str, Any]:
    """Digest the tracked Prod runtime/config/deployment authoring closure."""

    repository_root = repository_root.resolve()
    result = subprocess.run(
        ["git", "-C", str(repository_root), "ls-files", "-z", "--", *_PROD_BUNDLE_PATHS],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ReleaseQualificationError(
            "Prod runtime config/deployment bundle cannot enumerate tracked inputs"
        )
    try:
        relative_paths = sorted(
            item.decode("utf-8") for item in result.stdout.split(b"\0") if item
        )
    except UnicodeDecodeError as exc:
        raise ReleaseQualificationError(
            "Prod runtime config/deployment bundle path is not UTF-8"
        ) from exc
    if not relative_paths or len(relative_paths) != len(set(relative_paths)):
        raise ReleaseQualificationError(
            "Prod runtime config/deployment bundle closure is empty or duplicated"
        )
    files: list[dict[str, str]] = []
    for relative in relative_paths:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
            raise ReleaseQualificationError(
                "Prod runtime config/deployment bundle path is unsafe"
            )
        current = repository_root
        for part in posix.parts:
            current = current / part
            if current.is_symlink():
                raise ReleaseQualificationError(
                    f"Prod runtime config/deployment bundle traverses symlink: {relative}"
                )
        if not current.is_file():
            raise ReleaseQualificationError(
                f"Prod runtime config/deployment bundle input is missing: {relative}"
            )
        files.append({"path": relative, "digest": digest(current)})
    body: dict[str, Any] = {
        "schema": _PROD_BUNDLE_SCHEMA,
        "algorithm": "sha256_sorted_tracked_path_bytes_v1",
        "files": files,
    }
    body["digest"] = digest(body)
    return body


def _canonical_material(
    root: Path, value: object, field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    path, normalized = _exact_path(root, value, field)
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseQualificationError(f"{field} is invalid JSON") from exc
    if not isinstance(payload, dict) or raw != canonical_bytes(payload) + b"\n":
        raise ReleaseQualificationError(f"{field} bytes are not canonical JSON")
    return payload, normalized


def _self_material_digest(material: Mapping[str, Any], field: str) -> str:
    unsigned = dict(material)
    claimed = _digest(unsigned.pop("materialDigest", None), f"{field}.materialDigest")
    if digest(unsigned) != claimed:
        raise ReleaseQualificationError(f"{field} self material digest drifted")
    return claimed


def _repository_from_factory_ref(locator: str, field: str) -> str:
    without_registry = locator.removeprefix("ghcr.io/").split("@", 1)[0]
    parts = without_registry.split("/")
    if len(parts) < 3:
        raise ReleaseQualificationError(f"{field} lacks repository identity")
    return "/".join(parts[:2])


def _validate_service_factory_material(
    *,
    material: Mapping[str, Any],
    payload_exact: Mapping[str, str],
    locator: str,
    locator_digest: str,
    request: Mapping[str, Any],
    request_exact: Mapping[str, str],
    request_locator: str,
    request_transport_digest: str,
    allocation: Mapping[str, Any],
    allocation_exact: Mapping[str, str],
    allocation_locator: str,
    allocation_transport_digest: str,
    repository_root: Path,
) -> dict[str, Any]:
    from quwoquan_ops.ci.plan_service_release_images import (
        RUNTIME_IMAGE_OWNERS,
        TRUST_DOMAINS,
    )
    from quwoquan_ops.cli.prod.oci_supply_chain import OIDC_ISSUER, PREDICATES

    expected_keys = {
        "schema", "sourceGitSha", "sourceTree", "qualificationRequest",
        "rcTagAdmission", "artifactBuildNumber", "artifactBuildNumberAllocation",
        "serviceDigest", "images", "prodRuntimeConfigDeploymentBundle", "producer",
        "buildPolicy", "materialDigest",
    }
    material_digest = _self_material_digest(material, "serviceFactoryMaterial")
    request_id = _digest(request.get("requestId"), "request.requestId")
    request_authority = request.get("rcTagAdmission")
    if not isinstance(request_authority, Mapping):
        raise ReleaseQualificationError("request RC admission is missing")
    request_rc_ref = _text(request_authority.get("ref"), "request.rcTagAdmission.ref")
    request_rc_fact_digest = _digest(
        request_authority.get("digest"), "request.rcTagAdmission.digest"
    )
    rc_locator, rc_transport_digest = _oci(request_rc_ref, "request.rcTagAdmission.ref")
    expected_request = {
        "ref": request_locator,
        "digest": request_transport_digest,
        "factDigest": request_exact["digest"],
        "requestId": request_id,
    }
    rc = material.get("rcTagAdmission")
    allocation_binding = material.get("artifactBuildNumberAllocation")
    if (
        set(material) != expected_keys
        or material.get("schema") != "quwoquan_ops.service_factory_material"
        or material.get("sourceGitSha") != request.get("sourceGitSha")
        or material.get("sourceTree") != request.get("sourceTree")
        or material.get("qualificationRequest") != expected_request
        or not isinstance(rc, Mapping)
        or set(rc) != {"ref", "digest", "factDigest", "admissionId", "tagName"}
        or rc.get("ref") != rc_locator
        or rc.get("digest") != rc_transport_digest
        or rc.get("factDigest") != request_rc_fact_digest
        or rc.get("tagName") != request.get("tagName")
        or _DIGEST.fullmatch(str(rc.get("admissionId") or "")) is None
        or material.get("artifactBuildNumber") != allocation.get("artifactBuildNumber")
        or not isinstance(allocation_binding, Mapping)
        or set(allocation_binding) != {"ref", "digest", "factDigest", "allocationId"}
        or allocation_binding.get("ref") != allocation_locator
        or allocation_binding.get("digest") != allocation_transport_digest
        or allocation_binding.get("factDigest") != allocation_exact["digest"]
        or allocation_binding.get("allocationId") != allocation.get("allocationId")
        or material.get("buildPolicy") != "build_sign_attest_once"
    ):
        raise ReleaseQualificationError(
            "service factory material authority/build identity drifted"
        )

    expected_bundle = build_prod_runtime_config_deployment_bundle(repository_root)
    if material.get("prodRuntimeConfigDeploymentBundle") != expected_bundle:
        raise ReleaseQualificationError(
            "service Prod runtime config/deployment bundle closure drifted"
        )

    repository = _repository_from_factory_ref(locator, "serviceFactoryMaterialOciRef")
    producer = material.get("producer")
    signer_workflow = f"{repository}/.github/workflows/service_pipeline.yml"
    if (
        not isinstance(producer, Mapping)
        or set(producer) != {"repository", "signerWorkflow", "workflowRunId"}
        or producer.get("repository") != repository
        or producer.get("signerWorkflow") != signer_workflow
    ):
        raise ReleaseQualificationError("service factory producer identity drifted")
    _text(producer.get("workflowRunId"), "serviceFactoryMaterial.producer.workflowRunId")

    images = material.get("images")
    expected_order = [
        (trust_domain, owner)
        for trust_domain in TRUST_DOMAINS
        for owner in RUNTIME_IMAGE_OWNERS
    ]
    if not isinstance(images, list) or len(images) != len(expected_order):
        raise ReleaseQualificationError("service image material is incomplete")
    subjects: list[dict[str, str]] = []
    for index, (image, expected_subject) in enumerate(zip(images, expected_order)):
        if not isinstance(image, Mapping) or set(image) != {
            "trustDomain", "runtimeImageOwner", "ociRef", "digest",
            "signature", "attestations",
        }:
            raise ReleaseQualificationError(f"service image[{index}] shape drifted")
        subject = (image.get("trustDomain"), image.get("runtimeImageOwner"))
        image_ref, image_oci_digest = _oci(image.get("ociRef"), f"service.images[{index}].ociRef")
        image_digest = _digest(image.get("digest"), f"service.images[{index}].digest")
        signature = image.get("signature")
        attestations = image.get("attestations")
        if (
            subject != expected_subject
            or image_oci_digest != image_digest
            or not isinstance(signature, Mapping)
            or set(signature) != {"issuer", "signerWorkflow", "verificationDigest"}
            or signature.get("issuer") != OIDC_ISSUER
            or signature.get("signerWorkflow") != signer_workflow
            or not isinstance(attestations, Mapping)
            or set(attestations) != set(PREDICATES)
        ):
            raise ReleaseQualificationError("service image signature identity drifted")
        verification_digests: dict[str, str] = {}
        for name, predicate_type in PREDICATES.items():
            attestation = attestations.get(name)
            if (
                not isinstance(attestation, Mapping)
                or set(attestation) != {"predicateType", "verificationDigest"}
                or attestation.get("predicateType") != predicate_type
            ):
                raise ReleaseQualificationError("service image attestation shape drifted")
            verification_digests[name] = _digest(
                attestation.get("verificationDigest"),
                f"service.images[{index}].attestations.{name}.verificationDigest",
            )
        expected_signature_digest = digest(
            {
                "subject": image_ref,
                "issuer": OIDC_ISSUER,
                "signerWorkflow": signer_workflow,
                "attestations": verification_digests,
            }
        )
        if signature.get("verificationDigest") != expected_signature_digest:
            raise ReleaseQualificationError("service image verification digest drifted")
        subjects.append(
            {
                "trustDomain": str(subject[0]),
                "runtimeImageOwner": str(subject[1]),
                "digest": image_digest,
            }
        )
    service_digest = digest({"images": subjects})
    if material.get("serviceDigest") != service_digest:
        raise ReleaseQualificationError("service aggregate artifact digest drifted")
    return {
        "ociRef": locator,
        "ociDigest": locator_digest,
        "payloadDigest": payload_exact["digest"],
        "materialDigest": material_digest,
        "serviceDigest": service_digest,
        "prodRuntimeConfigDeploymentBundle": expected_bundle,
    }


def _validate_app_factory_material(
    *,
    material: Mapping[str, Any],
    payload_exact: Mapping[str, str],
    locator: str,
    locator_digest: str,
    request: Mapping[str, Any],
    request_locator: str,
    request_transport_digest: str,
    allocation: Mapping[str, Any],
    allocation_locator: str,
    allocation_transport_digest: str,
) -> dict[str, Any]:
    from quwoquan_ops.ci.render_release_application_package import (
        ARTIFACT_REQUIRED_FIELDS,
        _validate_artifact_manifest,
    )

    if "appEvidenceDigest" in material:
        raise ReleaseQualificationError(
            "app factory material contains self-referential appEvidenceDigest"
        )
    expected_keys = {
        "schema", "sourceGitSha", "sourceTreeDigest", "qualificationRequest",
        "rcTagAdmissionRef", "artifactBuildNumber", "artifactBuildNumberAllocation",
        "artifacts", "materialDigest",
    }
    material_digest = _self_material_digest(material, "appFactoryMaterial")
    expected_repository = _repository_from_factory_ref(
        locator, "appFactoryMaterialOciRef"
    )
    if not locator.startswith(
        f"ghcr.io/{expected_repository}/app-candidate-artifact@sha256:"
    ):
        raise ReleaseQualificationError("app factory OCI repository drifted")
    app_tree = f"sha1:{request.get('sourceTree')}"
    request_rc = request.get("rcTagAdmission")
    rc_match = _RC.fullmatch(_text(request.get("tagName"), "request.tagName"))
    if rc_match is None:
        raise ReleaseQualificationError("app factory request RC tag is invalid")
    expected_display_version = ".".join(rc_match.groups()[:3])
    artifacts = material.get("artifacts")
    allocation_binding = material.get("artifactBuildNumberAllocation")
    if (
        set(material) != expected_keys
        or material.get("schema") != "quwoquan_ops.app_factory_material"
        or material.get("sourceGitSha") != request.get("sourceGitSha")
        or material.get("sourceTreeDigest") != app_tree
        or material.get("qualificationRequest")
        != {"ref": request_locator, "digest": request_transport_digest}
        or not isinstance(request_rc, Mapping)
        or material.get("rcTagAdmissionRef") != request_rc.get("ref")
        or material.get("artifactBuildNumber") != allocation.get("artifactBuildNumber")
        or not isinstance(allocation_binding, Mapping)
        or set(allocation_binding) != {"ref", "digest"}
        or allocation_binding.get("ref") != allocation_locator
        or allocation_binding.get("digest") != allocation_transport_digest
        or not isinstance(artifacts, Mapping)
        or set(artifacts) != {"android", "ios", "web"}
    ):
        raise ReleaseQualificationError(
            "app factory material authority/build identity drifted"
        )

    authority_fields = {
        "qualificationRequestRef",
        "qualificationRequestDigest",
        "rcTagAdmissionRef",
        "artifactBuildNumberAllocationRef",
        "artifactBuildNumberAllocationDigest",
    }
    product_ids = {
        "android": "android-prod-apk",
        "ios": "ios-prod-app",
        "web": "web-shared",
    }
    artifact_manifests: dict[str, dict[str, Any]] = {}
    artifact_digests: dict[str, str] = {}
    expected_build_number = str(allocation.get("artifactBuildNumber"))
    for platform, product_id in product_ids.items():
        value = artifacts.get(platform)
        expected_fields = set(ARTIFACT_REQUIRED_FIELDS) | authority_fields
        if platform in {"android", "ios"}:
            expected_fields.add("runtimeConfigTrustEnvelopeDigest")
        if not isinstance(value, Mapping) or set(value) != expected_fields:
            raise ReleaseQualificationError(
                f"app {platform} AppArtifactManifest shape drifted"
            )
        manifest = dict(value)
        try:
            normalized = _validate_artifact_manifest(
                manifest,
                build_product_id=product_id,
                source_git_sha=str(request.get("sourceGitSha") or ""),
                source_tree_digest=app_tree,
            )
        except ValueError as exc:
            raise ReleaseQualificationError(
                f"app {platform} AppArtifactManifest identity drifted: {exc}"
            ) from exc
        if (
            _text(manifest.get("displayVersion"), f"app.artifacts.{platform}.displayVersion")
            != expected_display_version
            or manifest.get("buildNumber") != expected_build_number
            or manifest.get("qualificationRequestRef") != request_locator
            or manifest.get("qualificationRequestDigest") != request_transport_digest
            or manifest.get("rcTagAdmissionRef") != request_rc.get("ref")
            or manifest.get("artifactBuildNumberAllocationRef") != allocation_locator
            or manifest.get("artifactBuildNumberAllocationDigest")
            != allocation_transport_digest
            or manifest.get("promotable") is not True
        ):
            raise ReleaseQualificationError(
                f"app {platform} AppArtifactManifest authority/build identity drifted"
            )
        for field in ("artifactDigest", "signingIdentityDigest", "buildProvenanceDigest"):
            _digest(manifest.get(field), f"app.artifacts.{platform}.{field}")
        if platform in {"android", "ios"}:
            _digest(
                manifest.get("runtimeConfigTrustEnvelopeDigest"),
                f"app.artifacts.{platform}.runtimeConfigTrustEnvelopeDigest",
            )
        artifact_manifests[platform] = normalized
        artifact_digests[platform] = str(normalized["artifactDigest"])

    return {
        "ociRef": locator,
        "ociDigest": locator_digest,
        "payloadDigest": payload_exact["digest"],
        "materialDigest": material_digest,
        "artifactDigests": artifact_digests,
        "artifactManifests": artifact_manifests,
        "sourceTreeDigest": app_tree,
    }


def create_candidate_material_from_factory_outputs(
    *,
    root: Path,
    request_ref: Mapping[str, str],
    request_oci_ref: str,
    artifact_build_number_allocation_ref: Mapping[str, str],
    allocation_oci_ref: str,
    product_version_manifest_ref: Mapping[str, str],
    service_material_ref: Mapping[str, str],
    service_evidence_ref: str,
    service_source_git_sha: str,
    service_source_tree: str,
    service_qualification_request_ref: str,
    service_qualification_request_digest: str,
    service_material_digest: str,
    service_artifact_digest: str,
    app_material_ref: Mapping[str, str],
    app_evidence_ref: str,
    app_source_git_sha: str,
    app_source_tree: str,
    app_qualification_request_ref: str,
    app_qualification_request_digest: str,
    app_artifact_build_number: int,
    app_allocation_ref: str,
    app_allocation_digest: str,
    app_material_digest: str,
    app_android_artifact_digest: str,
    app_ios_artifact_digest: str,
    app_web_artifact_digest: str,
    created_at: str,
    repository_root: Path | None = None,
) -> Path:
    """Validate actual factory canonical bytes before reducing the one CMM."""

    root = root.resolve()
    repository_root = (
        Path(__file__).resolve().parents[2]
        if repository_root is None
        else repository_root.resolve()
    )
    request, request_exact = _exact(root, request_ref, "qualificationRequest")
    allocation, allocation_exact = _exact(
        root,
        artifact_build_number_allocation_ref,
        "artifactBuildNumberAllocation",
    )
    service_material, service_payload_exact = _canonical_material(
        root, service_material_ref, "serviceFactoryMaterial"
    )
    app_material, app_payload_exact = _canonical_material(
        root, app_material_ref, "appFactoryMaterial"
    )
    request_locator, request_transport_digest = _oci(
        request_oci_ref, "qualificationRequestOciRef"
    )
    allocation_locator, allocation_transport_digest = _oci(
        allocation_oci_ref, "artifactBuildNumberAllocationOciRef"
    )
    service_locator, service_oci_digest = _oci(
        service_evidence_ref, "serviceEvidenceRef"
    )
    app_locator, app_oci_digest = _oci(app_evidence_ref, "appEvidenceRef")
    source = _sha(request.get("sourceGitSha"), "request.sourceGitSha")
    tree = _sha(request.get("sourceTree"), "request.sourceTree")
    build_number = allocation.get("artifactBuildNumber")
    if (
        request.get("schema") != "quwoquan_ops.release_qualification_request.v1"
        or type(build_number) is not int
        or build_number < 1
    ):
        raise ReleaseQualificationError(
            "qualification request/build-number allocation drifted"
        )
    _validate_hosted_allocation(
        allocation=allocation,
        request=request,
        request_exact=request_exact,
        artifact_build_number=build_number,
    )
    service = _validate_service_factory_material(
        material=service_material,
        payload_exact=service_payload_exact,
        locator=service_locator,
        locator_digest=service_oci_digest,
        request=request,
        request_exact=request_exact,
        request_locator=request_locator,
        request_transport_digest=request_transport_digest,
        allocation=allocation,
        allocation_exact=allocation_exact,
        allocation_locator=allocation_locator,
        allocation_transport_digest=allocation_transport_digest,
        repository_root=repository_root,
    )
    app = _validate_app_factory_material(
        material=app_material,
        payload_exact=app_payload_exact,
        locator=app_locator,
        locator_digest=app_oci_digest,
        request=request,
        request_locator=request_locator,
        request_transport_digest=request_transport_digest,
        allocation=allocation,
        allocation_locator=allocation_locator,
        allocation_transport_digest=allocation_transport_digest,
    )

    scalar_drift = (
        service_source_git_sha != service_material.get("sourceGitSha")
        or service_source_tree != service_material.get("sourceTree")
        or service_qualification_request_ref != request_locator
        or service_qualification_request_digest != request_transport_digest
        or service_material_digest != service["materialDigest"]
        or service_artifact_digest != service["serviceDigest"]
        or app_source_git_sha != app_material.get("sourceGitSha")
        or app_source_tree != app_material.get("sourceTreeDigest")
        or app_qualification_request_ref != request_locator
        or app_qualification_request_digest != request_transport_digest
        or app_artifact_build_number != build_number
        or app_allocation_ref != allocation_locator
        or app_allocation_digest != allocation_transport_digest
        or app_material_digest != app["materialDigest"]
        or app_android_artifact_digest != app["artifactDigests"]["android"]
        or app_ios_artifact_digest != app["artifactDigests"]["ios"]
        or app_web_artifact_digest != app["artifactDigests"]["web"]
    )
    if scalar_drift:
        raise ReleaseQualificationError(
            "reusable factory scalar drifted from actual material bytes"
        )

    _, version_exact = _exact_path(
        root, product_version_manifest_ref, "productVersionManifest"
    )
    artifacts = _normalize_artifacts(
        (
            {"platform": "android", "ociRef": app_locator, "digest": app_oci_digest},
            {"platform": "ios", "ociRef": app_locator, "digest": app_oci_digest},
            {
                "platform": "service",
                "ociRef": service_locator,
                "digest": service_oci_digest,
            },
            {"platform": "web", "ociRef": app_locator, "digest": app_oci_digest},
        )
    )
    factory_outputs = {
        "service": service,
        "app": app,
        "qualificationRequestOciRef": request_locator,
        "artifactBuildNumberAllocationOciRef": allocation_locator,
    }
    exact_artifact_digests = {
        **app["artifactDigests"],
        "service": service["serviceDigest"],
    }
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "qualificationRequest": request_exact,
        "qualificationRequestOciRef": request_locator,
        "sourceGitSha": source,
        "sourceTree": tree,
        "tagName": request["tagName"],
        "artifactBuildNumber": build_number,
        "artifactBuildNumberAllocation": allocation_exact,
        "artifactBuildNumberAllocationOciRef": allocation_locator,
        "productVersionManifest": version_exact,
        "artifacts": artifacts,
        "factoryOutputs": factory_outputs,
        "supplyChainSubjects": [app_locator, service_locator],
        "artifactByteDigests": exact_artifact_digests,
        "buildPolicy": "build_sign_attest_once",
        "createdAt": _text(created_at, "createdAt"),
    }
    body["materialId"] = digest(body)
    return _write(
        root / "release-qualification/materials" / f"{body['materialId']}.json",
        body,
    )

def create_qualification_fact(
    *,
    root: Path,
    request_ref: Mapping[str, str],
    material_ref: Mapping[str, str],
    package_acceptance_ref: Mapping[str, str],
    provider_fact_ref: Mapping[str, str],
    uat_fact_ref: Mapping[str, str],
    supply_chain_fact_ref: Mapping[str, str],
    qualified_at: str,
) -> Path:
    root = root.resolve()
    request, request_exact = _exact(root, request_ref, "request")
    material, material_exact = _exact(root, material_ref, "material")
    if (
        material.get("qualificationRequest") != request_exact
        or material.get("buildPolicy") != "build_sign_attest_once"
        or material.get("sourceGitSha") != request.get("sourceGitSha")
        or material.get("sourceTree") != request.get("sourceTree")
    ):
        raise ReleaseQualificationError("material is not build-once for request")
    artifacts = _normalize_artifacts(material.get("artifacts") or ())
    evidence: dict[str, dict[str, str]] = {}
    for name, exact in (
        ("packageAcceptance", package_acceptance_ref),
        ("provider", provider_fact_ref),
        ("uat", uat_fact_ref),
        ("supplyChain", supply_chain_fact_ref),
    ):
        fact, normalized = _exact(root, exact, name)
        if (
            fact.get("status") != "passed"
            or fact.get("materialId") != material.get("materialId")
            or fact.get("sourceGitSha") != request.get("sourceGitSha")
        ):
            raise ReleaseQualificationError(
                f"{name} is not passed for material"
            )
        if name == "packageAcceptance" and fact.get(
            "physicalDevicePlatforms"
        ) != ["android", "ios"]:
            raise ReleaseQualificationError(
                "final package acceptance requires both physical platforms"
            )
        evidence[name] = normalized
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.qualification_fact.v1",
        "decision": "qualified",
        "qualificationRequest": request_exact,
        "candidateMaterialManifest": material_exact,
        "sourceGitSha": request["sourceGitSha"],
        "sourceTree": request["sourceTree"],
        "tagName": request["tagName"],
        "artifactBuildNumber": material["artifactBuildNumber"],
        "artifacts": artifacts,
        "evidence": evidence,
        "qualifiedAt": _text(qualified_at, "qualifiedAt"),
    }
    body["qualificationId"] = digest(body)
    return _write(
        root / "release-qualification/qualified" / f"{body['qualificationId']}.json",
        body,
    )
