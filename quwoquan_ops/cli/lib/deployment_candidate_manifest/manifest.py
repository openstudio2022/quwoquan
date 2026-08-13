"""deployment candidate manifest 的写入、加载与全量校验（逐字迁自原单文件）。

``validate_packaged_graphql_read_registry``、``deployment_candidate_dir`` 与三个
deployment package 目录解析函数经包属性（``_pkg.``）消费，保持测试对包属性
monkeypatch 的既有语义。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

from .candidate_fs import (
    _UnsafeCandidatePath,
    _read_candidate_bytes,
    _read_candidate_object,
    _sha256_candidate_file,
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
        "environmentRuntimeDigest": _sha256_candidate_file(
            candidate_root,
            environment_runtime_ref,
            label="packaged environment runtime",
        ),
        "observabilityLogSink": load_observability_log_sink_package(
            env_name,
            target_name,
            candidate_root,
        ),
        "providerRuntime": load_provider_runtime_package(
            env_name,
            target_name,
            candidate_root,
        ),
        "release": release,
        "releaseInputClassification": release_classification,
        "contractGraphDigest": contract_graph_digest,
        "graphqlReadRegistry": graphql_read_registry,
        "specRefs": list(SPEC_REFS),
    }
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
    purpose: str = "self_verify",
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
        if purpose == "currentness":
            current = _release_binding(attestation_ref, label=label)
            if current != binding:
                raise ValueError(f"{label} release attestation bytes drifted")
    expected_classification = release_input_classification(release)
    if payload.get("releaseInputClassification") != expected_classification:
        raise ValueError("deployment candidate release input classification drifted")
    if (
        purpose == "currentness"
        and payload.get("contractGraphDigest") != canonical_contract_graph_digest()
    ):
        raise ValueError("deployment candidate ContractGraph bytes drifted")
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
