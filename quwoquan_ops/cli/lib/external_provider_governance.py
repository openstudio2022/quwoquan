"""Compile and validate external Capability/Adapter environment governance."""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "docs" / "external_service_registry.yaml"
BINDINGS_PATH = ROOT / "quwoquan_ops" / "environments" / "external_provider_bindings.yaml"
CONFORMANCE_PATH = (
    ROOT / "quwoquan_ops" / "environments" / "provider_conformance_manifest.yaml"
)
ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
ACCESS_POLICIES = frozenset(
    {
        "central_integration",
        "domain_owned_adapter",
        "client_platform_adapter",
        "data_pipeline_adapter",
        "runtime_shared_adapter",
    }
)
GOVERNANCE_REF_KEYS = frozenset(
    {"slo", "privacy", "cost", "degradation", "rollback"}
)
IMPLEMENTATION_STATUSES = frozenset(
    {
        "production",
        "implemented_fail_closed",
        "mock",
        "test_fixture_only",
        "sandbox",
        "planned",
        "registered_only",
        "none",
    }
)
CONFORMANCE_PROFILES = frozenset(
    {
        "generic_provider",
        "message_transport",
        "push_delivery",
        "model_gateway",
        "rtc_provider",
        "object_storage",
        "public_source",
        "client_platform",
        "runtime_infrastructure",
        "observability_log",
        "dns_resolver",
    }
)
ENVIRONMENT_BINDING_STATES = frozenset(
    {"enabled", "blocked", "not_required", "unavailable"}
)
READY_IMPLEMENTATION_STATUSES = frozenset({"production", "implemented_fail_closed"})
BINDING_SCOPES = frozenset({"root_composed", "shared_multi_consumer"})
BINDING_ROOT_REQUIRED_FIELDS = frozenset(
    {
        "root_id",
        "descriptor_owner",
        "descriptor_output",
        "entrypoint",
        "entrypoint_symbol",
        "resolver_path",
        "resolver_symbol",
    }
)
SHARED_BINDING_ROOT_FIELDS = frozenset({"usage", "required_redis_scenes"})
ADAPTER_ID_PATTERN = re.compile(r"^(?:ext|infra|data|dev|cap)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
PORT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
SECRET_REF_PATTERN = re.compile(r"^runtime_secret:[A-Z][A-Z0-9_]*$")
ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
ASSERTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
ENDPOINT_REF_PATTERN = re.compile(
    r"^(?:environment_binding:[a-z0-9_.-]+|platform_default|not_configured)$"
)
BINDING_ROOT_SYMBOL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA = (
    "provider-conformance-user-acceptance-prerequisite"
)
MESSAGE_TRANSPORT_REMOTE_UAT_REQUIRED_HARNESS = {
    "execution": "native_device_patrol",
    "composition": "production_remote",
    "endpoint": "stackctl_managed_environment_topology",
    "auth": "ci_injected_remote_test_session",
    "seed": "environment_managed_assistant_conversation_seed",
}
MESSAGE_TRANSPORT_REMOTE_UAT_REQUIRED_ASSERTIONS = frozenset(
    {
        "invite_assistant",
        "mention_assistant_in_conversation",
        "observe_remote_assistant_reply",
        "correlate_redis_consumer_observability",
    }
)
MESSAGE_TRANSPORT_REMOTE_UAT_FORBIDDEN_SUBSTITUTES = frozenset(
    {
        "memory_redis",
        "fixture_consumer",
        "ui_mock",
        "provider_override",
    }
)


@dataclass(frozen=True)
class ProviderGovernanceIssue:
    """One deterministic, user-actionable registry/compiler violation."""

    location: str
    message: str

    def render(self) -> str:
        return f"{self.location}: {self.message}"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected YAML object")
    return payload


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return _load_yaml(path)


def load_bindings(path: Path = BINDINGS_PATH) -> dict[str, Any]:
    return _load_yaml(path)


def load_conformance_manifest(path: Path = CONFORMANCE_PATH) -> dict[str, Any]:
    return _load_yaml(path)


def _as_non_empty_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _require_keys(
    payload: Mapping[str, Any],
    expected: Iterable[str],
    *,
    location: str,
    issues: list[ProviderGovernanceIssue],
) -> None:
    for key in expected:
        if key not in payload:
            issues.append(ProviderGovernanceIssue(location, f"missing required field {key!r}"))


def _path_from_ref(ref: object) -> Path | None:
    value = _as_non_empty_string(ref)
    if value is None:
        return None
    path_text = value.split("#", maxsplit=1)[0]
    if not path_text:
        return None
    candidate = (ROOT / path_text).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _validate_governance_refs(
    references: object,
    *,
    location: str,
    issues: list[ProviderGovernanceIssue],
) -> None:
    if not isinstance(references, Mapping):
        issues.append(ProviderGovernanceIssue(location, "governance_refs must be an object"))
        return
    if set(references) != GOVERNANCE_REF_KEYS:
        issues.append(
            ProviderGovernanceIssue(
                location,
                "governance_refs must contain only slo/privacy/cost/degradation/rollback",
            )
        )
        return
    for key, value in references.items():
        referenced_path = _path_from_ref(value)
        if referenced_path is None or not referenced_path.exists():
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.governance_refs.{key}",
                    "must point to an existing repository source document",
                )
            )


def _validate_environment_list(
    environments: object,
    *,
    location: str,
    issues: list[ProviderGovernanceIssue],
    allow_empty: bool,
) -> list[str]:
    if not isinstance(environments, list) or any(
        not isinstance(item, str) for item in environments
    ):
        issues.append(ProviderGovernanceIssue(location, "must be a list of environments"))
        return []
    values = [str(item) for item in environments]
    if len(values) != len(set(values)):
        issues.append(ProviderGovernanceIssue(location, "must not contain duplicate environments"))
    unknown = sorted(set(values) - ENVIRONMENTS)
    if unknown:
        issues.append(ProviderGovernanceIssue(location, f"contains unknown environments {unknown}"))
    if not allow_empty and not values:
        issues.append(ProviderGovernanceIssue(location, "must not be empty"))
    return values


def _validate_binding_roots(
    binding_scope: object,
    binding_roots: object,
    *,
    required: bool,
    location: str,
    issues: list[ProviderGovernanceIssue],
) -> None:
    """Validate static root projections for a release-required capability."""
    scope_location = f"{location}.binding_scope"
    roots_location = f"{location}.binding_roots"
    if not required:
        if binding_scope is not None:
            issues.append(
                ProviderGovernanceIssue(
                    scope_location,
                    "only release-required capabilities may declare binding_scope",
                )
            )
        if binding_roots is not None:
            issues.append(
                ProviderGovernanceIssue(
                    roots_location,
                    "only release-required capabilities may declare binding_roots",
                )
            )
        return
    scope = _as_non_empty_string(binding_scope)
    if scope not in BINDING_SCOPES:
        issues.append(
            ProviderGovernanceIssue(
                scope_location,
                f"must be one of {sorted(BINDING_SCOPES)} for release-required capabilities",
            )
        )
    if not isinstance(binding_roots, list) or not binding_roots:
        issues.append(
            ProviderGovernanceIssue(
                roots_location,
                "release-required capabilities must declare non-empty binding_roots",
            )
        )
        return
    if scope == "root_composed" and len(binding_roots) != 1:
        issues.append(
            ProviderGovernanceIssue(
                roots_location,
                "root_composed capabilities must declare exactly one binding root",
            )
        )
    if scope == "shared_multi_consumer" and len(binding_roots) < 2:
        issues.append(
            ProviderGovernanceIssue(
                roots_location,
                "shared_multi_consumer capabilities must declare multiple binding roots",
            )
        )

    root_ids: set[str] = set()
    for root_index, binding_root in enumerate(binding_roots):
        root_location = f"{roots_location}[{root_index}]"
        if not isinstance(binding_root, Mapping):
            issues.append(ProviderGovernanceIssue(root_location, "must be an object"))
            continue
        _require_keys(
            binding_root,
            BINDING_ROOT_REQUIRED_FIELDS,
            location=root_location,
            issues=issues,
        )
        root_id = _as_non_empty_string(binding_root.get("root_id"))
        if root_id is None:
            issues.append(
                ProviderGovernanceIssue(
                    f"{root_location}.root_id",
                    "must be a non-empty stable binding root ID",
                )
            )
        elif root_id in root_ids:
            issues.append(
                ProviderGovernanceIssue(
                    f"{root_location}.root_id",
                    "must be unique within its capability binding_roots",
                )
            )
        else:
            root_ids.add(root_id)

        if _as_non_empty_string(binding_root.get("descriptor_owner")) is None:
            issues.append(
                ProviderGovernanceIssue(
                    f"{root_location}.descriptor_owner",
                    "must be a non-empty descriptor owner",
                )
            )
        for path_field in ("descriptor_output", "entrypoint", "resolver_path"):
            path = _path_from_ref(binding_root.get(path_field))
            if path is None:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{root_location}.{path_field}",
                        "must be a repository-relative path",
                    )
                )
                continue
            if path_field == "descriptor_output":
                if (
                    path.suffix != ".go"
                    or not path.name.endswith(".g.go")
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{root_location}.{path_field}",
                            "must target a checked-in generated Go descriptor",
                        )
                    )
            elif not path.is_file():
                issues.append(
                    ProviderGovernanceIssue(
                        f"{root_location}.{path_field}",
                        "must point to an existing binding root source",
                    )
                )
        for symbol_field in ("entrypoint_symbol", "resolver_symbol"):
            symbol = _as_non_empty_string(binding_root.get(symbol_field))
            if symbol is None or not BINDING_ROOT_SYMBOL_PATTERN.fullmatch(symbol):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{root_location}.{symbol_field}",
                        "must be a stable Go binding root symbol",
                    )
                )
        if scope == "shared_multi_consumer" and binding_root.get("entrypoint_symbol") == "main":
            issues.append(
                ProviderGovernanceIssue(
                    f"{root_location}.entrypoint_symbol",
                    "shared message roots must name their concrete preflight symbol, not main",
                )
            )

        if scope == "shared_multi_consumer":
            _require_keys(
                binding_root,
                SHARED_BINDING_ROOT_FIELDS,
                location=root_location,
                issues=issues,
            )
            usage = binding_root.get("usage")
            if (
                not isinstance(usage, list)
                or not usage
                or any(_as_non_empty_string(item) is None for item in usage)
                or len(usage) != len(set(usage))
            ):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{root_location}.usage",
                        "must be a non-empty unique list of shared binding root usages",
                    )
                )
            required_redis_scenes = binding_root.get("required_redis_scenes")
            if (
                not isinstance(required_redis_scenes, list)
                or not required_redis_scenes
                or any(_as_non_empty_string(scene) is None for scene in required_redis_scenes)
                or len(required_redis_scenes) != len(set(required_redis_scenes))
            ):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{root_location}.required_redis_scenes",
                        "must be a non-empty unique list of Redis preflight scenes",
                    )
                )
        else:
            for field_name in SHARED_BINDING_ROOT_FIELDS:
                if field_name in binding_root:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{root_location}.{field_name}",
                            "is only valid for shared_multi_consumer binding roots",
                        )
                    )


def registry_issues(registry: Mapping[str, Any]) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    if registry.get("schema") != "external-provider-governance":
        issues.append(ProviderGovernanceIssue("registry", "schema must be external-provider-governance"))
    for retired_key in ("entries", "fields", "version", "schemaVersion"):
        if retired_key in registry:
            issues.append(
                ProviderGovernanceIssue(
                    "registry", f"retired or versioned field {retired_key!r} is forbidden"
                )
            )
    capabilities = registry.get("capabilities")
    adapters = registry.get("adapters")
    if not isinstance(capabilities, list) or not capabilities:
        issues.append(ProviderGovernanceIssue("registry.capabilities", "must be a non-empty list"))
        capabilities = []
    if not isinstance(adapters, list) or not adapters:
        issues.append(ProviderGovernanceIssue("registry.adapters", "must be a non-empty list"))
        adapters = []

    capability_ids: set[str] = set()
    capability_policies: dict[str, str] = {}
    required_capability_fields = {
        "capability_id",
        "owner",
        "canonical_port",
        "access_policy",
        "required_environments",
        "governance_refs",
        "acceptance_refs",
    }
    for index, capability in enumerate(capabilities):
        location = f"registry.capabilities[{index}]"
        if not isinstance(capability, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be an object"))
            continue
        if "composition" in capability:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.composition",
                    "retired composition field is forbidden; use binding_scope and binding_roots",
                )
            )
        _require_keys(capability, required_capability_fields, location=location, issues=issues)
        capability_id = _as_non_empty_string(capability.get("capability_id"))
        if capability_id is None or not CAPABILITY_ID_PATTERN.fullmatch(capability_id):
            issues.append(ProviderGovernanceIssue(f"{location}.capability_id", "must be stable dotted id"))
            continue
        if capability_id in capability_ids:
            issues.append(ProviderGovernanceIssue(f"{location}.capability_id", "must be unique"))
            continue
        capability_ids.add(capability_id)
        owner = _as_non_empty_string(capability.get("owner"))
        if owner is None:
            issues.append(ProviderGovernanceIssue(f"{location}.owner", "must be non-empty"))
        canonical_port = _as_non_empty_string(capability.get("canonical_port"))
        if canonical_port is None or not PORT_PATTERN.fullmatch(canonical_port):
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.canonical_port", "must be a stable typed Port name"
                )
            )
        access_policy = _as_non_empty_string(capability.get("access_policy"))
        if access_policy not in ACCESS_POLICIES:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.access_policy",
                    f"must be one of {sorted(ACCESS_POLICIES)}",
                )
            )
        else:
            capability_policies[capability_id] = access_policy
        _validate_environment_list(
            capability.get("required_environments"),
            location=f"{location}.required_environments",
            issues=issues,
            allow_empty=True,
        )
        required_environments = capability.get("required_environments")
        _validate_binding_roots(
            capability.get("binding_scope"),
            capability.get("binding_roots"),
            required=isinstance(required_environments, list) and bool(required_environments),
            location=location,
            issues=issues,
        )
        _validate_governance_refs(
            capability.get("governance_refs"), location=location, issues=issues
        )
        acceptance_refs = capability.get("acceptance_refs")
        if not isinstance(acceptance_refs, list) or not acceptance_refs:
            issues.append(
                ProviderGovernanceIssue(f"{location}.acceptance_refs", "must be non-empty list")
            )
        else:
            for ref_index, ref in enumerate(acceptance_refs):
                referenced_path = _path_from_ref(ref)
                if referenced_path is None or not referenced_path.exists():
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{location}.acceptance_refs[{ref_index}]",
                            "must point to an existing repository source document",
                        )
                    )

    required_adapter_fields = {
        "adapter_id",
        "display_name",
        "capability_id",
        "category",
        "vendor",
        "endpoint_ref",
        "access_policy",
        "consumers",
        "metadata_refs",
        "implementation_path",
        "sdk_dependencies",
        "implementation_status",
        "allowed_environments",
        "secret_refs",
        "production_grade",
        "conformance_profile",
        "governance_refs",
        "compliance",
        "declared_gap",
        "notes",
    }
    adapter_ids: set[str] = set()
    for index, adapter in enumerate(adapters):
        location = f"registry.adapters[{index}]"
        if not isinstance(adapter, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be an object"))
            continue
        _require_keys(adapter, required_adapter_fields, location=location, issues=issues)
        for retired_key in ("service_id", "endpoint", "secrets", "access_layer", "impl_status"):
            if retired_key in adapter:
                issues.append(
                    ProviderGovernanceIssue(
                        location, f"retired v1 adapter field {retired_key!r} is forbidden"
                    )
                )
        adapter_id = _as_non_empty_string(adapter.get("adapter_id"))
        if adapter_id is None or not ADAPTER_ID_PATTERN.fullmatch(adapter_id):
            issues.append(ProviderGovernanceIssue(f"{location}.adapter_id", "must be stable dotted id"))
        elif adapter_id in adapter_ids:
            issues.append(ProviderGovernanceIssue(f"{location}.adapter_id", "must be unique"))
        else:
            adapter_ids.add(adapter_id)
        capability_id = _as_non_empty_string(adapter.get("capability_id"))
        if capability_id not in capability_ids:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.capability_id", "must reference a registered capability"
                )
            )
        access_policy = _as_non_empty_string(adapter.get("access_policy"))
        if access_policy not in ACCESS_POLICIES:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.access_policy",
                    f"must be one of {sorted(ACCESS_POLICIES)}",
                )
            )
        elif (
            capability_id in capability_policies
            and access_policy != capability_policies[capability_id]
        ):
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.access_policy",
                    "must match its capability access_policy to prevent bypasses",
                )
            )
        endpoint_ref = _as_non_empty_string(adapter.get("endpoint_ref"))
        if endpoint_ref is None or not ENDPOINT_REF_PATTERN.fullmatch(endpoint_ref):
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.endpoint_ref",
                    "must be a binding reference, platform_default, or not_configured; "
                    "literal endpoints are forbidden",
                )
            )
        implementation_path = _as_non_empty_string(adapter.get("implementation_path"))
        implementation_status = _as_non_empty_string(adapter.get("implementation_status"))
        if implementation_status not in IMPLEMENTATION_STATUSES:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.implementation_status",
                    f"must be one of {sorted(IMPLEMENTATION_STATUSES)}",
                )
            )
        implementation_file = _path_from_ref(implementation_path)
        has_no_implementation = implementation_status in {
            "planned",
            "registered_only",
            "none",
        }
        if has_no_implementation:
            if implementation_path != "not_implemented":
                issues.append(
                    ProviderGovernanceIssue(
                        f"{location}.implementation_path",
                        "must be not_implemented until a real adapter boundary exists",
                    )
                )
        elif implementation_file is None or not implementation_file.exists():
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.implementation_path",
                    "must point to an existing in-repository implementation boundary",
                )
            )
        _validate_environment_list(
            adapter.get("allowed_environments"),
            location=f"{location}.allowed_environments",
            issues=issues,
            allow_empty=implementation_status in {"planned", "registered_only", "none"},
        )
        secret_refs = adapter.get("secret_refs")
        if not isinstance(secret_refs, list) or any(
            not isinstance(ref, str) or not SECRET_REF_PATTERN.fullmatch(ref)
            for ref in secret_refs
        ):
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.secret_refs",
                    "must only contain runtime_secret:<NAME> references",
                )
            )
        profile = _as_non_empty_string(adapter.get("conformance_profile"))
        if profile not in CONFORMANCE_PROFILES:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.conformance_profile",
                    f"must be one of {sorted(CONFORMANCE_PROFILES)}",
                )
            )
        if not isinstance(adapter.get("production_grade"), bool):
            issues.append(
                ProviderGovernanceIssue(f"{location}.production_grade", "must be a boolean")
            )
        if adapter.get("production_grade") is True and implementation_status in {
            "planned",
            "registered_only",
            "none",
            "mock",
            "test_fixture_only",
        }:
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.production_grade",
                    "cannot be true for a non-production implementation status",
                )
            )
        _validate_governance_refs(
            adapter.get("governance_refs"), location=location, issues=issues
        )
        for text_field in ("display_name", "category", "vendor", "compliance", "declared_gap", "notes"):
            if _as_non_empty_string(adapter.get(text_field)) is None:
                issues.append(ProviderGovernanceIssue(f"{location}.{text_field}", "must be non-empty"))
        for list_field in ("consumers", "metadata_refs", "sdk_dependencies"):
            list_value = adapter.get(list_field)
            if not isinstance(list_value, list) or any(
                not isinstance(item, str) for item in list_value
            ):
                issues.append(
                    ProviderGovernanceIssue(f"{location}.{list_field}", "must be a string list")
                )
    capabilities_by_id = {
        str(capability.get("capability_id")): capability
        for capability in capabilities
        if isinstance(capability, Mapping)
    }
    for capability_id, capability in capabilities_by_id.items():
        access_policy = capability.get("access_policy")
        capability_adapters = [
            adapter
            for adapter in adapters
            if isinstance(adapter, Mapping) and adapter.get("capability_id") == capability_id
        ]
        if access_policy == "runtime_shared_adapter":
            root_ids = {
                str(root.get("root_id"))
                for root in capability.get("binding_roots", [])
                if isinstance(root, Mapping) and _as_non_empty_string(root.get("root_id")) is not None
            }
            if not root_ids:
                continue
            for adapter in capability_adapters:
                adapter_location = (
                    "registry.adapters["
                    f"{next(index for index, item in enumerate(adapters) if item is adapter)}]"
                )
                consumers = adapter.get("consumers")
                consumer_set = (
                    {str(item) for item in consumers}
                    if isinstance(consumers, list) and all(isinstance(item, str) for item in consumers)
                    else set()
                )
                if consumer_set != root_ids or (
                    isinstance(consumers, list) and len(consumers) != len(consumer_set)
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{adapter_location}.consumers",
                            "must exactly equal its runtime_shared capability binding_roots",
                        )
                    )
        if capability_id in {"runtime.message.transport", "runtime.dns.resolution"}:
            for adapter in capability_adapters:
                adapter_location = (
                    "registry.adapters["
                    f"{next(index for index, item in enumerate(adapters) if item is adapter)}]"
                )
                production_consumption = adapter.get("production_consumption")
                if production_consumption not in {"required", "none"}:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{adapter_location}.production_consumption",
                            "must explicitly be required or none for runtime messaging/DNS adapters",
                        )
                    )
                if capability_id == "runtime.dns.resolution" and production_consumption != "none":
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{adapter_location}.production_consumption",
                            "runtime DNS is asset-only and must declare none",
                        )
                    )
    return issues


def binding_issues(
    registry: Mapping[str, Any], bindings: Mapping[str, Any]
) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    if bindings.get("schema") != "external-provider-environment-bindings":
        issues.append(
            ProviderGovernanceIssue(
                "bindings", "schema must be external-provider-environment-bindings"
            )
        )
    for forbidden_key in ("version", "schemaVersion"):
        if forbidden_key in bindings:
            issues.append(
                ProviderGovernanceIssue(
                    "bindings",
                    f"versioned field {forbidden_key!r} is forbidden",
                )
            )
    environment_bindings = bindings.get("environments")
    if not isinstance(environment_bindings, Mapping) or set(environment_bindings) != ENVIRONMENTS:
        issues.append(
            ProviderGovernanceIssue(
                "bindings.environments",
                "must declare exactly alpha/beta/gamma/prod",
            )
        )
        return issues
    adapters = registry.get("adapters")
    capabilities = registry.get("capabilities")
    if not isinstance(adapters, list) or not isinstance(capabilities, list):
        return issues
    adapter_by_id = {
        str(adapter.get("adapter_id")): adapter
        for adapter in adapters
        if isinstance(adapter, Mapping)
    }
    capability_by_id = {
        str(capability.get("capability_id")): capability
        for capability in capabilities
        if isinstance(capability, Mapping)
    }
    for environment in sorted(ENVIRONMENTS):
        scope = environment_bindings.get(environment)
        location = f"bindings.environments.{environment}"
        if not isinstance(scope, Mapping):
            issues.append(ProviderGovernanceIssue(location, "must be an object"))
            continue
        capability_bindings = scope.get("capabilities")
        if not isinstance(capability_bindings, list):
            issues.append(ProviderGovernanceIssue(f"{location}.capabilities", "must be a list"))
            continue
        seen_capabilities: set[str] = set()
        for index, binding in enumerate(capability_bindings):
            binding_location = f"{location}.capabilities[{index}]"
            if not isinstance(binding, Mapping):
                issues.append(ProviderGovernanceIssue(binding_location, "must be an object"))
                continue
            _require_keys(
                binding,
                {"capability_id", "state", "adapter_id", "endpoint_ref", "secret_refs"},
                location=binding_location,
                issues=issues,
            )
            capability_id = _as_non_empty_string(binding.get("capability_id"))
            if capability_id not in capability_by_id:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.capability_id",
                        "must reference a registered capability",
                    )
                )
                continue
            if capability_id in seen_capabilities:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.capability_id",
                        "must be bound once per environment",
                    )
                )
            seen_capabilities.add(capability_id)
            state = _as_non_empty_string(binding.get("state"))
            if state not in ENVIRONMENT_BINDING_STATES:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.state",
                        f"must be one of {sorted(ENVIRONMENT_BINDING_STATES)}",
                    )
                )
            adapter_id = _as_non_empty_string(binding.get("adapter_id"))
            if state in {"not_required", "unavailable"}:
                if adapter_id is not None:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.adapter_id",
                            "must be empty when state is not_required or unavailable",
                        )
                    )
            elif adapter_id not in adapter_by_id:
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.adapter_id",
                        "must reference a registered adapter unless not_required",
                    )
                )
            else:
                adapter = adapter_by_id[adapter_id]
                if adapter.get("capability_id") != capability_id:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.adapter_id",
                            "must implement the bound capability",
                        )
                    )
                if environment not in adapter.get("allowed_environments", []):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.adapter_id",
                            "is not allowed in this environment",
                        )
                    )
                implementation_status = adapter.get("implementation_status")
                if state == "enabled" and (
                    environment != "alpha"
                    and implementation_status not in READY_IMPLEMENTATION_STATUSES
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.adapter_id",
                            "non-alpha enabled bindings require a real fail-closed adapter",
                        )
                    )
                if state == "enabled" and environment == "prod" and adapter.get(
                    "production_grade"
                ) is not True:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.adapter_id",
                            "prod enabled bindings require production_grade=true",
                        )
                    )
            endpoint_ref = _as_non_empty_string(binding.get("endpoint_ref"))
            if endpoint_ref is None or not ENDPOINT_REF_PATTERN.fullmatch(endpoint_ref):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.endpoint_ref",
                        "must be a non-literal endpoint reference",
                    )
                )
            secret_refs = binding.get("secret_refs")
            if not isinstance(secret_refs, list) or any(
                not isinstance(ref, str) or not SECRET_REF_PATTERN.fullmatch(ref)
                for ref in secret_refs
            ):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.secret_refs",
                        "must only contain runtime_secret:<NAME> references",
                    )
                )
            endpoint_envs = binding.get("endpoint_envs")
            if endpoint_envs is not None and (
                not isinstance(endpoint_envs, Mapping)
                or not endpoint_envs
                or any(
                    not isinstance(role, str)
                    or not role
                    or not isinstance(environment_key, str)
                    or not ENVIRONMENT_KEY_PATTERN.fullmatch(environment_key)
                    for role, environment_key in endpoint_envs.items()
                )
            ):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.endpoint_envs",
                        "must map non-empty endpoint roles to environment keys",
                    )
                )
            timeout_ms = binding.get("timeout_ms")
            if timeout_ms is not None and (
                not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0
            ):
                issues.append(
                    ProviderGovernanceIssue(
                        f"{binding_location}.timeout_ms",
                        "must be a positive integer when declared",
                    )
                )
            if (
                isinstance(capability_id, str)
                and capability_id.startswith("assistant.")
                and state in {"enabled", "blocked"}
            ):
                if not isinstance(endpoint_envs, Mapping) or not endpoint_envs:
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.endpoint_envs",
                            "assistant bindings must declare endpoint environment keys",
                        )
                    )
                if (
                    not isinstance(timeout_ms, int)
                    or isinstance(timeout_ms, bool)
                    or timeout_ms <= 0
                ):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{binding_location}.timeout_ms",
                            "assistant bindings must declare a positive timeout",
                        )
                    )
        for capability_id, capability in capability_by_id.items():
            required_environments = capability.get("required_environments", [])
            if environment in required_environments and capability_id not in seen_capabilities:
                issues.append(
                    ProviderGovernanceIssue(
                        location,
                        f"missing binding for required capability {capability_id}",
                    )
                )
    return issues


def _message_transport_remote_uat_prerequisite_issues(
    source_path: Path,
    *,
    location: str,
) -> list[ProviderGovernanceIssue]:
    """拒绝用 widget/mock 测试为 Redis 消息链路生成 UAT 准出。"""

    issues: list[ProviderGovernanceIssue] = []
    if source_path.suffix not in {".yaml", ".yml"}:
        return [
            ProviderGovernanceIssue(
                location,
                "must declare the controlled Remote chat @ assistant UAT prerequisite, "
                "not a widget/mock test source",
            )
        ]
    try:
        prerequisite = _load_yaml(source_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [
            ProviderGovernanceIssue(
                location,
                f"has an unreadable Remote UAT prerequisite: {exc}",
            )
        ]
    expected_fields = {
        "schema",
        "status",
        "prerequisite_id",
        "reason_code",
        "recovery_action",
        "required_harness",
        "required_assertions",
        "forbidden_substitutes",
    }
    if set(prerequisite) != expected_fields:
        issues.append(
            ProviderGovernanceIssue(
                location,
                "Remote UAT prerequisite must contain only the controlled harness contract fields",
            )
        )
        return issues
    if prerequisite.get("schema") != MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA:
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must use the message transport Remote UAT prerequisite schema",
            )
        )
    if prerequisite.get("status") != "blocked":
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must remain blocked until a real Remote chat @ assistant journey is registered",
            )
        )
    if (
        prerequisite.get("prerequisite_id")
        != "runtime.message.transport.chat_assistant_remote_journey"
    ):
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must identify the runtime.message.transport chat @ assistant journey",
            )
        )
    if (
        prerequisite.get("reason_code")
        != "PROVIDER.CONFORMANCE.REMOTE_CHAT_ASSISTANT_UAT_HARNESS_REQUIRED"
        or prerequisite.get("recovery_action") != "configure"
    ):
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must fail closed with the Remote chat @ assistant harness prerequisite code",
            )
        )
    if prerequisite.get("required_harness") != MESSAGE_TRANSPORT_REMOTE_UAT_REQUIRED_HARNESS:
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must require native Patrol, production Remote composition, stackctl endpoint, "
                "CI auth and environment-managed seed",
            )
        )
    assertions = prerequisite.get("required_assertions")
    if (
        not isinstance(assertions, list)
        or len(assertions) != len(set(assertions))
        or set(assertions) != MESSAGE_TRANSPORT_REMOTE_UAT_REQUIRED_ASSERTIONS
    ):
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must require invite, @ mention, Remote reply and Redis consumer observability",
            )
        )
    forbidden_substitutes = prerequisite.get("forbidden_substitutes")
    if (
        not isinstance(forbidden_substitutes, list)
        or len(forbidden_substitutes) != len(set(forbidden_substitutes))
        or set(forbidden_substitutes)
        != MESSAGE_TRANSPORT_REMOTE_UAT_FORBIDDEN_SUBSTITUTES
    ):
        issues.append(
            ProviderGovernanceIssue(
                location,
                "must prohibit memory Redis, fixture consumers, UI mocks and Provider overrides",
            )
        )
    return issues


def conformance_manifest_issues(
    registry: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[ProviderGovernanceIssue]:
    issues: list[ProviderGovernanceIssue] = []
    if manifest.get("schema") != "provider-conformance-manifest":
        issues.append(
            ProviderGovernanceIssue(
                "conformance", "schema must be provider-conformance-manifest"
            )
        )
    for forbidden_key in ("version", "schemaVersion"):
        if forbidden_key in manifest:
            issues.append(
                ProviderGovernanceIssue(
                    "conformance",
                    f"versioned field {forbidden_key!r} is forbidden",
                )
            )
    profiles = manifest.get("profiles")
    if not isinstance(profiles, Mapping):
        issues.append(ProviderGovernanceIssue("conformance.profiles", "must be an object"))
        return issues
    registry_profiles = {
        str(adapter.get("conformance_profile"))
        for adapter in registry.get("adapters", [])
        if isinstance(adapter, Mapping)
    }
    common_assertion_ids = manifest.get("common_assertion_ids")
    if (
        not isinstance(common_assertion_ids, list)
        or not common_assertion_ids
        or not all(
            isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in common_assertion_ids
        )
        or len(common_assertion_ids) != len(set(common_assertion_ids))
    ):
        issues.append(
            ProviderGovernanceIssue(
                "conformance.common_assertion_ids",
                "must be a non-empty unique list of stable assertion IDs",
            )
        )
    profile_assertion_ids = manifest.get("profile_assertion_ids")
    if not isinstance(profile_assertion_ids, Mapping):
        issues.append(
            ProviderGovernanceIssue(
                "conformance.profile_assertion_ids",
                "must map every registry conformance profile to assertion IDs",
            )
        )
        profile_assertion_ids = {}
    for profile in sorted(registry_profiles):
        profile_definition = profiles.get(profile)
        location = f"conformance.profiles.{profile}"
        assertions = profile_assertion_ids.get(profile)
        if (
            not isinstance(assertions, list)
            or not assertions
            or not all(
                isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
                for assertion_id in assertions
            )
            or len(assertions) != len(set(assertions))
        ):
            issues.append(
                ProviderGovernanceIssue(
                    f"conformance.profile_assertion_ids.{profile}",
                    "must be a non-empty unique list of stable assertion IDs",
                )
            )
        if not isinstance(profile_definition, Mapping):
            issues.append(
                ProviderGovernanceIssue(location, "must define every registry conformance profile")
            )
            continue
        _require_keys(
            profile_definition,
            {"local_contract", "api_integration", "user_acceptance", "artifact_schema"},
            location=location,
            issues=issues,
        )
        for field_name in ("local_contract", "api_integration", "user_acceptance"):
            test_path = _path_from_ref(profile_definition.get(field_name))
            if test_path is None or not test_path.exists():
                issues.append(
                    ProviderGovernanceIssue(
                        f"{location}.{field_name}",
                        "must point to an existing test source",
                    )
                )
            elif profile == "message_transport" and field_name == "user_acceptance":
                issues.extend(
                    _message_transport_remote_uat_prerequisite_issues(
                        test_path,
                        location=f"{location}.{field_name}",
                    )
                )
        artifact_schema_path = _path_from_ref(profile_definition.get("artifact_schema"))
        if artifact_schema_path is None or not artifact_schema_path.exists():
            issues.append(
                ProviderGovernanceIssue(
                    f"{location}.artifact_schema",
                    "must point to an existing evidence schema",
                )
            )
    return issues


def _binding_readiness(
    *,
    environment: str,
    capability: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
    adapter_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    required = environment in capability.get("required_environments", [])
    if binding is None:
        return {
            "required": required,
            "state": "unavailable" if required else "not_required",
            "adapter_id": None,
            "adapter_preflight_ready": False,
            "adapter_ready": False,
            "capability_ready": False,
        }

    state = _as_non_empty_string(binding.get("state")) or "unavailable"
    adapter_id = _as_non_empty_string(binding.get("adapter_id"))
    adapter = adapter_by_id.get(adapter_id or "")
    adapter_ready = False
    if state == "enabled" and adapter is not None:
        status = adapter.get("implementation_status")
        adapter_ready = status in READY_IMPLEMENTATION_STATUSES
        if environment == "alpha":
            adapter_ready = status in {
                *READY_IMPLEMENTATION_STATUSES,
                "mock",
                "test_fixture_only",
                "sandbox",
            }
        if environment == "prod":
            adapter_ready = adapter_ready and adapter.get("production_grade") is True
    return {
        "required": required,
        "state": state,
        "adapter_id": adapter_id,
        "adapter_preflight_ready": adapter_ready,
        "adapter_ready": False,
        "capability_ready": False,
    }


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
    adapters = registry.get("adapters") if isinstance(registry.get("adapters"), list) else []
    capabilities = (
        registry.get("capabilities") if isinstance(registry.get("capabilities"), list) else []
    )
    adapter_by_id = {
        str(adapter.get("adapter_id")): adapter
        for adapter in adapters
        if isinstance(adapter, Mapping)
    }
    selected: dict[str, dict[str, dict[str, Any]]] = {}
    readiness: dict[str, dict[str, dict[str, Any]]] = {}
    for environment in sorted(ENVIRONMENTS):
        scope = (bindings.get("environments") or {}).get(environment, {})
        if not isinstance(scope, Mapping):
            continue
        environment_selected: dict[str, dict[str, Any]] = {}
        bindings_by_capability: dict[str, Mapping[str, Any]] = {}
        for binding in scope.get("capabilities", []):
            if isinstance(binding, Mapping):
                capability_id = _as_non_empty_string(binding.get("capability_id"))
                if capability_id:
                    bindings_by_capability[capability_id] = binding
                    environment_selected[capability_id] = {
                        key: binding.get(key)
                        for key in (
                            "state",
                            "adapter_id",
                            "endpoint_ref",
                            "secret_refs",
                            "endpoint_envs",
                            "timeout_ms",
                        )
                    }
        selected[environment] = environment_selected
        readiness[environment] = {
            str(capability.get("capability_id")): _binding_readiness(
                environment=environment,
                capability=capability,
                binding=bindings_by_capability.get(str(capability.get("capability_id"))),
                adapter_by_id=adapter_by_id,
            )
            for capability in capabilities
            if isinstance(capability, Mapping)
        }
    compiled = {
        "schema": "compiled-external-provider-governance",
        "capabilityCount": len(capabilities),
        "adapterCount": len(adapters),
        "capabilityOwners": {
            str(capability.get("capability_id")): str(capability.get("owner"))
            for capability in capabilities
            if isinstance(capability, Mapping)
        },
        "capabilityBindingRoots": {
            str(capability.get("capability_id")): [
                dict(binding_root)
                for binding_root in capability.get("binding_roots", [])
                if isinstance(binding_root, Mapping)
            ]
            for capability in capabilities
            if isinstance(capability, Mapping)
            and isinstance(capability.get("binding_roots"), list)
        },
        "selectedBindings": selected,
        "readiness": readiness,
        "issues": [issue.render() for issue in issues],
    }
    return compiled, issues


def load_and_compile(
    *,
    registry_path: Path = REGISTRY_PATH,
    bindings_path: Path = BINDINGS_PATH,
    conformance_path: Path = CONFORMANCE_PATH,
) -> tuple[dict[str, Any], list[ProviderGovernanceIssue]]:
    return compile_governance(
        load_registry(registry_path),
        load_bindings(bindings_path),
        load_conformance_manifest(conformance_path),
    )


def _go_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_go_bindings(
    compiled: Mapping[str, Any],
    *,
    descriptor_owner: str,
) -> str:
    """Render one descriptor owner's checked-in Go bindings from the receipt."""
    selected = compiled.get("selectedBindings")
    capability_binding_roots = compiled.get("capabilityBindingRoots")
    if not isinstance(selected, Mapping) or not isinstance(capability_binding_roots, Mapping):
        raise ValueError(
            "compiled governance is missing selected bindings or capability binding roots"
        )
    if not isinstance(descriptor_owner, str) or not descriptor_owner:
        raise ValueError("a non-empty descriptor owner is required")

    lines = [
        "// Code generated by external_provider_governance.py; DO NOT EDIT.",
        "",
        "package generated",
        "",
        "// ExternalProviderBindingOwner is the owner for this descriptor.",
        f"const ExternalProviderBindingOwner = {_go_string(descriptor_owner)}",
        "",
        "// ExternalProviderBinding is a build-time selected capability adapter.",
        "type ExternalProviderBinding struct {",
        "\tState                   string",
        "\tAdapterID               string",
        "\tEndpointRef             string",
        "\tEndpointEnvironmentKeys map[string]string",
        "\tSecretEnvironmentKeys   []string",
        "\tTimeoutMilliseconds     int",
        "}",
        "",
        "// ExternalProviderBindings contains only compiler-selected bindings.",
        "var ExternalProviderBindings = map[string]map[string]ExternalProviderBinding{",
    ]
    for environment in sorted(selected):
        capabilities = selected[environment]
        if not isinstance(environment, str) or not isinstance(capabilities, Mapping):
            continue
        lines.append(f"\t{_go_string(environment)}: {{")
        for capability_id in sorted(capabilities):
            binding = capabilities[capability_id]
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            roots = capability_binding_roots.get(capability_id)
            if not isinstance(roots, list) or not any(
                isinstance(root, Mapping)
                and root.get("descriptor_owner") == descriptor_owner
                for root in roots
            ):
                continue
            endpoint_envs = binding.get("endpoint_envs")
            if not isinstance(endpoint_envs, Mapping):
                endpoint_envs = {}
            secret_refs = binding.get("secret_refs")
            if not isinstance(secret_refs, list):
                secret_refs = []
            secret_environment_keys = [
                ref.removeprefix("runtime_secret:")
                for ref in secret_refs
                if isinstance(ref, str) and SECRET_REF_PATTERN.fullmatch(ref)
            ]
            lines.extend(
                [
                    f"\t\t{_go_string(capability_id)}: {{",
                    f"\t\t\tState: {_go_string(str(binding.get('state') or ''))},",
                    f"\t\t\tAdapterID: {_go_string(str(binding.get('adapter_id') or ''))},",
                    f"\t\t\tEndpointRef: {_go_string(str(binding.get('endpoint_ref') or ''))},",
                    "\t\t\tEndpointEnvironmentKeys: map[string]string{",
                ]
            )
            for role in sorted(endpoint_envs):
                environment_key = endpoint_envs[role]
                if isinstance(role, str) and isinstance(environment_key, str):
                    lines.append(f"\t\t\t\t{_go_string(role)}: {_go_string(environment_key)},")
            lines.append("\t\t\t},")
            lines.append("\t\t\tSecretEnvironmentKeys: []string{")
            for environment_key in secret_environment_keys:
                lines.append(f"\t\t\t\t{_go_string(environment_key)},")
            lines.extend(
                [
                    "\t\t\t},",
                    f"\t\t\tTimeoutMilliseconds: {int(binding.get('timeout_ms') or 0)},",
                    "\t\t},",
                ]
            )
        lines.append("\t},")
    lines.extend(
        [
            "}",
            "",
            "// ExternalProviderBindingRoot is one static consumer projection for this descriptor.",
            "type ExternalProviderBindingRoot struct {",
            "\tRootID              string",
            "\tRequiredRedisScenes []string",
            "}",
            "",
            "// ExternalProviderBindingRoots contains every compiler-approved root this descriptor owns.",
            "var ExternalProviderBindingRoots = map[string]map[string]ExternalProviderBindingRoot{",
        ]
    )
    for capability_id in sorted(capability_binding_roots):
        roots = capability_binding_roots[capability_id]
        if not isinstance(capability_id, str) or not isinstance(roots, list):
            continue
        owned_roots = [
            root
            for root in roots
            if isinstance(root, Mapping) and root.get("descriptor_owner") == descriptor_owner
        ]
        if not owned_roots:
            continue
        lines.append(f"\t{_go_string(capability_id)}: {{")
        for root in sorted(owned_roots, key=lambda item: str(item.get("root_id") or "")):
            root_id = _as_non_empty_string(root.get("root_id"))
            if root_id is None:
                continue
            scenes = root.get("required_redis_scenes")
            if not isinstance(scenes, list):
                scenes = []
            lines.extend(
                [
                    f"\t\t{_go_string(root_id)}: {{",
                    f"\t\t\tRootID: {_go_string(root_id)},",
                    "\t\t\tRequiredRedisScenes: []string{",
                ]
            )
            for scene in scenes:
                if isinstance(scene, str):
                    lines.append(f"\t\t\t\t{_go_string(scene)},")
            lines.extend(["\t\t\t},", "\t\t},"])
        lines.append("\t},")
    lines.extend(
        [
            "}",
            "",
            "// ExternalProviderBindingFor returns a compiler-selected binding.",
            "func ExternalProviderBindingFor(environment, capabilityID string) (ExternalProviderBinding, bool) {",
            "\tbyCapability, ok := ExternalProviderBindings[environment]",
            "\tif !ok {",
            "\t\treturn ExternalProviderBinding{}, false",
            "\t}",
            "\tbinding, ok := byCapability[capabilityID]",
            "\treturn binding, ok",
            "}",
            "",
            "// ExternalProviderBindingRootFor returns one compiler-approved root projection.",
            "func ExternalProviderBindingRootFor(capabilityID, rootID string) (ExternalProviderBindingRoot, bool) {",
            "\tbyRoot, ok := ExternalProviderBindingRoots[capabilityID]",
            "\tif !ok {",
            "\t\treturn ExternalProviderBindingRoot{}, false",
            "\t}",
            "\troot, ok := byRoot[rootID]",
            "\treturn root, ok",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def composition_issues(
    registry: Mapping[str, Any],
    compiled: Mapping[str, Any],
) -> list[ProviderGovernanceIssue]:
    """Verify every binding-root descriptor and static consumer without runtime scanning."""
    issues: list[ProviderGovernanceIssue] = []
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        return [ProviderGovernanceIssue("registry.capabilities", "must be a list")]
    checked_outputs: set[tuple[Path, str]] = set()
    for index, capability in enumerate(capabilities):
        if not isinstance(capability, Mapping):
            continue
        required_environments = capability.get("required_environments")
        if not isinstance(required_environments, list) or not required_environments:
            continue
        binding_roots = capability.get("binding_roots")
        if not isinstance(binding_roots, list):
            continue
        binding_scope = capability.get("binding_scope")
        for root_index, binding_root in enumerate(binding_roots):
            if not isinstance(binding_root, Mapping):
                continue
            location = f"registry.capabilities[{index}].binding_roots[{root_index}]"
            descriptor_owner = _as_non_empty_string(binding_root.get("descriptor_owner"))
            descriptor_output = _path_from_ref(binding_root.get("descriptor_output"))
            if descriptor_output is None or descriptor_owner is None:
                continue
            output_key = (descriptor_output, descriptor_owner)
            if output_key not in checked_outputs:
                checked_outputs.add(output_key)
                if not descriptor_output.is_file():
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{location}.descriptor_output",
                            "generated binding root descriptor is missing; run the provider binding codegen",
                        )
                    )
                else:
                    expected = render_go_bindings(
                        compiled,
                        descriptor_owner=descriptor_owner,
                    )
                    current = descriptor_output.read_text(encoding="utf-8")
                    if current != expected:
                        issues.append(
                            ProviderGovernanceIssue(
                                f"{location}.descriptor_output",
                                "generated binding root descriptor is stale; run the provider binding codegen",
                            )
                        )
            for path_field, symbol_field in (
                ("entrypoint", "entrypoint_symbol"),
                ("resolver_path", "resolver_symbol"),
            ):
                source_path = _path_from_ref(binding_root.get(path_field))
                symbol = _as_non_empty_string(binding_root.get(symbol_field))
                if source_path is None or symbol is None or not source_path.is_file():
                    continue
                if symbol not in source_path.read_text(encoding="utf-8"):
                    issues.append(
                        ProviderGovernanceIssue(
                            f"{location}.{path_field}",
                            f"must consume its binding through {symbol}",
                        )
                    )
            if binding_scope == "shared_multi_consumer":
                entrypoint = _path_from_ref(binding_root.get("entrypoint"))
                if entrypoint is not None and entrypoint.is_file():
                    entrypoint_source = entrypoint.read_text(encoding="utf-8")
                    entrypoint_symbol = _as_non_empty_string(
                        binding_root.get("entrypoint_symbol")
                    )
                    if "ExternalProviderBindingFor" not in entrypoint_source:
                        issues.append(
                            ProviderGovernanceIssue(
                                f"{location}.entrypoint",
                                "shared message root must consume its generated Binding descriptor",
                            )
                        )
                    if (
                        "RequireConfiguredRedisMessageTransport" not in entrypoint_source
                        and "RequireRedisMessageTransport" not in entrypoint_source
                    ):
                        issues.append(
                            ProviderGovernanceIssue(
                                f"{location}.entrypoint",
                                "shared message root must execute the Redis transport preflight",
                            )
                        )
                    main_path = entrypoint.parent / "main.go"
                    if (
                        entrypoint_symbol is not None
                        and main_path != entrypoint
                        and main_path.is_file()
                    ):
                        main_source = main_path.read_text(encoding="utf-8")
                        if entrypoint_symbol not in main_source:
                            issues.append(
                                ProviderGovernanceIssue(
                                    f"{location}.entrypoint",
                                    "shared message root preflight helper is not invoked by its composition root",
                                )
                            )
                        elif re.search(
                            rf"if\s+_,\s*err\s*:=\s*{re.escape(entrypoint_symbol)}\s*\(",
                            main_source,
                        ):
                            issues.append(
                                ProviderGovernanceIssue(
                                    f"{location}.entrypoint",
                                    "shared message root discards the resolved transport and can still use an unverified Redis scene",
                                )
                            )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--go-output",
        type=Path,
        help="write compiled bindings as a checked-in Go descriptor",
    )
    parser.add_argument(
        "--descriptor-owner",
        help="render only bindings for this descriptor owner",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when --go-output is absent or differs from compiler output",
    )
    args = parser.parse_args(argv)
    compiled, issues = load_and_compile()
    if args.go_output:
        if not args.descriptor_owner:
            parser.error("--descriptor-owner is required when --go-output is provided")
        rendered = render_go_bindings(
            compiled,
            descriptor_owner=args.descriptor_owner,
        )
        try:
            current = args.go_output.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = None
        if args.check:
            if current != rendered:
                print(f"generated provider bindings are stale: {args.go_output}")
                return 1
        else:
            args.go_output.parent.mkdir(parents=True, exist_ok=True)
            args.go_output.write_text(rendered, encoding="utf-8")
    print(json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
