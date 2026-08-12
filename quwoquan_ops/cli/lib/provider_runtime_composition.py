"""Compile packageable Provider runtime workloads from canonical Bindings.

The service-local external Bindings remain the only adapter selector.  This
module derives the target-local workload closure from those compiled Bindings
and the existing endpoint contracts; it does not maintain a Provider registry
or accept runtime feature flags.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .external_provider_governance import (
    FIRST_PARTY_AUTHORITY_ADAPTER,
    NONPROD_ENVIRONMENTS,
    PLATFORM_LOCAL_ADAPTERS,
    is_local_substitute_adapter,
    is_prod_forbidden_adapter,
    load_and_compile,
)
from .provider_endpoint_contract import CONTRACT_ROOT, ENVIRONMENT_KEY_RE

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "stackctl-provider-runtime-composition"
ENDPOINT_CONTRACT_SCHEMA = "provider-endpoint-contract"
COMPILED_BINDING_SCHEMA = "compiled-external-provider-bindings"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMPOSITION_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "bindingDigest",
        "runtimeCompositionDigest",
        "bindings",
        "materialKeys",
        "workloads",
    }
)
WORKLOAD_FIELDS = frozenset(
    {
        "role",
        "capabilityIds",
        "adapterIds",
        "endpointEnvironmentKeys",
        "composeProfiles",
        "contractRef",
        "contractDigest",
        "composeRef",
        "composeDigest",
    }
)

# These adapters are concrete infrastructure inside the candidate topology,
# not third-party vendor integrations.  Their endpoint shape is deliberately
# fixed here so a non-production Binding cannot turn an infrastructure
# exception into an arbitrary external endpoint.
_NONPROD_INFRASTRUCTURE_ENDPOINTS = {
    "infra.redis.message_transport": frozenset({""}),
    "infra.minio.object_storage": frozenset(
        {"environment_binding:content.object_storage"}
    ),
    "infra.livekit_sfu": frozenset({"environment_binding:rtc.livekit"}),
}


def compile_provider_runtime_composition(
    *,
    environment: str,
    target: str,
    compiled: Mapping[str, Any] | None = None,
    contract_root: Path | None = None,
) -> dict[str, Any]:
    """Derive an immutable Provider workload identity for one target.

    ``compiled`` and ``contract_root`` are injectable only for local-contract
    tests. Production callers omit them and therefore consume the canonical
    compiler output plus checked-in endpoint contracts.
    """

    validate_provider_runtime_scope(environment, target)
    source = compiled
    if source is None:
        loaded, issues = load_and_compile()
        if issues:
            raise RuntimeError("; ".join(issue.render() for issue in issues))
        source = loaded
    if source.get("schema") != COMPILED_BINDING_SCHEMA:
        raise ValueError("compiled Provider Binding schema mismatch")
    compiled_issues = source.get("issues") or []
    if compiled_issues:
        raise RuntimeError(
            "compiled Provider Bindings are invalid: "
            + "; ".join(str(issue) for issue in compiled_issues)
        )
    selected = source.get("selectedBindings")
    scope = selected.get(environment) if isinstance(selected, Mapping) else None
    if not isinstance(scope, Mapping) or not scope:
        raise ValueError(
            f"compiled Provider Bindings have no environment {environment}"
        )

    bindings = _canonical_bindings(scope)
    _validate_nonprod_isolation_policy(environment, bindings)
    endpoint_contracts = _load_endpoint_contracts(contract_root or CONTRACT_ROOT)
    workloads: dict[str, dict[str, Any]] = {}
    endpoint_material_keys: set[str] = set()
    secret_material_keys: set[str] = set()

    for binding in bindings:
        endpoint_material_keys.update(binding["endpointEnvironmentKeys"].values())
        secret_material_keys.update(binding["secretEnvironmentKeys"])
        if binding["state"] != "enabled":
            continue
        adapter_id = binding["adapterId"]
        endpoint_ref = binding["endpointRef"]
        if environment == "prod" and is_prod_forbidden_adapter(adapter_id):
            raise ValueError(
                "Prod Provider runtime forbids non-production adapter "
                f"{adapter_id} for {binding['capabilityId']}"
            )

        role = _local_topology_role(endpoint_ref)
        endpoint_contract = endpoint_contracts.get(role) if role else None
        if environment == "prod" and endpoint_contract is not None:
            raise ValueError(
                "Prod Provider runtime forbids non-production local workload "
                f"{role} for {binding['capabilityId']}"
            )
        if endpoint_contract is None:
            if (
                environment in NONPROD_ENVIRONMENTS
                and adapter_id not in PLATFORM_LOCAL_ADAPTERS
                and is_prod_forbidden_adapter(adapter_id)
            ):
                raise ValueError(
                    "non-production Provider substitute has no canonical "
                    f"endpoint workload contract: {binding['capabilityId']} "
                    f"adapter={adapter_id} endpointRef={endpoint_ref or '<empty>'}"
                )
            continue
        if (
            not endpoint_contract["composeRef"]
            or not endpoint_contract["composeDigest"]
        ):
            raise ValueError(
                f"local Provider workload {role} has no canonical Compose deployment"
            )

        endpoint_keys = set(binding["endpointEnvironmentKeys"].values())
        unknown_keys = sorted(endpoint_keys - endpoint_contract["endpointKeys"])
        if unknown_keys:
            raise ValueError(
                f"{binding['capabilityId']} references endpoint material outside "
                f"the {role} contract: {','.join(unknown_keys)}"
            )
        workload = workloads.setdefault(
            role,
            {
                "role": role,
                "capabilityIds": set(),
                "adapterIds": set(),
                "endpointEnvironmentKeys": set(),
                "composeProfiles": endpoint_contract["composeProfiles"],
                "contractRef": endpoint_contract["contractRef"],
                "contractDigest": endpoint_contract["contractDigest"],
                "composeRef": endpoint_contract["composeRef"],
                "composeDigest": endpoint_contract["composeDigest"],
            },
        )
        workload["capabilityIds"].add(binding["capabilityId"])
        workload["adapterIds"].add(adapter_id)
        workload["endpointEnvironmentKeys"].update(endpoint_keys)

    normalized_workloads = [
        {
            **workload,
            "capabilityIds": sorted(workload["capabilityIds"]),
            "adapterIds": sorted(workload["adapterIds"]),
            "endpointEnvironmentKeys": sorted(workload["endpointEnvironmentKeys"]),
        }
        for _, workload in sorted(workloads.items())
    ]
    binding_digest = _digest(bindings)
    material_keys = {
        "endpoint": sorted(endpoint_material_keys),
        "secret": sorted(secret_material_keys),
    }
    runtime_digest = _digest(
        {
            "environment": environment,
            "target": target,
            "bindingDigest": binding_digest,
            "materialKeys": material_keys,
            "workloads": normalized_workloads,
        }
    )
    return {
        "schema": SCHEMA,
        "environment": environment,
        "target": target,
        "bindingDigest": binding_digest,
        "runtimeCompositionDigest": runtime_digest,
        "bindings": bindings,
        "materialKeys": material_keys,
        "workloads": normalized_workloads,
    }


def validate_provider_runtime_composition(
    payload: object,
    *,
    expected_environment: str,
    expected_target: str,
    require_current_contracts: bool = True,
) -> dict[str, Any]:
    """Validate a packaged composition without rereading workspace Bindings."""

    validate_provider_runtime_scope(expected_environment, expected_target)
    if not isinstance(payload, dict) or set(payload) != COMPOSITION_FIELDS:
        raise ValueError("Provider runtime composition fields mismatch")
    if payload.get("schema") != SCHEMA:
        raise ValueError("Provider runtime composition schema mismatch")
    if (
        payload.get("environment") != expected_environment
        or payload.get("target") != expected_target
    ):
        raise ValueError("Provider runtime composition target identity mismatch")

    bindings = payload.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("Provider runtime composition bindings are missing")
    raw_scope: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "capabilityId",
            "state",
            "adapterId",
            "endpointRef",
            "endpointEnvironmentKeys",
            "secretEnvironmentKeys",
        }:
            raise ValueError("Provider runtime composition Binding fields mismatch")
        capability_id = str(binding.get("capabilityId") or "")
        if capability_id in raw_scope:
            raise ValueError("Provider runtime composition has duplicate capability")
        raw_scope[capability_id] = {
            "state": binding.get("state"),
            "adapter_id": binding.get("adapterId"),
            "endpoint_ref": binding.get("endpointRef"),
            "endpoint_envs": binding.get("endpointEnvironmentKeys"),
            "secret_refs": binding.get("secretEnvironmentKeys"),
        }
    if _canonical_bindings(raw_scope) != bindings:
        raise ValueError("Provider runtime composition bindings are not canonical")
    _validate_nonprod_isolation_policy(expected_environment, bindings)
    binding_digest = str(payload.get("bindingDigest") or "")
    if binding_digest != _digest(bindings):
        raise ValueError("Provider runtime composition bindingDigest mismatch")

    material_keys = payload.get("materialKeys")
    if not isinstance(material_keys, dict) or set(material_keys) != {
        "endpoint",
        "secret",
    }:
        raise ValueError("Provider runtime composition materialKeys mismatch")
    for kind in ("endpoint", "secret"):
        keys = material_keys.get(kind)
        if (
            not isinstance(keys, list)
            or keys != sorted(set(keys))
            or any(
                not isinstance(key, str) or ENVIRONMENT_KEY_RE.fullmatch(key) is None
                for key in keys
            )
        ):
            raise ValueError(
                f"Provider runtime composition {kind} material keys are invalid"
            )
    expected_material_keys = {
        "endpoint": sorted(
            {
                key
                for binding in bindings
                for key in binding["endpointEnvironmentKeys"].values()
            }
        ),
        "secret": sorted(
            {
                key
                for binding in bindings
                for key in binding["secretEnvironmentKeys"]
            }
        ),
    }
    if material_keys != expected_material_keys:
        raise ValueError("Provider runtime composition materialKeys closure mismatch")

    workloads = payload.get("workloads")
    if not isinstance(workloads, list):
        raise TypeError("Provider runtime composition workloads are invalid")
    by_capability = {
        str(binding["capabilityId"]): binding for binding in bindings
    }
    workload_roles: set[str] = set()
    represented_capabilities: set[str] = set()
    canonical_contracts = (
        _load_endpoint_contracts(CONTRACT_ROOT) if require_current_contracts else {}
    )
    for workload in workloads:
        if not isinstance(workload, dict) or set(workload) != WORKLOAD_FIELDS:
            raise ValueError("Provider runtime composition workload fields mismatch")
        role = str(workload.get("role") or "")
        if not role or role in workload_roles:
            raise ValueError("Provider runtime composition workload role is invalid")
        workload_roles.add(role)
        for field in (
            "capabilityIds",
            "adapterIds",
            "endpointEnvironmentKeys",
            "composeProfiles",
        ):
            values = workload.get(field)
            if not isinstance(values, list) or values != sorted(set(values)):
                raise ValueError(
                    f"Provider runtime composition workload {field} is not canonical"
                )
        for ref_field, digest_field in (
            ("contractRef", "contractDigest"),
            ("composeRef", "composeDigest"),
        ):
            reference = str(workload.get(ref_field) or "")
            digest = str(workload.get(digest_field) or "")
            if bool(reference) != bool(digest) or (
                digest and DIGEST_RE.fullmatch(digest) is None
            ):
                raise ValueError(
                    f"Provider runtime composition workload {digest_field} is invalid"
                )
        capability_ids = workload["capabilityIds"]
        if not capability_ids:
            raise ValueError(
                "Provider runtime composition workload has no capabilities"
            )
        selected_bindings: list[dict[str, Any]] = []
        for capability_id in capability_ids:
            binding = by_capability.get(str(capability_id))
            if binding is None or binding.get("state") != "enabled":
                raise ValueError(
                    "Provider runtime composition workload capability is not enabled"
                )
            if binding.get("endpointRef") != f"local_topology:{role}":
                raise ValueError(
                    "Provider runtime composition adapter/endpoint workload mismatch"
                )
            if capability_id in represented_capabilities:
                raise ValueError(
                    "Provider runtime composition capability has duplicate workloads"
                )
            represented_capabilities.add(str(capability_id))
            selected_bindings.append(binding)
        expected_adapter_ids = sorted(
            {str(binding["adapterId"]) for binding in selected_bindings}
        )
        expected_endpoint_keys = sorted(
            {
                key
                for binding in selected_bindings
                for key in binding["endpointEnvironmentKeys"].values()
            }
        )
        if workload["adapterIds"] != expected_adapter_ids:
            raise ValueError(
                "Provider runtime composition adapter/workload mismatch"
            )
        if workload["endpointEnvironmentKeys"] != expected_endpoint_keys:
            raise ValueError(
                "Provider runtime composition endpoint material mismatch"
            )
        if require_current_contracts:
            canonical_contract = canonical_contracts.get(role)
            if canonical_contract is None:
                raise ValueError(
                    f"Provider runtime composition workload contract is unknown: {role}"
                )
            for field in (
                "composeProfiles",
                "contractRef",
                "contractDigest",
                "composeRef",
                "composeDigest",
            ):
                if workload[field] != canonical_contract[field]:
                    raise ValueError(
                        "Provider runtime composition canonical workload drift: "
                        f"{role} {field}"
                    )
    if [str(workload["role"]) for workload in workloads] != sorted(workload_roles):
        raise ValueError("Provider runtime composition workloads are not canonical")

    if expected_environment == "prod":
        if workloads:
            raise ValueError("Prod Provider runtime cannot contain local workloads")
        for binding in bindings:
            if is_prod_forbidden_adapter(str(binding.get("adapterId") or "")):
                raise ValueError(
                    "Prod Provider runtime contains non-production adapter"
                )
    else:
        for binding in bindings:
            adapter_id = str(binding.get("adapterId") or "")
            if (
                binding.get("state") == "enabled"
                and adapter_id not in PLATFORM_LOCAL_ADAPTERS
                and is_prod_forbidden_adapter(adapter_id)
                and binding["capabilityId"] not in represented_capabilities
            ):
                raise ValueError(
                    "Provider runtime composition substitute workload is missing"
                )

    runtime_digest = _digest(
        {
            "environment": expected_environment,
            "target": expected_target,
            "bindingDigest": binding_digest,
            "materialKeys": material_keys,
            "workloads": workloads,
        }
    )
    if payload.get("runtimeCompositionDigest") != runtime_digest:
        raise ValueError("Provider runtime composition digest mismatch")
    return payload


def _validate_nonprod_isolation_policy(
    environment: str,
    bindings: list[dict[str, Any]],
) -> None:
    """Keep non-production third-party capabilities behind local substitutes.

    This rule is intentionally independent from the currently selected
    environment Binding.  Rehashing a package or changing the authority source
    to a production vendor therefore cannot make an Alpha/Beta/Gamma runtime
    composition acceptable.
    """

    if environment not in NONPROD_ENVIRONMENTS:
        return
    for binding in bindings:
        if binding.get("state") != "enabled":
            continue
        capability_id = str(binding["capabilityId"])
        adapter_id = str(binding["adapterId"])
        endpoint_ref = str(binding["endpointRef"])
        if adapter_id == FIRST_PARTY_AUTHORITY_ADAPTER:
            if not endpoint_ref.startswith("service_topology:"):
                raise ValueError(
                    "non-production first-party authority must use service topology: "
                    f"{capability_id}"
                )
            continue
        if adapter_id == "ext.obs.elasticsearch":
            if endpoint_ref != f"local_topology:{environment}.elasticsearch":
                raise ValueError(
                    "non-production Elasticsearch endpoint crosses target isolation: "
                    f"{capability_id}"
                )
            continue
        allowed_infrastructure_endpoints = _NONPROD_INFRASTRUCTURE_ENDPOINTS.get(
            adapter_id
        )
        if allowed_infrastructure_endpoints is not None:
            if endpoint_ref not in allowed_infrastructure_endpoints:
                raise ValueError(
                    "non-production infrastructure Provider endpoint is not isolated: "
                    f"{capability_id} adapter={adapter_id}"
                )
            continue
        if (
            not is_local_substitute_adapter(adapter_id)
            or not endpoint_ref.startswith("local_topology:")
        ):
            raise ValueError(
                "non-production third-party Provider must select a local substitute: "
                f"{capability_id} adapter={adapter_id} "
                f"endpointRef={endpoint_ref or '<empty>'}"
            )


def _canonical_bindings(scope: Mapping[str, Any]) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for capability_id, raw_binding in sorted(scope.items()):
        capability = str(capability_id).strip()
        if not capability or not isinstance(raw_binding, Mapping):
            raise ValueError("compiled Provider Binding entry is invalid")
        state = str(raw_binding.get("state") or "").strip()
        adapter_id = str(raw_binding.get("adapter_id") or "").strip()
        endpoint_ref = str(raw_binding.get("endpoint_ref") or "").strip()
        endpoint_envs = raw_binding.get("endpoint_envs") or {}
        secret_refs = raw_binding.get("secret_refs") or []
        if not state or not isinstance(endpoint_envs, Mapping):
            raise ValueError(f"{capability} compiled Provider Binding is incomplete")
        if isinstance(secret_refs, (str, bytes)) or not isinstance(
            secret_refs, Sequence
        ):
            raise TypeError(
                f"{capability} compiled Provider secret references are invalid"
            )
        canonical_endpoints = {
            str(role): str(key)
            for role, key in sorted(endpoint_envs.items())
            if str(role).strip() and str(key).strip()
        }
        canonical_secrets = sorted(
            {str(key).strip() for key in secret_refs if str(key).strip()}
        )
        invalid_keys = sorted(
            key
            for key in [*canonical_endpoints.values(), *canonical_secrets]
            if ENVIRONMENT_KEY_RE.fullmatch(key) is None
        )
        if invalid_keys:
            raise ValueError(
                f"{capability} compiled Provider material keys are invalid: "
                + ",".join(invalid_keys)
            )
        bindings.append(
            {
                "capabilityId": capability,
                "state": state,
                "adapterId": adapter_id,
                "endpointRef": endpoint_ref,
                "endpointEnvironmentKeys": canonical_endpoints,
                "secretEnvironmentKeys": canonical_secrets,
            }
        )
    return bindings


def _load_endpoint_contracts(contract_root: Path) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for path in sorted(contract_root.glob("*/contract/endpoints.yaml")):
        _validate_repo_regular_file(path, label="Provider endpoint contract")
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Provider endpoint contract is unreadable: {path}: {exc}"
            ) from exc
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema") != ENDPOINT_CONTRACT_SCHEMA
        ):
            raise ValueError(f"Provider endpoint contract schema mismatch: {path}")
        role = str(payload.get("role") or "").strip()
        endpoints = payload.get("endpoints")
        if not role or not isinstance(endpoints, Mapping) or not endpoints:
            raise ValueError(f"Provider endpoint contract is incomplete: {path}")
        if role in contracts:
            raise ValueError(f"duplicate Provider endpoint workload role: {role}")
        compose_path = path.parents[1] / "deploy" / "compose.yaml"
        endpoint_keys = {str(key) for key in endpoints}
        contracts[role] = {
            "endpointKeys": endpoint_keys,
            "contractPath": path,
            "composePath": compose_path,
        }

    for role, contract in contracts.items():
        compose_path = contract.pop("composePath")
        contract_path = contract.pop("contractPath")
        if not compose_path.is_file():
            # Some external integrations, such as LiveKit, are deployed by the
            # platform base and are not selected by a local_topology Binding.
            contract.update(
                {
                    "composeProfiles": [],
                    "contractRef": _display_path(contract_path),
                    "contractDigest": _sha256_file(contract_path),
                    "composeRef": "",
                    "composeDigest": "",
                }
            )
            continue
        _validate_repo_regular_file(compose_path, label="Provider workload Compose")
        try:
            compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Provider workload Compose is unreadable: {compose_path}: {exc}"
            ) from exc
        services = compose.get("services") if isinstance(compose, Mapping) else None
        service = services.get(role) if isinstance(services, Mapping) else None
        if service is None:
            raise ValueError(
                f"Provider workload Compose does not own service {role}: {compose_path}"
            )
        if not isinstance(service, Mapping):
            raise TypeError(
                f"Provider workload Compose service is invalid for {role}: {compose_path}"
            )
        profiles = service.get("profiles") or []
        if isinstance(profiles, (str, bytes)) or not isinstance(profiles, Sequence):
            raise TypeError(f"Provider workload profiles are invalid: {compose_path}")
        contract.update(
            {
                "composeProfiles": sorted(
                    {
                        str(profile).strip()
                        for profile in profiles
                        if str(profile).strip()
                    }
                ),
                "contractRef": _display_path(contract_path),
                "contractDigest": _sha256_file(contract_path),
                "composeRef": _display_path(compose_path),
                "composeDigest": _sha256_file(compose_path),
            }
        )
    return contracts


def _validate_repo_regular_file(path: Path, *, label: str) -> None:
    """Reject absolute/ref traversal and every symlink component under ROOT."""

    root = ROOT.resolve()
    candidate = path if path.is_absolute() else ROOT / path
    unresolved = candidate.absolute()
    try:
        relative = unresolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} is outside the repository: {path}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} contains a symlink: {path}")
    resolved = candidate.resolve()
    if (
        not resolved.is_relative_to(root)
        or not resolved.is_file()
        or ".." in relative.parts
    ):
        raise ValueError(f"{label} is not a safe repository file: {path}")


def _local_topology_role(endpoint_ref: str) -> str:
    prefix = "local_topology:"
    return endpoint_ref.removeprefix(prefix) if endpoint_ref.startswith(prefix) else ""


def validate_provider_runtime_scope(environment: str, target: str) -> None:
    """Fail closed when a Provider environment is paired with another target."""

    expected_target = (
        f"{environment}-local" if environment in NONPROD_ENVIRONMENTS else "prod-hosted"
    )
    if environment not in {*NONPROD_ENVIRONMENTS, "prod"}:
        raise ValueError(f"unsupported Provider environment: {environment}")
    if target != expected_target:
        raise ValueError(
            "Provider target/environment mismatch: "
            f"environment={environment} target={target}"
        )


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
