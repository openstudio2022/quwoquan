"""从对象 operations.yaml 与环境 config 派生 registry / bindings / manifest。

原单文件逐字搬运。可被测试 patch 的符号（``SERVICES_ROOT`` /
``_service_roots``）在消费点一律经薄入口模块命名空间
``_entry.X`` 属性访问，保持与拆分前单文件相同的 mock.patch 语义。
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

import quwoquan_ops.cli.lib.external_provider_governance as _entry

from .constants import ENVIRONMENTS, ROOT, is_local_substitute_adapter


def _source_root(source_root: Path | None) -> Path:
    root = ROOT if source_root is None else Path(source_root)
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"external Provider source_root is not a directory: {root}")
    return resolved


def _services_root(source_root: Path | None) -> Path:
    if source_root is None:
        return _entry.SERVICES_ROOT
    return _source_root(source_root) / "quwoquan_service" / "services"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return payload


def _service_roots(source_root: Path | None = None) -> list[Path]:
    """Return checked-in service roots, excluding generated output directories."""
    services_root = _services_root(source_root)
    return sorted(
        path
        for path in services_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


@lru_cache(maxsize=32)
def load_environment_bindings(
    environment: str,
    *,
    source_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """只读取请求环境，供 candidate-scoped compiler 使用。"""
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unsupported Provider environment: {environment}")
    service_roots = (
        _entry._service_roots()
        if source_root is None
        else _service_roots(source_root)
    )
    scope: dict[str, dict[str, Any]] = {}
    for service_root in service_roots:
        config_path = service_root / "environments" / environment / "config.yaml"
        config = _load_yaml(config_path)
        bindings = config.get("externalBindings") or {}
        if not isinstance(bindings, Mapping):
            raise ValueError(f"{config_path}: externalBindings must be a mapping")
        scope[service_root.name] = {
            str(capability_id): binding for capability_id, binding in bindings.items()
        }
    return scope


@lru_cache(maxsize=8)
def load_bindings(
    path: Path | None = None,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    if path is not None:
        raise ValueError("global external provider binding files are forbidden")
    environments = {
        env: load_environment_bindings(env, source_root=source_root)
        for env in ENVIRONMENTS
    }
    return {
        "schema": "service-local-external-provider-bindings",
        "environments": environments,
    }


def _operation_sources(
    source_root: Path | None = None,
) -> list[tuple[Path, str, str, str, dict[str, Any]]]:
    sources: list[tuple[Path, str, str, str, dict[str, Any]]] = []
    service_roots = (
        _entry._service_roots()
        if source_root is None
        else _service_roots(source_root)
    )
    for service_root in service_roots:
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


def _descriptor_output(
    service_id: str,
    object_root: Path,
    *,
    source_root: Path | None = None,
) -> Path:
    service_root = _services_root(source_root) / service_id
    context, object_name = object_root.parts[-2:]
    return service_root / "generated" / context / object_name / "external_provider_bindings.g.go"


def _find_adapter_source(
    adapter_id: str,
    *,
    source_root: Path | None = None,
) -> Path | None:
    root = _source_root(source_root)
    services_root = _services_root(source_root)
    roots = [
        services_root,
        root / "quwoquan_service" / "control-plane",
        root / "quwoquan_service" / "runtime",
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
    if source.is_relative_to(services_root):
        relative = source.relative_to(services_root)
        service_root = services_root / relative.parts[0]
        service_relative = Path(*relative.parts[1:])
        if (
            len(service_relative.parts) >= 4
            and service_relative.parts[0] == "internal"
        ):
            return service_root.joinpath(*service_relative.parts[:3])
        # Adapters assembled from cmd/ and internal/ packages must bind the
        # digest to the whole service source closure, not only an ID constant.
        return service_root
    runtime_root = root / "quwoquan_service" / "runtime"
    if source.is_relative_to(runtime_root):
        relative = source.relative_to(runtime_root)
        return runtime_root / relative.parts[0]
    control_plane_root = root / "quwoquan_service" / "control-plane"
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
    source_root: Path | None = None,
) -> dict[str, Any] | None:
    if owner is None:
        return None
    root = _source_root(source_root)
    service_id, object_root = owner
    return {
        "root_id": f"{domain}.{context}.{object_name}",
        "descriptor_owner": service_id,
        "descriptor_output": _descriptor_output(
            service_id,
            object_root,
            source_root=source_root,
        )
        .relative_to(root)
        .as_posix(),
        "role": role,
        "required_scenes": list(dependency.get("scenes") or []),
    }


@lru_cache(maxsize=8)
def load_registry(
    path: Path | None = None,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Return a compatibility-shaped, fully derived view for existing runners."""
    if path is not None:
        raise ValueError("manual external provider registries are forbidden")
    root = _source_root(source_root)
    capabilities: list[dict[str, Any]] = []
    by_capability: dict[str, dict[str, Any]] = {}
    unresolved_uses: dict[str, list[dict[str, Any]]] = {}
    for operations_path, domain, context, object_name, document in _operation_sources(
        source_root
    ):
        dependencies = document.get("externalDependencies") or []
        if not isinstance(dependencies, list):
            continue
        owner = _source_owner(operations_path, context, object_name)
        for dependency in dependencies:
            if not isinstance(dependency, Mapping):
                continue
            capability_id = str(dependency.get("capability") or "")
            role = _dependency_role(dependency)
            root_record = _root_record(
                owner=owner,
                domain=domain,
                context=context,
                object_name=object_name,
                role=role,
                dependency=dependency,
                source_root=source_root,
            )
            declaration = {
                "port": dependency.get("port"),
                "operations": list(dependency.get("operations") or []),
                "scenes": list(dependency.get("scenes") or []),
                "source": operations_path.relative_to(root).as_posix(),
                "root": root_record,
                "role": role,
            }
            if role == "use":
                if capability_id in by_capability:
                    by_capability[capability_id]["consumer_uses"].append(declaration)
                    if root_record is not None:
                        by_capability[capability_id]["binding_roots"].append(root_record)
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
                        "binding_roots": [root_record] if root_record is not None else [],
                        "consumer_uses": [],
                        "source": operations_path.relative_to(root).as_posix(),
                        "_invalid_role": role,
                    }
                )
                continue
            if capability_id in by_capability:
                # Duplicates remain visible to registry_issues without aliases.
                existing = dict(dependency)
                existing["capability_id"] = capability_id
                existing["_duplicate_owner"] = f"{domain}.{context}.{object_name}"
                existing["binding_roots"] = (
                    [root_record] if root_record is not None else []
                )
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
                "binding_roots": [root_record] if root_record is not None else [],
                "consumer_uses": [],
                "source": operations_path.relative_to(root).as_posix(),
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
        source = _find_adapter_source(adapter_id, source_root=source_root)
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
                    source.relative_to(root).as_posix() if source is not None else ""
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


@lru_cache(maxsize=8)
def load_conformance_manifest(
    path: Path | None = None,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Derive runner conventions; no test-path or assertion registry is read."""
    if path is not None:
        raise ValueError("manual conformance manifests are forbidden")
    registry = load_registry(source_root=source_root)
    profiles = sorted(
        {
            str(item.get("conformance_profile"))
            for item in registry["capabilities"]
            if item.get("conformance_profile")
        }
    )
    sources = {
        "local_contract": "quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence__contract__local_contract_test.py",
        "api_integration": "quwoquan_ops/tests/acceptance/api_integration/test_external_provider_governance__api_integration_test.py",
        "user_acceptance": "quwoquan_ops/tests/acceptance/user_acceptance/test_external_provider_governance__user_acceptance_test.py",
    }
    return {
        "schema": "derived-provider-conformance",
        "profiles": {profile: dict(sources) for profile in profiles},
        "common_assertion_ids": [],
        "profile_assertion_ids": {
            profile: [f"{profile}.contract"] for profile in profiles
        },
    }
