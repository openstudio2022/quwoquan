"""从 canonical contracts 派生 App 可达能力闭包。

覆盖集合是以下入口的并集，而不是手工中央清单：
- ui_surfaces.yaml 的 operation_ids
- ContractGraph 中带 clientContract 的 operation
- persisted GraphQL 的 canonicalOperationId
- realtime_event_catalog 的 App 消费事件
- PlatformCapabilities 的实际 native flag
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

_GRAPHQL_CANONICAL_RE = re.compile(
    r"canonicalOperationId:\s*'([^']+)'"
)
_PLATFORM_FLAG_RE = re.compile(
    r"required this\.([A-Za-z_][A-Za-z0-9_]*)",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_ui_surface_local_ids(root: Path | None = None) -> tuple[str, ...]:
    path = (root or repository_root()) / (
        "quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids: list[str] = []
    seen: set[str] = set()
    for surface in payload.get("surfaces") or []:
        for local_id in surface.get("operation_ids") or []:
            if local_id not in seen:
                seen.add(local_id)
                ids.append(str(local_id))
    return tuple(ids)


def load_contract_graph(root: Path | None = None) -> Mapping[str, Any]:
    path = (root or repository_root()) / "quwoquan_service/generated/contract_graph.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_client_contract_operations(
    root: Path | None = None,
) -> tuple[dict[str, Any], ...]:
    graph = load_contract_graph(root)
    return tuple(
        operation
        for operation in graph.get("operations") or []
        if isinstance(operation, dict) and operation.get("clientContract")
    )


def load_graphql_canonical_ids(root: Path | None = None) -> tuple[str, ...]:
    path = (root or repository_root()) / (
        "quwoquan_app/lib/runtime/transport/graphql_read/generated/"
        "persisted_graphql_queries.g.dart"
    )
    text = path.read_text(encoding="utf-8")
    search = path.with_name('search_page.g.dart').read_text(encoding='utf-8')
    return tuple(dict.fromkeys(_GRAPHQL_CANONICAL_RE.findall(text + search)))


def load_realtime_events(root: Path | None = None) -> tuple[dict[str, Any], ...]:
    path = (root or repository_root()) / (
        "quwoquan_service/contracts/metadata/_shared/realtime_event_catalog.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    events = payload.get("events") or []
    return tuple(event for event in events if isinstance(event, dict))


def load_platform_capability_flags(root: Path | None = None) -> tuple[str, ...]:
    path = (root or repository_root()) / (
        "quwoquan_app/lib/runtime/platform/platform_capabilities.dart"
    )
    text = path.read_text(encoding="utf-8")
    constructor = text.split("const PlatformCapabilities({", 1)[1].split("});", 1)[0]
    return tuple(_PLATFORM_FLAG_RE.findall(constructor))


def derive_app_reachable_capability_catalog(
    root: Path | None = None,
) -> dict[str, Any]:
    repo = root or repository_root()
    surface_local_ids = load_ui_surface_local_ids(repo)
    client_ops = load_client_contract_operations(repo)
    graphql_ids = load_graphql_canonical_ids(repo)
    realtime_events = load_realtime_events(repo)
    platform_flags = load_platform_capability_flags(repo)

    by_local_id: dict[str, dict[str, Any]] = {}
    ambiguous: dict[str, list[str]] = {}
    for operation in client_ops:
        local_id = str(operation["localId"])
        previous = by_local_id.get(local_id)
        if previous is not None and previous['id'] != operation['id']:
            ambiguous[local_id] = sorted(set(ambiguous.get(local_id, [str(previous['id'])]) + [str(operation['id'])]))
        else:
            by_local_id[local_id] = operation
    if ambiguous:
        raise ValueError(f'APP.CAPABILITY.local_id_ambiguous: {ambiguous}')

    missing_surface_ops = tuple(
        local_id for local_id in surface_local_ids if local_id not in by_local_id
    )
    surface_canonical_ids = tuple(
        str(by_local_id[local_id]["id"])
        for local_id in surface_local_ids
        if local_id in by_local_id
    )
    client_canonical_ids = tuple(str(operation["id"]) for operation in client_ops)
    kinds: dict[str, int] = {}
    domains: dict[str, int] = {}
    objects: dict[str, int] = {}
    for operation in client_ops:
        kind = str(operation.get("kind") or "")
        domain = str(operation.get("domain") or "")
        object_id = str(operation.get("objectId") or "")
        kinds[kind] = kinds.get(kind, 0) + 1
        domains[domain] = domains.get(domain, 0) + 1
        objects[object_id] = objects.get(object_id, 0) + 1

    return {
        "surfaceLocalOperationCount": len(surface_local_ids),
        "clientContractOperationCount": len(client_ops),
        "surfaceCanonicalOperationIds": surface_canonical_ids,
        "clientCanonicalOperationIds": client_canonical_ids,
        "missingSurfaceLocalIds": missing_surface_ops,
        "graphqlCanonicalOperationIds": graphql_ids,
        "realtimeEventRefs": tuple(
            str(event.get("event_ref") or event.get("wire_type") or "")
            for event in realtime_events
        ),
        # 能力位和事件只是声明，不等同 native 绑定/事件消费实现。
        "platformCapabilityFlags": platform_flags,
        "declaredPlatformCapabilityFlags": platform_flags,
        "nativeGatewayBindings": (),
        "nativeBindingEvidenceStatus": "unverified",
        "startupOperationBindings": (),
        "startupBindingEvidenceStatus": "unverified",
        "graphqlDescriptorCanonicalOperationIds": tuple(
            item for item in graphql_ids
            if item != 'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery'
        ),
        "graphqlTransportCanonicalOperationIds": tuple(
            item for item in graphql_ids
            if item == 'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery'
        ),
        "declaredRealtimeEventRefs": tuple(
            str(event.get('event_ref') or event.get('wire_type') or '')
            for event in realtime_events
        ),
        "bindingCompleteness": "GATE_BLOCK",
        "kindCounts": dict(sorted(kinds.items())),
        "domainCounts": dict(sorted(domains.items())),
        "objectCounts": dict(sorted(objects.items())),
        "objectCount": len(objects),
    }
