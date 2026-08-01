"""Validate protected non-production Provider material without generating it.

The service-local environment bindings are the only inventory.  This module
only copies already injected values into a stackctl child environment; it never
persists credentials and never fabricates endpoints, tokens, or Provider
success.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .external_provider_governance import NONPROD_ENVIRONMENTS, load_bindings


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


def load_protected_provider_environment(
    *,
    environment: str,
    target_name: str,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return required Provider values already injected by a protected owner.

    Missing or placeholder material is a deployment preflight failure.  Values
    are never written to a receipt, repository path, or deployment secret file.
    """

    if environment not in NONPROD_ENVIRONMENTS:
        raise ValueError(
            "protected non-production Provider material is only valid for "
            f"Alpha/Beta/Gamma, got {environment}"
        )
    if target_name != f"{environment}-local":
        raise ValueError(
            "Provider target/environment mismatch: "
            f"environment={environment} target={target_name}"
        )

    material = os.environ if source is None else source
    endpoint_keys, secret_keys = _required_material_for_environment(environment)
    required_keys = sorted(endpoint_keys | secret_keys)
    missing = [key for key in required_keys if not str(material.get(key) or "").strip()]
    if missing:
        raise RuntimeError(
            "GATE_BLOCK: protected Provider material is missing: "
            + ",".join(missing)
        )

    invalid = [
        key
        for key in required_keys
        if _looks_like_placeholder(str(material[key]))
    ]
    if invalid:
        raise RuntimeError(
            "GATE_BLOCK: protected Provider material contains placeholder values: "
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

    return {key: str(material[key]).strip() for key in required_keys}


def provider_environment_reference_names(
    environment: str,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return canonical Provider env references without reading their values.

    Packaging uses this inventory only to satisfy build-tool interpolation.
    Runtime preflight continues to use ``load_protected_provider_environment``
    and therefore remains fail-closed on missing or invalid protected values.
    """

    endpoints, secrets = _required_material_for_environment(environment)
    return frozenset(endpoints), frozenset(secrets)


def _required_material_for_environment(
    environment: str,
) -> tuple[set[str], set[str]]:
    bindings = load_bindings()
    scope = bindings["environments"][environment]
    endpoint_keys: set[str] = set()
    secret_keys: set[str] = set()
    for service_bindings in scope.values():
        if not isinstance(service_bindings, Mapping):
            continue
        for binding in service_bindings.values():
            if not isinstance(binding, Mapping) or binding.get("state") != "enabled":
                continue
            endpoint_ref = str(binding.get("endpointRef") or "")
            # Local infrastructure endpoints are resolved by the packaged
            # topology and must not be shadowed by protected Provider input.
            topology_owned = endpoint_ref.startswith("local_topology:")
            if not topology_owned:
                endpoint_envs = binding.get("endpointEnvs") or {}
                if isinstance(endpoint_envs, Mapping):
                    endpoint_keys.update(
                        str(value)
                        for value in endpoint_envs.values()
                        if str(value) not in _PLATFORM_OWNED_KEYS
                    )
            secret_keys.update(
                str(value)
                for value in (binding.get("secretRefs") or [])
                if str(value) not in _PLATFORM_OWNED_KEYS
            )
    return endpoint_keys, secret_keys


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in _FORBIDDEN_VALUE_MARKERS)
