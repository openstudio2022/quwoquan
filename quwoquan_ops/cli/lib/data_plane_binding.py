"""Deployment-only data-plane binding validation, redaction, and resolution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping

import yaml


SCHEMA = "qwq.data_plane_binding.v1"
ENGINES = frozenset(
    {"postgres", "mongodb", "elasticsearch", "redis", "object_storage"}
)
INJECT_KINDS = frozenset(
    {"dsn", "uri", "addr", "endpoint", "database", "index", "api_key", "literal"}
)
RESOURCE_FIELDS = frozenset(
    {"engine", "physicalIdentity", "failureDomain", "shared"}
)
BINDING_FIELDS = frozenset(
    {
        "service",
        "slot",
        "engine",
        "resource",
        "namespace",
        "secretRef",
        "shared",
        "required",
        "backupRef",
        "metricsRef",
        "inject",
    }
)
_SAFE_RESOURCE_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_SAFE_SERVICE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SAFE_SLOT = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*$")
_SAFE_IDENTITY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_SAFE_NAMESPACE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SECRET_REF = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_SEARCH_GENERATION = re.compile(r"(?:^|[-_.])v([1-9][0-9]*)$")
_IDENTITY_MODES = frozenset({"external", "local", "prevalidate"})
_DEFAULT_ENGINE_SLOTS = {
    "postgres": "postgres",
    "mongodb": "mongodb",
    "elasticsearch": "elasticsearch",
    "redis": "redis",
    "object_storage": "object_storage",
}
CONTRACT_GRAPH_REF = PurePosixPath("quwoquan_service/generated/contract_graph.json")
_DEPLOYMENT_CONTROL_SERVICE = "deployment-control"
_SEARCH_OBJECTS_ADMIN_SLOT = "search.objects.admin"
_TELEMETRY_ADMIN_SLOT = "telemetry.admin"
_METRICS_OWNER_PREFIX = {
    "search.objects": "search-objects-",
    "telemetry": "product-telemetry-",
    "runtime-logs": "runtime-logs-",
}
_KIND_ENGINES = {
    "dsn": frozenset({"postgres"}),
    "uri": frozenset({"mongodb"}),
    "addr": frozenset({"redis"}),
    "endpoint": frozenset({"elasticsearch", "object_storage"}),
    "database": frozenset({"postgres", "mongodb", "redis", "object_storage"}),
    "index": frozenset({"elasticsearch"}),
    "api_key": frozenset({"elasticsearch", "object_storage"}),
    "literal": ENGINES,
}


class DataPlaneBindingError(ValueError):
    """The deployment binding is malformed or cannot be resolved safely."""


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _optional_ref(
    value: object,
    *,
    label: str,
    allow_empty: bool,
    secret: bool,
    issues: list[str],
) -> str | None:
    if value is None or (allow_empty and value == ""):
        return None
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label} must be null or a non-empty reference")
        return None
    normalized = value.strip()
    pattern = _SECRET_REF if secret else _SAFE_IDENTITY
    if pattern.fullmatch(normalized) is None or "://" in normalized:
        kind = "environment reference name" if secret else "safe reference"
        issues.append(f"{label} must be a {kind}")
        return None
    return normalized


def _physical_identity(
    value: object,
    *,
    label: str,
    issues: list[str],
) -> str | dict[str, str] | None:
    if isinstance(value, str):
        normalized = value.strip()
        if _SAFE_IDENTITY.fullmatch(normalized) is None or "://" in normalized:
            issues.append(f"{label} must be a safe non-endpoint identity")
            return None
        return normalized
    if not isinstance(value, Mapping) or not value:
        issues.append(f"{label} must be a safe identity or mode mapping")
        return None
    unknown = sorted(set(value) - _IDENTITY_MODES)
    if unknown:
        issues.append(f"{label} contains unsupported modes: {unknown}")
    normalized_modes: dict[str, str] = {}
    for mode, raw in sorted(value.items()):
        if mode not in _IDENTITY_MODES:
            continue
        identity = str(raw or "").strip()
        if _SAFE_IDENTITY.fullmatch(identity) is None or "://" in identity:
            issues.append(f"{label}.{mode} must be a safe non-endpoint identity")
            continue
        normalized_modes[mode] = identity
    if not normalized_modes:
        return None
    return normalized_modes


def validate_data_plane_binding(
    target: Mapping[str, Any],
    *,
    target_name: str = "target",
    required: bool = False,
) -> list[str]:
    """Return deterministic validation issues for one target's ``dataPlane``."""

    _, issues = _normalize_data_plane_binding(
        target,
        target_name=target_name,
        required=required,
    )
    return issues


def _normalize_data_plane_binding(
    target: Mapping[str, Any],
    *,
    target_name: str,
    required: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    data_plane = target.get("dataPlane")
    if data_plane is None:
        if required:
            issues.append(f"{target_name}: dataPlane is required")
        return None, issues
    if not isinstance(data_plane, Mapping):
        return None, [f"{target_name}: dataPlane must be a mapping"]
    if set(data_plane) != {"resources", "bindings"}:
        issues.append(
            f"{target_name}: dataPlane may contain only resources/bindings"
        )
    resources = data_plane.get("resources")
    bindings = data_plane.get("bindings")
    if not isinstance(resources, Mapping) or not resources:
        issues.append(f"{target_name}: dataPlane.resources must be a non-empty mapping")
        resources = {}
    if not isinstance(bindings, Mapping) or not bindings:
        issues.append(f"{target_name}: dataPlane.bindings must be a non-empty mapping")
        bindings = {}

    normalized_resources: dict[str, dict[str, Any]] = {}
    for resource_key, raw in sorted(resources.items(), key=lambda item: str(item[0])):
        label = f"{target_name}: dataPlane.resources.{resource_key}"
        if not isinstance(resource_key, str) or _SAFE_RESOURCE_KEY.fullmatch(resource_key) is None:
            issues.append(f"{label} key must be a safe lowercase resource key")
            continue
        if not isinstance(raw, Mapping):
            issues.append(f"{label} must be a mapping")
            continue
        if set(raw) != RESOURCE_FIELDS:
            issues.append(f"{label} fields must be exactly {sorted(RESOURCE_FIELDS)}")
        engine = str(raw.get("engine") or "").strip()
        if engine not in ENGINES:
            issues.append(f"{label}.engine must be one of {sorted(ENGINES)}")
        identity = _physical_identity(
            raw.get("physicalIdentity"),
            label=f"{label}.physicalIdentity",
            issues=issues,
        )
        failure_domain = str(raw.get("failureDomain") or "").strip()
        if _SAFE_IDENTITY.fullmatch(failure_domain) is None or "://" in failure_domain:
            issues.append(f"{label}.failureDomain must be a safe non-empty identity")
        shared = raw.get("shared")
        if type(shared) is not bool:
            issues.append(f"{label}.shared must be bool")
        normalized_resources[resource_key] = {
            "engine": engine,
            "physicalIdentity": identity,
            "failureDomain": failure_domain,
            "shared": shared,
        }

    normalized_bindings: dict[str, dict[str, Any]] = {}
    resource_users: dict[str, list[str]] = {}
    namespace_users: dict[tuple[str, str], list[str]] = {}
    injected_keys: dict[tuple[str, str], str] = {}
    search_roles: list[tuple[str, dict[str, Any]]] = []
    telemetry_roles: list[tuple[str, dict[str, Any]]] = []
    runtime_log_roles: list[tuple[str, dict[str, Any]]] = []
    for binding_key, raw in sorted(bindings.items(), key=lambda item: str(item[0])):
        label = f"{target_name}: dataPlane.bindings.{binding_key}"
        if not isinstance(binding_key, str):
            issues.append(f"{label} key must be <service>.<slot>")
            continue
        if not isinstance(raw, Mapping):
            issues.append(f"{label} must be a mapping")
            continue
        if set(raw) != BINDING_FIELDS:
            issues.append(f"{label} fields must be exactly {sorted(BINDING_FIELDS)}")
        service = str(raw.get("service") or "").strip()
        slot = str(raw.get("slot") or "").strip()
        expected_key = f"{service}.{slot}"
        if (
            _SAFE_SERVICE.fullmatch(service) is None
            or _SAFE_SLOT.fullmatch(slot) is None
            or binding_key != expected_key
        ):
            issues.append(f"{label} key/service/slot must agree as <service>.<slot>")
        engine = str(raw.get("engine") or "").strip()
        if engine not in ENGINES:
            issues.append(f"{label}.engine must be one of {sorted(ENGINES)}")
        resource = str(raw.get("resource") or "").strip()
        resource_spec = normalized_resources.get(resource)
        if resource_spec is None:
            issues.append(f"{label}.resource must reference an existing resource")
        elif resource_spec.get("engine") != engine:
            issues.append(f"{label}.engine must match resource engine")
        namespace = str(raw.get("namespace") or "").strip()
        if _SAFE_NAMESPACE.fullmatch(namespace) is None:
            issues.append(f"{label}.namespace must be a safe non-empty namespace")
        shared = raw.get("shared")
        required_value = raw.get("required")
        if type(shared) is not bool:
            issues.append(f"{label}.shared must be bool")
        if type(required_value) is not bool:
            issues.append(f"{label}.required must be bool")
        secret_ref = _optional_ref(
            raw.get("secretRef"),
            label=f"{label}.secretRef",
            allow_empty=True,
            secret=True,
            issues=issues,
        )
        backup_ref = _optional_ref(
            raw.get("backupRef"),
            label=f"{label}.backupRef",
            allow_empty=False,
            secret=False,
            issues=issues,
        )
        metrics_ref = _optional_ref(
            raw.get("metricsRef"),
            label=f"{label}.metricsRef",
            allow_empty=False,
            secret=False,
            issues=issues,
        )
        if backup_ref is None:
            issues.append(f"{label}.backupRef must be non-empty")
        if metrics_ref is None:
            issues.append(f"{label}.metricsRef must be non-empty")
        inject = raw.get("inject")
        normalized_inject: dict[str, dict[str, Any]] = {}
        deployment_only = _is_deployment_only_service(service)
        if deployment_only:
            if not isinstance(inject, Mapping) or inject:
                issues.append(
                    f"{label}.inject must be empty for deployment-control binding"
                )
                inject = {}
        elif not isinstance(inject, Mapping) or (
            required_value is True and not inject
        ):
            issues.append(f"{label}.inject must be a non-empty mapping when required")
            inject = {}
        for env_key, descriptor in sorted(inject.items(), key=lambda item: str(item[0])):
            inject_label = f"{label}.inject.{env_key}"
            if not isinstance(env_key, str) or _ENV_KEY.fullmatch(env_key) is None:
                issues.append(f"{inject_label} key must be an environment key")
                continue
            if not isinstance(descriptor, Mapping) or not descriptor:
                issues.append(f"{inject_label} must be a mapping")
                continue
            kind = str(descriptor.get("kind") or "").strip()
            allowed_inject_fields = {"kind", "secretRef"}
            if kind in {"literal", "database", "index"}:
                allowed_inject_fields.add("value")
            if (
                not set(descriptor).issubset(allowed_inject_fields)
                or "kind" not in descriptor
            ):
                issues.append(
                    f"{inject_label} contains fields forbidden for kind {kind or '<empty>'}"
                )
            if kind not in INJECT_KINDS:
                issues.append(f"{inject_label}.kind must be one of {sorted(INJECT_KINDS)}")
            elif engine in ENGINES and engine not in _KIND_ENGINES[kind]:
                issues.append(f"{inject_label}.kind is incompatible with {engine}")
            inject_secret_ref = _optional_ref(
                descriptor.get("secretRef"),
                label=f"{inject_label}.secretRef",
                allow_empty=True,
                secret=True,
                issues=issues,
            )
            normalized_descriptor: dict[str, Any] = {"kind": kind}
            if inject_secret_ref is not None:
                normalized_descriptor["secretRef"] = inject_secret_ref
            if kind == "literal":
                literal = descriptor.get("value")
                if literal not in {"true", "false"}:
                    issues.append(
                        f"{inject_label}.value must be a non-secret bool literal"
                    )
                else:
                    normalized_descriptor["value"] = literal
                if inject_secret_ref is not None:
                    issues.append(f"{inject_label}.secretRef is forbidden for literal")
            elif kind in {"database", "index"} and "value" in descriptor:
                explicit_value = str(descriptor.get("value") or "").strip()
                if (
                    _SAFE_NAMESPACE.fullmatch(explicit_value) is None
                    or "://" in explicit_value
                    or "$" in explicit_value
                ):
                    issues.append(
                        f"{inject_label}.value must be a safe non-secret namespace"
                    )
                else:
                    normalized_descriptor["value"] = explicit_value
                if inject_secret_ref is not None:
                    issues.append(
                        f"{inject_label}.secretRef is forbidden with explicit value"
                    )
            normalized_inject[env_key] = normalized_descriptor
            produced = [env_key]
            if kind == "addr" and env_key.endswith("_ADDR"):
                produced.extend((env_key[:-5] + "_MODE", env_key[:-5] + "_TLS"))
            for produced_key in produced:
                identity = (service, produced_key)
                previous = injected_keys.get(identity)
                if previous is not None and previous != binding_key:
                    issues.append(
                        f"{label}.inject duplicates {service}.{produced_key} from {previous}"
                    )
                injected_keys[identity] = binding_key
        normalized = {
            "service": service,
            "slot": slot,
            "engine": engine,
            "resource": resource,
            "namespace": namespace,
            "secretRef": secret_ref,
            "shared": shared,
            "required": required_value,
            "backupRef": backup_ref,
            "metricsRef": metrics_ref,
            "inject": normalized_inject,
        }
        normalized_bindings[binding_key] = normalized
        resource_users.setdefault(resource, []).append(binding_key)
        namespace_users.setdefault((resource, namespace), []).append(binding_key)
        if slot in {
            "search.objects.reader",
            "search.objects.writer",
            "search.objects.admin",
        }:
            search_roles.append((binding_key, normalized))
        if slot == "telemetry":
            telemetry_roles.append((binding_key, normalized))
        if slot == "runtime-logs":
            runtime_log_roles.append((binding_key, normalized))

    for resource, users in sorted(resource_users.items()):
        if len(users) < 2:
            continue
        resource_spec = normalized_resources.get(resource) or {}
        if resource_spec.get("shared") is not True:
            issues.append(
                f"{target_name}: co-located resource {resource} must declare shared=true"
            )
        for binding_key in users:
            if (normalized_bindings.get(binding_key) or {}).get("shared") is not True:
                issues.append(
                    f"{target_name}: co-located binding {binding_key} must declare shared=true"
                )
    endpoint_refs_by_resource: dict[str, set[str | None]] = {}
    for binding in normalized_bindings.values():
        for descriptor in binding["inject"].values():
            if descriptor.get("kind") != "endpoint":
                continue
            endpoint_refs_by_resource.setdefault(binding["resource"], set()).add(
                descriptor.get("secretRef") or binding.get("secretRef")
            )
    for resource, endpoint_refs in sorted(endpoint_refs_by_resource.items()):
        if len(endpoint_refs) > 1:
            issues.append(
                f"{target_name}: {resource} endpoint refs must be identical for "
                "bindings sharing one physical resource"
            )

    physical_resources_by_mode: dict[tuple[str, str], list[str]] = {}
    for resource_key, resource in normalized_resources.items():
        identity = resource.get("physicalIdentity")
        for mode in sorted(_IDENTITY_MODES):
            mode_identity = identity if isinstance(identity, str) else (
                identity.get(mode) if isinstance(identity, Mapping) else None
            )
            if isinstance(mode_identity, str) and mode_identity:
                physical_resources_by_mode.setdefault(
                    (mode, mode_identity), []
                ).append(resource_key)
    for (mode, _), resource_keys in sorted(physical_resources_by_mode.items()):
        if len(resource_keys) < 2:
            continue
        for resource_key in sorted(resource_keys):
            if normalized_resources[resource_key].get("shared") is not True:
                issues.append(
                    f"{target_name}: co-located resource {resource_key} in {mode} "
                    "must declare shared=true"
                )
            for binding_key in resource_users.get(resource_key, []):
                if (normalized_bindings.get(binding_key) or {}).get("shared") is not True:
                    issues.append(
                        f"{target_name}: co-located binding {binding_key} in {mode} "
                        "must declare shared=true"
                    )
    search_keys = {key for key, _ in search_roles}
    for (resource, namespace), users in sorted(namespace_users.items()):
        if len(users) > 1 and not set(users).issubset(search_keys):
            issues.append(
                f"{target_name}: namespace collision on {resource}/{namespace}: {sorted(users)}"
            )

    if search_roles:
        readers = [item for item in search_roles if item[1]["slot"].endswith(".reader")]
        writers = [item for item in search_roles if item[1]["slot"].endswith(".writer")]
        admins = [item for item in search_roles if item[1]["slot"].endswith(".admin")]
        if len(readers) != 1 or not writers or len(admins) != 1:
            issues.append(
                f"{target_name}: search.objects requires exactly one reader, "
                "at least one writer, and exactly one deployment-only admin"
            )
        if any(
            not _is_deployment_only_service(item[1].get("service"))
            or item[1]["slot"] != _SEARCH_OBJECTS_ADMIN_SLOT
            or item[1]["required"] is not True
            for item in admins
        ):
            issues.append(
                f"{target_name}: search.objects admin must be deployment-only"
            )
        triples = {
            (
                item[1]["resource"],
                item[1]["namespace"],
                (
                    generation.group(1)
                    if (generation := _SEARCH_GENERATION.search(item[1]["namespace"]))
                    else None
                ),
            )
            for item in search_roles
        }
        if any(triple[2] is None for triple in triples) or len(triples) != 1:
            issues.append(
                f"{target_name}: search.objects reader/writers/admin must share "
                "resource, namespace, and vN generation"
            )
        reader_refs = {item[1]["secretRef"] for item in readers if item[1]["secretRef"]}
        writer_refs = {item[1]["secretRef"] for item in writers if item[1]["secretRef"]}
        admin_refs = {item[1]["secretRef"] for item in admins if item[1]["secretRef"]}
        credential_refs_present = bool(reader_refs or writer_refs or admin_refs)
        credentials_required = target_name in {"prod-hosted", "external"}
        if credential_refs_present or credentials_required:
            role_refs = (reader_refs, writer_refs, admin_refs)
            if (
                any(len(refs) != 1 for refs in role_refs)
                or any(not item[1]["secretRef"] for item in search_roles)
                or not reader_refs.isdisjoint(writer_refs)
                or not reader_refs.isdisjoint(admin_refs)
                or not writer_refs.isdisjoint(admin_refs)
            ):
                issues.append(
                    f"{target_name}: search.objects reader/writer/admin credential "
                    "refs must be present and role-separated"
                )
            for binding_key, binding in [*readers, *writers]:
                api_key_refs = {
                    descriptor.get("secretRef") or binding.get("secretRef")
                    for descriptor in binding["inject"].values()
                    if descriptor.get("kind") == "api_key"
                }
                if api_key_refs != {binding.get("secretRef")} or None in api_key_refs:
                    issues.append(
                        f"{target_name}: {binding_key} must inject only its role API key"
                    )

    owner_groups = {
        "search.objects": [
            item for item in search_roles if not item[1]["slot"].endswith(".admin")
        ],
        "telemetry": telemetry_roles,
        "runtime-logs": runtime_log_roles,
    }
    owner_metrics: dict[str, set[str]] = {}
    for owner, members in owner_groups.items():
        refs = {
            str(binding.get("metricsRef") or "")
            for _, binding in members
            if binding.get("metricsRef")
        }
        owner_metrics[owner] = refs
        prefix = _METRICS_OWNER_PREFIX[owner]
        for binding_key, binding in members:
            metrics_ref = str(binding.get("metricsRef") or "")
            if metrics_ref and not metrics_ref.startswith(prefix):
                issues.append(
                    f"{target_name}: {binding_key}.metricsRef must use {prefix} owner prefix"
                )
    present_owner_refs = [refs for refs in owner_metrics.values() if refs]
    for index, refs in enumerate(present_owner_refs):
        for other in present_owner_refs[index + 1 :]:
            if not refs.isdisjoint(other):
                issues.append(
                    f"{target_name}: search/telemetry/runtime metricsRef owners must be distinct"
                )

    telemetry_admins = [
        (key, binding)
        for key, binding in normalized_bindings.items()
        if _is_deployment_only_service(binding.get("service"))
        and binding["slot"] == _TELEMETRY_ADMIN_SLOT
    ]
    if telemetry_roles or runtime_log_roles or telemetry_admins:
        if len(telemetry_admins) != 1:
            issues.append(
                f"{target_name}: telemetry/runtime-logs require exactly one "
                "deployment-only admin"
            )
        elif telemetry_admins[0][1]["required"] is not True:
            issues.append(
                f"{target_name}: telemetry admin must be required and deployment-only"
            )
        elif telemetry_roles and runtime_log_roles:
            _, telemetry_admin = telemetry_admins[0]
            owner_resources = {
                telemetry_roles[0][1]["resource"],
                runtime_log_roles[0][1]["resource"],
            }
            if telemetry_admin["resource"] not in owner_resources or len(owner_resources) != 1:
                issues.append(
                    f"{target_name}: telemetry admin must share the telemetry/runtime "
                    "physical resource"
                )
            if target_name in {"prod-hosted", "external"} and not telemetry_admin.get(
                "secretRef"
            ):
                issues.append(
                    f"{target_name}: telemetry admin credential ref must be present"
                )

    if telemetry_roles or runtime_log_roles:
        if len(telemetry_roles) != 1 or len(runtime_log_roles) != 1:
            issues.append(
                f"{target_name}: telemetry and runtime-logs require one binding each"
            )
        elif telemetry_roles and runtime_log_roles:
            telemetry_key, telemetry = telemetry_roles[0]
            runtime_key, runtime_logs = runtime_log_roles[0]

            def logical_members(binding: Mapping[str, Any]) -> set[str]:
                members = {str(binding.get("namespace") or "")}
                for descriptor in binding.get("inject", {}).values():
                    if descriptor.get("kind") in {"database", "index"}:
                        members.add(str(descriptor.get("value") or binding["namespace"]))
                return {member for member in members if member}

            if not logical_members(telemetry).isdisjoint(logical_members(runtime_logs)):
                issues.append(
                    f"{target_name}: telemetry and runtime-logs namespaces must be disjoint"
                )
            if telemetry.get("backupRef") == runtime_logs.get("backupRef"):
                issues.append(
                    f"{target_name}: telemetry and runtime-logs backupRef must be distinct"
                )
            if telemetry.get("metricsRef") == runtime_logs.get("metricsRef"):
                issues.append(
                    f"{target_name}: telemetry and runtime-logs metricsRef must be distinct"
                )
            telemetry_ref = telemetry.get("secretRef")
            runtime_ref = runtime_logs.get("secretRef")
            credentials_required = (
                target_name in {"prod-hosted", "external"}
                or bool(telemetry_ref)
                or bool(runtime_ref)
            )
            if credentials_required and (
                not telemetry_ref or not runtime_ref or telemetry_ref == runtime_ref
            ):
                issues.append(
                    f"{target_name}: telemetry and runtime-logs credential refs must be "
                    "present and role-separated"
                )
            if credentials_required:
                for binding_key, binding in (
                    (telemetry_key, telemetry),
                    (runtime_key, runtime_logs),
                ):
                    api_key_refs = {
                        descriptor.get("secretRef") or binding.get("secretRef")
                        for descriptor in binding["inject"].values()
                        if descriptor.get("kind") == "api_key"
                    }
                    if (
                        api_key_refs != {binding.get("secretRef")}
                        or None in api_key_refs
                    ):
                        issues.append(
                            f"{target_name}: {binding_key} must inject only its owner API key"
                        )

    normalized_data_plane = {
        "resources": normalized_resources,
        "bindings": normalized_bindings,
    }
    return normalized_data_plane, issues


def validate_contract_graph_data_plane_bindings(
    contract_graph: Mapping[str, Any],
    data_plane: Mapping[str, Any],
    *,
    target_name: str = "target",
) -> list[str]:
    """Cross-check required object resources against deployment bindings.

    The normal slot is derived only from the resource identity's service and
    engine. Elasticsearch ``query_projection`` resources use the existing
    cross-service ``search.objects.writer`` provider seam; no object registry
    or per-environment object binding is introduced.

    DEC-032 具名 slot：当一个服务对同一引擎持有多个逻辑资源（隔离级别 / 保留策略确有
    不同，例如 product-ops 的 telemetry 与 runtime-logs 两个 Elasticsearch 落点）时，
    默认 ``<engine>`` slot 没有 binding，此时资源 localName（``_`` 归一为 ``-``）必须
    与该服务的一个同引擎 binding slot 精确同名；仍不匹配即缺 binding，fail closed。
    """

    issues: list[str] = []
    objects = contract_graph.get("objects")
    bindings = data_plane.get("bindings")
    if not isinstance(objects, list):
        return [f"{target_name}: ContractGraph.objects must be an array"]
    if not isinstance(bindings, Mapping):
        return [f"{target_name}: dataPlane.bindings must be a mapping"]

    candidates_by_slot: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = {}
    for binding_key, binding in sorted(bindings.items(), key=lambda item: str(item[0])):
        if not isinstance(binding, Mapping):
            continue
        service = str(binding.get("service") or "").strip()
        slot = str(binding.get("slot") or "").strip()
        candidates_by_slot.setdefault((service, slot), []).append(
            (str(binding_key), binding)
        )

    seen_identities: set[str] = set()
    required_search_writer_services: set[str] = set()
    for object_index, object_row in enumerate(objects):
        if not isinstance(object_row, Mapping):
            issues.append(
                f"{target_name}: ContractGraph.objects[{object_index}] must be a mapping"
            )
            continue
        resources = object_row.get("storageResources")
        if resources is None:
            continue
        if not isinstance(resources, list):
            issues.append(
                f"{target_name}: ContractGraph.objects[{object_index}].storageResources "
                "must be an array"
            )
            continue
        for resource_index, resource in enumerate(resources):
            label = (
                f"{target_name}: ContractGraph.objects[{object_index}]"
                f".storageResources[{resource_index}]"
            )
            if not isinstance(resource, Mapping):
                issues.append(f"{label} must be a mapping")
                continue
            required = resource.get("required")
            if type(required) is not bool:
                issues.append(f"{label}.required must be bool")
                continue
            if not required:
                continue
            identity = str(resource.get("identity") or "").strip()
            local_name = str(resource.get("localName") or "").strip()
            segments = identity.split("/")
            if len(segments) != 4 or not all(segments) or segments[-1] != local_name:
                issues.append(
                    f"{label}.identity must be derived as service/context/object/localName"
                )
                continue
            if identity in seen_identities:
                issues.append(f"{label}.identity {identity} is duplicated")
                continue
            seen_identities.add(identity)
            service = segments[0]
            engine = str(resource.get("engine") or "").strip()
            role = str(resource.get("role") or "").strip()
            if engine == "elasticsearch" and role == "query_projection":
                required_search_writer_services.add(service)
            default_slot = _DEFAULT_ENGINE_SLOTS.get(engine)
            if default_slot is None:
                issues.append(f"{label}.engine {engine!r} has no default slot")
                continue
            slot = (
                "search.objects.writer"
                if engine == "elasticsearch" and role == "query_projection"
                else default_slot
            )
            candidates = candidates_by_slot.get((service, slot), [])
            if not candidates and slot == default_slot:
                named_slot = local_name.replace("_", "-")
                named_candidates = candidates_by_slot.get((service, named_slot), [])
                if named_candidates:
                    slot = named_slot
                    candidates = named_candidates
            binding_identity = f"{service}.{slot}"
            if not candidates:
                issues.append(
                    f"{target_name}: required object resource {identity} is missing "
                    f"binding {binding_identity}"
                )
                continue
            if len(candidates) != 1:
                issues.append(
                    f"{target_name}: required object resource {identity} has ambiguous "
                    f"binding {binding_identity}: {[key for key, _ in candidates]}"
                )
                continue
            binding_key, binding = candidates[0]
            if str(binding.get("engine") or "").strip() != engine:
                issues.append(
                    f"{target_name}: required object resource {identity} engine {engine} "
                    f"does not match binding {binding_key} engine "
                    f"{str(binding.get('engine') or '').strip()}"
                )
            if binding.get("required") is not True:
                issues.append(
                    f"{target_name}: required object resource {identity} binding "
                    f"{binding_key} must declare required=true"
                )

    for binding_key, binding in sorted(bindings.items(), key=lambda item: str(item[0])):
        if not isinstance(binding, Mapping):
            continue
        service = str(binding.get("service") or "").strip()
        slot = str(binding.get("slot") or "").strip()
        if slot == "search.objects.writer" and service not in required_search_writer_services:
            issues.append(
                f"{target_name}: search writer binding {binding_key} has no required "
                "ContractGraph query_projection resource"
            )
    return issues


def _load_contract_graph_for_binding(repo_root: Path) -> Mapping[str, Any]:
    path = repo_root / CONTRACT_GRAPH_REF
    try:
        encoded = _safe_runtime_source(path)
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, DataPlaneBindingError) as exc:
        raise DataPlaneBindingError(
            f"canonical ContractGraph is unavailable or invalid: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise DataPlaneBindingError("canonical ContractGraph root must be a mapping")
    return payload


def canonical_data_plane_binding(
    target: Mapping[str, Any],
    *,
    target_name: str = "target",
) -> dict[str, Any]:
    """Return the strictly validated, redacted, deterministic binding artifact."""

    normalized, issues = _normalize_data_plane_binding(
        target,
        target_name=target_name,
        required=True,
    )
    if issues or normalized is None:
        raise DataPlaneBindingError("; ".join(issues))
    payload = {
        "schema": SCHEMA,
        **normalized,
    }
    return {
        **payload,
        "bindingDigest": _sha256(_canonical_json(payload)),
    }


def binding_digest(target: Mapping[str, Any], *, target_name: str = "target") -> str:
    return str(
        canonical_data_plane_binding(target, target_name=target_name)["bindingDigest"]
    )


def validate_canonical_data_plane_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a packaged canonical artifact and recompute its binding digest."""

    if not isinstance(payload, Mapping) or set(payload) != {
        "schema",
        "resources",
        "bindings",
        "bindingDigest",
    }:
        raise DataPlaneBindingError("canonical data-plane binding fields mismatch")
    if payload.get("schema") != SCHEMA:
        raise DataPlaneBindingError("canonical data-plane binding schema mismatch")
    if payload.get("resources") == {} and payload.get("bindings") == {}:
        identity = {"schema": SCHEMA, "resources": {}, "bindings": {}}
        expected = _sha256(_canonical_json(identity))
        if payload.get("bindingDigest") != expected:
            raise DataPlaneBindingError(
                "canonical data-plane binding digest drifted"
            )
        return {**identity, "bindingDigest": expected}
    rebuilt = canonical_data_plane_binding(
        {"dataPlane": {"resources": payload["resources"], "bindings": payload["bindings"]}},
        target_name="packaged dataPlane",
    )
    if payload.get("bindingDigest") != rebuilt["bindingDigest"]:
        raise DataPlaneBindingError("canonical data-plane binding digest drifted")
    return rebuilt


def _selected_physical_identity(resource: Mapping[str, Any], mode: str) -> str:
    identity = resource.get("physicalIdentity")
    if isinstance(identity, str):
        return identity
    if isinstance(identity, Mapping):
        selected = identity.get(mode)
        if isinstance(selected, str) and selected:
            return selected
    raise DataPlaneBindingError(
        f"data-plane resource has no explicit physicalIdentity for {mode}"
    )


def _secret_expression(reference: str) -> str:
    return "${" + reference + ":?}"


def _is_deployment_only_service(service: object) -> bool:
    return service == _DEPLOYMENT_CONTROL_SERVICE


def resolve_data_plane_environment(
    target: Mapping[str, Any],
    *,
    mode: str,
    target_name: str = "target",
) -> dict[str, Any]:
    """Resolve one validated target into service-scoped Compose environment values.

    The returned projection contains only local container coordinates, non-secret
    namespaces, and Compose references. It never resolves or accepts secret values.
    """

    if mode not in {"external", "local", "prevalidate"}:
        raise DataPlaneBindingError(f"unsupported data-plane resolution mode: {mode}")
    validation_name = "external" if mode == "external" else target_name
    canonical = canonical_data_plane_binding(target, target_name=validation_name)
    resources = canonical["resources"]
    environments: dict[str, dict[str, str]] = {}
    deployment_environments: dict[str, dict[str, str]] = {}
    for binding_key, binding in canonical["bindings"].items():
        resource = resources[binding["resource"]]
        if not binding["inject"]:
            if _is_deployment_only_service(binding.get("service")):
                reference = binding.get("secretRef")
                if mode == "external" and binding["required"] and not reference:
                    raise DataPlaneBindingError(
                        f"{binding_key} requires an external secretRef"
                    )
                endpoint_reference = reference
                if binding["engine"] == "elasticsearch":
                    endpoint_references = {
                        descriptor.get("secretRef")
                        or peer.get("secretRef")
                        for peer in canonical["bindings"].values()
                        if peer["resource"] == binding["resource"]
                        for descriptor in peer["inject"].values()
                        if descriptor["kind"] == "endpoint"
                    }
                    if len(endpoint_references) == 1:
                        endpoint_reference = next(iter(endpoint_references))
                target_environment = deployment_environments.setdefault(
                    binding_key, {}
                )
                if mode == "external":
                    target_environment["endpoint"] = (
                        _secret_expression(endpoint_reference)
                        if endpoint_reference
                        else ""
                    )
                    target_environment["credential"] = (
                        _secret_expression(reference) if reference else ""
                    )
                elif binding["engine"] == "elasticsearch":
                    target_environment["endpoint"] = (
                        f"http://{_selected_physical_identity(resource, mode)}:9200"
                    )
                    target_environment["credential"] = "local-development-admin"
            continue
        service_environment = environments.setdefault(binding["service"], {})
        for env_key, descriptor in binding["inject"].items():
            kind = descriptor["kind"]
            reference = descriptor.get("secretRef") or binding.get("secretRef")
            value: str | None
            if kind == "literal":
                value = descriptor["value"]
            elif kind in {"database", "index"}:
                value = descriptor.get("value") or binding["namespace"]
            elif kind == "api_key":
                if mode == "external" and not reference and binding["required"]:
                    raise DataPlaneBindingError(
                        f"{binding_key}.{env_key} requires an external secretRef"
                    )
                value = _secret_expression(reference) if reference else None
            elif mode == "external":
                if not reference:
                    if binding["required"]:
                        raise DataPlaneBindingError(
                            f"{binding_key}.{env_key} requires an external secretRef"
                        )
                    value = None
                else:
                    value = _secret_expression(reference)
            else:
                identity = _selected_physical_identity(resource, mode)
                engine = binding["engine"]
                if kind == "dsn" and engine == "postgres":
                    value = (
                        f"postgres://quwoquan:quwoquan@{identity}:5432/"
                        f"{binding['namespace']}?sslmode=disable"
                    )
                elif kind == "uri" and engine == "mongodb":
                    value = f"mongodb://{identity}:27017/?directConnection=true"
                elif kind == "addr" and engine == "redis":
                    value = f"{identity}:6379"
                elif kind == "endpoint" and engine == "elasticsearch":
                    value = f"http://{identity}:9200"
                elif kind == "endpoint" and engine == "object_storage":
                    value = f"http://{identity}:9000"
                else:  # Validation owns the kind/engine closed set.
                    raise DataPlaneBindingError(
                        f"{binding_key}.{env_key} cannot resolve {engine}/{kind}"
                    )
            if value is None:
                continue
            service_environment[env_key] = value
            if kind == "addr" and env_key.endswith("_ADDR"):
                root = env_key[:-5]
                service_environment[root + "_MODE"] = "standalone"
                service_environment[root + "_TLS"] = "false"
    return {
        "bindingDigest": canonical["bindingDigest"],
        "environment": environments,
        "deploymentEnvironment": deployment_environments,
    }


DATA_PLANE_BINDING_PACKAGE_REF = PurePosixPath(
    "packages/runtime-shared/data-plane-binding.json"
)
_REQUIRED_DATA_PLANE_TARGETS = frozenset(
    {"alpha-local", "beta-local", "gamma-local", "prod-hosted"}
)


def _package_sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _safe_runtime_source(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise DataPlaneBindingError(
            f"environment runtime source is unavailable: {path}"
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise DataPlaneBindingError(
            f"environment runtime source must be a regular file: {path}"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DataPlaneBindingError(
            f"environment runtime source is unreadable: {path}"
        ) from exc


def _write_binding_artifact(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise DataPlaneBindingError("data-plane binding package already exists")
    try:
        parent = path.parent
        metadata = parent.lstat()
        if parent.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise DataPlaneBindingError("runtime-shared package root is unsafe")
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short data-plane binding write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise DataPlaneBindingError(
            f"data-plane binding artifact cannot be created safely: {path}"
        ) from exc


def materialize_data_plane_binding_package(
    environment: str,
    target: str,
    runtime_shared_root: Path,
    *,
    repo_root: Path,
) -> dict[str, str]:
    """Seal the target binding from an immutable package source capsule."""

    runtime_source = (
        repo_root / "quwoquan_ops" / "environments" / environment / "runtime.yaml"
    )
    try:
        runtime = yaml.safe_load(_safe_runtime_source(runtime_source).decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise DataPlaneBindingError(
            f"environment runtime source is invalid: {runtime_source}"
        ) from exc
    if not isinstance(runtime, Mapping) or runtime.get("environment") != environment:
        raise DataPlaneBindingError("environment runtime identity mismatch")
    targets = runtime.get("targets")
    runtime_target = targets.get(target) if isinstance(targets, Mapping) else None
    if not isinstance(runtime_target, Mapping):
        raise DataPlaneBindingError(
            f"environment runtime target is unavailable: {environment}/{target}"
        )
    required = target in _REQUIRED_DATA_PLANE_TARGETS
    normalized, issues = _normalize_data_plane_binding(
        runtime_target,
        target_name=target,
        required=required,
    )
    if issues:
        raise DataPlaneBindingError("; ".join(issues))
    if normalized is not None and required:
        graph_issues = validate_contract_graph_data_plane_bindings(
            _load_contract_graph_for_binding(repo_root),
            normalized,
            target_name=target,
        )
        if graph_issues:
            raise DataPlaneBindingError("; ".join(graph_issues))
    if normalized is None:
        identity = {"schema": SCHEMA, "resources": {}, "bindings": {}}
        canonical = {**identity, "bindingDigest": _sha256(_canonical_json(identity))}
    else:
        canonical = canonical_data_plane_binding(runtime_target, target_name=target)
    encoded = (
        json.dumps(canonical, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    artifact = runtime_shared_root / DATA_PLANE_BINDING_PACKAGE_REF.name
    _write_binding_artifact(artifact, encoded)
    return {
        "ref": DATA_PLANE_BINDING_PACKAGE_REF.as_posix(),
        "digest": _package_sha256(encoded),
        "bindingDigest": str(canonical["bindingDigest"]),
    }
