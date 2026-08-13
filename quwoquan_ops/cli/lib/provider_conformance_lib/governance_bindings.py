"""编译后 Provider 治理/Binding 的投影与 cell 派生辅助。"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance as governance

from .constants import (
    ENVIRONMENTS,
    LAYERS,
    MESSAGE_TRANSPORT_CAPABILITY_ID,
    MESSAGE_TRANSPORT_METRIC_NAMES,
    MESSAGE_TRANSPORT_METRIC_REFS,
    RECEIPT_REF_PATTERN,
    RELEASE_ENVIRONMENT,
    REQUIRED_FIELDS,
    SENSITIVE_RECEIPT_REF_PATTERN,
)

def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _root_id_list(root_ids: object) -> list[str] | None:
    if not isinstance(root_ids, list) or not root_ids:
        return None
    if not all(_is_non_empty_string(root_id) for root_id in root_ids):
        return None
    if len(root_ids) != len(set(root_ids)):
        return None
    return list(root_ids)


def _binding_root_ids(roots: object) -> list[str] | None:
    if not isinstance(roots, list) or not roots:
        return None
    if not all(isinstance(root, Mapping) for root in roots):
        return None
    return _root_id_list([root.get("root_id") for root in roots])


def compiled_capability_binding_roots(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
) -> list[dict[str, Any]]:
    """读取 BindingCompiler 唯一输出的 Capability 根组合。"""
    roots_by_capability = compiled.get("capabilityBindingRoots")
    if not isinstance(roots_by_capability, Mapping):
        raise ValueError("compiled provider binding receipt is missing capabilityBindingRoots")
    roots = roots_by_capability.get(capability_id)
    root_ids = _binding_root_ids(roots)
    if root_ids is None:
        raise ValueError(
            f"compiled provider binding receipt has invalid binding roots for {capability_id}"
        )
    return [dict(root) for root in roots]


def required_metric_refs(capability_id: str) -> tuple[str, ...]:
    if capability_id != MESSAGE_TRANSPORT_CAPABILITY_ID:
        return ()
    registry = governance.load_registry()
    capability = next(
        (
            item
            for item in registry.get("capabilities") or []
            if isinstance(item, Mapping)
            and item.get("capability_id") == capability_id
        ),
        None,
    )
    declared_metrics = ()
    if isinstance(capability, Mapping):
        raw_metrics = capability.get("observability_metrics") or ()
        if isinstance(raw_metrics, list):
            declared_metrics = tuple(
                str(metric)
                for metric in raw_metrics
                if isinstance(metric, str) and metric.strip()
            )
    metric_names = declared_metrics or MESSAGE_TRANSPORT_METRIC_NAMES
    return tuple(
        MESSAGE_TRANSPORT_METRIC_REFS.get(
            metric_name,
            f"provider-conformance://{capability_id}/metrics/{metric_name}",
        )
        for metric_name in metric_names
    )


def _selected_binding(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> Mapping[str, Any] | None:
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return None
    environment_bindings = selected_bindings.get(environment)
    if not isinstance(environment_bindings, Mapping):
        return None
    binding = environment_bindings.get(capability_id)
    return binding if isinstance(binding, Mapping) else None


def _selected_adapter_id(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> str | None:
    binding = _selected_binding(
        compiled,
        capability_id=capability_id,
        environment=environment,
    )
    adapter_id = binding.get("adapter_id") if binding is not None else None
    return adapter_id if isinstance(adapter_id, str) else None


def provider_conformance_capability_ids(
    compiled: Mapping[str, Any],
) -> frozenset[str]:
    """Return only capabilities backed by external/infra Provider adapters."""
    declared = compiled.get("providerConformanceCapabilityIds")
    if (
        isinstance(declared, list)
        and len(declared) == len(set(declared))
        and all(isinstance(capability_id, str) for capability_id in declared)
    ):
        return frozenset(declared)
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return frozenset()
    return frozenset(
        str(capability_id)
        for environment_bindings in selected_bindings.values()
        if isinstance(environment_bindings, Mapping)
        for capability_id, binding in environment_bindings.items()
        if isinstance(binding, Mapping)
        and governance.requires_provider_conformance(binding)
    )


def expected_required_cell_keys(
    compiled: Mapping[str, Any],
) -> frozenset[tuple[str, str, str]]:
    """Derive the canonical release cell set from generated Bindings."""
    capability_ids = provider_conformance_capability_ids(compiled)
    if not capability_ids:
        raise ValueError("canonical Provider governance defines no capabilities")
    cells = {
        (capability_id, environment, layer)
        for capability_id in capability_ids
        for environment in ENVIRONMENTS
        for layer in LAYERS
    } | {
        (capability_id, RELEASE_ENVIRONMENT, "user_acceptance")
        for capability_id in capability_ids
    }
    expected_count = len(capability_ids) * (
        len(ENVIRONMENTS) * len(LAYERS) + 1
    )
    if len(cells) != expected_count:
        raise AssertionError(
            "Provider release cell derivation produced duplicate environment/layer keys"
        )
    return frozenset(cells)


def exact_required_cell_issues(
    evidence: Iterable[Mapping[str, Any]],
    *,
    compiled: Mapping[str, Any],
) -> list[str]:
    """Reject missing, duplicate, extra or legacy release evidence cells."""
    expected = expected_required_cell_keys(compiled)
    observed: list[tuple[str, str, str]] = []
    invalid: list[str] = []
    for index, item in enumerate(evidence):
        cell = (
            str(item.get("capabilityId") or ""),
            str(item.get("environment") or ""),
            str(item.get("testLayer") or ""),
        )
        if (
            item.get("schema") != "provider-conformance-evidence"
            or set(REQUIRED_FIELDS) - set(item)
            or cell not in expected
        ):
            invalid.append(f"evidence[{index}]={cell}")
            continue
        observed.append(cell)
    observed_set = set(observed)
    duplicate = sorted(
        cell for cell in observed_set if observed.count(cell) > 1
    )
    missing = sorted(expected - observed_set)
    extra = sorted(observed_set - expected)
    issues: list[str] = []
    if invalid:
        issues.append(
            "Provider release evidence contains non-canonical/legacy cells: "
            + ", ".join(invalid)
        )
    if duplicate:
        issues.append(f"Provider release evidence contains duplicate cells: {duplicate}")
    if missing or extra or len(observed) != len(expected):
        issues.append(
            "Provider release evidence must contain exactly the compiled required cells: "
            f"expected={len(expected)}, observed={len(observed)}, "
            f"missing={missing}, extra={extra}"
        )
    return issues


def _binding_preflight_ready(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> bool:
    readiness = compiled.get("readiness")
    if not isinstance(readiness, Mapping):
        return False
    environment_readiness = readiness.get(environment)
    if not isinstance(environment_readiness, Mapping):
        return False
    binding_readiness = environment_readiness.get(capability_id)
    return isinstance(binding_readiness, Mapping) and bool(
        binding_readiness.get("adapter_preflight_ready")
    )


def _valid_receipt_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and RECEIPT_REF_PATTERN.fullmatch(value) is not None
        and SENSITIVE_RECEIPT_REF_PATTERN.search(value) is None
    )


def network_boundary_for_layer(layer: str) -> str:
    return {
        "local_contract": "offline_harness",
        "api_integration": "remote_protocol",
        "user_acceptance": "user_journey",
    }[layer]


def capability_assertion_id(capability: Mapping[str, Any]) -> str:
    profile = capability.get("conformance_profile")
    if not isinstance(profile, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", profile):
        raise ValueError("capability conformance_profile must be a stable identifier")
    return f"provider.{profile}"
