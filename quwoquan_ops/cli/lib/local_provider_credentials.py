"""Materialize the canonical Alpha/Beta/Gamma substitute topology.

Object-owned adapter contracts plus service-local selections are the only
adapter inventory. This module projects their topology-owned endpoints and reuses the
target-scoped LiveKit material created by ``local_environment_auth``. It does
not create business data, Provider success evidence, or any Prod material.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .external_provider_governance import NONPROD_ENVIRONMENTS, load_and_compile
from .provider_config import packaged_runtime_bindings
from .provider_endpoint_contract import load_provider_endpoint_environment
from .provider_runtime_composition import validate_provider_runtime_composition

# Local infrastructure material is owned by its topology materializer.  It is
# deliberately excluded here so Provider validation does not create a second
# object-storage or Redis owner.
_PLATFORM_OWNED_KEYS = frozenset(
    {
        "CONTENT_OSS_ENDPOINT",
        "CONTENT_OSS_ACCESS_KEY_ID",
        "CONTENT_OSS_ACCESS_KEY_SECRET",
        "CONTENT_OSS_BUCKET",
        "CONTENT_OSS_REGION",
        "CONTENT_CDN_SIGN_KEY",
        "CONTENT_MEDIA_DELIVERY_BASE_URL",
        "CONTENT_MEDIA_UPLOAD_BASE_URL",
    }
)

_FORBIDDEN_VALUE_MARKERS = (
    ".invalid",
    "fixture.local",
    "example.com",
    "changeme",
    "placeholder",
)

_OWNER_ONLY_FILE_KEYS = frozenset(
    {
        "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE",
        "INTEGRATION_PUSH_APNS_KEY_FILE",
        "INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE",
    }
)


def load_nonprod_provider_environment(
    *,
    environment: str,
    target_name: str,
    source: Mapping[str, str] | None = None,
    debug_local: bool = True,
    runtime_composition: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Return topology-owned substitutes and target-scoped LiveKit secrets."""

    if environment not in NONPROD_ENVIRONMENTS:
        raise ValueError(
            "non-production Provider substitutes are only valid for "
            f"Alpha/Beta/Gamma, got {environment}"
        )
    if target_name != f"{environment}-local":
        raise ValueError(
            "Provider target/environment mismatch: "
            f"environment={environment} target={target_name}"
        )

    material = os.environ if source is None else source
    endpoint_keys, secret_keys = _required_material_for_environment(
        environment,
        debug_local=debug_local,
        target_name=target_name,
        runtime_composition=runtime_composition,
    )
    # local_topology endpoints are derived below and can never be overridden
    # by the invoking shell. Only target-scoped secrets remain runtime inputs.
    runtime_secret_keys = set(secret_keys)
    selected_endpoint_keys: set[str] | None = None
    if runtime_composition is not None:
        validated = validate_provider_runtime_composition(
            runtime_composition,
            expected_environment=environment,
            expected_target=target_name,
        )
        selected_endpoint_keys = set(validated["materialKeys"]["endpoint"])
        selected_roles = {
            str(workload["role"])
            for workload in validated["workloads"]
        }
        if debug_local and "sms-provider-substitute" in selected_roles:
            runtime_secret_keys.add("SMS_SUBSTITUTE_OPERATOR_TOKEN")
        if debug_local and "provider-protocol-substitute" in selected_roles:
            runtime_secret_keys.add("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN")
    elif debug_local:
        runtime_secret_keys.update(
            {
                "SMS_SUBSTITUTE_OPERATOR_TOKEN",
                "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN",
            }
        )
    required_keys = sorted(
        runtime_secret_keys
        if debug_local
        else endpoint_keys | runtime_secret_keys
    )
    missing = [key for key in required_keys if not str(material.get(key) or "").strip()]
    if missing:
        raise RuntimeError(
            "GATE_BLOCK: target-scoped nonprod Provider material is missing: "
            + ",".join(missing)
        )

    invalid = [
        key
        for key in required_keys
        if _looks_like_placeholder(str(material[key]))
    ]
    if invalid:
        raise RuntimeError(
            "GATE_BLOCK: target-scoped nonprod Provider material contains placeholder values: "
            + ",".join(invalid)
        )

    invalid_files: list[str] = []
    weak_file_modes: list[str] = []
    for key in sorted(secret_keys):
        if not key.endswith("_FILE"):
            continue
        path = Path(str(material[key]).strip()).expanduser()
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            invalid_files.append(key)
            continue
        if key in _OWNER_ONLY_FILE_KEYS and path.stat().st_mode & 0o077:
            weak_file_modes.append(key)
    if invalid_files:
        raise RuntimeError(
            "GATE_BLOCK: protected Provider file material is not an absolute "
            "regular file: "
            + ",".join(invalid_files)
        )
    if weak_file_modes:
        raise RuntimeError(
            "GATE_BLOCK: protected Provider private file permissions must be "
            "owner-only: "
            + ",".join(weak_file_modes)
        )

    values = load_provider_endpoint_environment() if debug_local else {}
    if selected_endpoint_keys is not None:
        values = {
            key: value
            for key, value in values.items()
            if key in selected_endpoint_keys
        }
    values.update({key: str(material[key]).strip() for key in required_keys})
    return values


def provider_environment_reference_names(
    environment: str,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return canonical Provider env references without reading their values.

    Packaging uses this inventory only to satisfy build-tool interpolation.
    Runtime preflight uses ``load_nonprod_provider_environment`` and therefore
    remains fail-closed on missing target-scoped LiveKit material.
    """

    endpoints, secrets = _required_material_for_environment(
        environment,
        debug_local=False,
    )
    return frozenset(endpoints), frozenset(secrets)


def _required_material_for_environment(
    environment: str,
    *,
    debug_local: bool = True,
    target_name: str = "",
    runtime_composition: Mapping[str, Any] | None = None,
) -> tuple[set[str], set[str]]:
    if runtime_composition is None:
        compiled, issues = load_and_compile()
        if issues:
            raise RuntimeError("; ".join(issue.render() for issue in issues))
        scope = compiled["selectedBindings"][environment]
    else:
        target = target_name or f"{environment}-local"
        validated = validate_provider_runtime_composition(
            runtime_composition,
            expected_environment=environment,
            expected_target=target,
        )
        scope = packaged_runtime_bindings(validated)
    endpoint_keys: set[str] = set()
    secret_keys: set[str] = set()
    for capability, binding in scope.items():
        if not isinstance(binding, Mapping) or binding.get("state") != "enabled":
            continue
        adapter_id = str(binding.get("adapter_id") or "")
        endpoint_ref = str(binding.get("endpoint_ref") or "")
        if str(capability) == "identity.sms.otp":
            local_capture = adapter_id == "ext.sms.local_capture"
            local_capture_endpoint = (
                endpoint_ref == "local_topology:sms-provider-substitute"
            )
            if local_capture != local_capture_endpoint:
                raise ValueError(
                    "packaged SMS adapter/endpoint selection mismatch"
                )
            if debug_local and local_capture:
                endpoint_envs = binding.get("endpoint_envs") or {}
                if (
                    not isinstance(endpoint_envs, Mapping)
                    or endpoint_envs.get("endpoint") != "INTEGRATION_SMS_ENDPOINT"
                ):
                    raise ValueError(
                        "packaged SMS local-capture endpoint material mismatch"
                    )
                secret_keys.update(
                    str(value)
                    for value in (binding.get("secret_refs") or [])
                    if str(value) not in _PLATFORM_OWNED_KEYS
                )
                continue
        # Local infrastructure endpoints are resolved by the packaged
        # topology and must not be shadowed by protected Provider input.
        topology_owned = endpoint_ref.startswith(
            ("local_topology:", "service_topology:")
        )
        if not topology_owned:
            endpoint_envs = binding.get("endpoint_envs") or {}
            if isinstance(endpoint_envs, Mapping):
                endpoint_keys.update(
                    str(value)
                    for value in endpoint_envs.values()
                    if str(value) not in _PLATFORM_OWNED_KEYS
                )
        secret_keys.update(
            str(value)
            for value in (binding.get("secret_refs") or [])
            if str(value) not in _PLATFORM_OWNED_KEYS
        )
    return endpoint_keys, secret_keys


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in _FORBIDDEN_VALUE_MARKERS)
