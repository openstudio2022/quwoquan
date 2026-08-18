"""Deployment candidate 的统一 environment artifact identity。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .candidate_fs import (
    _read_candidate_bytes,
    _read_candidate_object,
)
from .constants import (
    _DIGEST,
    ENVIRONMENT_ARTIFACT_METADATA_PATH,
    ENVIRONMENT_ARTIFACT_SCHEMA_PATH,
)


def _load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        metadata = yaml.safe_load(
            ENVIRONMENT_ARTIFACT_METADATA_PATH.read_text(encoding="utf-8")
        )
        schema = json.loads(
            ENVIRONMENT_ARTIFACT_SCHEMA_PATH.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ValueError("environmentArtifact canonical metadata is unreadable") from exc
    if not isinstance(metadata, dict) or not isinstance(schema, dict):
        raise TypeError("environmentArtifact canonical metadata must be objects")
    return metadata, schema


def _contract_shape() -> tuple[
    str,
    dict[str, str],
    frozenset[str],
    frozenset[str],
    frozenset[str],
    str,
]:
    metadata, schema = _load_contract()
    identity = metadata.get("identity")
    target_environment = metadata.get("target_environment")
    digest_contract = metadata.get("digest_contract")
    canonical_json = (
        digest_contract.get("canonical_json")
        if isinstance(digest_contract, dict)
        else None
    )
    required = schema.get("required")
    properties = schema.get("properties")
    if (
        not isinstance(identity, dict)
        or not isinstance(target_environment, dict)
        or not isinstance(digest_contract, dict)
        or digest_contract.get("algorithm") != "sha256"
        or digest_contract.get("input_encoding") != "utf-8"
        or not isinstance(canonical_json, dict)
        or canonical_json.get("sort_keys") is not True
        or canonical_json.get("ensure_ascii") is not False
        or canonical_json.get("separators") != [",", ":"]
        or not isinstance(required, list)
        or not isinstance(properties, dict)
        or schema.get("additionalProperties") is not False
        or set(required) != set(properties)
    ):
        raise ValueError("environmentArtifact canonical metadata shape is invalid")
    core_fields = identity.get("identity_core_fields")
    activation_fields = identity.get("activation_seal_fields")
    schema_value = str(identity.get("schema_value") or "")
    topology_ref = str(identity.get("runtime_topology_manifest_ref") or "")
    if (
        not schema_value
        or not topology_ref
        or not isinstance(core_fields, list)
        or not isinstance(activation_fields, list)
        or not set(core_fields).issubset(required)
        or set(core_fields)
        & {"imageSetDigest", "identityCoreDigest", "environmentArtifactDigest"}
        or set(activation_fields) != {"identityCoreDigest", "imageSetDigest"}
    ):
        raise ValueError("environmentArtifact canonical identity contract is invalid")
    targets: dict[str, str] = {}
    for target, environment in target_environment.items():
        normalized_target = str(target or "")
        normalized_environment = str(environment or "")
        if not normalized_target or not normalized_environment:
            raise ValueError("environmentArtifact target mapping is invalid")
        targets[normalized_target] = normalized_environment
    return (
        schema_value,
        targets,
        frozenset(str(field) for field in core_fields),
        frozenset(str(field) for field in required),
        frozenset(str(field) for field in activation_fields),
        topology_ref,
    )


def _require_digest(value: object, *, label: str) -> str:
    normalized = str(value or "")
    if _DIGEST.fullmatch(normalized) is None:
        raise ValueError(f"environmentArtifact {label} is invalid")
    return normalized


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _identity_projection(
    value: Mapping[str, Any],
    *,
    fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    missing = fields - set(value)
    if missing:
        raise ValueError(
            f"environmentArtifact {label} fields mismatch: missing {sorted(missing)}"
        )
    return {field: value[field] for field in sorted(fields)}


def environment_artifact_identity_core_digest(value: object) -> str:
    """复算镜像可内嵌的 identity core；输入明确排除最终 imageSetDigest。"""

    if not isinstance(value, Mapping):
        raise TypeError("environmentArtifact must be an object")
    (
        _schema_value,
        _targets,
        core_fields,
        _all_fields,
        _activation_fields,
        _topology_ref,
    ) = _contract_shape()
    return _sha256_json(
        _identity_projection(
            value,
            fields=core_fields,
            label="identity core",
        )
    )


def environment_artifact_digest(value: object) -> str:
    """复算外部 activation seal，绑定 core 与最终 image set。"""

    if not isinstance(value, Mapping):
        raise TypeError("environmentArtifact must be an object")
    (
        _schema_value,
        _targets,
        _core_fields,
        _all_fields,
        activation_fields,
        _topology_ref,
    ) = _contract_shape()
    activation = _identity_projection(
        value,
        fields=activation_fields,
        label="activation seal",
    )
    for field in activation_fields:
        activation[field] = _require_digest(activation[field], label=field)
    return _sha256_json(activation)


def _source_capsule(
    fingerprint: Mapping[str, Any],
    *,
    baseline_id: object,
    source_revision: object,
    workspace_status_digest: object,
    workspace_digest: object,
) -> dict[str, str]:
    fingerprint_identity = {
        "baselineId": fingerprint.get("baselineId"),
        "sourceRevision": fingerprint.get("sourceRevision"),
        "workspaceStatusDigest": fingerprint.get("workspaceStatusDigest"),
    }
    candidate_identity = {
        "baselineId": baseline_id,
        "sourceRevision": source_revision,
        "workspaceStatusDigest": workspace_status_digest,
    }
    if fingerprint_identity != candidate_identity:
        raise ValueError("environmentArtifact source capsule fingerprint drifted")
    normalized_revision = str(source_revision or "")
    if len(normalized_revision) != 40 or any(
        character not in "0123456789abcdef" for character in normalized_revision
    ):
        raise ValueError("environmentArtifact sourceCapsule.sourceRevision is invalid")
    return {
        "baselineId": _require_digest(baseline_id, label="sourceCapsule.baselineId"),
        "digest": _require_digest(workspace_digest, label="sourceCapsule.digest"),
        "sourceRevision": normalized_revision,
        "workspaceStatusDigest": _require_digest(
            workspace_status_digest,
            label="sourceCapsule.workspaceStatusDigest",
        ),
    }


def _provider_identity(provider_runtime: object) -> dict[str, str]:
    composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if not isinstance(composition, Mapping):
        raise TypeError("environmentArtifact Provider composition is missing")
    return {
        "bindingDigest": _require_digest(
            composition.get("bindingDigest"),
            label="provider.bindingDigest",
        ),
        "runtimeCompositionDigest": _require_digest(
            composition.get("runtimeCompositionDigest"),
            label="provider.runtimeCompositionDigest",
        ),
    }


def _runtime_topology_digest(
    candidate_root: Path,
    *,
    expected_environment: str,
    expected_target: str,
) -> str:
    (
        _schema_value,
        _targets,
        _core_fields,
        _all_fields,
        _activation_fields,
        topology_ref,
    ) = _contract_shape()
    encoded = _read_candidate_bytes(
        candidate_root,
        topology_ref,
        label="runtime topology manifest",
    )
    try:
        manifest = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("environmentArtifact runtime topology is unreadable") from exc
    if not isinstance(manifest, dict):
        raise TypeError("environmentArtifact runtime topology must be an object")
    if (
        manifest.get("environment") != expected_environment
        or manifest.get("target") != expected_target
    ):
        raise ValueError("environmentArtifact runtime topology target identity mismatch")
    _require_digest(
        manifest.get("topologyDigest"),
        label="runtimeTopology.topologyDigest",
    )
    return _sha256_bytes(encoded)


def _endpoint_authority_digest(
    environment_runtime: Mapping[str, Any],
    *,
    expected_environment: str,
    expected_target: str,
) -> str:
    public_bases = environment_runtime.get("publicBases")
    if not isinstance(public_bases, Mapping) or not public_bases:
        raise ValueError("environmentArtifact endpoint authority is missing")
    if any(
        not isinstance(name, str)
        or not name
        or not isinstance(value, str)
        or not value.strip()
        for name, value in public_bases.items()
    ):
        raise ValueError("environmentArtifact endpoint authority is invalid")
    return _sha256_json(
        {
            "environment": expected_environment,
            "target": expected_target,
            "publicBases": dict(public_bases),
        }
    )


def build_environment_artifact(
    *,
    environment: str,
    target: str,
    baseline_id: object,
    source_revision: object,
    workspace_status_digest: object,
    workspace_digest: object,
    package_digest: object,
    image_build_input_digest: object,
    image_set_digest: object,
    service_configuration_digest: object,
    app_runtime_digest: object,
    environment_runtime_digest: object,
    provider_runtime: object,
    contract_graph_digest: object,
    environment_runtime: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
    candidate_root: Path,
) -> dict[str, Any]:
    """从已封存 candidate 输入建立单一、可复算的环境制品身份。"""

    (
        schema_value,
        targets,
        _core_fields,
        _all_fields,
        _activation_fields,
        _topology_ref,
    ) = _contract_shape()
    if targets.get(target) != environment:
        raise ValueError("environmentArtifact target identity mismatch")
    source_capsule = _source_capsule(
        fingerprint,
        baseline_id=baseline_id,
        source_revision=source_revision,
        workspace_status_digest=workspace_status_digest,
        workspace_digest=workspace_digest,
    )
    graph_digest = _require_digest(
        contract_graph_digest,
        label="contractGraphDigest",
    )
    artifact: dict[str, Any] = {
        "schema": schema_value,
        "environment": environment,
        "target": target,
        "releaseTrainId": _sha256_json(
            {
                "sourceRevision": source_capsule["sourceRevision"],
                "contractGraphDigest": graph_digest,
            }
        ),
        "sourceCapsule": source_capsule,
        "packageDigest": _require_digest(package_digest, label="packageDigest"),
        "imageBuildInputDigest": _require_digest(
            image_build_input_digest,
            label="imageBuildInputDigest",
        ),
        "imageSetDigest": _require_digest(image_set_digest, label="imageSetDigest"),
        "configuration": {
            "serviceDigest": _require_digest(
                service_configuration_digest,
                label="configuration.serviceDigest",
            ),
            "appRuntimeDigest": _require_digest(
                app_runtime_digest,
                label="configuration.appRuntimeDigest",
            ),
            "environmentRuntimeDigest": _require_digest(
                environment_runtime_digest,
                label="configuration.environmentRuntimeDigest",
            ),
        },
        "provider": _provider_identity(provider_runtime),
        "endpointAuthorityDigest": _endpoint_authority_digest(
            environment_runtime,
            expected_environment=environment,
            expected_target=target,
        ),
        "runtimeTopologyDigest": _runtime_topology_digest(
            candidate_root,
            expected_environment=environment,
            expected_target=target,
        ),
        "contractGraphDigest": graph_digest,
    }
    artifact["identityCoreDigest"] = environment_artifact_identity_core_digest(
        artifact
    )
    artifact["environmentArtifactDigest"] = environment_artifact_digest(artifact)
    return artifact


def _expected_environment_artifact(
    candidate: Mapping[str, Any],
    *,
    expected_environment: str,
    expected_target: str,
    candidate_root: Path,
) -> dict[str, Any]:
    fingerprint = _read_candidate_object(
        candidate_root,
        "packages/app/package-fingerprint.json",
        label="package fingerprint",
    )
    environment_runtime = _read_candidate_object(
        candidate_root,
        "packages/app/environment_runtime.yaml",
        label="packaged environment runtime",
    )
    return build_environment_artifact(
        environment=expected_environment,
        target=expected_target,
        baseline_id=candidate.get("baselineId"),
        source_revision=candidate.get("sourceRevision"),
        workspace_status_digest=candidate.get("workspaceStatusDigest"),
        workspace_digest=candidate.get("workspaceDigest"),
        package_digest=candidate.get("packageDigest"),
        image_build_input_digest=candidate.get("buildInputDigest"),
        image_set_digest=candidate.get("imageDigest"),
        service_configuration_digest=candidate.get("configurationDigest"),
        app_runtime_digest=candidate.get("runtimeConfigDigest"),
        environment_runtime_digest=candidate.get("environmentRuntimeDigest"),
        provider_runtime=candidate.get("providerRuntime"),
        contract_graph_digest=candidate.get("contractGraphDigest"),
        environment_runtime=environment_runtime,
        fingerprint=fingerprint,
        candidate_root=candidate_root,
    )


def validate_environment_artifact(
    value: object,
    *,
    candidate: Mapping[str, Any],
    expected_environment: str,
    expected_target: str,
    candidate_root: Path,
) -> dict[str, Any]:
    """校验字段闭集、环境绑定与所有 package-owned 摘要。"""

    (
        schema_value,
        targets,
        _core_fields,
        all_fields,
        _activation_fields,
        _topology_ref,
    ) = _contract_shape()
    if not isinstance(value, dict) or set(value) != all_fields:
        raise ValueError("environmentArtifact fields mismatch")
    if value.get("schema") != schema_value:
        raise ValueError("environmentArtifact schema mismatch")
    if (
        value.get("environment") != expected_environment
        or value.get("target") != expected_target
        or targets.get(expected_target) != expected_environment
    ):
        raise ValueError("environmentArtifact target identity mismatch")
    for field in (
        "releaseTrainId",
        "packageDigest",
        "imageBuildInputDigest",
        "imageSetDigest",
        "endpointAuthorityDigest",
        "runtimeTopologyDigest",
        "contractGraphDigest",
        "identityCoreDigest",
        "environmentArtifactDigest",
    ):
        _require_digest(value.get(field), label=field)
    source_capsule = value.get("sourceCapsule")
    if not isinstance(source_capsule, dict) or set(source_capsule) != {
        "baselineId",
        "digest",
        "sourceRevision",
        "workspaceStatusDigest",
    }:
        raise ValueError("environmentArtifact sourceCapsule fields mismatch")
    configuration = value.get("configuration")
    if not isinstance(configuration, dict) or set(configuration) != {
        "serviceDigest",
        "appRuntimeDigest",
        "environmentRuntimeDigest",
    }:
        raise ValueError("environmentArtifact configuration fields mismatch")
    provider = value.get("provider")
    if not isinstance(provider, dict) or set(provider) != {
        "bindingDigest",
        "runtimeCompositionDigest",
    }:
        raise ValueError("environmentArtifact provider fields mismatch")
    expected = _expected_environment_artifact(
        candidate,
        expected_environment=expected_environment,
        expected_target=expected_target,
        candidate_root=candidate_root,
    )
    if value != expected:
        raise ValueError("environmentArtifact binding drifted or digest drifted")
    return value
