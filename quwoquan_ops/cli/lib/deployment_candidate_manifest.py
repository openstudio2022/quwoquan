"""Immutable local deployment candidate identity and release binding."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_candidate_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
)


CANDIDATE_MANIFEST_SCHEMA = "stackctl-deployment-candidate"
RUNTIME_CANDIDATE_TYPE = "runtime-full"
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
ROOT = Path(__file__).resolve().parents[3]
LOG_SINK_ADAPTER_ID = "ext.obs.elasticsearch"
_ELASTICSEARCH_IMAGE_RE = re.compile(
    r"docker\.elastic\.co/elasticsearch/elasticsearch@(sha256:[0-9a-f]{64})"
)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _release_binding(path_value: str, *, label: str) -> dict[str, str]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        raise ValueError(f"{label} release attestation is required")
    path = path.resolve()
    value = _read_object(path, label=f"{label} release attestation")
    release_id = str(value.get("releaseId") or "").strip()
    release_digest = str(value.get("payloadSha256") or "").strip()
    if value.get("schema") != "quwoquan_data.release_attestation":
        raise ValueError(f"{label} release attestation schema mismatch")
    if not release_id or _DIGEST.fullmatch(release_digest) is None:
        raise ValueError(f"{label} release identity is invalid")
    return {
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "attestationRef": str(path),
        "attestationDigest": _sha256_file(path),
    }


def _observability_log_sink_identity(
    env_name: str,
    target_name: str,
) -> dict[str, str]:
    """Bind the canonical Product Ops log sink without exposing credentials."""

    service_root = (
        ROOT / "quwoquan_service/services/product-ops-service"
    )
    compose_path = service_root / "deploy/local-elasticsearch.compose.yaml"
    binding_path = service_root / "environments" / env_name / "config.yaml"
    try:
        binding_text = binding_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"canonical Product Ops log sink is unreadable: {exc}") from exc
    if f"adapter: {LOG_SINK_ADAPTER_ID}" not in binding_text:
        raise ValueError(
            f"{env_name} Product Ops Binding must select {LOG_SINK_ADAPTER_ID}"
        )
    if env_name == "prod":
        if (
            "endpointRef: environment_binding:product_ops.elasticsearch"
            not in binding_text
            or "- PRODUCT_OPS_ELASTICSEARCH_API_KEY" not in binding_text
        ):
            raise ValueError("Prod Product Ops Binding must select protected managed ES")
        return {
            "adapterId": LOG_SINK_ADAPTER_ID,
            "deploymentMode": "managed-external",
            "imageDigest": "",
            "bindingDigest": _sha256_file(binding_path),
            "deploymentDigest": "",
            "clusterRef": "environment-binding:product_ops.elasticsearch",
        }
    if env_name not in {"alpha", "beta", "gamma"}:
        raise ValueError(f"unsupported Product Ops log sink environment: {env_name}")
    expected_endpoint = f"endpointRef: local_topology:{env_name}.elasticsearch"
    if expected_endpoint not in binding_text:
        raise ValueError(
            f"{env_name} Product Ops Binding is not target-local Elasticsearch"
        )
    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"canonical local Elasticsearch workload is unreadable: {exc}") from exc
    image_match = _ELASTICSEARCH_IMAGE_RE.search(compose_text)
    if image_match is None:
        raise ValueError("canonical Product Ops Elasticsearch image digest is missing")
    return {
        "adapterId": LOG_SINK_ADAPTER_ID,
        "deploymentMode": "package-bound-local",
        "imageDigest": image_match.group(1),
        "bindingDigest": _sha256_file(binding_path),
        "deploymentDigest": _sha256_file(compose_path),
        "clusterRef": f"target:{target_name}/product-ops/elasticsearch",
    }


def validate_release_attestations(
    release_attestation: str,
    rollback_release_attestation: str,
) -> dict[str, dict[str, str]]:
    """Fail before package/build work when immutable release inputs are absent."""

    return {
        "candidate": _release_binding(release_attestation, label="candidate"),
        "rollback": _release_binding(
            rollback_release_attestation,
            label="rollback",
        ),
    }


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

    app_dir = app_deployment_package_dir(env_name, target=target_name)
    candidate_root = app_dir.parent.parent
    fingerprint = _read_object(
        app_dir / "package-fingerprint.json",
        label="package fingerprint",
    )
    app_report = _read_object(app_dir / "report.json", label="App package report")
    environment_runtime_path = app_dir / "environment_runtime.yaml"
    environment_runtime = _read_object(
        environment_runtime_path,
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
        raise ValueError("package fingerprint digest bindings are missing")

    oci_path = (
        runtime_shared_deployment_package_dir(env_name, target=target_name)
        / "oci-images.json"
    )
    oci = _read_object(oci_path, label="package OCI image manifest") if oci_path.is_file() else None
    include_services = bool(fingerprint.get("includeServices"))
    if (
        candidate_type != RUNTIME_CANDIDATE_TYPE
        or fingerprint.get("candidateType") != RUNTIME_CANDIDATE_TYPE
        or not include_services
    ):
        raise ValueError("runtime candidate must be a full service package")
    legal_static_root = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    legal_static_current = legal_static_root / "current"
    legal_static_required = (
        legal_static_current / "release_metadata.json",
        legal_static_current / "checksums.json",
        legal_static_current / "public/legal/manifest.json",
    )
    if any(not path.is_file() for path in legal_static_required):
        raise ValueError("deployment candidate has no complete legal-static package")
    if oci is None:
        raise ValueError("full candidate has no package-bound OCI image manifest")
    release = validate_release_attestations(
        release_attestation,
        rollback_release_attestation,
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
        "runtimeSchemaVersion": runtime_schema_version,
        "runtimeConfigDigest": app_report.get("runtimeConfigDigest"),
        "environmentRuntimeDigest": _sha256_file(environment_runtime_path),
        "observabilityLogSink": _observability_log_sink_identity(
            env_name,
            target_name,
        ),
        "release": release,
        "specRefs": list(SPEC_REFS),
    }
    validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=True,
    )
    path = candidate_root / "manifest.json"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def validate_candidate_manifest(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    require_full: bool,
) -> dict[str, Any]:
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
        "runtimeSchemaVersion",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "observabilityLogSink",
        "release",
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
    if re.fullmatch(
        r"[a-z][a-z0-9-]*",
        str(payload.get("runtimeSchemaVersion") or ""),
    ) is None:
        raise ValueError("deployment candidate runtimeSchemaVersion is invalid")
    for field in (
        "baselineId",
        "workspaceDigest",
        "workspaceStatusDigest",
        "packageDigest",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
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
    log_sink = payload.get("observabilityLogSink")
    if not isinstance(log_sink, dict) or set(log_sink) != {
        "adapterId",
        "deploymentMode",
        "imageDigest",
        "bindingDigest",
        "deploymentDigest",
        "clusterRef",
    }:
        raise ValueError("deployment candidate observability log sink fields mismatch")
    if log_sink.get("adapterId") != LOG_SINK_ADAPTER_ID:
        raise ValueError("deployment candidate log sink adapter mismatch")
    if _DIGEST.fullmatch(str(log_sink.get("bindingDigest") or "")) is None:
        raise ValueError("deployment candidate log sink bindingDigest is invalid")
    if expected_environment == "prod":
        if (
            log_sink.get("deploymentMode") != "managed-external"
            or log_sink.get("imageDigest") != ""
            or log_sink.get("deploymentDigest") != ""
            or log_sink.get("clusterRef")
            != "environment-binding:product_ops.elasticsearch"
        ):
            raise ValueError("Prod deployment candidate must bind managed Elasticsearch")
    else:
        if log_sink.get("deploymentMode") != "package-bound-local":
            raise ValueError("local deployment candidate log sink mode mismatch")
        for field in ("imageDigest", "deploymentDigest"):
            if _DIGEST.fullmatch(str(log_sink.get(field) or "")) is None:
                raise ValueError(f"deployment candidate log sink {field} is invalid")
        if log_sink.get("clusterRef") != (
            f"target:{expected_target}/product-ops/elasticsearch"
        ):
            raise ValueError("deployment candidate log sink clusterRef mismatch")
    release = payload.get("release")
    if not isinstance(release, dict) or set(release) != {"candidate", "rollback"}:
        raise ValueError("full deployment candidate release binding mismatch")
    for label in ("candidate", "rollback"):
        binding = release.get(label)
        if not isinstance(binding, dict) or set(binding) != {
            "releaseId",
            "releaseDigest",
            "attestationRef",
            "attestationDigest",
        }:
            raise ValueError(f"deployment candidate {label} release fields mismatch")
        if not str(binding.get("releaseId") or ""):
            raise ValueError(f"deployment candidate {label} releaseId is invalid")
        for field in ("releaseDigest", "attestationDigest"):
            if _DIGEST.fullmatch(str(binding.get(field) or "")) is None:
                raise ValueError(
                    f"deployment candidate {label} {field} is invalid"
                )
    return payload


def load_candidate_manifest(
    env_name: str,
    target_name: str,
    baseline_id: str,
    *,
    require_full: bool,
) -> dict[str, Any]:
    path = deployment_candidate_dir(target_name, baseline_id) / "manifest.json"
    payload = _read_object(path, label="deployment candidate manifest")
    return validate_candidate_manifest(
        payload,
        expected_environment=env_name,
        expected_target=target_name,
        require_full=require_full,
    )
