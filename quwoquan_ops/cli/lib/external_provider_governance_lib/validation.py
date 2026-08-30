"""registry / bindings / conformance manifest 的治理校验（原单文件逐字搬运）。

``_service_roots`` 消费点经薄入口模块命名空间 ``_entry.X`` 属性访问，
保持与拆分前单文件相同的 mock.patch 语义。
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.external_provider_governance as _entry

from .constants import (
    ADAPTER_RE,
    CAPABILITY_RE,
    ENV_KEY_RE,
    ENVIRONMENTS,
    MESSAGE_TRANSPORT_CAPABILITY_ID,
    MESSAGE_TRANSPORT_REQUIRED_METRICS,
    NONPROD_ENVIRONMENTS,
    RELEASE_ADAPTER_ENVIRONMENTS,
    STATES,
    is_prod_forbidden_adapter,
)
from .models import ProviderGovernanceIssue


def registry_issues(registry: Mapping[str, Any]) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        return [ProviderGovernanceIssue("metadata", "derived capabilities must be a list")]
    seen: set[str] = set()
    for index, capability in enumerate(capabilities):
        location = f"metadata.externalDependencies[{index}]"
        if not isinstance(capability, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be a mapping"))
            continue
        capability_id = str(capability.get("capability_id") or "")
        if not CAPABILITY_RE.fullmatch(capability_id):
            issues.append(ProviderGovernanceIssue(location, "invalid capability id"))
        if capability.get("_invalid_role"):
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "external dependency role must be owner or use",
                )
            )
        if capability.get("_missing_owner"):
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "capability-use requires exactly one capability owner",
                )
            )
        if capability_id in seen or capability.get("_duplicate_owner"):
            issues.append(ProviderGovernanceIssue(location, "capability must have one object owner"))
        seen.add(capability_id)
        if (
            not capability.get("canonical_port")
            or not capability.get("operations")
            or not capability.get("conformance_profile")
        ):
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "capability owner requires port, operations and conformance",
                )
            )
        adapter_contracts = capability.get("adapter_contracts")
        if not isinstance(adapter_contracts, Mapping) or not adapter_contracts:
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "capability owner requires adapterContracts",
                )
            )
        else:
            for adapter_id, contract in adapter_contracts.items():
                contract_location = f"{location}.adapterContracts.{adapter_id}"
                if not ADAPTER_RE.fullmatch(str(adapter_id)):
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "adapter id is invalid",
                        )
                    )
                if not isinstance(contract, Mapping):
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "adapter contract must be a mapping",
                        )
                    )
                    continue
                endpoint_envs = contract.get("endpointEnvs") or {}
                secret_refs = contract.get("secretRefs") or []
                allowed_overrides = contract.get("allowEnvironmentOverrides") or []
                if not isinstance(endpoint_envs, Mapping) or any(
                    not ENV_KEY_RE.fullmatch(str(value))
                    for value in endpoint_envs.values()
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "endpointEnvs must contain environment key names",
                        )
                    )
                if not isinstance(secret_refs, list) or any(
                    not ENV_KEY_RE.fullmatch(str(value))
                    for value in secret_refs
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "secretRefs must contain environment key names",
                        )
                    )
                if int(contract.get("defaultTimeoutMs") or 0) <= 0:
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "defaultTimeoutMs must be positive",
                        )
                    )
                if not isinstance(allowed_overrides, list) or (
                    set(str(value) for value in allowed_overrides)
                    - {"endpointEnvs", "secretRefs", "timeoutMs"}
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            contract_location,
                            "allowEnvironmentOverrides contains unsupported fields",
                        )
                    )
        if capability_id == MESSAGE_TRANSPORT_CAPABILITY_ID:
            declared_metrics = capability.get("observability_metrics")
            if tuple(declared_metrics or ()) != MESSAGE_TRANSPORT_REQUIRED_METRICS:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{location}.observability.metrics",
                        "runtime.message.transport owner must declare fixed "
                        "pending_lag/dead_letter/publish_p95/consume_p95 metrics",
                    )
                )
        roots = capability.get("binding_roots")
        if not isinstance(roots, list) or not roots:
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "object path must reverse-map to at least one source service",
                )
            )
        owner_operations = set(capability.get("operations") or [])
        for use in capability.get("consumer_uses") or []:
            if not isinstance(use, Mapping):
                issues.append(ProviderGovernanceIssue(location, "capability-use must be a mapping"))
                continue
            use_location = str(use.get("source") or location)
            if use.get("port") != capability.get("canonical_port"):
                issues.append(
                    ProviderGovernanceIssue(
                        use_location,
                        "capability-use must reference the owner canonical port",
                    )
                )
            use_operations = set(use.get("operations") or [])
            if not use_operations or not use_operations.issubset(owner_operations):
                issues.append(
                    ProviderGovernanceIssue(
                        use_location,
                        "capability-use operations must be a non-empty owner subset",
                    )
                )
            scenes = use.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                issues.append(
                    ProviderGovernanceIssue(
                        use_location,
                        "capability-use must declare local scene semantics",
                    )
                )
            if not isinstance(use.get("root"), Mapping):
                issues.append(
                    ProviderGovernanceIssue(
                        use_location,
                        "capability-use object path must reverse-map to one source service",
                    )
                )
    return issues


def _service_binding_scope(
    bindings: Mapping[str, Any],
    environment: str,
    service_id: str,
) -> Mapping[str, Any]:
    environments = bindings.get("environments")
    if not isinstance(environments, Mapping):
        return {}
    scope = environments.get(environment)
    if not isinstance(scope, Mapping):
        return {}
    service_bindings = scope.get(service_id)
    return service_bindings if isinstance(service_bindings, Mapping) else {}


def _binding_record(
    binding: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    endpoint_envs = dict(contract.get("endpointEnvs") or {})
    secret_refs = list(contract.get("secretRefs") or [])
    timeout_ms = int(contract.get("defaultTimeoutMs") or 0)
    if "endpointEnvs" in binding:
        endpoint_envs = dict(binding.get("endpointEnvs") or {})
    if "secretRefs" in binding:
        secret_refs = list(binding.get("secretRefs") or [])
    if "timeoutMs" in binding:
        timeout_ms = int(binding.get("timeoutMs") or 0)
    return {
        "state": binding.get("state"),
        "adapter_id": str(binding.get("adapter") or ""),
        "endpoint_ref": binding.get("endpointRef"),
        "endpoint_envs": endpoint_envs,
        "secret_refs": secret_refs,
        "timeout_ms": timeout_ms,
    }


def binding_issues(
    registry: Mapping[str, Any],
    bindings: Mapping[str, Any],
    *,
    source_root: Path | None = None,
    environments_to_validate: tuple[str, ...] = ENVIRONMENTS,
) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    environments = bindings.get("environments")
    if bindings.get("schema") != "service-local-external-provider-bindings":
        issues.append(
            ProviderGovernanceIssue(
                "bindings.schema",
                "must be service-local-external-provider-bindings",
            )
        )
    expected_environments = set(environments_to_validate)
    if (
        not expected_environments
        or expected_environments - set(ENVIRONMENTS)
        or not isinstance(environments, Mapping)
        or set(environments) != expected_environments
    ):
        return [
            *issues,
            ProviderGovernanceIssue(
                "bindings.environments",
                "must exactly match the requested Provider environments",
            ),
        ]

    expected_by_service: dict[str, dict[str, set[str]]] = {}
    for capability in registry.get("capabilities", []):
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        for root in capability.get("binding_roots") or []:
            if not isinstance(root, Mapping):
                continue
            service_id = str(root.get("descriptor_owner") or "")
            role = str(root.get("role") or "")
            if service_id and capability_id:
                expected_by_service.setdefault(service_id, {}).setdefault(
                    capability_id, set()
                ).add(role)

    adapter_ids = {
        str(item.get("adapter_id"))
        for item in registry.get("adapters", [])
        if isinstance(item, Mapping)
    }
    adapter_contracts_by_capability = {
        str(item.get("capability_id") or ""): item.get("adapter_contracts") or {}
        for item in registry.get("capabilities", [])
        if isinstance(item, Mapping)
    }
    for env in environments_to_validate:
        scope = environments.get(env)
        location = f"bindings.environments.{env}"
        if not isinstance(scope, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be a service mapping"))
            continue
        service_roots = (
            _entry._service_roots()
            if source_root is None
            else _entry._service_roots(source_root)
        )
        if set(scope) != {service_root.name for service_root in service_roots}:
            issues.append(
                ProviderGovernanceIssue(
                    location,
                    "must cover exactly the checked-in service environment configs",
                )
            )
        for service_id, service_bindings in scope.items():
            service_location = f"{location}.{service_id}"
            if not isinstance(service_bindings, Mapping):
                issues.append(ProviderGovernanceIssue(service_location, "must be a capability mapping"))
                continue
            expected = expected_by_service.get(str(service_id), {})
            expected_owner_bindings = {
                capability_id
                for capability_id, roles in expected.items()
                if "owner" in roles
            }
            if set(service_bindings) != expected_owner_bindings:
                issues.append(
                    ProviderGovernanceIssue(
                        service_location,
                        "must declare exactly locally owned external capabilities; "
                        f"missing={sorted(expected_owner_bindings - set(service_bindings))}, "
                        f"extra={sorted(set(service_bindings) - expected_owner_bindings)}; "
                        "consumer bindings are generated from capability-use",
                    )
                )
            for capability_id, binding in service_bindings.items():
                item_location = f"{service_location}.{capability_id}"
                if not isinstance(binding, Mapping):
                    issues.append(ProviderGovernanceIssue(item_location, "must be a mapping"))
                    continue
                roles = expected.get(str(capability_id), set())
                owner_binding = "owner" in roles
                if not owner_binding:
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            "consumer binding is generated from capability-use and must be omitted",
                        )
                    )
                    continue
                allowed = {
                    "state",
                    "adapter",
                    "endpointRef",
                    "endpointEnvs",
                    "secretRefs",
                    "timeoutMs",
                }
                if set(binding) - allowed:
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            "contains unsupported fields",
                        )
                    )
                state = str(binding.get("state") or "")
                if state not in STATES:
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            f"state must be one of {sorted(STATES)}",
                        )
                    )
                if state == "not_required":
                    if set(binding) != {"state"}:
                        issues.append(
                            ProviderGovernanceIssue(
                                item_location,
                                "not_required may only declare state",
                            )
                        )
                    continue
                adapter_id = str(binding.get("adapter") or "")
                if not ADAPTER_RE.fullmatch(adapter_id) or adapter_id not in adapter_ids:
                    issues.append(ProviderGovernanceIssue(item_location, "adapter must resolve to source"))
                capability_contracts = adapter_contracts_by_capability.get(
                    str(capability_id), {}
                )
                contract = (
                    capability_contracts.get(adapter_id, {})
                    if isinstance(capability_contracts, Mapping)
                    else {}
                )
                if not isinstance(contract, Mapping) or not contract:
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            "adapter must be declared by the capability owner contract",
                        )
                    )
                    contract = {}
                allowed_overrides = set(
                    str(value)
                    for value in (contract.get("allowEnvironmentOverrides") or [])
                )
                supplied_overrides = set(binding) & {
                    "endpointEnvs",
                    "secretRefs",
                    "timeoutMs",
                }
                disallowed_overrides = supplied_overrides - allowed_overrides
                if disallowed_overrides:
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            "adapter material is owner-declared; environment contains "
                            f"disallowed overrides={sorted(disallowed_overrides)}",
                        )
                    )
                effective = _binding_record(binding, contract)
                if int(effective.get("timeout_ms") or 0) <= 0:
                    issues.append(ProviderGovernanceIssue(item_location, "timeoutMs must be positive"))
                endpoint_envs = effective.get("endpoint_envs") or {}
                secret_refs = effective.get("secret_refs") or []
                if not isinstance(endpoint_envs, Mapping) or any(
                    not ENV_KEY_RE.fullmatch(str(value)) for value in endpoint_envs.values()
                ):
                    issues.append(ProviderGovernanceIssue(item_location, "endpointEnvs must contain environment key names"))
                if not isinstance(secret_refs, list) or any(
                    not ENV_KEY_RE.fullmatch(str(value)) for value in secret_refs
                ):
                    issues.append(ProviderGovernanceIssue(item_location, "secretRefs must contain environment key names"))
                if env in RELEASE_ADAPTER_ENVIRONMENTS and is_prod_forbidden_adapter(
                    adapter_id
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            item_location,
                            f"{env} forbids mock, fixture, recorder or local-substitute adapters",
                        )
                    )
                if env in NONPROD_ENVIRONMENTS and state != "not_required":
                    if state != "enabled":
                        issues.append(
                            ProviderGovernanceIssue(
                                item_location,
                                "alpha/beta/gamma required Provider bindings must be enabled; "
                                "missing protected sandbox material fails during deployment preflight",
                            )
                        )
                if env in RELEASE_ADAPTER_ENVIRONMENTS and state != "not_required":
                    if state != "enabled":
                        issues.append(
                            ProviderGovernanceIssue(
                                item_location,
                                f"{env} release bindings must be enabled; "
                                "missing runtime material fails during deployment preflight",
                            )
                        )
    return issues


def conformance_manifest_issues(
    registry: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[ProviderGovernanceIssue]:
    profiles = manifest.get("profiles")
    if not isinstance(profiles, Mapping):
        return [ProviderGovernanceIssue("conformance", "derived profiles must be a mapping")]
    expected = {
        str(item.get("conformance_profile"))
        for item in registry.get("capabilities", [])
        if isinstance(item, Mapping)
    }
    if set(profiles) != expected:
        return [ProviderGovernanceIssue("conformance", "profiles must derive from object dependencies")]
    return []
