"""Compile object-declared external capabilities and environment bindings.

There is deliberately no provider or capability registry. Capability identity,
ports and conformance semantics come from object ``operations.yaml`` files;
environment selection comes from each service's environment config;
implementation paths are discovered from source. The compiled receipt and
generated Go descriptors are derived artifacts only.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
SERVICES_ROOT = ROOT / "quwoquan_service" / "services"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
NONPROD_ENVIRONMENTS = ("alpha", "beta", "gamma")
RELEASE_ADAPTER_ENVIRONMENTS = ("prod",)
STATES = {"enabled", "blocked", "not_required"}
READY_IMPLEMENTATION_STATUSES = frozenset({"production"})
MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA = (
    "provider-conformance-user-acceptance-prerequisite"
)
MESSAGE_TRANSPORT_CAPABILITY_ID = "runtime.message.transport"
MESSAGE_TRANSPORT_REQUIRED_METRICS = (
    "pending_lag",
    "dead_letter",
    "publish_p95",
    "consume_p95",
)
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
ADAPTER_RE = re.compile(r"^(?:ext|infra|data)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Platform-local adapters can be production-grade when the selected topology is remote.
PLATFORM_LOCAL_ADAPTERS = frozenset(
    {
        "infra.redis.message_transport",
        "infra.minio.object_storage",
    }
)
FIRST_PARTY_AUTHORITY_ADAPTER = "ext.first_party.http_authority"
LOCAL_SUBSTITUTE_MARKERS = (
    "fixture",
    "mock",
    "fake",
    "local_recorder",
    "local_capture",
    "local_log_sink",
    "protocol_substitute",
    "minio",
    "_local",
    ".local.",
)


def is_local_substitute_adapter(adapter_id: str) -> bool:
    """Return True when adapter is a non-prod Port-equivalent substitute."""
    if adapter_id in PLATFORM_LOCAL_ADAPTERS:
        return True
    return any(marker in adapter_id for marker in LOCAL_SUBSTITUTE_MARKERS)


def is_prod_forbidden_adapter(adapter_id: str) -> bool:
    """Return True when adapter must not be selected in a release environment."""
    if adapter_id == "infra.redis.message_transport":
        return False
    return any(marker in adapter_id for marker in LOCAL_SUBSTITUTE_MARKERS)


def requires_provider_conformance(binding: Mapping[str, Any]) -> bool:
    """Separate third-party/infra Provider cells from first-party service calls."""
    adapter_id = str(binding.get("adapter_id") or "")
    return (
        binding.get("state") != "not_required"
        and bool(adapter_id)
        and adapter_id != FIRST_PARTY_AUTHORITY_ADAPTER
    )


@dataclass(frozen=True)
class ProviderGovernanceIssue:
    location: str
    message: str

    def render(self) -> str:
        return f"{self.location}: {self.message}"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return payload


def _service_roots() -> list[Path]:
    """Return checked-in service roots, excluding generated output directories."""
    return sorted(
        path
        for path in SERVICES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


@lru_cache(maxsize=1)
def load_bindings(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        raise ValueError("global external provider binding files are forbidden")
    environments: dict[str, dict[str, dict[str, Any]]] = {
        env: {} for env in ENVIRONMENTS
    }
    for service_root in _service_roots():
        for env in ENVIRONMENTS:
            config_path = service_root / "environments" / env / "config.yaml"
            config = _load_yaml(config_path)
            bindings = config.get("externalBindings") or {}
            if not isinstance(bindings, Mapping):
                raise ValueError(f"{config_path}: externalBindings must be a mapping")
            environments[env][service_root.name] = {
                str(capability_id): binding for capability_id, binding in bindings.items()
            }
    return {
        "schema": "service-local-external-provider-bindings",
        "environments": environments,
    }


def _operation_sources() -> list[tuple[Path, str, str, str, dict[str, Any]]]:
    sources: list[tuple[Path, str, str, str, dict[str, Any]]] = []
    for service_root in _service_roots():
        domain_path = service_root / "contracts" / "domain.yaml"
        domain = str(_load_yaml(domain_path).get("domain") or "").strip()
        for path in sorted((service_root / "contracts").glob("*/*/operations.yaml")):
            context, object_name = path.relative_to(service_root / "contracts").parts[:2]
            sources.append((path, domain, context, object_name, _load_yaml(path)))
    return sources


def _source_owner(operations_path: Path, context: str, object_name: str) -> tuple[str, Path] | None:
    service_root = operations_path.parents[3]
    object_root = service_root / "internal" / context / object_name
    if not object_root.is_dir():
        return None
    return service_root.name, object_root


def _descriptor_output(service_id: str, object_root: Path) -> Path:
    service_root = SERVICES_ROOT / service_id
    context, object_name = object_root.parts[-2:]
    return service_root / "generated" / context / object_name / "external_provider_bindings.g.go"


def _find_adapter_source(adapter_id: str) -> Path | None:
    roots = [
        SERVICES_ROOT,
        ROOT / "quwoquan_service" / "control-plane",
        ROOT / "quwoquan_service" / "runtime",
    ]
    quoted = f'"{adapter_id}"'
    candidates: list[Path] = []
    for source_root in roots:
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*.go"):
            if "generated" in path.parts or path.name.endswith("_test.go"):
                continue
            try:
                if quoted in path.read_text(encoding="utf-8"):
                    candidates.append(path)
            except UnicodeDecodeError:
                continue
    if not candidates:
        return None
    source = sorted(candidates)[0]
    if source.is_relative_to(SERVICES_ROOT):
        relative = source.relative_to(SERVICES_ROOT)
        service_root = SERVICES_ROOT / relative.parts[0]
        service_relative = Path(*relative.parts[1:])
        if (
            len(service_relative.parts) >= 4
            and service_relative.parts[0] == "internal"
        ):
            return service_root.joinpath(*service_relative.parts[:3])
        # Adapters assembled from cmd/ and internal/ packages must bind the
        # digest to the whole service source closure, not only an ID constant.
        return service_root
    runtime_root = ROOT / "quwoquan_service" / "runtime"
    if source.is_relative_to(runtime_root):
        relative = source.relative_to(runtime_root)
        return runtime_root / relative.parts[0]
    control_plane_root = ROOT / "quwoquan_service" / "control-plane"
    if source.is_relative_to(control_plane_root):
        relative = source.relative_to(control_plane_root)
        return control_plane_root / relative.parts[0]
    return source.parent


def _dependency_role(dependency: Mapping[str, Any]) -> str:
    return str(dependency.get("role") or "owner").strip()


def _root_record(
    *,
    owner: tuple[str, Path] | None,
    domain: str,
    context: str,
    object_name: str,
    role: str,
    dependency: Mapping[str, Any],
) -> dict[str, Any] | None:
    if owner is None:
        return None
    service_id, object_root = owner
    return {
        "root_id": f"{domain}.{context}.{object_name}",
        "descriptor_owner": service_id,
        "descriptor_output": _descriptor_output(service_id, object_root)
        .relative_to(ROOT)
        .as_posix(),
        "role": role,
        "required_scenes": list(dependency.get("scenes") or []),
    }


@lru_cache(maxsize=1)
def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Return a compatibility-shaped, fully derived view for existing runners."""
    if path is not None:
        raise ValueError("manual external provider registries are forbidden")
    capabilities: list[dict[str, Any]] = []
    by_capability: dict[str, dict[str, Any]] = {}
    unresolved_uses: dict[str, list[dict[str, Any]]] = {}
    for operations_path, domain, context, object_name, document in _operation_sources():
        dependencies = document.get("externalDependencies") or []
        if not isinstance(dependencies, list):
            continue
        owner = _source_owner(operations_path, context, object_name)
        for dependency in dependencies:
            if not isinstance(dependency, Mapping):
                continue
            capability_id = str(dependency.get("capability") or "")
            role = _dependency_role(dependency)
            root = _root_record(
                owner=owner,
                domain=domain,
                context=context,
                object_name=object_name,
                role=role,
                dependency=dependency,
            )
            declaration = {
                "port": dependency.get("port"),
                "operations": list(dependency.get("operations") or []),
                "scenes": list(dependency.get("scenes") or []),
                "source": operations_path.relative_to(ROOT).as_posix(),
                "root": root,
                "role": role,
            }
            if role == "use":
                if capability_id in by_capability:
                    by_capability[capability_id]["consumer_uses"].append(declaration)
                    if root is not None:
                        by_capability[capability_id]["binding_roots"].append(root)
                else:
                    unresolved_uses.setdefault(capability_id, []).append(declaration)
                continue
            if role != "owner":
                capabilities.append(
                    {
                        "capability_id": capability_id,
                        "canonical_port": dependency.get("port"),
                        "operations": list(dependency.get("operations") or []),
                        "conformance_profile": dependency.get("conformance"),
                        "adapter_contracts": dict(
                            dependency.get("adapterContracts") or {}
                        ),
                        "owner": f"{domain}.{context}.{object_name}",
                        "binding_roots": [root] if root is not None else [],
                        "consumer_uses": [],
                        "source": operations_path.relative_to(ROOT).as_posix(),
                        "_invalid_role": role,
                    }
                )
                continue
            if capability_id in by_capability:
                # Duplicates remain visible to registry_issues without aliases.
                existing = dict(dependency)
                existing["capability_id"] = capability_id
                existing["_duplicate_owner"] = f"{domain}.{context}.{object_name}"
                existing["binding_roots"] = [root] if root is not None else []
                existing["consumer_uses"] = []
                existing["adapter_contracts"] = dict(
                    dependency.get("adapterContracts") or {}
                )
                capabilities.append(existing)
                continue
            service_id = owner[0] if owner is not None else ""
            observability = dependency.get("observability") or {}
            observability_metrics: list[str] = []
            if isinstance(observability, Mapping):
                raw_metrics = observability.get("metrics") or []
                if isinstance(raw_metrics, list):
                    observability_metrics = [
                        str(metric)
                        for metric in raw_metrics
                        if isinstance(metric, str) and metric.strip()
                    ]
            capability = {
                "capability_id": capability_id,
                "canonical_port": dependency.get("port"),
                "operations": list(dependency.get("operations") or []),
                "conformance_profile": dependency.get("conformance"),
                "adapter_contracts": dict(
                    dependency.get("adapterContracts") or {}
                ),
                "observability_metrics": observability_metrics,
                "owner": f"{domain}.{context}.{object_name}",
                "service_id": service_id,
                "binding_roots": [root] if root is not None else [],
                "consumer_uses": [],
                "source": operations_path.relative_to(ROOT).as_posix(),
            }
            capabilities.append(capability)
            by_capability[capability_id] = capability
            for use in unresolved_uses.pop(capability_id, []):
                capability["consumer_uses"].append(use)
                if use["root"] is not None:
                    capability["binding_roots"].append(use["root"])

    for capability_id, uses in unresolved_uses.items():
        first = uses[0]
        roots = [
            use["root"]
            for use in uses
            if isinstance(use.get("root"), Mapping)
        ]
        capabilities.append(
            {
                "capability_id": capability_id,
                "canonical_port": "",
                "operations": [],
                "conformance_profile": "",
                "adapter_contracts": {},
                "owner": "",
                "service_id": "",
                "binding_roots": roots,
                "consumer_uses": uses,
                "source": first["source"],
                "_missing_owner": True,
            }
        )

    adapter_pairs: set[tuple[str, str]] = set()
    for capability in capabilities:
        if not isinstance(capability, Mapping):
            continue
        capability_id = str(capability.get("capability_id") or "")
        contracts = capability.get("adapter_contracts") or {}
        if not isinstance(contracts, Mapping):
            continue
        for adapter_id in contracts:
            adapter_pairs.add((capability_id, str(adapter_id)))
    adapters: list[dict[str, Any]] = []
    for capability_id, adapter_id in sorted(adapter_pairs):
        source = _find_adapter_source(adapter_id)
        capability = by_capability.get(capability_id, {})
        adapters.append(
            {
                "adapter_id": adapter_id,
                "capability_id": capability_id,
                "conformance_profile": capability.get("conformance_profile"),
                "contract": dict(
                    (capability.get("adapter_contracts") or {}).get(
                        adapter_id
                    )
                    or {}
                ),
                "implementation_path": (
                    source.relative_to(ROOT).as_posix() if source is not None else ""
                ),
                "implementation_status": (
                    "sandbox"
                    if is_local_substitute_adapter(adapter_id)
                    and adapter_id != "infra.redis.message_transport"
                    else "production"
                ),
            }
        )
    return {
        "schema": "derived-external-capabilities",
        "capabilities": capabilities,
        "adapters": adapters,
    }


def load_conformance_manifest(path: Path | None = None) -> dict[str, Any]:
    """Derive runner conventions; no test-path or assertion registry is read."""
    if path is not None:
        raise ValueError("manual conformance manifests are forbidden")
    registry = load_registry()
    profiles = sorted(
        {
            str(item.get("conformance_profile"))
            for item in registry["capabilities"]
            if item.get("conformance_profile")
        }
    )
    sources = {
        "local_contract": "quwoquan_ops/tests/local_contract/provider_conformance_evidence__contract__local_contract_test.py",
        "api_integration": "quwoquan_ops/tests/acceptance/api_integration/external_provider_governance__api_integration_test.py",
        "user_acceptance": "quwoquan_ops/tests/acceptance/user_acceptance/external_provider_governance__user_acceptance_test.py",
    }
    return {
        "schema": "derived-provider-conformance",
        "profiles": {profile: dict(sources) for profile in profiles},
        "common_assertion_ids": [],
        "profile_assertion_ids": {
            profile: [f"{profile}.contract"] for profile in profiles
        },
    }


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
    registry: Mapping[str, Any], bindings: Mapping[str, Any]
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
    if not isinstance(environments, Mapping) or set(environments) != set(ENVIRONMENTS):
        return [*issues, ProviderGovernanceIssue("bindings.environments", "must be exactly alpha/beta/gamma/prod")]

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
    for env in ENVIRONMENTS:
        scope = environments.get(env)
        location = f"bindings.environments.{env}"
        if not isinstance(scope, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be a service mapping"))
            continue
        if set(scope) != {
            service_root.name
            for service_root in _service_roots()
        }:
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


def compile_governance(
    registry: Mapping[str, Any],
    bindings: Mapping[str, Any],
    conformance_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[ProviderGovernanceIssue]]:
    issues = [
        *registry_issues(registry),
        *binding_issues(registry, bindings),
        *conformance_manifest_issues(registry, conformance_manifest),
    ]
    capabilities = [item for item in registry.get("capabilities", []) if isinstance(item, Mapping)]
    adapters = [item for item in registry.get("adapters", []) if isinstance(item, Mapping)]
    adapter_by_key = {
        (
            str(item.get("capability_id") or ""),
            str(item.get("adapter_id") or ""),
        ): item
        for item in adapters
    }
    selected: dict[str, dict[str, dict[str, Any]]] = {}
    selected_roots: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    readiness: dict[str, dict[str, dict[str, Any]]] = {}
    environments = bindings.get("environments") or {}
    for env in ENVIRONMENTS:
        selected[env] = {}
        selected_roots[env] = {}
        readiness[env] = {}
        scope = environments.get(env) if isinstance(environments, Mapping) else {}
        if not isinstance(scope, Mapping):
            continue
        for capability in capabilities:
            capability_id = str(capability.get("capability_id"))
            owner_service = str(capability.get("service_id") or "")
            binding = _service_binding_scope(bindings, env, owner_service).get(capability_id)
            if not isinstance(binding, Mapping):
                continue
            adapter_id = str(binding.get("adapter") or "")
            adapter = adapter_by_key.get((capability_id, adapter_id), {})
            contract = adapter.get("contract") or {}
            selected[env][capability_id] = _binding_record(binding, contract)
            source_path = ROOT / str(adapter.get("implementation_path") or "")
            state = str(binding.get("state") or "")
            required = state != "not_required"
            ready = state == "enabled" and bool(adapter_id) and source_path.exists()
            if env in RELEASE_ADAPTER_ENVIRONMENTS and required and adapter_id:
                ready = ready and not is_prod_forbidden_adapter(adapter_id)
            readiness[env][capability_id] = {
                "state": state,
                "required": required,
                "adapter_id": adapter_id,
                "local_substitute": is_local_substitute_adapter(adapter_id),
                "adapter_preflight_ready": ready,
                "adapter_ready": ready,
                "capability_ready": ready,
            }
            for root in capability.get("binding_roots") or []:
                if not isinstance(root, Mapping):
                    continue
                root_id = str(root.get("root_id") or "")
                service_id = str(root.get("descriptor_owner") or "")
                if not root_id or not service_id:
                    continue
                root_binding = dict(selected[env][capability_id])
                root_binding["required_scenes"] = list(root.get("required_scenes") or [])
                selected_roots[env].setdefault(root_id, {})[capability_id] = root_binding
    provider_conformance_capability_ids = sorted(
        {
            capability_id
            for environment_bindings in selected.values()
            for capability_id, binding in environment_bindings.items()
            if requires_provider_conformance(binding)
        }
    )
    compiled = {
        "schema": "compiled-external-provider-bindings",
        "capabilityCount": len(capabilities),
        "adapterCount": len(adapters),
        "providerConformanceCapabilityCount": len(
            provider_conformance_capability_ids
        ),
        "providerConformanceCapabilityIds": provider_conformance_capability_ids,
        "capabilityOwners": {
            str(item.get("capability_id")): str(item.get("owner")) for item in capabilities
        },
        "capabilityBindingRoots": {
            str(item.get("capability_id")): list(item.get("binding_roots") or [])
            for item in capabilities
        },
        "selectedBindings": selected,
        "selectedRootBindings": selected_roots,
        "readiness": readiness,
        "issues": [issue.render() for issue in issues],
    }
    return compiled, issues


def load_and_compile(
    *,
    registry_path: Path | None = None,
    bindings_path: Path | None = None,
    conformance_path: Path | None = None,
) -> tuple[dict[str, Any], list[ProviderGovernanceIssue]]:
    if registry_path is not None or conformance_path is not None:
        raise ValueError("manual registry and conformance manifest inputs are forbidden")
    registry = load_registry()
    return compile_governance(
        registry,
        load_bindings(bindings_path),
        load_conformance_manifest(),
    )


def render_go_bindings(
    compiled: Mapping[str, Any],
    *,
    descriptor_owner: str,
    descriptor_root_id: str,
) -> str:
    selected_roots = compiled.get("selectedRootBindings")
    if not isinstance(selected_roots, Mapping):
        raise ValueError("compiled bindings are incomplete")
    source_path = descriptor_root_id.replace(".", "/") + "/operations.yaml"
    lines = [
        f"// Code generated by external_provider_governance.py from {source_path}; DO NOT EDIT.",
        "", "package generated", "",
        f"const ExternalProviderBindingOwner = {json.dumps(descriptor_owner)}", "",
        f"const ExternalProviderBindingObject = {json.dumps(descriptor_root_id)}", "",
        "type ExternalProviderBinding struct {",
        "\tState string", "\tAdapterID string", "\tEndpointRef string",
        "\tEndpointEnvironmentKeys map[string]string", "\tSecretEnvironmentKeys []string",
        "\tTimeoutMilliseconds int", "\tRequiredRedisScenes []string", "}", "",
        "var ExternalProviderBindings = map[string]map[string]ExternalProviderBinding{",
    ]
    for env in ENVIRONMENTS:
        lines.append(f"\t{json.dumps(env)}: {{")
        root_bindings = selected_roots.get(env)
        scope = (
            root_bindings.get(descriptor_root_id)
            if isinstance(root_bindings, Mapping)
            else {}
        )
        if isinstance(scope, Mapping):
            for capability_id in sorted(scope):
                binding = scope.get(capability_id)
                if not isinstance(binding, Mapping):
                    continue
                lines.append(f"\t\t{json.dumps(capability_id)}: {{")
                lines.append(f"\t\t\tState: {json.dumps(str(binding.get('state') or ''))},")
                lines.append(f"\t\t\tAdapterID: {json.dumps(str(binding.get('adapter_id') or ''))},")
                lines.append(f"\t\t\tEndpointRef: {json.dumps(str(binding.get('endpoint_ref') or ''))},")
                lines.append("\t\t\tEndpointEnvironmentKeys: map[string]string{")
                for role, key in sorted((binding.get("endpoint_envs") or {}).items()):
                    lines.append(f"\t\t\t\t{json.dumps(str(role))}: {json.dumps(str(key))},")
                lines.append("\t\t\t},")
                lines.append("\t\t\tSecretEnvironmentKeys: []string{")
                for key in binding.get("secret_refs") or []:
                    lines.append(f"\t\t\t\t{json.dumps(str(key))},")
                lines.append("\t\t\t},")
                lines.append(f"\t\t\tTimeoutMilliseconds: {int(binding.get('timeout_ms') or 0)},")
                lines.append("\t\t\tRequiredRedisScenes: []string{")
                for scene in binding.get("required_scenes") or []:
                    lines.append(f"\t\t\t\t{json.dumps(str(scene))},")
                lines.append("\t\t\t},")
                lines.append("\t\t},")
        lines.append("\t},")
    lines.extend([
        "}", "",
        "func ExternalProviderBindingFor(environment, capabilityID string) (ExternalProviderBinding, bool) {",
        "\tbyCapability, ok := ExternalProviderBindings[environment]",
        "\tif !ok { return ExternalProviderBinding{}, false }",
        "\tbinding, ok := byCapability[capabilityID]",
        "\treturn binding, ok", "}", "",
    ])
    source = "\n".join(lines)
    try:
        result = subprocess.run(
            ("gofmt",),
            input=source,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gofmt is required to generate canonical Go bindings") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown gofmt failure"
        raise ValueError(f"cannot format generated Go bindings: {detail}")
    return result.stdout


def _descriptor_roots(registry: Mapping[str, Any]) -> list[dict[str, str]]:
    roots: dict[str, dict[str, str]] = {}
    for capability in registry.get("capabilities", []):
        if not isinstance(capability, Mapping):
            continue
        for root in capability.get("binding_roots") or []:
            if not isinstance(root, Mapping):
                continue
            root_id = str(root.get("root_id") or "")
            record = {
                "root_id": root_id,
                "descriptor_owner": str(root.get("descriptor_owner") or ""),
                "descriptor_output": str(root.get("descriptor_output") or ""),
            }
            if root_id and root_id in roots and roots[root_id] != record:
                raise ValueError(f"{root_id}: derived descriptor root is inconsistent")
            if root_id:
                roots[root_id] = record
    return [roots[root_id] for root_id in sorted(roots)]


def composition_issues(
    registry: Mapping[str, Any], compiled: Mapping[str, Any]
) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    for root in _descriptor_roots(registry):
        owner = root["descriptor_owner"]
        root_id = root["root_id"]
        output = root["descriptor_output"]
        if not owner or not output:
            continue
        output_path = ROOT / output
        if not output_path.is_file():
            issues.append(ProviderGovernanceIssue(output, "generated binding descriptor is missing"))
            continue
        expected = render_go_bindings(
            compiled,
            descriptor_owner=owner,
            descriptor_root_id=root_id,
        )
        if output_path.read_text(encoding="utf-8") != expected:
            issues.append(ProviderGovernanceIssue(output, "generated binding descriptor is stale"))
    return issues


def write_go_bindings(
    registry: Mapping[str, Any],
    compiled: Mapping[str, Any],
    *,
    check: bool,
) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    for root in _descriptor_roots(registry):
        output = root["descriptor_output"]
        output_path = ROOT / output
        rendered = render_go_bindings(
            compiled,
            descriptor_owner=root["descriptor_owner"],
            descriptor_root_id=root["root_id"],
        )
        current = output_path.read_text(encoding="utf-8") if output_path.is_file() else None
        if check:
            if current != rendered:
                issues.append(
                    ProviderGovernanceIssue(output, "generated binding descriptor is stale")
                )
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-bindings", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    registry = load_registry()
    compiled, issues = compile_governance(
        registry,
        load_bindings(),
        load_conformance_manifest(),
    )
    if args.check and not args.go_bindings:
        parser.error("--check requires --go-bindings")
    if args.go_bindings:
        issues = [*issues, *write_go_bindings(registry, compiled, check=args.check)]
    if args.quiet:
        print(
            "external-provider-governance: "
            f"capabilities={compiled['capabilityCount']} "
            f"adapters={compiled['adapterCount']} issues={len(issues)}"
        )
    else:
        print(json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
