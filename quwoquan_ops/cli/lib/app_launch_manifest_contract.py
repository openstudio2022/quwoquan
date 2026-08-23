"""Canonical App launch-manifest, trust-envelope, package, and handoff contract."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from .app_identity import (
    build_profile_for_environment,
    launch_policy_for_build_profile,
)
from .app_launch_manifest_schema import (
    canonical_ports,
    is_digest_identity,
    parse_rfc3339_utc as _parse_rfc3339_utc,
    validate_schema_document as _validate_schema_document,
)
from .app_runtime_config_signing import (
    canonical_signed_payload,
    decode_keyring,
    verify_signature,
)
from .common import load_json_yaml


ROOT = Path(__file__).resolve().parents[3]
LAUNCH_MANIFEST_METADATA = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
)
_RUNTIME_CONFIG_TRUST_ENVELOPE_FIELDS = {
    "schema",
    "schemaVersion",
    "buildProfile",
    "signatureAlgorithm",
    "trustedPublicKeys",
}


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
    if "content_binding_contract" in decoded:
        raise LaunchManifestContractError(
            "launch manifest metadata must not declare content binding; "
            "content activation identity is a runtime server-side fact"
        )
    launch_policies = decoded.get("launch_policies")
    if (
        not isinstance(launch_policies, dict)
        or not launch_policies
        or any(
            not isinstance(policy, str)
            or not policy
            or not isinstance(policy_contract, dict)
            or not isinstance(policy_contract.get("environments"), list)
            or not policy_contract["environments"]
            or not isinstance(policy_contract.get("build_profiles"), list)
            or not policy_contract["build_profiles"]
            or any(
                not isinstance(environment, str) or not environment
                for environment in policy_contract["environments"]
            )
            or any(
                not isinstance(profile, str) or not profile
                for profile in policy_contract["build_profiles"]
            )
            for policy, policy_contract in launch_policies.items()
        )
    ):
        raise LaunchManifestContractError("launch_policies definition is invalid")
    runtime_package_contract = decoded.get("runtime_config_package")
    runtime_trust_contract = decoded.get("runtime_config_trust")
    runtime_value_keys = decoded.get("runtime_value_keys")
    if (
        not isinstance(runtime_package_contract, dict)
        or runtime_package_contract.get("signature_algorithm") != "ed25519"
        or runtime_package_contract.get("signed_payload_excludes") != ["signature"]
        or not isinstance(runtime_package_contract.get("max_lifetime_seconds"), int)
        or int(runtime_package_contract["max_lifetime_seconds"]) <= 0
        or not isinstance(runtime_package_contract.get("max_future_skew_seconds"), int)
        or int(runtime_package_contract["max_future_skew_seconds"]) < 0
        or not isinstance(runtime_trust_contract, dict)
        or runtime_trust_contract.get("schema_version") != "1"
        or runtime_trust_contract.get("signature_algorithm") != "ed25519"
        or runtime_trust_contract.get("build_profiles") != ["nonprod", "prod"]
        or not isinstance(runtime_value_keys, dict)
        or not runtime_value_keys
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(declaration, dict)
            or declaration.get("type") != "string"
            or declaration.get("category") not in {"endpoint", "launch"}
            or declaration.get("required") is not True
            for key, declaration in runtime_value_keys.items()
        )
    ):
        raise LaunchManifestContractError(
            "runtime_config_trust, runtime_config_package, or runtime_value_keys definition is invalid"
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
    for schema_name in (
        "runtime_config_trust_envelope",
        "runtime_config_package",
        "runtime_config_activation_request",
        "runtime_config_activation_receipt",
        "app_effective_launch_manifest",
        "app_launcher_handoff",
    ):
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

    trust_schema = schemas["runtime_config_trust_envelope"]
    trust_fields = trust_schema["fields"]
    if (
        trust_schema["additional_fields"] is not False
        or set(trust_schema["required_fields"])
        != _RUNTIME_CONFIG_TRUST_ENVELOPE_FIELDS
        or set(trust_fields) != _RUNTIME_CONFIG_TRUST_ENVELOPE_FIELDS
        or trust_schema["schema_value"] != "app-runtime-config-trust"
        or trust_fields.get("schemaVersion", {}).get("const")
        != runtime_trust_contract["schema_version"]
        or trust_fields.get("signatureAlgorithm", {}).get("const")
        != runtime_trust_contract["signature_algorithm"]
        or trust_fields.get("buildProfile", {}).get("allowed_values")
        != runtime_trust_contract["build_profiles"]
        or trust_fields.get("trustedPublicKeys", {}).get("value_type") != "string"
    ):
        raise LaunchManifestContractError(
            "runtime_config_trust_envelope must use the canonical profile-scoped shape"
        )

    runtime_fields = schemas["runtime_config_package"]["fields"]
    runtime_values_field = runtime_fields.get("runtime")
    if (
        not isinstance(runtime_values_field, dict)
        or runtime_values_field.get("additional_fields") is not False
        or set(runtime_values_field.get("required_fields", []))
        != set(runtime_value_keys)
        or set(runtime_values_field.get("fields", {})) != set(runtime_value_keys)
        or runtime_fields.get("signatureAlgorithm", {}).get("const") != "ed25519"
        or runtime_fields.get("schemaVersion", {}).get("const")
        != runtime_package_contract.get("schema_version")
    ):
        raise LaunchManifestContractError(
            "runtime_config_package schema disagrees with its canonical declaration"
        )
    forbidden_runtime_tokens = ("release", "rollout", "gray", "channel", "secret")
    if any(
        any(token in key.lower() for token in forbidden_runtime_tokens)
        for key in runtime_value_keys
    ):
        raise LaunchManifestContractError(
            "runtime_value_keys must not contain release, rollout, channel, or secret fields"
        )

    effective_fields = schemas["app_effective_launch_manifest"]["fields"]
    forbidden_content_fields = {
        "contentBindingState",
        "contentReleaseId",
        "contentManifestDigest",
        "contentReadinessReceiptDigest",
    }
    if forbidden_content_fields & set(effective_fields):
        raise LaunchManifestContractError(
            "app_effective_launch_manifest must not carry content release identity"
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
    for environment in environment_values:
        try:
            profile = build_profile_for_environment(environment)
            policy = launch_policy_for_build_profile(profile)
        except ValueError as exc:
            raise LaunchManifestContractError(
                f"App build profile metadata is invalid for {environment}: {exc}"
            ) from exc
        policy_contract = launch_policies.get(policy)
        if (
            not isinstance(policy_contract, dict)
            or environment not in policy_contract.get("environments", [])
            or profile not in policy_contract.get("build_profiles", [])
        ):
            raise LaunchManifestContractError(
                "launch_policies disagrees with canonical App build profiles"
            )
    handoff_fields = schemas["app_launcher_handoff"]["fields"]
    if (
        handoff_fields.get("runtimeConfigPackage", {}).get("schema_ref")
        != "runtime_config_package"
        or "dartDefines" in handoff_fields
        or "dartDefinesDigest" in handoff_fields
    ):
        raise LaunchManifestContractError(
            "app_launcher_handoff must carry runtimeConfigPackage without Dart defines"
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


def effective_launch_manifest_digest(
    manifest: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    return _digest_bytes(
        _canonical_json_bytes(manifest, selected_contract), selected_contract
    )


def runtime_config_package_digest(
    package: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    return _digest_bytes(
        _canonical_json_bytes(package, selected_contract), selected_contract
    )


def build_runtime_config_activation_request(
    handoff: dict[str, Any],
    *,
    expected_active_digest: str = "",
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one launcher handoff into the native activation request."""

    selected_contract = contract or load_launch_manifest_contract()
    schema = selected_contract["schemas"]["runtime_config_activation_request"]
    request = {
        "schema": schema["schema_value"],
        "schemaVersion": schema["fields"]["schemaVersion"]["const"],
        "environment": handoff.get("environment"),
        "buildProfile": handoff.get("buildProfile"),
        "target": handoff.get("target"),
        "package": deepcopy(handoff.get("runtimeConfigPackage")),
        "packageDigest": handoff.get("runtimeConfigPackageDigest"),
        "trustEnvelopeDigest": handoff.get("runtimeConfigTrustEnvelopeDigest"),
        "effectiveLaunchManifest": deepcopy(handoff.get("effectiveLaunchManifest")),
        "effectiveLaunchManifestDigest": handoff.get(
            "effectiveLaunchManifestDigest"
        ),
        "expectedActiveDigest": expected_active_digest,
    }
    issues = validate_runtime_config_activation_request(request, selected_contract)
    if issues:
        raise ValueError("; ".join(issues))
    return request


def runtime_config_activation_request_digest(
    request: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    return _digest_bytes(
        _canonical_json_bytes(request, selected_contract), selected_contract
    )


def validate_runtime_config_activation_request(
    request: object,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the package, manifest, profile, target, and CAS request binding."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        request,
        "runtime_config_activation_request",
        contract=selected_contract,
        field_path="activation request",
    )
    if not isinstance(request, dict):
        return issues

    package = request.get("package")
    if isinstance(package, dict):
        expected_package_digest = runtime_config_package_digest(
            package,
            selected_contract,
        )
        if request.get("packageDigest") != expected_package_digest:
            issues.append("activation request packageDigest does not match package")

    effective_manifest = request.get("effectiveLaunchManifest")
    if isinstance(effective_manifest, dict):
        expected_manifest_digest = effective_launch_manifest_digest(
            effective_manifest,
            selected_contract,
        )
        if request.get("effectiveLaunchManifestDigest") != expected_manifest_digest:
            issues.append(
                "activation request effectiveLaunchManifestDigest does not match "
                "effectiveLaunchManifest"
            )

        request_manifest_fields = (
            ("environment", "environment"),
            ("buildProfile", "buildProfile"),
            ("target", "target"),
            ("packageDigest", "runtimeConfigPackageDigest"),
            ("trustEnvelopeDigest", "runtimeConfigTrustEnvelopeDigest"),
        )
        for request_field, manifest_field in request_manifest_fields:
            if request.get(request_field) != effective_manifest.get(manifest_field):
                issues.append(
                    f"activation request {request_field} does not match "
                    f"effectiveLaunchManifest.{manifest_field}"
                )

    if isinstance(package, dict) and isinstance(effective_manifest, dict):
        for field in ("environment", "buildProfile", "target", "launchPolicy"):
            if package.get(field) != effective_manifest.get(field):
                issues.append(
                    f"activation request package.{field} does not match "
                    f"effectiveLaunchManifest.{field}"
                )

    return list(dict.fromkeys(issues))


def validate_runtime_config_activation_receipt(
    receipt: object,
    request: object,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a native activation receipt against its exact request."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        receipt,
        "runtime_config_activation_receipt",
        contract=selected_contract,
        field_path="activation receipt",
    )
    request_issues = validate_runtime_config_activation_request(
        request,
        selected_contract,
    )
    issues.extend(
        f"activation receipt request is invalid: {issue}" for issue in request_issues
    )
    if not isinstance(receipt, dict) or not isinstance(request, dict):
        return list(dict.fromkeys(issues))

    expected_request_digest = runtime_config_activation_request_digest(
        request,
        selected_contract,
    )
    if receipt.get("requestDigest") != expected_request_digest:
        issues.append("activation receipt requestDigest does not match request")

    status = receipt.get("status")
    for field in (
        "environment",
        "buildProfile",
        "target",
        "packageDigest",
        "trustEnvelopeDigest",
        "effectiveLaunchManifestDigest",
    ):
        if status == "activated" and receipt.get(field) in {None, ""}:
            issues.append(f"activation receipt activated status requires {field}")
        if receipt.get(field) != request.get(field):
            issues.append(f"activation receipt {field} does not match request")

    if status == "activated":
        if receipt.get("previousActiveDigest") != request.get(
            "expectedActiveDigest"
        ):
            issues.append(
                "activation receipt previousActiveDigest does not match "
                "expectedActiveDigest"
            )
        if receipt.get("activePackageDigest") != request.get("packageDigest"):
            issues.append(
                "activation receipt activePackageDigest does not match packageDigest"
            )
        if receipt.get("errorCode") != "":
            issues.append("activation receipt activated status must have empty errorCode")
        if receipt.get("validationIssues") != []:
            issues.append(
                "activation receipt activated status must have empty validationIssues"
            )
    elif status == "failed":
        error_code = receipt.get("errorCode")
        validation_issues = receipt.get("validationIssues")
        if error_code == "":
            issues.append("activation receipt failed status requires errorCode")
        if not isinstance(validation_issues, list) or not validation_issues:
            issues.append(
                "activation receipt failed status requires validationIssues"
            )
        elif error_code not in validation_issues:
            issues.append(
                "activation receipt validationIssues must include errorCode"
            )
        registered_codes = selected_contract.get("runtime_config_error_codes")
        registered = (
            set(registered_codes) if isinstance(registered_codes, dict) else set()
        )
        members: list[str] = []
        if isinstance(error_code, str) and error_code:
            members.append(error_code)
        if isinstance(validation_issues, list):
            members.extend(
                issue for issue in validation_issues if isinstance(issue, str)
            )
        for member in dict.fromkeys(members):
            if member not in registered:
                issues.append(
                    "activation receipt error code is not registered: " + member
                )
        if receipt.get("activePackageDigest") != receipt.get("previousActiveDigest"):
            issues.append(
                "activation receipt failed status must preserve the active package"
            )

    return list(dict.fromkeys(issues))


def runtime_config_payload_digest(
    package: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    digest_input = {key: value for key, value in package.items() if key != "signature"}
    digest_input["payloadDigest"] = ""
    return _digest_bytes(
        _canonical_json_bytes(digest_input, selected_contract), selected_contract
    )


def build_runtime_config_trust_envelope(
    build_profile: str,
    trusted_public_keys: dict[str, str],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical profile-scoped trust envelope from an external keyring."""

    selected_contract = contract or load_launch_manifest_contract()
    try:
        canonical_keyring = decode_keyring(
            json.dumps(
                trusted_public_keys,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"runtimeConfigTrustEnvelope trustedPublicKeys is invalid: {exc}") from exc
    schema = selected_contract["schemas"]["runtime_config_trust_envelope"]
    trust_contract = selected_contract["runtime_config_trust"]
    envelope = {
        "schema": schema["schema_value"],
        "schemaVersion": trust_contract["schema_version"],
        "buildProfile": build_profile,
        "signatureAlgorithm": trust_contract["signature_algorithm"],
        "trustedPublicKeys": canonical_keyring,
    }
    issues = validate_runtime_config_trust_envelope(envelope, selected_contract)
    if issues:
        raise ValueError("; ".join(issues))
    return envelope


def validate_runtime_config_trust_envelope(
    runtime_config_trust_envelope: object,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the profile-only trust envelope and its canonical Ed25519 keyring."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        runtime_config_trust_envelope,
        "runtime_config_trust_envelope",
        contract=selected_contract,
        field_path="runtimeConfigTrustEnvelope",
    )
    if not isinstance(runtime_config_trust_envelope, dict):
        return issues
    keyring_value = runtime_config_trust_envelope.get("trustedPublicKeys")
    if isinstance(keyring_value, dict):
        try:
            canonical_keyring = decode_keyring(
                json.dumps(
                    keyring_value,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
        except (TypeError, ValueError) as exc:
            issues.append(
                f"runtimeConfigTrustEnvelope trustedPublicKeys is invalid: {exc}"
            )
        else:
            if keyring_value != canonical_keyring:
                issues.append(
                    "runtimeConfigTrustEnvelope trustedPublicKeys is not canonical"
                )
    return list(dict.fromkeys(issues))


def runtime_config_trust_envelope_digest(
    runtime_config_trust_envelope: object,
    contract: dict[str, Any] | None = None,
) -> str:
    selected_contract = contract or load_launch_manifest_contract()
    issues = validate_runtime_config_trust_envelope(
        runtime_config_trust_envelope,
        selected_contract,
    )
    if issues:
        raise ValueError("; ".join(issues))
    if not isinstance(runtime_config_trust_envelope, dict):
        raise ValueError("runtimeConfigTrustEnvelope must be object")
    return _digest_bytes(
        _canonical_json_bytes(runtime_config_trust_envelope, selected_contract),
        selected_contract,
    )


def validate_runtime_config_package(
    package: object,
    runtime_config_trust_envelope: object,
    contract: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Validate one signed runtime package against an explicit trust envelope."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        package,
        "runtime_config_package",
        contract=selected_contract,
        field_path="runtimeConfigPackage",
    )
    if not isinstance(package, dict):
        return issues
    if not isinstance(runtime_config_trust_envelope, dict):
        issues.append("runtimeConfigTrustEnvelope is required")
        envelope_keyring = None
        envelope_profile = None
    else:
        issues.extend(
            validate_runtime_config_trust_envelope(
                runtime_config_trust_envelope,
                selected_contract,
            )
        )
        envelope_keyring = runtime_config_trust_envelope.get("trustedPublicKeys")
        envelope_profile = runtime_config_trust_envelope.get("buildProfile")

    environment = package.get("environment")
    target = package.get("target")
    build_profile = package.get("buildProfile")
    launch_policy = package.get("launchPolicy")
    if selected_contract["target_environment"].get(target) != environment:
        issues.append("runtimeConfigPackage target/environment mapping is invalid")
    try:
        expected_profile = build_profile_for_environment(str(environment))
        expected_policy = launch_policy_for_build_profile(expected_profile)
    except ValueError as exc:
        issues.append(f"runtimeConfigPackage build profile mapping is invalid: {exc}")
    else:
        if build_profile != expected_profile:
            issues.append(
                "runtimeConfigPackage buildProfile is invalid for its environment"
            )
        if launch_policy != expected_policy:
            issues.append(
                "runtimeConfigPackage launchPolicy is invalid for its buildProfile"
            )
    if envelope_profile != build_profile:
        issues.append(
            "runtimeConfigPackage buildProfile disagrees with runtimeConfigTrustEnvelope"
        )
    runtime = package.get("runtime")
    runtime_keys = set(selected_contract["runtime_value_keys"])
    if isinstance(runtime, dict):
        for key in sorted(set(runtime) - runtime_keys):
            issue = f"runtimeConfigPackage.runtime.{key} is not declared by metadata"
            if issue not in issues:
                issues.append(issue)
        if runtime.get("appRuntimeEnv") != environment:
            issues.append("runtimeConfigPackage runtime environment identity drifted")

    expected_payload_digest = runtime_config_payload_digest(package, selected_contract)
    if package.get("payloadDigest") != expected_payload_digest:
        issues.append("runtimeConfigPackage payloadDigest does not match canonical payload")

    issued_at = _parse_rfc3339_utc(package.get("issuedAt"))
    expires_at = _parse_rfc3339_utc(package.get("expiresAt"))
    freshness = selected_contract["runtime_config_package"]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if issued_at is not None and expires_at is not None:
        if expires_at <= issued_at:
            issues.append("runtimeConfigPackage expiresAt must be later than issuedAt")
        maximum_lifetime = timedelta(
            seconds=int(freshness["max_lifetime_seconds"])
        )
        if expires_at - issued_at > maximum_lifetime:
            issues.append("runtimeConfigPackage lifetime exceeds metadata maximum")
        maximum_future = timedelta(
            seconds=int(freshness["max_future_skew_seconds"])
        )
        if issued_at > current + maximum_future:
            issues.append("runtimeConfigPackage issuedAt is too far in the future")
        if expires_at <= current:
            issues.append("runtimeConfigPackage is expired")

    package_keyring_value = package.get("trustedPublicKeys")
    signature_key_id = package.get("signatureKeyId")
    signature_value = package.get("signature")
    package_keyring: dict[str, str] | None = None
    if isinstance(package_keyring_value, dict):
        try:
            package_keyring = decode_keyring(
                json.dumps(
                    package_keyring_value,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
        except (TypeError, ValueError) as exc:
            issues.append(f"runtimeConfigPackage trustedPublicKeys is invalid: {exc}")
    if isinstance(envelope_keyring, dict):
        try:
            keyring = decode_keyring(
                json.dumps(
                    envelope_keyring,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
        except (TypeError, ValueError) as exc:
            issues.append(f"runtimeConfigTrustEnvelope trustedPublicKeys is invalid: {exc}")
        else:
            if package_keyring != keyring:
                issues.append(
                    "runtimeConfigPackage trustedPublicKeys disagrees with runtimeConfigTrustEnvelope"
                )
            public_value = keyring.get(str(signature_key_id))
            if public_value is None:
                issues.append(
                    "runtimeConfigPackage signatureKeyId is absent from runtimeConfigTrustEnvelope"
                )
            elif isinstance(signature_value, str):
                try:
                    signature = base64.b64decode(signature_value, validate=True)
                    public_key = base64.b64decode(public_value, validate=True)
                    verify_signature(
                        public_key,
                        canonical_signed_payload(package),
                        signature,
                    )
                except ValueError as exc:
                    issues.append(f"runtimeConfigPackage signature is invalid: {exc}")
    return list(dict.fromkeys(issues))


def validate_handoff_against_metadata(
    handoff: object,
    runtime_config_trust_envelope: object,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    """Validate one handoff against metadata and an explicit trust envelope."""

    selected_contract = contract or load_launch_manifest_contract()
    issues = _validate_schema_document(
        handoff,
        "app_launcher_handoff",
        contract=selected_contract,
        field_path="handoff",
    )
    if not isinstance(handoff, dict):
        return issues
    if not isinstance(runtime_config_trust_envelope, dict):
        issues.append("runtimeConfigTrustEnvelope is required")
        envelope_digest = None
        envelope_profile = None
    else:
        envelope_issues = validate_runtime_config_trust_envelope(
            runtime_config_trust_envelope,
            selected_contract,
        )
        issues.extend(envelope_issues)
        envelope_profile = runtime_config_trust_envelope.get("buildProfile")
        try:
            envelope_digest = runtime_config_trust_envelope_digest(
                runtime_config_trust_envelope,
                selected_contract,
            )
        except ValueError:
            envelope_digest = None
    effective_manifest = handoff.get("effectiveLaunchManifest")
    if not isinstance(effective_manifest, dict):
        return list(dict.fromkeys(issues))

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

    build_profile = effective_manifest.get("buildProfile")
    if build_profile != envelope_profile:
        issues.append(
            "effectiveLaunchManifest.buildProfile disagrees with runtimeConfigTrustEnvelope"
        )
    for field_path, actual_digest in (
        (
            "handoff.runtimeConfigTrustEnvelopeDigest",
            handoff.get("runtimeConfigTrustEnvelopeDigest"),
        ),
        (
            "effectiveLaunchManifest.runtimeConfigTrustEnvelopeDigest",
            effective_manifest.get("runtimeConfigTrustEnvelopeDigest"),
        ),
    ):
        if envelope_digest is not None and actual_digest != envelope_digest:
            issues.append(f"{field_path} does not match canonical trust envelope")

    launch_policy = effective_manifest.get("launchPolicy")
    policy_contract = selected_contract["launch_policies"].get(launch_policy)
    environment = effective_manifest.get("environment")
    if not isinstance(policy_contract, dict):
        issues.append(f"effective launch policy is unsupported: {launch_policy}")
    elif environment not in policy_contract.get("environments", []):
        issues.append(
            f"effective launch policy {launch_policy} is invalid for {environment}"
        )
    runtime_package = handoff.get("runtimeConfigPackage")
    if isinstance(runtime_package, dict):
        issues.extend(
            validate_runtime_config_package(
                runtime_package,
                runtime_config_trust_envelope,
                selected_contract,
            )
        )
        expected_package_digest = runtime_config_package_digest(
            runtime_package,
            selected_contract,
        )
        if handoff.get("runtimeConfigPackageDigest") != expected_package_digest:
            issues.append(
                "runtimeConfigPackageDigest does not match canonical metadata"
            )
        if (
            effective_manifest.get("runtimeConfigPackageDigest")
            != expected_package_digest
        ):
            issues.append(
                "effective launch manifest runtimeConfigPackageDigest is invalid"
            )
        for field in ("environment", "buildProfile", "target", "launchPolicy"):
            if runtime_package.get(field) != effective_manifest.get(field):
                issues.append(
                    f"runtimeConfigPackage.{field} disagrees with "
                    f"effectiveLaunchManifest.{field}"
                )
    compile_diagnostics = handoff.get("compileDiagnostics")
    if isinstance(compile_diagnostics, dict):
        forbidden_fragments = (
            "APP_RUNTIME_ENV",
            "GATEWAY",
            "RTC",
            "CDN",
            "BASE_URL",
            "ENDPOINT",
            "SECRET",
        )
        for key in compile_diagnostics:
            upper = str(key).upper()
            if any(fragment in upper for fragment in forbidden_fragments):
                issues.append(
                    f"compileDiagnostics.{key} must not contain runtime configuration"
                )

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
        return list(dict.fromkeys(issues))
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
    return list(dict.fromkeys(issues))

