"""环境 active candidate 身份解析与候选回执校验。

可被测试 patch 的符号（_current_commit、service_deployment_package_dir、
load_startup_attempt、can_reuse_package、resolve_nonprod_active_candidate）
一律经薄入口 `_pc` 在调用时读取。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import Any

import yaml

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance as _pc
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    output_root,
    runtime_shared_deployment_package_dir,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import startup_attempt_path

from .attestation import _current_contract_graph_digest, _digest_bytes
from .constants import (
    ENVIRONMENTS,
    NATIVE_READBACK_ARTIFACT_RE,
    RELEASE_ENVIRONMENT,
    REMOTE_READBACK_SCHEMA,
    SHA256_PATTERN,
)
from .evidence_store import _output_path

def candidate_image_digest(
    environment: str,
    *,
    registry: Mapping[str, Any] | None = None,
) -> str:
    """Derive the immutable local candidate from capability-owner packages."""
    if environment not in ENVIRONMENTS:
        raise ValueError(
            "local candidate image digest only supports alpha/beta/gamma"
        )
    catalog = registry if registry is not None else governance.load_registry()
    capabilities = catalog.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("Provider registry has no capability catalog")
    services = sorted(
        {
            str(capability.get("service_id") or "").strip()
            for capability in capabilities
            if isinstance(capability, Mapping)
        }
    )
    if not services or any(not service for service in services):
        raise ValueError("Provider capabilities must declare owning service_id")
    current_commit = _pc._current_commit()
    if current_commit is None:
        raise ValueError("cannot derive Provider candidate without current Git revision")

    image_set: list[dict[str, str]] = []
    target = f"{environment}-local"
    for service in services:
        package = _pc.service_deployment_package_dir(
            environment,
            service,
            target=target,
        )
        image_lock_path = package / "image.lock"
        provenance_path = package / "provenance.json"
        if not image_lock_path.is_file() or not provenance_path.is_file():
            raise ValueError(
                f"{environment} Provider candidate package is incomplete: {service}"
            )
        try:
            image_lock = yaml.safe_load(
                image_lock_path.read_text(encoding="utf-8")
            ) or {}
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise ValueError(
                f"{environment} Provider candidate package is unreadable: {service}"
            ) from exc
        if not isinstance(image_lock, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError(
                f"{environment} Provider candidate package is invalid: {service}"
            )
        provenance_digests = provenance.get("digests")
        if not isinstance(provenance_digests, Mapping):
            raise ValueError(
                f"{environment} Provider candidate provenance has no digests: "
                f"{service}"
            )
        image_digest = str(image_lock.get("digest") or "")
        source_tree_digest = str(provenance_digests.get("sourceTree") or "")
        if (
            image_lock.get("service") != service
            or image_lock.get("digestSource") != "build-input"
            or not SHA256_PATTERN.fullmatch(image_digest)
            or image_digest != source_tree_digest
            or provenance.get("service") != service
            or provenance.get("environment") != environment
            or provenance.get("gitRevision") != current_commit
        ):
            raise ValueError(
                f"{environment} Provider candidate package is stale or inconsistent: "
                f"{service}"
            )
        image_set.append({"service": service, "imageDigest": image_digest})

    return _digest_bytes(
        json.dumps(
            {
                "schema": "provider-conformance-candidate-image-set",
                "commit": current_commit,
                "services": image_set,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _artifact_reference(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(output_root().resolve())
    except ValueError as exc:
        raise ValueError("candidate receipt must remain under QWQ_OUTPUT_ROOT") from exc
    return f".qwq_output/{relative.as_posix()}"


def _inactive_candidate(reason: str) -> dict[str, object]:
    return {
        "active": False,
        "receiptRef": "",
        "receiptDigest": "",
        "reason": reason,
    }


def _nonprod_active_candidate_issues(
    *,
    environment: str,
    target: str,
    startup: Mapping[str, Any],
    active: Mapping[str, Any],
    manifest: Mapping[str, Any],
    oci: Mapping[str, Any],
    commit: str,
    image_digest: str,
    contract_graph_digest: str,
    expected_image_digest: str,
    expected_contract_graph_digest: str | None,
) -> list[str]:
    """Validate one canonical startup receipt against its activated package."""
    issues: list[str] = []
    if startup.get("target") != target or startup.get("env") != environment:
        issues.append("startup receipt target/environment mismatch")
    if startup.get("status") != "running":
        issues.append("startup receipt status is not running")
    if startup.get("workload") != "full":
        issues.append("startup receipt workload is not provider-matrix compatible")
    baseline_id = str(active.get("baselineId") or "")
    candidate_digest = str(startup.get("candidateDigest") or "")
    if (
        SHA256_PATTERN.fullmatch(candidate_digest) is None
        or candidate_digest != baseline_id
        or manifest.get("baselineId") != baseline_id
    ):
        issues.append("startup receipt candidateDigest does not bind the active candidate")
    if manifest.get("sourceRevision") != commit:
        issues.append("active candidate commit does not match the executed cell")
    if expected_image_digest != image_digest:
        issues.append("active package image identity does not match the executed cell")
    if (
        expected_contract_graph_digest is None
        or expected_contract_graph_digest != contract_graph_digest
    ):
        issues.append("active candidate ContractGraph does not match the executed cell")

    service_configuration = str(manifest.get("configurationDigest") or "")
    startup_config = str(startup.get("configurationDigest") or "")
    if (
        SHA256_PATTERN.fullmatch(startup_config) is None
        or startup_config != service_configuration
        or oci.get("configurationDigest") != service_configuration
    ):
        issues.append("startup receipt configuration digest is stale")
    if (
        oci.get("schema") != "stackctl-package-oci-images"
        or oci.get("environment") != environment
        or oci.get("target") != target
        or oci.get("imageDigest") != manifest.get("imageDigest")
        or oci.get("buildInputDigest") != manifest.get("buildInputDigest")
    ):
        issues.append("active candidate OCI identity is inconsistent")

    startup_composition = startup.get("imageComposition")
    startup_images = (
        startup_composition.get("images")
        if isinstance(startup_composition, Mapping)
        else None
    )
    oci_images = oci.get("images")
    runtime_refs: dict[str, str] = {}
    if (
        not isinstance(startup_images, Mapping)
        or not isinstance(oci_images, Mapping)
        or set(startup_images) != set(oci_images)
    ):
        issues.append("startup receipt image composition does not match the active package")
    else:
        for service, descriptor in oci_images.items():
            startup_descriptor = startup_images.get(service)
            expected_runtime_image = (
                descriptor.get("imageDigest")
                if isinstance(descriptor, Mapping)
                else None
            )
            startup_ref = (
                startup_descriptor.get("ref")
                if isinstance(startup_descriptor, Mapping)
                else None
            )
            if (
                not isinstance(expected_runtime_image, str)
                or SHA256_PATTERN.fullmatch(expected_runtime_image) is None
                or startup_ref != expected_runtime_image
            ):
                issues.append(
                    f"startup receipt runtime image is stale for {service}"
                )
                continue
            runtime_refs[str(service)] = expected_runtime_image
        if runtime_refs and startup.get("imageTransportTag") != immutable_image_digest(
            runtime_refs
        ):
            issues.append("startup receipt image transport digest is stale")
    return issues


def resolve_nonprod_active_candidate(
    *,
    environment: str,
    registry: Mapping[str, Any],
    commit: str,
    image_digest: str,
    contract_graph_digest: str,
) -> dict[str, object]:
    """Resolve active local runtime identity through canonical receipt loaders."""
    if environment not in ENVIRONMENTS:
        return _inactive_candidate("environment is not a nonprod Provider matrix")
    target = f"{environment}-local"
    try:
        startup = _pc.load_startup_attempt(target)
        if not isinstance(startup, Mapping):
            return _inactive_candidate("canonical startup receipt is missing")
        reusable, reuse_reason = _pc.can_reuse_package(
            environment,
            target,
        )
        if not reusable:
            return _inactive_candidate(
                f"active candidate package is stale: {reuse_reason}"
            )
        active = active_deployment_candidate(target)
        if not isinstance(active, Mapping):
            return _inactive_candidate("active deployment candidate is missing")
        baseline_id = str(active.get("baselineId") or "")
        manifest = load_candidate_manifest(
            environment,
            target,
            baseline_id,
            require_full=True,
        )
        oci_path = (
            runtime_shared_deployment_package_dir(environment, target=target)
            / "oci-images.json"
        )
        oci = json.loads(oci_path.read_text(encoding="utf-8"))
        if not isinstance(oci, Mapping):
            return _inactive_candidate("active candidate OCI receipt is invalid")
        expected_image_digest = candidate_image_digest(
            environment,
            registry=registry,
        )
        expected_contract_graph_digest = _current_contract_graph_digest()
        issues = _nonprod_active_candidate_issues(
            environment=environment,
            target=target,
            startup=startup,
            active=active,
            manifest=manifest,
            oci=oci,
            commit=commit,
            image_digest=image_digest,
            contract_graph_digest=contract_graph_digest,
            expected_image_digest=expected_image_digest,
            expected_contract_graph_digest=expected_contract_graph_digest,
        )
        if issues:
            return _inactive_candidate("; ".join(issues))
        receipt_path = startup_attempt_path(target)
        receipt_raw = receipt_path.read_bytes()
        return {
            "active": True,
            "receiptRef": _artifact_reference(receipt_path),
            "receiptDigest": _digest_bytes(receipt_raw),
            "reason": "",
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _inactive_candidate(str(exc))


def resolve_prod_active_candidate(
    *,
    case_result_path: Path,
    case_result: Mapping[str, Any],
    capability_id: str,
    adapter_id: str,
    image_digest: str,
    config_digest: str,
    contract_graph_digest: str,
    adapter_digest: str,
) -> dict[str, object]:
    """Bind Prod promotability to the canonical native/operator readback."""
    descriptor = case_result.get("nativeReadback")
    if not isinstance(descriptor, Mapping):
        return _inactive_candidate("Prod active candidate readback is unavailable")
    artifact_name = descriptor.get("artifactName")
    artifact_digest = descriptor.get("artifactDigest")
    if (
        not isinstance(artifact_name, str)
        or not NATIVE_READBACK_ARTIFACT_RE.fullmatch(artifact_name)
        or not isinstance(artifact_digest, str)
        or SHA256_PATTERN.fullmatch(artifact_digest) is None
    ):
        return _inactive_candidate("Prod active candidate readback descriptor is invalid")
    receipt_path = case_result_path.parent / artifact_name
    try:
        raw = receipt_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return _inactive_candidate(f"Prod active candidate readback is unreadable: {exc}")
    actual_digest = _digest_bytes(raw)
    if actual_digest != artifact_digest:
        return _inactive_candidate("Prod active candidate readback digest mismatch")
    expected = {
        "schema": REMOTE_READBACK_SCHEMA,
        "status": "passed",
        "capabilityId": capability_id,
        "adapterId": adapter_id,
        "imageDigest": image_digest,
        "configDigest": config_digest,
        "contractGraphDigest": contract_graph_digest,
        "adapterDigest": adapter_digest,
    }
    if not isinstance(payload, Mapping) or any(
        payload.get(field) != value for field, value in expected.items()
    ):
        return _inactive_candidate(
            "Prod active candidate readback does not match the executed cell"
        )
    if payload.get("releaseReadiness") != case_result.get("releaseReadiness"):
        return _inactive_candidate(
            "Prod active candidate readback release readiness is inconsistent"
        )
    return {
        "active": True,
        "receiptRef": _artifact_reference(receipt_path),
        "receiptDigest": actual_digest,
        "reason": "",
    }


def active_candidate_receipt_issues(
    item: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    root: Path,
) -> list[str]:
    """Re-resolve active identity; never trust candidateStatus from evidence."""
    if item.get("candidateStatus") != "active_immutable":
        return []
    environment = str(item.get("environment") or "")
    expected_ref = str(item.get("candidateReceiptRef") or "")
    expected_digest = str(item.get("candidateReceiptDigest") or "")
    if environment in ENVIRONMENTS:
        binding = _pc.resolve_nonprod_active_candidate(
            environment=environment,
            registry=registry,
            commit=str(item.get("commit") or ""),
            image_digest=str(item.get("imageDigest") or ""),
            contract_graph_digest=str(item.get("contractGraphDigest") or ""),
        )
        if (
            binding.get("active") is not True
            or binding.get("receiptRef") != expected_ref
            or binding.get("receiptDigest") != expected_digest
        ):
            return [
                "candidateStatus=active_immutable is not backed by the current "
                f"canonical startup receipt: {binding.get('reason') or 'identity mismatch'}"
            ]
        return []
    if environment != RELEASE_ENVIRONMENT:
        return ["candidateStatus uses an unsupported evidence environment"]

    receipt_path = _output_path(expected_ref, root=root)
    if receipt_path is None or not receipt_path.is_file():
        return ["Prod active candidate readback receipt is unavailable"]
    try:
        raw = receipt_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Prod active candidate readback receipt is unreadable: {exc}"]
    if _digest_bytes(raw) != expected_digest:
        return ["Prod active candidate readback receipt digest mismatch"]
    expected = {
        "schema": REMOTE_READBACK_SCHEMA,
        "status": "passed",
        "capabilityId": item.get("capabilityId"),
        "adapterId": item.get("adapterId"),
        "imageDigest": item.get("imageDigest"),
        "configDigest": item.get("configDigest"),
        "contractGraphDigest": item.get("contractGraphDigest"),
        "adapterDigest": item.get("adapterDigest"),
        "releaseReadiness": item.get("releaseReadiness"),
    }
    if not isinstance(payload, Mapping) or any(
        payload.get(field) != value for field, value in expected.items()
    ):
        return ["Prod active candidate readback does not match evidence identity"]
    return []


def binding_config_digest(
    binding: Mapping[str, Any],
    binding_roots: Iterable[Mapping[str, Any]],
) -> str:
    """Digest the compiled Binding selected for a concrete execution cell."""
    return _digest_bytes(
        json.dumps(
            {
                "binding": binding,
                "bindingRoots": list(binding_roots),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
