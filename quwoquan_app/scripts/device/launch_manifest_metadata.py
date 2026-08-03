"""Read and enforce the canonical effective-launch-manifest metadata contract."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from quwoquan_ops.cli.lib.common import load_json_yaml  # noqa: E402
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    app_deployment_package_dir,
    deployment_target_for_env,
)
LAUNCH_MANIFEST_METADATA = (
    ROOT
    / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
)


class LaunchManifestContractError(ValueError):
    """The canonical launch-manifest metadata is absent or internally invalid."""


def load_launch_manifest_contract(
    path: Path = LAUNCH_MANIFEST_METADATA,
) -> dict[str, Any]:
    """Load and structurally validate the canonical launch-manifest metadata."""

    if not path.is_file():
        raise LaunchManifestContractError(
            f"launch manifest metadata is missing: {path}"
        )
    try:
        decoded = load_json_yaml(path)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise LaunchManifestContractError(
            f"launch manifest metadata cannot be loaded: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise LaunchManifestContractError("launch manifest metadata must be an object")
    if decoded.get("schema_id") != "app_launch_manifest":
        raise LaunchManifestContractError(
            "launch manifest metadata schema_id must be app_launch_manifest"
        )

    target_environment = decoded.get("target_environment")
    if not isinstance(target_environment, dict) or not target_environment:
        raise LaunchManifestContractError(
            "launch manifest target_environment must be a non-empty object"
        )
    if any(
        not isinstance(target, str)
        or not target
        or not isinstance(environment, str)
        or not environment
        for target, environment in target_environment.items()
    ):
        raise LaunchManifestContractError(
            "launch manifest target_environment contains an invalid mapping"
        )
    local_targets = decoded.get("local_transport_targets")
    if (
        not isinstance(local_targets, list)
        or any(not isinstance(target, str) for target in local_targets)
        or not set(local_targets).issubset(target_environment)
    ):
        raise LaunchManifestContractError(
            "local_transport_targets must only contain declared targets"
        )
    content_binding = decoded.get("content_binding_contract")
    if not isinstance(content_binding, dict):
        raise LaunchManifestContractError(
            "content_binding_contract must be an object"
        )
    binding_fields = content_binding.get("fields")
    digest_fields = content_binding.get("digest_fields")
    required_launch_modes = content_binding.get("required_launch_modes")
    if (
        not isinstance(binding_fields, list)
        or not binding_fields
        or any(not isinstance(field, str) or not field for field in binding_fields)
        or len(set(binding_fields)) != len(binding_fields)
        or not isinstance(digest_fields, list)
        or any(field not in binding_fields for field in digest_fields)
        or not isinstance(required_launch_modes, list)
        or any(
            not isinstance(mode, str) or not mode for mode in required_launch_modes
        )
    ):
        raise LaunchManifestContractError(
            "content_binding_contract definition is invalid"
        )

    digest_contract = decoded.get("digest_contract")
    if not isinstance(digest_contract, dict):
        raise LaunchManifestContractError("digest_contract must be an object")
    algorithm = digest_contract.get("algorithm")
    encoding = digest_contract.get("input_encoding")
    canonical_json = digest_contract.get("canonical_json")
    if not isinstance(algorithm, str) or algorithm not in hashlib.algorithms_available:
        raise LaunchManifestContractError("digest_contract algorithm is unsupported")
    expected_identity_format = (
        f"{algorithm}:<{hashlib.new(algorithm).digest_size * 2}-lowercase-hex>"
    )
    if digest_contract.get("identity_format") != expected_identity_format:
        raise LaunchManifestContractError(
            "digest_contract identity_format disagrees with its algorithm"
        )
    if not isinstance(encoding, str):
        raise LaunchManifestContractError("digest_contract input_encoding is invalid")
    try:
        "contract-probe".encode(encoding)
    except LookupError as exc:
        raise LaunchManifestContractError(
            "digest_contract input_encoding is unsupported"
        ) from exc
    if not isinstance(canonical_json, dict):
        raise LaunchManifestContractError(
            "digest_contract canonical_json must be an object"
        )
    separators = canonical_json.get("separators")
    if (
        not isinstance(canonical_json.get("sort_keys"), bool)
        or not isinstance(canonical_json.get("ensure_ascii"), bool)
        or not isinstance(separators, list)
        or len(separators) != 2
        or any(not isinstance(value, str) for value in separators)
    ):
        raise LaunchManifestContractError(
            "digest_contract canonical_json settings are invalid"
        )

    schemas = decoded.get("schemas")
    if not isinstance(schemas, dict):
        raise LaunchManifestContractError("launch manifest schemas must be an object")
    for schema_name in ("app_effective_launch_manifest", "app_launcher_handoff"):
        schema = schemas.get(schema_name)
        if not isinstance(schema, dict):
            raise LaunchManifestContractError(f"missing schema {schema_name}")
        fields = schema.get("fields")
        required = schema.get("required_fields")
        if (
            not isinstance(schema.get("schema_value"), str)
            or not isinstance(schema.get("additional_fields"), bool)
            or not isinstance(fields, dict)
            or not isinstance(required, list)
            or any(not isinstance(field, str) for field in required)
            or not set(required).issubset(fields)
        ):
            raise LaunchManifestContractError(
                f"schema {schema_name} definition is invalid"
            )
        schema_field = fields.get("schema")
        if (
            not isinstance(schema_field, dict)
            or schema_field.get("const") != schema.get("schema_value")
        ):
            raise LaunchManifestContractError(
                f"schema {schema_name} schema field disagrees with schema_value"
            )

    effective_fields = schemas["app_effective_launch_manifest"]["fields"]
    if not set(binding_fields).issubset(effective_fields):
        raise LaunchManifestContractError(
            "content binding fields must belong to app_effective_launch_manifest"
        )
    environment_values = effective_fields.get("environment", {}).get(
        "allowed_values"
    )
    target_values = effective_fields.get("target", {}).get("allowed_values")
    if (
        not isinstance(environment_values, list)
        or not isinstance(target_values, list)
        or set(target_environment.values()) - set(environment_values)
        or set(target_environment) != set(target_values)
    ):
        raise LaunchManifestContractError(
            "target_environment disagrees with effective manifest allowed values"
        )
    return decoded


def _digest_bytes(payload: bytes, contract: dict[str, Any]) -> str:
    digest_contract = contract["digest_contract"]
    algorithm = str(digest_contract["algorithm"])
    digest = hashlib.new(algorithm)
    digest.update(payload)
    return f"{algorithm}:{digest.hexdigest()}"


def _canonical_json_bytes(value: Any, contract: dict[str, Any]) -> bytes:
    digest_contract = contract["digest_contract"]
    settings = digest_contract["canonical_json"]
    return json.dumps(
        value,
        ensure_ascii=settings["ensure_ascii"],
        sort_keys=settings["sort_keys"],
        separators=tuple(settings["separators"]),
    ).encode(digest_contract["input_encoding"])


def is_digest_identity(value: object, contract: dict[str, Any]) -> bool:
    if not isinstance(value, str):
        return False
    algorithm = str(contract["digest_contract"]["algorithm"])
    digest_size = hashlib.new(algorithm).digest_size * 2
    return (
        re.fullmatch(
            rf"{re.escape(algorithm)}:[0-9a-f]{{{digest_size}}}", value
        )
        is not None
    )


def runtime_config_digest(
    environment: str,
    contract: dict[str, Any] | None = None,
    *,
    target: str = "",
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    digest_contract = selected_contract["digest_contract"]
    algorithm = str(digest_contract["algorithm"])
    target_name = target or deployment_target_for_env(environment)
    path = app_deployment_package_dir(
        environment,
        target=target_name,
    ) / "app_runtime.yaml"
    if not path.is_file():
        raise RuntimeError(
            "packaged runtime identity input is missing; run stackctl package first: "
            f"{path}"
        )
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return f"{algorithm}:{digest.hexdigest()}"


def dart_defines_digest(
    defines: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    normalized = {str(key): str(value).strip() for key, value in defines.items()}
    return _digest_bytes(
        _canonical_json_bytes(normalized, selected_contract), selected_contract
    )


def effective_launch_manifest_digest(
    manifest: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    return _digest_bytes(
        _canonical_json_bytes(manifest, selected_contract), selected_contract
    )


def _validate_url_format(value: object, format_name: str) -> bool:
    if not isinstance(value, str) or not value or value.strip() != value:
        return False
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    if format_name == "https_origin":
        return parsed.path in {"", "/"} and not parsed.params
    if format_name == "https_url_no_query_fragment_credentials":
        return not parsed.params
    return False


def _validate_schema_value(
    value: object,
    field_contract: dict[str, Any],
    *,
    field_path: str,
    contract: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    expected_type = field_contract.get("type")
    type_matches = {
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
    }.get(str(expected_type), False)
    if not type_matches:
        return [f"{field_path} must be {expected_type}"]
    if "const" in field_contract and value != field_contract["const"]:
        issues.append(f"{field_path} must equal {field_contract['const']}")
    allowed_values = field_contract.get("allowed_values")
    if isinstance(allowed_values, list) and value not in allowed_values:
        issues.append(f"{field_path} is not an allowed value")
    minimum_length = field_contract.get("min_length")
    if (
        isinstance(minimum_length, int)
        and isinstance(value, str)
        and len(value) < minimum_length
    ):
        issues.append(f"{field_path} is shorter than {minimum_length}")
    format_name = field_contract.get("format")
    if format_name == "sha256_identity" and not is_digest_identity(value, contract):
        issues.append(f"{field_path} must be a canonical digest identity")
    elif format_name in {
        "https_origin",
        "https_url_no_query_fragment_credentials",
    } and not _validate_url_format(value, str(format_name)):
        issues.append(f"{field_path} must satisfy {format_name}")
    elif format_name not in {
        None,
        "sha256_identity",
        "https_origin",
        "https_url_no_query_fragment_credentials",
    }:
        issues.append(f"{field_path} uses unsupported format {format_name}")
    value_type = field_contract.get("value_type")
    if value_type == "string" and isinstance(value, dict):
        if any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in value.items()
        ):
            issues.append(f"{field_path} must contain string-only keys and values")
    nested_fields = field_contract.get("fields")
    if isinstance(nested_fields, dict) and isinstance(value, dict):
        nested_required = field_contract.get("required_fields", [])
        if not isinstance(nested_required, list):
            issues.append(f"metadata for {field_path} has invalid required_fields")
        else:
            for field in nested_required:
                if field not in value:
                    issues.append(f"{field_path}.{field} is required")
        if field_contract.get("additional_fields") is False:
            for field in sorted(set(value) - set(nested_fields)):
                issues.append(f"{field_path}.{field} is not declared by metadata")
        for field, nested_value in value.items():
            nested_contract = nested_fields.get(field)
            if isinstance(nested_contract, dict):
                issues.extend(
                    _validate_schema_value(
                        nested_value,
                        nested_contract,
                        field_path=f"{field_path}.{field}",
                        contract=contract,
                    )
                )
    schema_ref = field_contract.get("schema_ref")
    if isinstance(schema_ref, str) and isinstance(value, dict):
        issues.extend(
            _validate_schema_document(
                value,
                schema_ref,
                contract=contract,
                field_path=field_path,
            )
        )
    return issues


def _validate_schema_document(
    document: dict[str, Any],
    schema_name: str,
    *,
    contract: dict[str, Any],
    field_path: str,
) -> list[str]:
    schema = contract["schemas"][schema_name]
    fields = schema["fields"]
    issues: list[str] = []
    for field in schema["required_fields"]:
        if field not in document:
            issues.append(f"{field_path}.{field} is required")
    if not schema["additional_fields"]:
        for field in sorted(set(document) - set(fields)):
            issues.append(f"{field_path}.{field} is not declared by metadata")
    for field, value in document.items():
        field_contract = fields.get(field)
        if not isinstance(field_contract, dict):
            continue
        issues.extend(
            _validate_schema_value(
                value,
                field_contract,
                field_path=f"{field_path}.{field}",
                contract=contract,
            )
        )
    return issues


def validate_handoff_against_metadata(
    handoff: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate shape, identity and topology only from canonical metadata."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        handoff,
        "app_launcher_handoff",
        contract=selected_contract,
        field_path="handoff",
    )
    effective_manifest = handoff.get("effectiveLaunchManifest")
    if not isinstance(effective_manifest, dict):
        return issues

    handoff_fields = selected_contract["schemas"]["app_launcher_handoff"]["fields"]
    for field, field_contract in handoff_fields.items():
        if not isinstance(field_contract, dict):
            continue
        source = field_contract.get("source")
        if not isinstance(source, str):
            continue
        source_schema, separator, source_field = source.partition(".")
        if separator != "." or source_schema != "app_effective_launch_manifest":
            issues.append(f"metadata source for handoff.{field} is unsupported")
            continue
        if handoff.get(field) != effective_manifest.get(source_field):
            issues.append(
                f"handoff.{field} disagrees with effectiveLaunchManifest.{source_field}"
            )

    expected_effective_digest = _digest_bytes(
        _canonical_json_bytes(effective_manifest, selected_contract),
        selected_contract,
    )
    if handoff.get("effectiveLaunchManifestDigest") != expected_effective_digest:
        issues.append("effectiveLaunchManifestDigest does not match canonical metadata")

    binding_contract = selected_contract["content_binding_contract"]
    binding_fields = binding_contract["fields"]
    binding_values = {
        field: effective_manifest.get(field) for field in binding_fields
    }
    populated_fields = [
        field
        for field, value in binding_values.items()
        if isinstance(value, str) and bool(value)
    ]
    if populated_fields and len(populated_fields) != len(binding_fields):
        issues.append("effective launch content binding must be all empty or complete")
    if len(populated_fields) == len(binding_fields):
        for field in binding_contract["digest_fields"]:
            if not is_digest_identity(binding_values[field], selected_contract):
                issues.append(
                    f"effective launch content binding {field} must be a canonical digest identity"
                )
    launch_mode = effective_manifest.get("launchMode")
    if (
        launch_mode in binding_contract["required_launch_modes"]
        and len(populated_fields) != len(binding_fields)
    ):
        issues.append(
            f"effective launch content binding is required for launch mode {launch_mode}"
        )

    defines = handoff.get("dartDefines")
    if isinstance(defines, dict):
        normalized_defines = {
            str(key): str(value).strip() for key, value in defines.items()
        }
        expected_defines_digest = _digest_bytes(
            _canonical_json_bytes(normalized_defines, selected_contract),
            selected_contract,
        )
        if handoff.get("dartDefinesDigest") != expected_defines_digest:
            issues.append("dartDefinesDigest does not match canonical metadata")

    target = effective_manifest.get("target")
    environment = effective_manifest.get("environment")
    target_environments = selected_contract["target_environment"]
    if target_environments.get(target) != environment:
        issues.append("effective launch target/environment mapping is invalid")
    local_targets = set(selected_contract["local_transport_targets"])
    requires_local_transport = target in local_targets
    if effective_manifest.get("requiresLocalTransport") is not requires_local_transport:
        issues.append("requiresLocalTransport disagrees with canonical target topology")

    transport = effective_manifest.get("transport")
    if not isinstance(transport, dict):
        return issues
    transport_required = transport.get("required")
    transport_fields = (
        "reverseExpectedPorts",
        "reverseActualPorts",
        "reverseReceiptDigest",
        "consumerLeaseId",
    )
    if transport_required is True:
        if target not in local_targets:
            issues.append("transport.required is only valid for a local target")
        for field in ("reverseReceiptDigest", "consumerLeaseId"):
            if not is_digest_identity(transport.get(field), selected_contract):
                issues.append(f"transport.{field} must be a canonical digest identity")
        try:
            expected_ports = canonical_ports(
                str(transport.get("reverseExpectedPorts", ""))
            )
            actual_ports = canonical_ports(
                str(transport.get("reverseActualPorts", ""))
            )
            if expected_ports != actual_ports:
                issues.append("Android reverse expected/actual ports do not match")
        except ValueError as exc:
            issues.append(str(exc))
    elif transport_required is False:
        if any(transport.get(field) not in {"", None} for field in transport_fields):
            issues.append("transport evidence must be empty when transport.required=false")
    return issues


def canonical_ports(raw: str) -> str:
    values: set[int] = set()
    for value in raw.split(","):
        normalized = value.strip()
        if not normalized:
            continue
        if not normalized.isdigit() or int(normalized) <= 0 or int(normalized) > 65535:
            raise ValueError(f"invalid Android reverse port: {normalized}")
        values.add(int(normalized))
    if not values:
        raise ValueError("Android reverse ports are empty")
    return ",".join(str(value) for value in sorted(values))
