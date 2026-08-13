"""metadata 对象/切片枚举、Router 源码与页面 owner/parent 图校验。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import (
    APP,
    ROOT,
    ROUTER_DIR,
    SERVICES,
    _load_yaml,
    _nonempty_string,
    _snake_case,
    _string_list,
)


def _metadata_objects_and_slices(
    errors: list[str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], set[str]]:
    objects: dict[str, str] = {}
    slices: dict[str, str] = {}
    object_domains: dict[str, str] = {}
    service_domains: set[str] = set()
    for domain_file in sorted(SERVICES.glob("*/contracts/domain.yaml")):
        contracts_root = domain_file.parent
        try:
            domain_doc = _load_yaml(domain_file)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"无法读取服务 domain 定义 {domain_file.relative_to(ROOT)}: {exc}")
            continue
        domain = domain_doc.get("domain")
        if not _nonempty_string(domain):
            errors.append(f"{domain_file.relative_to(ROOT)}: domain 缺失")
            continue
        domain = str(domain).strip()
        service_domains.add(domain)
        definition_files = sorted(contracts_root.glob("*/*/object.yaml"))
        for definition in definition_files:
            relative_parts = definition.relative_to(contracts_root).parts
            if any(part.startswith("_") for part in relative_parts):
                continue
            try:
                data = _load_yaml(definition)
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"无法读取业务对象定义 {definition.relative_to(ROOT)}: {exc}")
                continue
            raw_name = definition.parent.name
            object_id = f"{domain}.{_snake_case(raw_name)}"
            if object_id in objects:
                errors.append(
                    f"业务 object_id 重复推导: {object_id} "
                    f"({objects[object_id]}, {definition.relative_to(ROOT)})"
                )
                continue
            rel = definition.relative_to(ROOT).as_posix()
            objects[object_id] = rel
            object_domains[object_id] = domain
            slices[object_id] = rel
            projection_dir = definition.parent / "projections"
            if projection_dir.is_dir():
                for projection in sorted(projection_dir.glob("*.yaml")):
                    ref = f"{object_id}.projection.{projection.stem}"
                    slices[ref] = projection.relative_to(ROOT).as_posix()
    return objects, slices, object_domains, service_domains


def _router_sources() -> tuple[str, dict[str, str]]:
    sources: dict[str, str] = {}
    for path in sorted(ROUTER_DIR.glob("app_router*.dart")):
        rel = path.relative_to(APP).as_posix()
        sources[rel] = path.read_text(encoding="utf-8")
    return "\n".join(sources.values()), sources


def _generated_route_paths(source: str) -> dict[str, str]:
    routes: dict[str, str] = {}
    for match in re.finditer(
        r"static const String ([A-Za-z][A-Za-z0-9]*) = '([^']*)';",
        source,
    ):
        identifier, path = match.groups()
        if identifier.endswith("Segment"):
            continue
        route_id = (
            identifier[: -len("PathTemplate")]
            if identifier.endswith("PathTemplate")
            else identifier
        )
        routes[route_id] = path
    return routes


def _validate_parent_graph(
    pages_by_id: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    adjacency: dict[str, list[str]] = {}
    for page_id, page in pages_by_id.items():
        parents: list[str] = []
        parent = page.get("parent_page_id")
        if _nonempty_string(parent):
            parents.append(str(parent).strip())
        additional = page.get("additional_parent_page_ids", [])
        if additional != []:
            parsed = _string_list(additional)
            if parsed is None:
                errors.append(f"{page_id}: additional_parent_page_ids 必须是非空字符串列表")
            else:
                parents.extend(parsed)
        for candidate in parents:
            if candidate not in pages_by_id:
                errors.append(f"{page_id}: parent 不存在: {candidate}")
            if candidate == page_id:
                errors.append(f"{page_id}: parent 不得指向自身")
        adjacency[page_id] = parents

    state: dict[str, int] = {}

    def visit(node: str, chain: list[str]) -> None:
        current = state.get(node, 0)
        if current == 1:
            cycle = " -> ".join(chain + [node])
            errors.append(f"页面 parent 成环: {cycle}")
            return
        if current == 2:
            return
        state[node] = 1
        for parent in adjacency.get(node, []):
            if parent in pages_by_id:
                visit(parent, chain + [node])
        state[node] = 2

    for page_id in pages_by_id:
        visit(page_id, [])


def _effective_route_ids(
    page_id: str,
    pages_by_id: dict[str, dict[str, Any]],
    cache: dict[str, set[str]],
    visiting: set[str],
) -> set[str]:
    if page_id in cache:
        return cache[page_id]
    if page_id in visiting:
        return set()
    visiting.add(page_id)
    page = pages_by_id[page_id]
    out: set[str] = set()
    route_id = page.get("route_id")
    if _nonempty_string(route_id):
        out.add(str(route_id).strip())
    for route in page.get("additional_route_ids", []) or []:
        if _nonempty_string(route):
            out.add(str(route).strip())
    parent_ids: list[str] = []
    parent = page.get("parent_page_id")
    if _nonempty_string(parent):
        parent_ids.append(str(parent).strip())
    for parent_id in page.get("additional_parent_page_ids", []) or []:
        if _nonempty_string(parent_id):
            parent_ids.append(str(parent_id).strip())
    for parent_id in parent_ids:
        if parent_id in pages_by_id:
            out.update(
                _effective_route_ids(parent_id, pages_by_id, cache, visiting)
            )
    visiting.remove(page_id)
    cache[page_id] = out
    return out


def _source_experience_owners(source_path: object) -> set[str]:
    if not _nonempty_string(source_path):
        return set()
    parts = Path(str(source_path)).parts
    if len(parts) >= 3 and parts[:2] == ("lib", "ui"):
        return {parts[2]}
    return set()


def _validate_owner_bindings(
    pages_by_id: dict[str, dict[str, Any]],
    object_domains: dict[str, str],
    service_domains: set[str],
    errors: list[str],
) -> None:
    """让页面 experience/data owner 可由本地契约、页面树或 UI 源路径反推。"""

    for page_id, page in pages_by_id.items():
        data_owners = _string_list(page.get("data_owners"))
        if data_owners is None:
            continue
        if len(data_owners) != len(set(data_owners)):
            errors.append(f"{page_id}: data_owners 不得重复")
        for owner in data_owners:
            if owner != "app" and owner not in service_domains:
                errors.append(
                    f"{page_id}: data_owner {owner!r} 无服务 contracts/domain.yaml 佐证"
                )

        object_ids = _string_list(page.get("object_ids"), allow_empty=True) or []
        required_data_owners = {
            object_domains[object_id]
            for object_id in object_ids
            if object_id in object_domains
        }
        missing = sorted(required_data_owners - set(data_owners))
        if missing:
            errors.append(
                f"{page_id}: object_ids 所属服务未列入 data_owners: {missing}"
            )

        experience_owner = page.get("experience_owner")
        if not _nonempty_string(experience_owner):
            continue
        parent_owners = {
            str(pages_by_id[parent].get("experience_owner")).strip()
            for parent in (
                page.get("parent_page_id"),
                *(page.get("additional_parent_page_ids") or []),
            )
            if _nonempty_string(parent) and parent in pages_by_id
            and _nonempty_string(pages_by_id[parent].get("experience_owner"))
        }
        derivable_owners = (
            {"app"}
            | service_domains
            | _source_experience_owners(page.get("source_path"))
            | parent_owners
        )
        # Canonical object pages no longer carry the experience namespace in
        # their physical path. The page id owns that namespace, so its first
        # segment is the stable, metadata-local derivation source.
        derivable_owners.add(page_id.split(".", 1)[0])
        if str(experience_owner).strip() not in derivable_owners:
            errors.append(
                f"{page_id}: experience_owner {experience_owner!r} 无 UI 路径、父页面或服务领域佐证"
            )
