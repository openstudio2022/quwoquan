"""编译 compiled receipt 并汇总治理 issue（原单文件逐字搬运）。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .constants import (
    ENVIRONMENTS,
    RELEASE_ADAPTER_ENVIRONMENTS,
    ROOT,
    is_local_substitute_adapter,
    is_prod_forbidden_adapter,
    requires_provider_conformance,
)
from .derived_sources import load_bindings, load_conformance_manifest, load_registry
from .models import ProviderGovernanceIssue
from .validation import (
    _binding_record,
    _service_binding_scope,
    binding_issues,
    conformance_manifest_issues,
    registry_issues,
)


def compile_governance(
    registry: Mapping[str, Any],
    bindings: Mapping[str, Any],
    conformance_manifest: Mapping[str, Any],
    *,
    source_root: Path | None = None,
    environments: tuple[str, ...] = ENVIRONMENTS,
) -> tuple[dict[str, Any], list[ProviderGovernanceIssue]]:
    source_base = ROOT if source_root is None else Path(source_root).resolve()
    issues = [
        *registry_issues(registry),
        *binding_issues(
            registry,
            bindings,
            source_root=source_root,
            environments_to_validate=environments,
        ),
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
    binding_environments = bindings.get("environments") or {}
    for env in environments:
        selected[env] = {}
        selected_roots[env] = {}
        readiness[env] = {}
        scope = (
            binding_environments.get(env)
            if isinstance(binding_environments, Mapping)
            else {}
        )
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
            source_path = source_base / str(
                adapter.get("implementation_path") or ""
            )
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
    source_root: Path | None = None,
) -> tuple[dict[str, Any], list[ProviderGovernanceIssue]]:
    if registry_path is not None or conformance_path is not None:
        raise ValueError("manual registry and conformance manifest inputs are forbidden")
    registry = load_registry(source_root=source_root)
    return compile_governance(
        registry,
        load_bindings(bindings_path, source_root=source_root),
        load_conformance_manifest(source_root=source_root),
        source_root=source_root,
    )
