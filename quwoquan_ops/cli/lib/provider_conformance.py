"""Validate Provider Conformance evidence and derive evidence-backed readiness."""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.immutable_image_composition import immutable_image_digest
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    output_root,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)
from quwoquan_ops.cli.lib.package_reuse import can_reuse_package
from quwoquan_ops.cli.lib.startup_attempt_receipt import (
    load_startup_attempt,
    startup_attempt_path,
)


EVIDENCE_SCHEMA = ROOT / "quwoquan_ops" / "environments" / "provider_conformance_evidence.schema.json"
# Alpha/Beta/Gamma exercise Port-equivalent substitutes. Prod owns the
# independent hosted real-Provider rollout receipt.
ENVIRONMENTS = ("alpha", "beta", "gamma")
RELEASE_ENVIRONMENT = "prod"
RELEASE_READINESS_ENVIRONMENTS = frozenset({RELEASE_ENVIRONMENT})
EVIDENCE_ENVIRONMENTS = (*ENVIRONMENTS, RELEASE_ENVIRONMENT)
READINESS_ENVIRONMENTS = EVIDENCE_ENVIRONMENTS
LAYERS = ("local_contract", "api_integration", "user_acceptance")
CELL_PROFILES = {
    ("alpha", "local_contract"): "baseline",
    ("beta", "local_contract"): "baseline",
    ("gamma", "local_contract"): "baseline",
    ("alpha", "api_integration"): "smoke",
    ("beta", "api_integration"): "integration",
    ("gamma", "api_integration"): "release",
    ("alpha", "user_acceptance"): "smoke",
    ("beta", "user_acceptance"): "integration",
    ("gamma", "user_acceptance"): "release",
}


def execution_profile_for(environment: str, layer: str) -> str | None:
    """Return the only permitted profile for a conformance evidence cell."""
    if environment == RELEASE_ENVIRONMENT:
        return "release" if layer == "user_acceptance" else None
    return CELL_PROFILES.get((environment, layer))


def requires_release_readiness(environment: str, layer: str) -> bool:
    return environment in RELEASE_READINESS_ENVIRONMENTS and layer == "user_acceptance"
MESSAGE_TRANSPORT_CAPABILITY_ID = governance.MESSAGE_TRANSPORT_CAPABILITY_ID
MESSAGE_TRANSPORT_METRIC_NAMES = governance.MESSAGE_TRANSPORT_REQUIRED_METRICS
MESSAGE_TRANSPORT_METRIC_REFS = {
    "pending_lag": "prometheus://qwq_message_transport_pending_lag",
    "dead_letter": "prometheus://qwq_message_transport_dead_letter",
    "publish_p95": "promql://qwq_message_transport_publish_p95",
    "consume_p95": "promql://qwq_message_transport_consume_p95",
}
REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "artifactRef",
        "artifactDigest",
        "artifactAttestation",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "assertionCount",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "cleanupReceipt",
        "acceptanceRefs",
        "observabilityRefs",
    }
)
RELEASE_READINESS_FIELDS = frozenset(
    {
        "bindingPreflightReceiptRef",
        "adapterHealthReceiptRef",
        "switchCompatibilityReceiptRef",
        "callbackDrainReceiptRef",
        "lastGoodReceiptRef",
        "rollbackReceiptRef",
    }
)
EXECUTION_REPORT_SCHEMA = "provider-conformance-test-report"
EXECUTION_REPORT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "testSource",
        "testCommand",
        "exitCode",
    }
)
CASE_RESULT_SCHEMA = "provider-conformance-case-results"
CASE_RESULT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "status",
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "typedPort",
        "contractRef",
        "networkBoundary",
        "testTarget",
        "configDigest",
        "assertionIds",
        "caseResults",
        "dataDigest",
        "cleanupReceipt",
        "observabilityRefs",
    }
)
CASE_RESULT_RELEASE_FIELDS = frozenset({"releaseReadiness"})
REMOTE_READBACK_SCHEMA = "provider-remote-uat-readback"
CASE_RESULT_REMOTE_FIELDS = frozenset({"nativeReadback"})
NATIVE_READBACK_ARTIFACT_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*\.native-device-readback\.json$"
)
SOURCE_METADATA_RE = re.compile(
    r"^\s*(?:#|//)\s*provider_conformance:\s*(\{.+\})\s*$"
)
SOURCE_STATIC_BLOCK_RE = re.compile(
    r"\b(?:should[\s_-]*block|gate[\s_-]*block|not[\s_-]*run|dry[\s_-]*run)\b",
    re.IGNORECASE,
)
SOURCE_DYNAMIC_EXECUTOR_RE = re.compile(
    r"(?:QWQ_PROVIDER_CONFORMANCE_EXECUTOR_COMMAND_JSON|"
    r"external_provider_executor)",
)
TEST_LAYER_ROOTS = {
    "local_contract": ROOT / "quwoquan_ops" / "tests" / "local_contract",
    "api_integration": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "api_integration",
    "user_acceptance": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance",
}
PUBLIC_ASSERTION_IDS = frozenset(
    {
        "provider.success",
        "provider.validation",
        "provider.auth",
        "provider.network_dns",
        "provider.timeout",
        "provider.throttle",
        "provider.retry",
        "provider.idempotency",
        "provider.callback_ordering",
        "provider.redaction",
        "provider.observability",
    }
)
RELEASE_ASSERTION_IDS = frozenset(
    {
        "provider.adapter_health",
        "provider.adapter_switch",
        "provider.adapter_rollback",
    }
)
ALLOWED_FIELDS = REQUIRED_FIELDS | {"failure", "releaseReadiness"}
ADAPTER_PATTERN = re.compile(r"^(?:ext|infra|data|dev|cap)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
ARTIFACT_ATTESTATION_PATTERN = re.compile(
    r"^(?:hmac-sha256|local-sha256):[a-f0-9]{64}$"
)
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{7,64}$")
ASSERTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
RECEIPT_REF_PATTERN = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
SENSITIVE_RECEIPT_REF_PATTERN = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?|://)", re.IGNORECASE
)
MAX_EVIDENCE_AGE = timedelta(hours=24)


def _issue(location: str, message: str) -> str:
    return f"{location}: {message}"


def _output_path(reference: str, *, root: Path) -> Path | None:
    parts = Path(reference).parts
    if not parts or parts[0] != ".qwq_output":
        return None
    candidate = root / Path(*parts[1:])
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def evidence_files(root: Path | None = None) -> list[Path]:
    base = Path(root) if root is not None else output_root()
    files: list[Path] = []
    for environment in EVIDENCE_ENVIRONMENTS:
        run_root = base / "env" / environment / "runs"
        if run_root.is_dir():
            files.extend(sorted(run_root.rglob("provider-conformance-*.evidence.json")))
    return files


def load_evidence_paths(
    paths: Iterable[Path],
    *,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load one caller-owned evidence set without inheriting historical runs."""
    configured_root = Path(root) if root is not None else output_root()
    resolved_root = configured_root.resolve()
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in sorted(Path(item) for item in paths):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            issues.append(
                _issue(
                    path.as_posix(),
                    "evidence path must be a regular file inside QWQ_OUTPUT_ROOT",
                )
            )
            continue
        if path.is_symlink() or not resolved.is_file():
            issues.append(
                _issue(path.as_posix(), "evidence path must be a regular non-symlink file")
            )
            continue
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue(path.as_posix(), f"invalid evidence JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            issues.append(_issue(path.as_posix(), "evidence root must be an object"))
            continue
        payload["_source"] = path
        evidence.append(payload)
    return evidence, issues


def load_evidence(root: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    return load_evidence_paths(evidence_files(root), root=root)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _root_id_list(root_ids: object) -> list[str] | None:
    if not isinstance(root_ids, list) or not root_ids:
        return None
    if not all(_is_non_empty_string(root_id) for root_id in root_ids):
        return None
    if len(root_ids) != len(set(root_ids)):
        return None
    return list(root_ids)


def _binding_root_ids(roots: object) -> list[str] | None:
    if not isinstance(roots, list) or not roots:
        return None
    if not all(isinstance(root, Mapping) for root in roots):
        return None
    return _root_id_list([root.get("root_id") for root in roots])


def compiled_capability_binding_roots(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
) -> list[dict[str, Any]]:
    """读取 BindingCompiler 唯一输出的 Capability 根组合。"""
    roots_by_capability = compiled.get("capabilityBindingRoots")
    if not isinstance(roots_by_capability, Mapping):
        raise ValueError("compiled provider binding receipt is missing capabilityBindingRoots")
    roots = roots_by_capability.get(capability_id)
    root_ids = _binding_root_ids(roots)
    if root_ids is None:
        raise ValueError(
            f"compiled provider binding receipt has invalid binding roots for {capability_id}"
        )
    return [dict(root) for root in roots]


def required_metric_refs(capability_id: str) -> tuple[str, ...]:
    if capability_id != MESSAGE_TRANSPORT_CAPABILITY_ID:
        return ()
    registry = governance.load_registry()
    capability = next(
        (
            item
            for item in registry.get("capabilities") or []
            if isinstance(item, Mapping)
            and item.get("capability_id") == capability_id
        ),
        None,
    )
    declared_metrics = ()
    if isinstance(capability, Mapping):
        raw_metrics = capability.get("observability_metrics") or ()
        if isinstance(raw_metrics, list):
            declared_metrics = tuple(
                str(metric)
                for metric in raw_metrics
                if isinstance(metric, str) and metric.strip()
            )
    metric_names = declared_metrics or MESSAGE_TRANSPORT_METRIC_NAMES
    return tuple(
        MESSAGE_TRANSPORT_METRIC_REFS.get(
            metric_name,
            f"provider-conformance://{capability_id}/metrics/{metric_name}",
        )
        for metric_name in metric_names
    )


def _selected_binding(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> Mapping[str, Any] | None:
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return None
    environment_bindings = selected_bindings.get(environment)
    if not isinstance(environment_bindings, Mapping):
        return None
    binding = environment_bindings.get(capability_id)
    return binding if isinstance(binding, Mapping) else None


def _selected_adapter_id(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> str | None:
    binding = _selected_binding(
        compiled,
        capability_id=capability_id,
        environment=environment,
    )
    adapter_id = binding.get("adapter_id") if binding is not None else None
    return adapter_id if isinstance(adapter_id, str) else None


def provider_conformance_capability_ids(
    compiled: Mapping[str, Any],
) -> frozenset[str]:
    """Return only capabilities backed by external/infra Provider adapters."""
    declared = compiled.get("providerConformanceCapabilityIds")
    if (
        isinstance(declared, list)
        and len(declared) == len(set(declared))
        and all(isinstance(capability_id, str) for capability_id in declared)
    ):
        return frozenset(declared)
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return frozenset()
    return frozenset(
        str(capability_id)
        for environment_bindings in selected_bindings.values()
        if isinstance(environment_bindings, Mapping)
        for capability_id, binding in environment_bindings.items()
        if isinstance(binding, Mapping)
        and governance.requires_provider_conformance(binding)
    )


def expected_required_cell_keys(
    compiled: Mapping[str, Any],
) -> frozenset[tuple[str, str, str]]:
    """Derive the canonical release cell set from generated Bindings."""
    capability_ids = provider_conformance_capability_ids(compiled)
    if not capability_ids:
        raise ValueError("canonical Provider governance defines no capabilities")
    cells = {
        (capability_id, environment, layer)
        for capability_id in capability_ids
        for environment in ENVIRONMENTS
        for layer in LAYERS
    } | {
        (capability_id, RELEASE_ENVIRONMENT, "user_acceptance")
        for capability_id in capability_ids
    }
    expected_count = len(capability_ids) * (
        len(ENVIRONMENTS) * len(LAYERS) + 1
    )
    if len(cells) != expected_count:
        raise AssertionError(
            "Provider release cell derivation produced duplicate environment/layer keys"
        )
    return frozenset(cells)


def exact_required_cell_issues(
    evidence: Iterable[Mapping[str, Any]],
    *,
    compiled: Mapping[str, Any],
) -> list[str]:
    """Reject missing, duplicate, extra or legacy release evidence cells."""
    expected = expected_required_cell_keys(compiled)
    observed: list[tuple[str, str, str]] = []
    invalid: list[str] = []
    for index, item in enumerate(evidence):
        cell = (
            str(item.get("capabilityId") or ""),
            str(item.get("environment") or ""),
            str(item.get("testLayer") or ""),
        )
        if (
            item.get("schema") != "provider-conformance-evidence"
            or set(REQUIRED_FIELDS) - set(item)
            or cell not in expected
        ):
            invalid.append(f"evidence[{index}]={cell}")
            continue
        observed.append(cell)
    observed_set = set(observed)
    duplicate = sorted(
        cell for cell in observed_set if observed.count(cell) > 1
    )
    missing = sorted(expected - observed_set)
    extra = sorted(observed_set - expected)
    issues: list[str] = []
    if invalid:
        issues.append(
            "Provider release evidence contains non-canonical/legacy cells: "
            + ", ".join(invalid)
        )
    if duplicate:
        issues.append(f"Provider release evidence contains duplicate cells: {duplicate}")
    if missing or extra or len(observed) != len(expected):
        issues.append(
            "Provider release evidence must contain exactly the compiled required cells: "
            f"expected={len(expected)}, observed={len(observed)}, "
            f"missing={missing}, extra={extra}"
        )
    return issues


def _binding_preflight_ready(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> bool:
    readiness = compiled.get("readiness")
    if not isinstance(readiness, Mapping):
        return False
    environment_readiness = readiness.get(environment)
    if not isinstance(environment_readiness, Mapping):
        return False
    binding_readiness = environment_readiness.get(capability_id)
    return isinstance(binding_readiness, Mapping) and bool(
        binding_readiness.get("adapter_preflight_ready")
    )


def _valid_receipt_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and RECEIPT_REF_PATTERN.fullmatch(value) is not None
        and SENSITIVE_RECEIPT_REF_PATTERN.search(value) is None
    )


def network_boundary_for_layer(layer: str) -> str:
    return {
        "local_contract": "offline_harness",
        "api_integration": "remote_protocol",
        "user_acceptance": "user_journey",
    }[layer]


def capability_assertion_id(capability: Mapping[str, Any]) -> str:
    profile = capability.get("conformance_profile")
    if not isinstance(profile, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", profile):
        raise ValueError("capability conformance_profile must be a stable identifier")
    return f"provider.{profile}"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


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
    current_commit = _current_commit()
    if current_commit is None:
        raise ValueError("cannot derive Provider candidate without current Git revision")

    image_set: list[dict[str, str]] = []
    target = f"{environment}-local"
    for service in services:
        package = service_deployment_package_dir(
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
        startup = load_startup_attempt(target)
        if not isinstance(startup, Mapping):
            return _inactive_candidate("canonical startup receipt is missing")
        reusable, reuse_reason = can_reuse_package(
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
        binding = resolve_nonprod_active_candidate(
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


def implementation_digest(path: Path) -> str | None:
    """Digest one Adapter source file or its deterministic source closure."""
    try:
        if path.is_file():
            return _digest_bytes(path.read_bytes())
        if not path.is_dir():
            return None
        source_suffixes = {
            ".c",
            ".cc",
            ".go",
            ".h",
            ".html",
            ".java",
            ".js",
            ".kt",
            ".mod",
            ".proto",
            ".py",
            ".rs",
            ".sh",
            ".sql",
            ".sum",
            ".swift",
            ".tmpl",
            ".ts",
        }
        files = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and candidate.suffix in source_suffixes
            and not candidate.name.endswith("_test.go")
            and not any(
                part in {"testdata", "tests", ".git", ".qwq_output"}
                for part in candidate.relative_to(path).parts
            )
        )
        if not files:
            return None
        digest = hashlib.sha256()
        for candidate in files:
            digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"
    except OSError:
        return None


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


def _source_spec_refs(raw_source: str, *, location: str) -> list[str]:
    refs = [
        match.group(1)
        for line in raw_source.splitlines()
        if (
            match := re.match(r"^\s*(?://|#)\s*spec_ref:\s*(\S+)\s*$", line)
        )
        is not None
    ]
    if not refs:
        raise ValueError(f"{location} must declare at least one spec_ref")
    return list(dict.fromkeys(refs))


def _source_metadata(raw_source: str, *, location: str) -> Mapping[str, Any]:
    declarations = [
        match.group(1)
        for line in raw_source.splitlines()
        if (match := SOURCE_METADATA_RE.match(line)) is not None
    ]
    if len(declarations) != 1:
        raise ValueError(
            f"{location} must declare exactly one provider_conformance JSON header"
        )
    try:
        metadata = json.loads(declarations[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{location} has invalid provider_conformance JSON: {exc}") from exc
    if not isinstance(metadata, Mapping):
        raise ValueError(f"{location} provider_conformance header must be an object")
    return metadata


def load_test_source(
    path: Path,
    *,
    capabilities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load a self-describing executable Provider Conformance source.

    The test source, instead of a registry/manifest, declares its identity,
    exact command and target. Its command must write a CaseResult document to
    ``QWQ_PROVIDER_CONFORMANCE_RESULT_PATH``.
    """
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Provider Conformance test source must be inside the repository") from exc
    if not resolved.is_file() or resolved.suffix not in {".py", ".go"}:
        raise ValueError(f"{relative} is not a supported Provider Conformance test source")
    raw = resolved.read_text(encoding="utf-8")
    metadata = _source_metadata(raw, location=relative)
    required = {
        "adapterId",
        "capabilityId",
        "testLayer",
        "typedPort",
        "contractRef",
        "assertionIds",
        "command",
        "target",
        "networkBoundary",
    }
    if set(metadata) != required:
        raise ValueError(
            f"{relative} provider_conformance header fields must be exactly {sorted(required)}"
        )
    layer = metadata.get("testLayer")
    if layer not in LAYERS:
        raise ValueError(f"{relative} declares an unsupported testLayer")
    layer_root = TEST_LAYER_ROOTS[str(layer)].resolve()
    if layer_root not in resolved.parents:
        raise ValueError(f"{relative} must live under the declared {layer} test root")
    adapter_id = metadata.get("adapterId")
    capability_id = metadata.get("capabilityId")
    typed_port = metadata.get("typedPort")
    contract_ref = metadata.get("contractRef")
    target = metadata.get("target")
    command = metadata.get("command")
    assertion_ids = metadata.get("assertionIds")
    if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
        raise ValueError(f"{relative} declares an invalid adapterId")
    if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
        raise ValueError(f"{relative} declares an invalid capabilityId")
    if not all(_is_non_empty_string(value) for value in (typed_port, contract_ref, target)):
        raise ValueError(f"{relative} must declare typedPort, contractRef and target")
    if (
        not isinstance(command, list)
        or not command
        or not all(_is_non_empty_string(item) and "\n" not in item for item in command)
    ):
        raise ValueError(f"{relative} must declare a concrete argv command")
    if any(
        re.search(r"(?:--dry-run|\bdry[\s_-]*run\b)", item, re.IGNORECASE)
        for item in command
    ):
        raise ValueError(f"{relative} command must not declare a dry-run")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or not all(
            isinstance(assertion_id, str)
            and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        raise ValueError(f"{relative} must declare unique stable assertionIds")
    missing_public = PUBLIC_ASSERTION_IDS - set(assertion_ids)
    if missing_public:
        raise ValueError(
            f"{relative} omits mandatory public assertions {sorted(missing_public)}"
        )
    if capabilities is None:
        capabilities = {
            str(capability["capability_id"]): capability
            for capability in governance.load_registry().get("capabilities", [])
            if isinstance(capability, Mapping) and capability.get("capability_id")
        }
    capability = capabilities.get(str(capability_id))
    if capability is None:
        raise ValueError(f"{relative} declares an unknown capabilityId")
    expected_capability_assertion = capability_assertion_id(capability)
    if expected_capability_assertion not in assertion_ids:
        raise ValueError(
            f"{relative} omits capability assertion {expected_capability_assertion}"
        )
    if typed_port != capability.get("canonical_port"):
        raise ValueError(f"{relative} typedPort does not match the canonical capability Port")
    if contract_ref != capability.get("source"):
        raise ValueError(f"{relative} contractRef does not match the capability source")
    if metadata.get("networkBoundary") != network_boundary_for_layer(str(layer)):
        raise ValueError(f"{relative} networkBoundary conflicts with its testLayer")
    if "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH" not in raw:
        raise ValueError(
            f"{relative} must write command results to QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
        )
    if layer in {"api_integration", "user_acceptance"} and SOURCE_STATIC_BLOCK_RE.search(raw):
        raise ValueError(
            f"{relative} is a static should-block/GATE_BLOCK test and cannot prove remote evidence"
        )
    if SOURCE_DYNAMIC_EXECUTOR_RE.search(raw):
        raise ValueError(
            f"{relative} delegates to a runtime-selected executor and cannot prove "
            "the declared Adapter/target"
        )
    return {
        **dict(metadata),
        "testSource": relative,
        "testSourceDigest": _digest_bytes(raw.encode("utf-8")),
        "acceptanceRefs": _source_spec_refs(raw, location=relative),
    }


def discover_test_sources() -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[str]]:
    """Discover source-declared harnesses without a path or assertion registry."""
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: list[str] = []
    capabilities = {
        str(capability["capability_id"]): capability
        for capability in governance.load_registry().get("capabilities", [])
        if isinstance(capability, Mapping) and capability.get("capability_id")
    }
    for root in TEST_LAYER_ROOTS.values():
        if not root.is_dir():
            continue
        paths = [
            *root.rglob("*provider_conformance*.py"),
            *root.rglob("*provider_conformance*.go"),
        ]
        for path in sorted(paths):
            raw = path.read_text(encoding="utf-8")
            if not any(
                SOURCE_METADATA_RE.match(line) for line in raw.splitlines()
            ):
                continue
            try:
                source = load_test_source(path, capabilities=capabilities)
            except (OSError, ValueError) as exc:
                issues.append(str(exc))
                continue
            key = (
                str(source["capabilityId"]),
                str(source["adapterId"]),
                str(source["testLayer"]),
            )
            if key in sources:
                issues.append(
                    f"{source['testSource']} duplicates Provider Conformance source "
                    f"for capability/adapter/layer {key}"
                )
                continue
            sources[key] = source
    return sources, issues


def source_for_cell(
    *,
    capability_id: str,
    adapter_id: str,
    layer: str,
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> Mapping[str, Any] | None:
    catalog, _ = discover_test_sources() if sources is None else (sources, [])
    return catalog.get((capability_id, adapter_id, layer))


def source_coverage_issues(
    *,
    compiled: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return release-blocking gaps in the selected-Binding source catalog.

    One self-describing source may serve the same Adapter in more than one
    environment, so coverage is evaluated by the unique
    Capability/Adapter/layer key consumed by ``source_for_cell`` rather than
    by blindly counting all nine environment cells.
    """

    catalog, discovery_issues = (
        discover_test_sources() if sources is None else (dict(sources), [])
    )
    issues = list(discovery_issues)
    required: dict[str, set[tuple[str, str]]] = defaultdict(set)
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return [*issues, _issue("source_coverage", "compiled selected Bindings are unavailable")]
    for environment in ENVIRONMENTS:
        environment_bindings = selected_bindings.get(environment)
        if not isinstance(environment_bindings, Mapping):
            issues.append(
                _issue(
                    f"source_coverage.{environment}",
                    "compiled selected Bindings are unavailable",
                )
            )
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if not governance.requires_provider_conformance(binding):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{environment}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].update((adapter_id, layer) for layer in LAYERS)
    release_bindings = selected_bindings.get(RELEASE_ENVIRONMENT)
    if not isinstance(release_bindings, Mapping):
        issues.append(
            _issue(
                f"source_coverage.{RELEASE_ENVIRONMENT}",
                "compiled selected Bindings are unavailable",
            )
        )
    else:
        for capability_id, binding in release_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if not governance.requires_provider_conformance(binding):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{RELEASE_ENVIRONMENT}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].add((adapter_id, "user_acceptance"))
    for capability_id, cells in sorted(required.items()):
        missing = [
            f"{adapter_id}/{layer}"
            for adapter_id, layer in sorted(cells)
            if (capability_id, adapter_id, layer) not in catalog
        ]
        if missing:
            issues.append(
                _issue(
                    f"source_coverage.{capability_id}",
                    "missing self-describing executable sources for " + ", ".join(missing),
                )
            )
    return issues


def local_source_coverage_issues(
    *,
    compiled: Mapping[str, Any],
    environment: str,
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Check only this nonprod target's selected Adapter across all three layers."""
    if environment not in ENVIRONMENTS:
        return [
            _issue(
                "source_coverage",
                f"unsupported nonprod environment {environment}",
            )
        ]
    catalog, discovery_issues = (
        discover_test_sources() if sources is None else (dict(sources), [])
    )
    issues = list(discovery_issues)
    selected_bindings = compiled.get("selectedBindings")
    environment_bindings = (
        selected_bindings.get(environment)
        if isinstance(selected_bindings, Mapping)
        else None
    )
    if not isinstance(environment_bindings, Mapping):
        return [
            *issues,
            _issue(
                f"source_coverage.{environment}",
                "compiled selected Bindings are unavailable",
            ),
        ]
    for capability_id, binding in sorted(environment_bindings.items()):
        if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
            continue
        if not governance.requires_provider_conformance(binding):
            continue
        adapter_id = binding.get("adapter_id")
        if not isinstance(adapter_id, str):
            issues.append(
                _issue(
                    f"source_coverage.{environment}.{capability_id}",
                    "selected Binding has no Adapter ID",
                )
            )
            continue
        missing = [
            f"{adapter_id}/{layer}"
            for layer in LAYERS
            if (capability_id, adapter_id, layer) not in catalog
        ]
        if missing:
            issues.append(
                _issue(
                    f"source_coverage.{environment}.{capability_id}",
                    "missing self-describing executable sources for "
                    + ", ".join(missing),
                )
            )
    return issues


def sign_execution_report(raw: bytes, *, key: str | None = None) -> str:
    """为不可变执行报告生成仅 CI 持有密钥可复核的证明。"""
    signing_key = key or os.environ.get("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", "")
    if not signing_key:
        raise ValueError("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY is required")
    return "hmac-sha256:" + hmac.new(
        signing_key.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()


def current_source_tree_state() -> str:
    """Return clean only when Git proves there are no tracked/untracked changes."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "dirty"
    return "dirty" if completed.stdout else "clean"


def ci_attestation_authority_available(*, commit: str | None = None) -> bool:
    """Recognize the reviewed GitHub workflow authority, never a local key alone."""
    current_commit = commit or _current_commit()
    reviewed_commit = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT",
        "",
    ).strip()
    return (
        os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        and os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY",
            "",
        ).strip()
        == "ci"
        and bool(
            os.environ.get(
                "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
                "",
            ).strip()
        )
        and current_commit is not None
        and reviewed_commit == current_commit
        and current_source_tree_state() == "clean"
    )


def evidence_identity(
    *,
    commit: str,
    candidate_receipt_bound: bool,
    candidate_receipt_ref: str = "",
    candidate_receipt_digest: str = "",
) -> dict[str, object]:
    """Derive signed promotability identity from source, candidate and authority."""
    source_tree_state = current_source_tree_state()
    reviewed = (
        os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        and os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT",
            "",
        ).strip()
        == commit
    )
    ci_authority = (
        reviewed
        and source_tree_state == "clean"
        and ci_attestation_authority_available(commit=commit)
    )
    receipt_identity_complete = (
        bool(candidate_receipt_ref)
        and SHA256_PATTERN.fullmatch(candidate_receipt_digest) is not None
    )
    candidate_status = (
        "active_immutable"
        if candidate_receipt_bound and receipt_identity_complete
        else "unverified"
    )
    non_promotable = not (
        source_tree_state == "clean"
        and reviewed
        and candidate_status == "active_immutable"
        and ci_authority
    )
    return {
        "nonPromotable": non_promotable,
        "sourceTreeState": source_tree_state,
        "commitReview": "reviewed" if reviewed else "unreviewed",
        "candidateStatus": candidate_status,
        "candidateReceiptRef": (
            candidate_receipt_ref if candidate_status == "active_immutable" else ""
        ),
        "candidateReceiptDigest": (
            candidate_receipt_digest if candidate_status == "active_immutable" else ""
        ),
        "attestationAuthority": "ci" if ci_authority else "local",
    }


def attest_execution_report(
    raw: bytes,
    *,
    identity: Mapping[str, object],
) -> str:
    """Use CI HMAC only for promotable identity; local evidence gets a checksum."""
    if identity.get("attestationAuthority") == "ci":
        return sign_execution_report(raw)
    return "local-sha256:" + hashlib.sha256(raw).hexdigest()


def evidence_is_promotable(
    item: Mapping[str, Any],
    *,
    require_runtime_authority: bool = True,
) -> bool:
    intrinsic = (
        item.get("nonPromotable") is False
        and item.get("sourceTreeState") == "clean"
        and item.get("commitReview") == "reviewed"
        and item.get("candidateStatus") == "active_immutable"
        and _is_non_empty_string(item.get("candidateReceiptRef"))
        and _digest(item.get("candidateReceiptDigest")) is not None
        and item.get("attestationAuthority") == "ci"
    )
    if not intrinsic or not require_runtime_authority:
        return intrinsic
    commit = _commit_digest(item.get("commit"))
    return commit is not None and ci_attestation_authority_available(commit=commit)


def _observability_refs_valid(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"logs", "traces", "metrics"}
        and all(
            isinstance(value[facet], list)
            and value[facet]
            and all(_is_non_empty_string(ref) for ref in value[facet])
            for facet in ("logs", "traces", "metrics")
        )
    )


def _native_readback_valid(
    value: object,
    *,
    case_result_path: Path,
) -> bool:
    """Verify the Provider two-device device readback sidecar is present and content-bound."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "artifactName",
        "artifactDigest",
    }:
        return False
    if value.get("schema") != REMOTE_READBACK_SCHEMA:
        return False
    artifact_name = value.get("artifactName")
    artifact_digest = value.get("artifactDigest")
    if (
        not isinstance(artifact_name, str)
        or not NATIVE_READBACK_ARTIFACT_RE.fullmatch(artifact_name)
        or not isinstance(artifact_digest, str)
        or not SHA256_PATTERN.fullmatch(artifact_digest)
    ):
        return False
    artifact_path = case_result_path.parent / artifact_name
    try:
        actual_digest = f"sha256:{hashlib.sha256(artifact_path.read_bytes()).hexdigest()}"
    except OSError:
        return False
    return hmac.compare_digest(artifact_digest, actual_digest)


def load_case_results(
    artifact_path: Path,
    *,
    source: Mapping[str, Any],
    environment: str,
    config_digest: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate the real test-owned CaseResult artifact for one execution cell."""
    issues: list[str] = []
    try:
        result = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [_issue(str(artifact_path), f"invalid CaseResult artifact: {exc}")]
    if not isinstance(result, dict):
        return None, [_issue(str(artifact_path), "CaseResult artifact root must be an object")]
    is_release_case = requires_release_readiness(
        environment,
        str(source.get("testLayer") or ""),
    )
    is_remote_release_case = is_release_case and str(source.get("target") or "").startswith(
        "provider-remote-"
    )
    expected_fields = (
        CASE_RESULT_REQUIRED_FIELDS | CASE_RESULT_RELEASE_FIELDS
        if is_release_case
        else CASE_RESULT_REQUIRED_FIELDS
    )
    allowed_fields = expected_fields | (
        CASE_RESULT_REMOTE_FIELDS if is_remote_release_case else frozenset()
    )
    missing = expected_fields - set(result)
    unknown = set(result) - allowed_fields
    if missing or unknown:
        if missing:
            issues.append(
                _issue(str(artifact_path), f"CaseResult missing fields {sorted(missing)}")
            )
        if unknown:
            issues.append(
                _issue(str(artifact_path), f"CaseResult contains unknown fields {sorted(unknown)}")
            )
        return None, issues
    if result.get("schema") != CASE_RESULT_SCHEMA:
        issues.append(_issue(str(artifact_path), "CaseResult has unsupported schema"))
    expected = {
        "adapterId": source.get("adapterId"),
        "capabilityId": source.get("capabilityId"),
        "environment": environment,
        "testLayer": source.get("testLayer"),
        "typedPort": source.get("typedPort"),
        "contractRef": source.get("contractRef"),
        "networkBoundary": source.get("networkBoundary"),
        "testTarget": source.get("target"),
        "configDigest": config_digest,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"CaseResult {field} does not match the executed source/binding",
                )
            )
    if result.get("status") != "passed":
        issues.append(_issue(str(artifact_path), "CaseResult status must be passed"))
    assertion_ids = result.get("assertionIds")
    expected_assertion_ids = source.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or tuple(sorted(assertion_ids)) != tuple(sorted(expected_assertion_ids or []))
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult assertionIds must exactly match its source-declared assertion set",
            )
        )
    cases = result.get("caseResults")
    if not isinstance(cases, list) or len(cases) != len(assertion_ids or []):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must contain exactly one result for every assertionId",
            )
        )
    else:
        case_ids: list[str] = []
        for case in cases:
            if (
                not isinstance(case, Mapping)
                or set(case) != {"assertionId", "status", "logRef", "traceRef", "metricRefs"}
                or not _is_non_empty_string(case.get("assertionId"))
                or case.get("status") != "passed"
                or not _is_non_empty_string(case.get("logRef"))
                or not _is_non_empty_string(case.get("traceRef"))
                or not isinstance(case.get("metricRefs"), list)
                or not case["metricRefs"]
                or not all(_is_non_empty_string(ref) for ref in case["metricRefs"])
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "every CaseResult must be a passed assertion with log/trace/metric references",
                    )
                )
                break
            case_ids.append(str(case["assertionId"]))
        if sorted(case_ids) != sorted(assertion_ids or []):
            issues.append(
                _issue(
                    str(artifact_path),
                    "CaseResult assertion records must exactly cover assertionIds",
                )
            )
    if not isinstance(result.get("configDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("configDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult configDigest must be sha256"))
    if not isinstance(result.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("dataDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult dataDigest must be sha256"))
    if not _valid_receipt_ref(result.get("cleanupReceipt")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult cleanupReceipt must be a non-sensitive receipt reference",
            )
        )
    if not _observability_refs_valid(result.get("observabilityRefs")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult observabilityRefs must contain logs/traces/metrics",
            )
        )
    elif isinstance(cases, list):
        observability_refs = result["observabilityRefs"]
        for case in cases:
            if not isinstance(case, Mapping):
                continue
            if (
                case.get("logRef") not in observability_refs["logs"]
                or case.get("traceRef") not in observability_refs["traces"]
                or not set(case.get("metricRefs", [])).issubset(
                    set(observability_refs["metrics"])
                )
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "CaseResult observabilityRefs must include each assertion's log/trace/metric references",
                    )
                )
                break
    if is_release_case and not _release_readiness_valid(result):
        issues.append(
            _issue(
                str(artifact_path),
                "release Provider CaseResult must contain test-owned release "
                "readiness receipts",
            )
        )
    if (
        is_remote_release_case
        and "nativeReadback" in result
        and not _native_readback_valid(
            result.get("nativeReadback"),
            case_result_path=artifact_path,
        )
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "Provider two-device Remote CaseResult must bind an existing native-device readback "
                "sidecar with a matching digest",
            )
        )
    if re.search(
        r"(?:endpoint|secret|credential|token|password|https?://)",
        json.dumps(result, sort_keys=True),
        re.IGNORECASE,
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must not contain endpoint, credential, token or URL values",
            )
        )
    return result, issues


def _validate_execution_report(
    *,
    artifact_path: Path,
    evidence: Mapping[str, Any],
    expected_source: Mapping[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    try:
        raw = artifact_path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [_issue(str(artifact_path), f"invalid execution report: {exc}")]
    if not isinstance(report, Mapping):
        return [_issue(str(artifact_path), "execution report root must be an object")]
    fields = set(report)
    missing = EXECUTION_REPORT_REQUIRED_FIELDS - fields
    unknown = fields - EXECUTION_REPORT_REQUIRED_FIELDS
    if missing or unknown:
        if missing:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report missing fields {sorted(missing)}",
                )
            )
        if unknown:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report contains unknown fields {sorted(unknown)}",
                )
            )
        return issues
    if report.get("schema") != EXECUTION_REPORT_SCHEMA:
        issues.append(
            _issue(
                str(artifact_path),
                "execution report has unsupported schema",
            )
        )
    expected_digest = evidence.get("artifactDigest")
    actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if expected_digest != actual_digest:
        issues.append(
            _issue(
                str(artifact_path),
                "artifactDigest does not match the immutable execution report bytes",
            )
        )
    supplied_attestation = evidence.get("artifactAttestation")
    if (
        not isinstance(supplied_attestation, str)
        or not ARTIFACT_ATTESTATION_PATTERN.fullmatch(supplied_attestation)
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "artifactAttestation must be an HMAC-SHA256 or local-SHA256 value",
            )
        )
    elif evidence.get("attestationAuthority") == "local":
        expected_attestation = "local-sha256:" + hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(supplied_attestation, expected_attestation):
            issues.append(
                _issue(
                    str(artifact_path),
                    "local artifactAttestation does not match the execution report checksum",
                )
            )
    elif evidence.get("attestationAuthority") == "ci":
        if not ci_attestation_authority_available(
            commit=_commit_digest(evidence.get("commit"))
        ):
            issues.append(
                _issue(
                    str(artifact_path),
                    "CI attestation authority is unavailable; protected HMAC "
                    "verification was not performed",
                )
            )
        else:
            try:
                expected_attestation = sign_execution_report(raw)
            except ValueError as exc:
                issues.append(_issue(str(artifact_path), str(exc)))
            else:
                if not hmac.compare_digest(supplied_attestation, expected_attestation):
                    issues.append(
                        _issue(
                            str(artifact_path),
                            "artifactAttestation is not trusted for the immutable execution report",
                        )
                    )
    for field in (
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "bindingRoots",
        "testArtifactRef",
        "testArtifactDigest",
        "testSourceDigest",
        "testTarget",
        "typedPort",
        "contractRef",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
    ):
        if report.get(field) != evidence.get(field):
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report {field} does not match evidence",
                )
            )
    if report.get("testSource") != (
        expected_source.get("testSource") if expected_source is not None else None
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "execution report testSource does not match the discovered source contract",
            )
        )
    if not _is_non_empty_string(report.get("testCommand")):
        issues.append(_issue(str(artifact_path), "execution report testCommand is required"))
    if report.get("exitCode") != 0:
        issues.append(_issue(str(artifact_path), "execution report exitCode must be zero"))
    return issues


def _release_readiness_valid(item: Mapping[str, Any]) -> bool:
    release_readiness = item.get("releaseReadiness")
    return (
        isinstance(release_readiness, Mapping)
        and set(release_readiness) == RELEASE_READINESS_FIELDS
        and all(_valid_receipt_ref(release_readiness[field]) for field in RELEASE_READINESS_FIELDS)
    )


def _current_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit if COMMIT_PATTERN.fullmatch(commit) else None


def _current_contract_graph_digest() -> str | None:
    path = ROOT / "quwoquan_service" / "generated" / "contract_graph.json"
    try:
        return _digest_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def _current_adapter_digest(adapter: Mapping[str, Any]) -> str | None:
    implementation_path = adapter.get("implementation_path")
    if not isinstance(implementation_path, str):
        return None
    path = ROOT / implementation_path
    return implementation_digest(path)


def validate_evidence(
    evidence: Iterable[Mapping[str, Any]],
    *,
    registry: Mapping[str, Any],
    root: Path | None = None,
    current_commit: str | None = None,
    compiled: Mapping[str, Any] | None = None,
    source_catalog: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
    expected_image_digest: str | None = None,
) -> list[str]:
    issues: list[str] = []
    compiled_governance = compiled
    if compiled_governance is None:
        compiled_governance, _ = governance.compile_governance(
            registry,
            governance.load_bindings(),
            governance.load_conformance_manifest(),
        )
    discovered_sources, source_issues = (
        discover_test_sources() if source_catalog is None else (dict(source_catalog), [])
    )
    issues.extend(source_issues)
    configured_expected_image = (
        expected_image_digest
        if expected_image_digest is not None
        else os.environ.get("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", "")
    )
    adapter_by_id = {
        str(adapter.get("adapter_id")): adapter
        for adapter in registry.get("adapters", [])
        if isinstance(adapter, Mapping)
    }
    capability_by_id = {
        str(capability.get("capability_id")): capability
        for capability in registry.get("capabilities", [])
        if isinstance(capability, Mapping)
    }
    configured_root = Path(root) if root is not None else output_root()
    duplicate_cells: set[tuple[str, str, str]] = set()
    artifact_refs: set[str] = set()
    for index, item in enumerate(evidence):
        location = str(item.get("_source") or f"evidence[{index}]")
        fields = set(item) - {"_source"}
        missing = REQUIRED_FIELDS - fields
        unknown = fields - ALLOWED_FIELDS
        if missing:
            issues.append(_issue(location, f"missing required fields {sorted(missing)}"))
            continue
        if unknown:
            issues.append(_issue(location, f"contains unknown fields {sorted(unknown)}"))
            continue
        if item.get("schema") != "provider-conformance-evidence":
            issues.append(_issue(location, "has unsupported evidence schema"))
        if not isinstance(item.get("nonPromotable"), bool):
            issues.append(_issue(location, "nonPromotable must be a boolean"))
        if item.get("sourceTreeState") not in {"clean", "dirty"}:
            issues.append(_issue(location, "sourceTreeState must be clean or dirty"))
        if item.get("commitReview") not in {"reviewed", "unreviewed"}:
            issues.append(_issue(location, "commitReview must be reviewed or unreviewed"))
        if item.get("candidateStatus") not in {"active_immutable", "unverified"}:
            issues.append(
                _issue(
                    location,
                    "candidateStatus must be active_immutable or unverified",
                )
            )
        candidate_receipt_ref = item.get("candidateReceiptRef")
        candidate_receipt_digest = item.get("candidateReceiptDigest")
        if item.get("candidateStatus") == "active_immutable":
            if (
                not isinstance(candidate_receipt_ref, str)
                or not candidate_receipt_ref.startswith(
                    f".qwq_output/env/{item.get('environment')}/"
                )
                or not isinstance(candidate_receipt_digest, str)
                or SHA256_PATTERN.fullmatch(candidate_receipt_digest) is None
            ):
                issues.append(
                    _issue(
                        location,
                        "active candidate requires a canonical receipt ref and digest",
                    )
                )
        elif candidate_receipt_ref != "" or candidate_receipt_digest != "":
            issues.append(
                _issue(
                    location,
                    "unverified candidate must not claim a candidate receipt",
                )
            )
        if item.get("attestationAuthority") not in {"ci", "local"}:
            issues.append(_issue(location, "attestationAuthority must be ci or local"))
        if (
            item.get("sourceTreeState") == "dirty"
            or item.get("commitReview") != "reviewed"
            or item.get("candidateStatus") != "active_immutable"
            or item.get("attestationAuthority") != "ci"
        ) and item.get("nonPromotable") is not True:
            issues.append(
                _issue(
                    location,
                    "dirty/unreviewed/non-CI/unverified evidence must fail closed "
                    "with nonPromotable=true",
                )
            )
        supplied_attestation = item.get("artifactAttestation")
        if (
            item.get("attestationAuthority") == "local"
            and isinstance(supplied_attestation, str)
            and not supplied_attestation.startswith("local-sha256:")
        ):
            issues.append(
                _issue(
                    location,
                    "local attestation authority must use a local-sha256 checksum",
                )
            )
        if (
            item.get("attestationAuthority") == "ci"
            and isinstance(supplied_attestation, str)
            and not supplied_attestation.startswith("hmac-sha256:")
        ):
            issues.append(
                _issue(
                    location,
                    "CI attestation authority must use an HMAC-SHA256 attestation",
                )
            )
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
            issues.append(_issue(location, "adapterId must be a stable Adapter ID"))
            continue
        adapter = adapter_by_id.get(adapter_id)
        if adapter is None:
            issues.append(_issue(location, "adapterId is not registered"))
            continue
        capability = (
            capability_by_id.get(capability_id)
            if isinstance(capability_id, str)
            else None
        )
        if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
            issues.append(_issue(location, "capabilityId must be a stable Capability ID"))
        elif adapter.get("capability_id") != capability_id:
            issues.append(_issue(location, "capabilityId does not match adapterId"))
        elif not _is_non_empty_string(
            (capability_by_id.get(capability_id) or {}).get("canonical_port")
        ):
            issues.append(
                _issue(
                    location,
                    "capabilityId does not resolve to a registered canonical typed Port",
                )
            )
        elif item.get("typedPort") != capability.get("canonical_port"):
            issues.append(
                _issue(location, "typedPort does not match the capability canonical typed Port")
            )
        elif item.get("contractRef") != capability.get("source"):
            issues.append(
                _issue(location, "contractRef does not match the capability contract source")
            )
        evidence_root_ids = _root_id_list(item.get("bindingRoots"))
        if evidence_root_ids is None:
            issues.append(
                _issue(location, "bindingRoots must be a non-empty unique ordered root_id list")
            )
        elif not isinstance(capability, Mapping):
            issues.append(
                _issue(location, "bindingRoots cannot resolve an evidence capability")
            )
        else:
            registry_root_ids = _binding_root_ids(capability.get("binding_roots"))
            try:
                compiled_roots = compiled_capability_binding_roots(
                    compiled_governance,
                    capability_id=capability_id,
                )
            except ValueError as exc:
                issues.append(_issue(location, str(exc)))
            else:
                compiled_root_ids = _binding_root_ids(compiled_roots)
                if registry_root_ids is None or compiled_root_ids is None:
                    issues.append(
                        _issue(
                            location,
                            "registry/compiled capability binding roots must be non-empty and unique",
                        )
                    )
                elif registry_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "registry and compiled capability binding roots diverge",
                        )
                    )
                elif evidence_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "bindingRoots must strictly match registry/compiled capability roots",
                        )
                    )
        environment = item.get("environment")
        layer = item.get("testLayer")
        expected_source: Mapping[str, Any] | None = None
        selected_binding: Mapping[str, Any] | None = None
        compiled_roots: list[dict[str, Any]] | None = None
        expected_profile = (
            execution_profile_for(environment, layer)
            if isinstance(environment, str) and isinstance(layer, str)
            else None
        )
        if expected_profile is None:
            issues.append(_issue(location, "environment/testLayer is not a required conformance cell"))
        elif item.get("executionProfile") != expected_profile:
            issues.append(_issue(location, "executionProfile does not match the nine-cell contract"))
        else:
            selected_binding = _selected_binding(
                compiled_governance,
                capability_id=capability_id,
                environment=environment,
            )
            selected_adapter_id = (
                selected_binding.get("adapter_id")
                if isinstance(selected_binding, Mapping)
                else None
            )
            if not isinstance(selected_adapter_id, str):
                issues.append(
                    _issue(
                        location,
                        "capability has no selected Binding adapter in this evidence environment",
                    )
                )
            elif not governance.requires_provider_conformance(selected_binding):
                issues.append(
                    _issue(
                        location,
                        "first-party authority Bindings are not Provider Conformance cells",
                    )
                )
            elif adapter_id != selected_adapter_id:
                issues.append(
                    _issue(
                        location,
                        "adapterId does not match the environment-selected Binding adapter",
                    )
                )
            expected_source = source_for_cell(
                capability_id=str(capability_id),
                adapter_id=adapter_id,
                layer=layer,
                sources=discovered_sources,
            )
            if expected_source is None:
                issues.append(
                    _issue(
                        location,
                        "no self-describing executable Provider Conformance source exists "
                        "for the selected capability/adapter/layer",
                    )
                )
            else:
                if item.get("testSource") != expected_source.get("testSource"):
                    issues.append(
                        _issue(location, "testSource does not match the discovered source contract")
                    )
                if item.get("testSourceDigest") != expected_source.get("testSourceDigest"):
                    issues.append(
                        _issue(location, "testSourceDigest does not match current source bytes")
                    )
                if item.get("testTarget") != expected_source.get("target"):
                    issues.append(
                        _issue(location, "testTarget does not match the discovered source contract")
                    )
                if item.get("typedPort") != expected_source.get("typedPort"):
                    issues.append(
                        _issue(location, "typedPort does not match the discovered source contract")
                    )
                if item.get("contractRef") != expected_source.get("contractRef"):
                    issues.append(
                        _issue(location, "contractRef does not match the discovered source contract")
                    )
                if item.get("networkBoundary") != expected_source.get("networkBoundary"):
                    issues.append(
                        _issue(location, "networkBoundary does not match the discovered source contract")
                    )
                if item.get("acceptanceRefs") != expected_source.get("acceptanceRefs"):
                    issues.append(
                        _issue(location, "acceptanceRefs must exactly match source spec_ref values")
                    )
            if isinstance(selected_binding, Mapping):
                try:
                    compiled_roots = compiled_capability_binding_roots(
                        compiled_governance,
                        capability_id=str(capability_id),
                    )
                except ValueError:
                    compiled_roots = None
            implementation_status = adapter.get("implementation_status")
            accepted_statuses = (
                governance.READY_IMPLEMENTATION_STATUSES
                if environment in governance.RELEASE_ADAPTER_ENVIRONMENTS
                else {
                    *governance.READY_IMPLEMENTATION_STATUSES,
                    "sandbox",
                }
            )
            if implementation_status not in accepted_statuses:
                issues.append(
                    _issue(
                        location,
                        "adapterId implementation is not eligible for this environment evidence",
                    )
                )
        cell = (str(capability_id), str(environment), str(layer))
        if cell in duplicate_cells:
            issues.append(_issue(location, "duplicates a Capability/environment/layer cell"))
        duplicate_cells.add(cell)
        if item.get("status") != "passed":
            issues.append(
                _issue(
                    location,
                    "blocked/failed/dry-run reports are not Provider Conformance evidence",
                )
            )
        parsed_time: datetime | None = None
        try:
            parsed_time = datetime.fromisoformat(str(item["executedAt"]).replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("missing timezone")
            if parsed_time > datetime.now(timezone.utc):
                issues.append(_issue(location, "executedAt cannot be in the future"))
            elif current_commit is not None and datetime.now(timezone.utc) - parsed_time > MAX_EVIDENCE_AGE:
                issues.append(_issue(location, "executedAt exceeds the 24-hour readiness window"))
        except (TypeError, ValueError):
            issues.append(_issue(location, "executedAt must be an ISO-8601 timestamp with timezone"))
        artifact_path: Path | None = None
        test_artifact_path: Path | None = None
        for field, destination in (
            ("artifactRef", "execution"),
            ("testArtifactRef", "test"),
        ):
            reference = item.get(field)
            if not isinstance(reference, str) or not reference.startswith(
                f".qwq_output/env/{environment}/runs/"
            ):
                issues.append(
                    _issue(location, f"{field} must remain inside its environment run root")
                )
                continue
            path = _output_path(reference, root=configured_root)
            if path is None or not path.exists():
                issues.append(_issue(location, f"{field} must resolve to an existing output artifact"))
            elif configured_root.resolve() not in path.parents and path != configured_root:
                issues.append(_issue(location, f"{field} escapes configured output root"))
            elif reference in artifact_refs:
                issues.append(_issue(location, f"{field} must identify one conformance cell only"))
            artifact_refs.add(reference)
            if destination == "execution":
                artifact_path = path
            else:
                test_artifact_path = path
        for field in (
            "artifactDigest",
            "testArtifactDigest",
            "testSourceDigest",
            "imageDigest",
            "configDigest",
            "contractGraphDigest",
            "adapterDigest",
        ):
            if not isinstance(item.get(field), str) or not SHA256_PATTERN.fullmatch(str(item[field])):
                issues.append(_issue(location, f"{field} must be a sha256 digest"))
        if artifact_path is not None and artifact_path.exists():
            issues.extend(
                _validate_execution_report(
                    artifact_path=artifact_path,
                    evidence=item,
                    expected_source=expected_source,
                )
            )
        if test_artifact_path is not None and test_artifact_path.exists():
            expected_test_artifact_digest = _digest_bytes(test_artifact_path.read_bytes())
            if item.get("testArtifactDigest") != expected_test_artifact_digest:
                issues.append(
                    _issue(
                        location,
                        "testArtifactDigest does not match the test-owned CaseResult artifact",
                    )
                )
            if expected_source is not None and isinstance(environment, str):
                _, case_result_issues = load_case_results(
                    test_artifact_path,
                    source=expected_source,
                    environment=environment,
                    config_digest=str(item.get("configDigest") or ""),
                )
                issues.extend(case_result_issues)
        if not isinstance(item.get("commit"), str) or not COMMIT_PATTERN.fullmatch(str(item["commit"])):
            issues.append(_issue(location, "commit must be a git commit digest"))
        elif current_commit is not None and item["commit"] != current_commit:
            issues.append(_issue(location, "commit does not match the current source revision"))
        expected_image = configured_expected_image
        if expected_image_digest is None and environment in ENVIRONMENTS:
            try:
                expected_image = candidate_image_digest(
                    str(environment),
                    registry=registry,
                )
            except ValueError as exc:
                issues.append(_issue(location, str(exc)))
                expected_image = ""
        if not isinstance(expected_image, str) or not SHA256_PATTERN.fullmatch(expected_image):
            issues.append(
                _issue(
                    location,
                    "active immutable candidate image digest is unavailable",
                )
            )
        elif item.get("imageDigest") != expected_image:
            issues.append(_issue(location, "imageDigest does not match the active immutable image"))
        for candidate_issue in active_candidate_receipt_issues(
            item,
            registry=registry,
            root=configured_root,
        ):
            issues.append(_issue(location, candidate_issue))
        if isinstance(selected_binding, Mapping) and compiled_roots is not None:
            current_config_digest = binding_config_digest(selected_binding, compiled_roots)
            if item.get("configDigest") != current_config_digest:
                issues.append(
                    _issue(location, "configDigest does not match the current selected Binding")
                )
        current_contract_graph_digest = _current_contract_graph_digest()
        if current_contract_graph_digest is None:
            issues.append(_issue(location, "current ContractGraph digest is unavailable"))
        elif item.get("contractGraphDigest") != current_contract_graph_digest:
            issues.append(_issue(location, "contractGraphDigest is stale"))
        current_adapter_digest = _current_adapter_digest(adapter)
        if current_adapter_digest is None:
            issues.append(_issue(location, "current Adapter digest is unavailable"))
        elif item.get("adapterDigest") != current_adapter_digest:
            issues.append(_issue(location, "adapterDigest is stale"))
        if not isinstance(item.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(str(item["dataDigest"])):
            issues.append(_issue(location, "dataDigest must be a sha256 digest"))
        if not isinstance(item.get("assertionCount"), int) or item["assertionCount"] <= 0:
            issues.append(_issue(location, "assertionCount must be greater than zero"))
        assertion_ids = item.get("assertionIds")
        if (
            not isinstance(assertion_ids, list)
            or not assertion_ids
            or not all(
                isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
                for assertion_id in assertion_ids
            )
            or len(assertion_ids) != len(set(assertion_ids))
        ):
            issues.append(_issue(location, "assertionIds must be a non-empty unique stable list"))
        else:
            if not PUBLIC_ASSERTION_IDS.issubset(set(assertion_ids)):
                issues.append(
                    _issue(
                        location,
                        "assertionIds omit mandatory public Provider scenarios",
                    )
                )
            if expected_source is not None and tuple(sorted(assertion_ids)) != tuple(
                sorted(expected_source.get("assertionIds", []))
            ):
                issues.append(
                    _issue(
                        location,
                        "assertionIds must exactly match the discovered source assertion set",
                    )
                )
            if item.get("assertionCount") != len(assertion_ids):
                issues.append(_issue(location, "assertionCount must equal assertionIds length"))
        if item.get("networkBoundary") not in {
            "offline_harness",
            "remote_protocol",
            "user_journey",
        }:
            issues.append(_issue(location, "networkBoundary is invalid"))
        elif layer == "local_contract" and item["networkBoundary"] != "offline_harness":
            issues.append(_issue(location, "local_contract must use offline_harness"))
        elif layer == "api_integration" and item["networkBoundary"] != "remote_protocol":
            issues.append(_issue(location, "api_integration must use remote_protocol"))
        elif layer == "user_acceptance" and item["networkBoundary"] != "user_journey":
            issues.append(_issue(location, "user_acceptance must use user_journey"))
        if not _valid_receipt_ref(item.get("cleanupReceipt")):
            issues.append(
                _issue(location, "cleanupReceipt must be a non-sensitive receipt reference")
            )
        acceptance_refs = item.get("acceptanceRefs")
        if not isinstance(acceptance_refs, list) or not acceptance_refs or not all(
            isinstance(ref, str) and ref.startswith("specs/feature-tree/") for ref in acceptance_refs
        ):
            issues.append(
                _issue(location, "acceptanceRefs must be non-empty feature-tree references")
            )
        if (
            expected_source is not None
            and acceptance_refs != expected_source.get("acceptanceRefs")
        ):
            issues.append(
                _issue(location, "acceptanceRefs must exactly match source spec_ref values")
            )
        observability_refs = item.get("observabilityRefs")
        if not _observability_refs_valid(observability_refs):
            issues.append(
                _issue(location, "observabilityRefs must contain non-empty logs/traces/metrics lists")
            )
        else:
            required_metric_refs_for_capability = required_metric_refs(
                capability_id if isinstance(capability_id, str) else ""
            )
            if not set(required_metric_refs_for_capability).issubset(
                set(observability_refs["metrics"])
            ):
                issues.append(
                    _issue(
                        location,
                        "runtime.message.transport metrics must include fixed non-sensitive "
                        "pending_lag/dead_letter/publish_p95/consume_p95 references",
                    )
                )
        if item["status"] == "passed" and "failure" in item:
            issues.append(_issue(location, "passed evidence must not contain failure"))
        if expected_source is not None and item.get("testCommand") != shlex.join(
            list(expected_source["command"])
        ):
            issues.append(
                _issue(location, "testCommand does not match the source-declared executable argv")
            )
        is_release_cell = requires_release_readiness(str(environment), str(layer))
        if is_release_cell and not _release_readiness_valid(item):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance requires adapter-health, "
                    "switch and rollback receipt references",
                )
            )
        if is_release_cell and not RELEASE_ASSERTION_IDS.issubset(
            set(assertion_ids) if isinstance(assertion_ids, list) else set()
        ):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance must execute "
                    "adapter health/switch/rollback assertions",
                )
            )
        elif not is_release_cell and "releaseReadiness" in item:
            issues.append(
                _issue(
                    location,
                    "releaseReadiness is reserved for Gamma/Prod release "
                    "user_acceptance cells",
                )
            )
    return issues


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and SHA256_PATTERN.fullmatch(value) else None


def _commit_digest(value: object) -> str | None:
    return value if isinstance(value, str) and COMMIT_PATTERN.fullmatch(value) else None


def _assertion_semantics(cell: Mapping[str, Any]) -> tuple[str, ...] | None:
    assertion_ids = cell.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or not all(
            isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        return None
    return tuple(
        sorted(
            assertion_id
            for assertion_id in assertion_ids
            if assertion_id not in RELEASE_ASSERTION_IDS
        )
    )


def _cells_share_release(
    cells: Iterable[Mapping[str, Any] | None],
    *,
    expected_environments: Iterable[str],
    require_adapter_digest: bool,
) -> bool:
    evidence_cells = list(cells)
    if not evidence_cells or any(
        cell is None or cell.get("status") != "passed" for cell in evidence_cells
    ):
        return False
    concrete_cells = [cell for cell in evidence_cells if cell is not None]
    if any(
        not evidence_is_promotable(
            cell,
            require_runtime_authority=False,
        )
        for cell in concrete_cells
    ):
        return False
    release_digests = {
        (
            _commit_digest(cell.get("commit")),
            _digest(cell.get("imageDigest")),
            _digest(cell.get("contractGraphDigest")),
        )
        for cell in concrete_cells
    }
    if len(release_digests) != 1 or any(None in digest for digest in release_digests):
        return False
    release_commit = next(iter(release_digests))[0]
    if not isinstance(release_commit, str) or not ci_attestation_authority_available(
        commit=release_commit
    ):
        return False
    if len({_assertion_semantics(cell) for cell in concrete_cells}) != 1:
        return False
    if any(_assertion_semantics(cell) is None for cell in concrete_cells):
        return False
    if (
        len({cell.get("typedPort") for cell in concrete_cells}) != 1
        or len({cell.get("contractRef") for cell in concrete_cells}) != 1
    ):
        return False
    for environment in expected_environments:
        environment_cells = [
            cell for cell in concrete_cells if cell.get("environment") == environment
        ]
        if not environment_cells or len(
            {_digest(cell.get("configDigest")) for cell in environment_cells}
        ) != 1:
            return False
        if _digest(environment_cells[0].get("configDigest")) is None:
            return False
    if require_adapter_digest:
        adapter_digests = {_digest(cell.get("adapterDigest")) for cell in concrete_cells}
        if len(adapter_digests) != 1 or None in adapter_digests:
            return False
    return True


def _cells_share_local_candidate(
    cells: Iterable[Mapping[str, Any] | None],
    *,
    environment: str,
) -> bool:
    """Prove one capability's three layers share one active local candidate.

    Local authority is intentionally accepted here, but it remains explicitly
    non-promotable.  This predicate never participates in release readiness.
    """
    evidence_cells = list(cells)
    if len(evidence_cells) != len(LAYERS) or any(
        cell is None
        or cell.get("status") != "passed"
        or cell.get("environment") != environment
        or cell.get("candidateStatus") != "active_immutable"
        for cell in evidence_cells
    ):
        return False
    concrete_cells = [cell for cell in evidence_cells if cell is not None]
    for cell in concrete_cells:
        authority = cell.get("attestationAuthority")
        attestation = cell.get("artifactAttestation")
        if authority == "local":
            if (
                cell.get("nonPromotable") is not True
                or not isinstance(attestation, str)
                or not attestation.startswith("local-sha256:")
            ):
                return False
        elif authority == "ci":
            if (
                not evidence_is_promotable(
                    cell,
                    require_runtime_authority=False,
                )
                or not isinstance(attestation, str)
                or not attestation.startswith("hmac-sha256:")
            ):
                return False
        else:
            return False
    candidate_identities = {
        (
            _commit_digest(cell.get("commit")),
            _digest(cell.get("imageDigest")),
            _digest(cell.get("contractGraphDigest")),
            cell.get("candidateReceiptRef"),
            _digest(cell.get("candidateReceiptDigest")),
        )
        for cell in concrete_cells
    }
    if len(candidate_identities) != 1 or any(
        value is None or not value
        for value in next(iter(candidate_identities), ())
    ):
        return False
    if (
        len({cell.get("adapterId") for cell in concrete_cells}) != 1
        or len({_digest(cell.get("adapterDigest")) for cell in concrete_cells}) != 1
        or len({_digest(cell.get("configDigest")) for cell in concrete_cells}) != 1
        or len({cell.get("typedPort") for cell in concrete_cells}) != 1
        or len({cell.get("contractRef") for cell in concrete_cells}) != 1
        or len({_assertion_semantics(cell) for cell in concrete_cells}) != 1
        or any(_assertion_semantics(cell) is None for cell in concrete_cells)
    ):
        return False
    return all(
        _digest(cell.get("adapterDigest")) is not None
        and _digest(cell.get("configDigest")) is not None
        for cell in concrete_cells
    )


def local_functional_readiness_issues(
    *,
    compiled: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
    environment: str,
) -> list[str]:
    """Validate one nonprod environment's compiled cells without release claims."""
    if environment not in ENVIRONMENTS:
        return [
            _issue(
                "local_functional_readiness",
                f"unsupported nonprod environment {environment}",
            )
        ]
    capability_ids = provider_conformance_capability_ids(compiled)
    expected = {
        (capability_id, environment, layer)
        for capability_id in capability_ids
        for layer in LAYERS
    }
    evidence_cells = list(evidence)
    observed = [
        (
            str(item.get("capabilityId") or ""),
            str(item.get("environment") or ""),
            str(item.get("testLayer") or ""),
        )
        for item in evidence_cells
    ]
    observed_set = set(observed)
    issues: list[str] = []
    duplicate = sorted(cell for cell in observed_set if observed.count(cell) > 1)
    missing = sorted(expected - observed_set)
    extra = sorted(observed_set - expected)
    expected_count = len(capability_ids) * len(LAYERS)
    if not capability_ids or len(expected) != expected_count:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "generated Bindings must derive a non-empty unique capability/cell set",
            )
        )
    if duplicate:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                f"current invocation contains duplicate cells: {duplicate}",
            )
        )
    if missing or extra or len(observed) != len(expected):
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "current invocation must contain exactly the environment's "
                f"{expected_count} compiled cells: observed={len(observed)}, "
                f"missing={missing}, extra={extra}",
            )
        )
    candidate_identities = {
        (
            _commit_digest(item.get("commit")),
            _digest(item.get("imageDigest")),
            _digest(item.get("contractGraphDigest")),
            item.get("candidateReceiptRef"),
            _digest(item.get("candidateReceiptDigest")),
        )
        for item in evidence_cells
    }
    if not evidence_cells or len(candidate_identities) != 1 or any(
        value is None or not value
        for value in next(iter(candidate_identities), ())
    ):
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "all cells must bind one active immutable candidate identity",
            )
        )
    by_key = {
        (
            str(item.get("capabilityId") or ""),
            str(item.get("testLayer") or ""),
        ): item
        for item in evidence_cells
        if item.get("environment") == environment
    }
    for capability_id in sorted(capability_ids):
        binding = _selected_binding(
            compiled,
            capability_id=capability_id,
            environment=environment,
        )
        selected_adapter = (
            binding.get("adapter_id") if isinstance(binding, Mapping) else None
        )
        cells = [by_key.get((capability_id, layer)) for layer in LAYERS]
        if (
            not isinstance(binding, Mapping)
            or binding.get("state") != "enabled"
            or not governance.requires_provider_conformance(binding)
            or not isinstance(selected_adapter, str)
            or any(
                cell is not None and cell.get("adapterId") != selected_adapter
                for cell in cells
            )
            or not _binding_preflight_ready(
                compiled,
                capability_id=capability_id,
                environment=environment,
            )
            or not _cells_share_local_candidate(cells, environment=environment)
        ):
            issues.append(
                _issue(
                    f"local_functional_readiness.{environment}.{capability_id}",
                    "selected Adapter lacks a candidate-bound three-layer local closure",
                )
            )
    return issues


def load_validate_local_functional_readiness(
    paths: Iterable[Path],
    *,
    environment: str,
    compiled: Mapping[str, Any],
    registry: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]],
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate only the evidence emitted by one stackctl environment attempt."""
    evidence, load_issues = load_evidence_paths(paths, root=root)
    current_commit = _current_commit()
    issues = [*load_issues]
    if evidence and current_commit is None:
        issues.append(
            _issue(
                f"local_functional_readiness.{environment}",
                "cannot determine the current git revision",
            )
        )
    issues.extend(
        local_source_coverage_issues(
            compiled=compiled,
            environment=environment,
            sources=sources,
        )
    )
    issues.extend(
        validate_evidence(
            evidence,
            registry=registry,
            root=root,
            current_commit=current_commit,
            compiled=compiled,
            source_catalog=sources,
        )
    )
    issues.extend(
        local_functional_readiness_issues(
            compiled=compiled,
            evidence=evidence,
            environment=environment,
        )
    )
    return evidence, list(dict.fromkeys(issues))


def derive_readiness(
    *,
    compiled: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    by_cell: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    conformance_capability_ids = provider_conformance_capability_ids(compiled)
    for item in evidence:
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        environment = item.get("environment")
        layer = item.get("testLayer")
        if all(isinstance(value, str) for value in (adapter_id, capability_id, environment, layer)):
            if (
                _selected_adapter_id(
                    compiled,
                    capability_id=capability_id,
                    environment=environment,
                )
                == adapter_id
                and execution_profile_for(environment, layer) is not None
            ):
                by_cell[(capability_id, environment, layer)] = item

    selected_adapter_environments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for environment in ENVIRONMENTS:
        selected_bindings = compiled.get("selectedBindings", {})
        environment_bindings = (
            selected_bindings.get(environment)
            if isinstance(selected_bindings, Mapping)
            else None
        )
        if not isinstance(environment_bindings, Mapping):
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            if capability_id not in conformance_capability_ids:
                continue
            adapter_id = binding.get("adapter_id")
            if isinstance(adapter_id, str):
                selected_adapter_environments[(capability_id, adapter_id)].add(environment)

    adapter_ready: dict[tuple[str, str], bool] = {}
    for (capability_id, adapter_id), selected_environments in selected_adapter_environments.items():
        expected_cells = [
            by_cell.get((capability_id, environment, layer))
            for environment in sorted(selected_environments)
            for layer in LAYERS
        ]
        adapter_evidence_ready = _cells_share_release(
            expected_cells,
            expected_environments=selected_environments,
            require_adapter_digest=True,
        )
        preflight_ready = all(
            _binding_preflight_ready(
                compiled,
                capability_id=capability_id,
                environment=environment,
            )
            for environment in selected_environments
        )
        adapter_ready[(capability_id, adapter_id)] = (
            adapter_evidence_ready and preflight_ready
        )

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for environment, capabilities in compiled.get("readiness", {}).items():
        environment_result: dict[str, dict[str, Any]] = {}
        for capability_id, baseline in capabilities.items():
            item = dict(baseline)
            adapter_id = item.get("adapter_id")
            provider_conformance_required = (
                capability_id in conformance_capability_ids
            )
            item["provider_conformance_required"] = provider_conformance_required
            if not provider_conformance_required:
                preflight_ready = bool(item.get("adapter_preflight_ready"))
                item["evidence_ready"] = False
                item["adapter_ready"] = preflight_ready
                item["matrix_selected_adapters_ready"] = True
                if environment == RELEASE_ENVIRONMENT:
                    item["prod_remote_release_ready"] = False
                item["capability_ready"] = (
                    item.get("state") == "enabled" and preflight_ready
                )
                environment_result[capability_id] = item
                continue
            expected_cells = [
                by_cell.get((capability_id, evidence_environment, layer))
                for evidence_environment in ENVIRONMENTS
                for layer in LAYERS
            ]
            capability_matrix_ready = _cells_share_release(
                expected_cells,
                expected_environments=ENVIRONMENTS,
                require_adapter_digest=False,
            )
            prod_remote_release_cell = by_cell.get(
                (capability_id, RELEASE_ENVIRONMENT, "user_acceptance")
            )
            prod_remote_release_ready = (
                prod_remote_release_cell is not None
                and prod_remote_release_cell.get("status") == "passed"
                and _release_readiness_valid(prod_remote_release_cell)
            )
            matrix_selected_adapters_ready = all(
                adapter_ready.get(
                    (
                        capability_id,
                        _selected_adapter_id(
                            compiled,
                            capability_id=capability_id,
                            environment=evidence_environment,
                        ),
                    ),
                    False,
                )
                for evidence_environment in ENVIRONMENTS
            )
            selected_adapter_ready = (
                adapter_ready.get((capability_id, adapter_id), False)
                if isinstance(adapter_id, str)
                else False
            )
            item["evidence_ready"] = capability_matrix_ready
            item["adapter_ready"] = selected_adapter_ready
            item["matrix_selected_adapters_ready"] = matrix_selected_adapters_ready
            if environment == RELEASE_ENVIRONMENT:
                item["prod_remote_release_ready"] = prod_remote_release_ready
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
                    and prod_remote_release_ready
                )
            else:
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and selected_adapter_ready
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
                )
            environment_result[capability_id] = item
        result[environment] = environment_result
    return result


def load_validate_and_derive(
    *, root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    compiled, governance_issues = governance.load_and_compile()
    evidence, evidence_load_issues = load_evidence(root)
    current_commit = _current_commit()
    current_commit_issues = (
        ["cannot determine the current git revision for evidence validation"]
        if evidence and current_commit is None
        else []
    )
    executable_sources, source_discovery_issues = discover_test_sources()
    evidence_issues = validate_evidence(
        evidence,
        registry=governance.load_registry(),
        root=root,
        current_commit=current_commit,
        compiled=compiled,
        source_catalog=executable_sources,
    )
    readiness = derive_readiness(compiled=compiled, evidence=evidence)
    coverage_issues = source_coverage_issues(
        compiled=compiled,
        sources=executable_sources,
    )
    report = {
        "schema": "provider-conformance-readiness",
        "evidenceCount": len(evidence),
        "executableSourceCount": len(executable_sources),
        "sourceCoverageIssues": coverage_issues,
        "readiness": readiness,
        "issues": [
            *(issue.render() for issue in governance_issues),
            *evidence_load_issues,
            *current_commit_issues,
            *source_discovery_issues,
            *coverage_issues,
            *evidence_issues,
        ],
    }
    return report, report["issues"]


def readiness_issues(
    report: Mapping[str, Any],
    *,
    environment: str,
) -> list[str]:
    if environment not in READINESS_ENVIRONMENTS:
        return [_issue("readiness", f"unsupported readiness environment {environment}")]
    issues: list[str] = []
    if not ci_attestation_authority_available():
        issues.append(
            _issue(
                f"readiness.{environment}",
                "promotable evidence requires a clean reviewed commit and "
                "CI attestation authority",
            )
        )
    source_coverage = report.get("sourceCoverageIssues")
    if isinstance(source_coverage, list):
        issues.extend(str(issue) for issue in source_coverage)
    evidence_count = report.get("evidenceCount")
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        return [
            *issues,
            _issue(
                f"readiness.{environment}",
                "zero Provider Conformance evidence artifacts cannot satisfy release readiness",
            )
        ]
    readiness_by_environment = report.get("readiness")
    readiness = (
        readiness_by_environment.get(environment)
        if isinstance(readiness_by_environment, Mapping)
        else None
    )
    if not isinstance(readiness, Mapping):
        return [_issue(f"readiness.{environment}", "is unavailable")]
    for capability_id, capability_readiness in readiness.items():
        if not isinstance(capability_readiness, Mapping):
            continue
        if capability_readiness.get("required") and not capability_readiness.get(
            "capability_ready"
        ):
            issues.append(
                _issue(
                    f"readiness.{environment}.{capability_id}",
                    "required capability lacks current selected-Binding release evidence",
                )
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Provider Conformance evidence and calculate readiness."
    )
    parser.add_argument("--require-ready", choices=READINESS_ENVIRONMENTS)
    args = parser.parse_args()
    report, issues = load_validate_and_derive()
    if args.require_ready:
        issues.extend(readiness_issues(report, environment=args.require_ready))
        report["issues"] = issues
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
