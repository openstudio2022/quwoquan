#!/usr/bin/env python3
"""阻断页面到对象、路由、Surface 与 Query Slice 的契约漂移。

触发范围：页面扫描集、共享路由/Surface、生产 Router 或页面对象契约发生变化。
阻断条件：页面漏登、引用/路径漂移、不可达路由、弱类型展示、无效对象/父级等。
修复方式：回到 ``metadata/_shared/page_object_contract.yaml`` 及其真实装配证据修正，
不得在质量矩阵或 typing inventory 维护第二套对象绑定。脚本已接入 ``make
verify-app-page-horizontal-quality`` 与仓库 App gate。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

from page_disk_scan_paths import matrix_disk_scan_paths


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
SERVICES = ROOT / "quwoquan_service" / "services"
CONTRACT = METADATA / "_shared" / "page_object_contract.yaml"
ROUTES = METADATA / "_shared" / "app_routes.yaml"
SURFACES = METADATA / "_shared" / "ui_surfaces.yaml"
ROUTER_DIR = APP / "lib" / "app" / "navigation"
GENERATED_ROUTES = ROUTER_DIR / "generated" / "app_route_paths.g.dart"
GENERATED_SURFACES = ROUTER_DIR / "generated" / "app_ui_surfaces.g.dart"
PLATFORM_CAPABILITIES = APP / "lib" / "core" / "platform" / "platform_capabilities.dart"

PAGE_KINDS = frozenset({"routed", "embedded", "shell", "component", "helper"})
AUTH_REQUIREMENTS = frozenset({"public", "optional", "required", "inherited"})
PAGE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SOURCE_PATH_RE = re.compile(r"^lib/.+\.dart$")
TYPE_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
LOCAL_SLICE_RE = re.compile(r"^local\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
BANNED_PRESENTATION_RE = re.compile(r"(?:\bMap\b|\bdynamic\b|\bGeneric\b)", re.I)


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return data


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, allow_empty: bool = False) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not allow_empty and not value:
        return None
    if any(not _nonempty_string(item) for item in value):
        return None
    return [str(item).strip() for item in value]


def _snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()


def _dart_library_text(source: Path, errors: list[str], page_id: str) -> str:
    """返回 canonical library 与其直接 Dart part 的源码。

    页面可以通过 ``part`` 拆分，但 page_object_contract 的 ``source_path``
    仍应指向唯一 library 入口，而不是把实现分片登记为第二个页面。这里按 Dart
    library 语义验证 entry widget，同时拒绝缺失或越出 App 根目录的 part。
    """

    source_text = source.read_text(encoding="utf-8", errors="ignore")
    chunks = [source_text]
    for match in re.finditer(
        r"^\s*part\s+['\"]([^'\"]+)['\"]\s*;",
        source_text,
        re.MULTILINE,
    ):
        part_uri = match.group(1)
        part_path = (source.parent / part_uri).resolve()
        try:
            part_path.relative_to(APP.resolve())
        except ValueError:
            errors.append(f"{page_id}: Dart part 越出 App 根目录: {part_uri}")
            continue
        if not part_path.is_file():
            errors.append(f"{page_id}: Dart part 不存在: {part_uri}")
            continue
        chunks.append(part_path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


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


def _all_dart_type_tokens() -> set[str]:
    tokens: set[str] = set()
    # 页面可直接消费 App 类型或 pure contracts package 的 generated/typed
    # presentation；后者仍属于 production App 编译图，不是 Mock/测试旁路。
    for root in (
        APP / "lib",
        APP / "packages" / "quwoquan_cloud_contracts" / "lib",
    ):
        for path in root.rglob("*.dart"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            tokens.update(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", text))
    return tokens


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
        if str(experience_owner).strip() not in derivable_owners:
            errors.append(
                f"{page_id}: experience_owner {experience_owner!r} 无 UI 路径、父页面或服务领域佐证"
            )


def main() -> int:
    if yaml is None:
        print("page_object_contract: BLOCK: PyYAML required", file=sys.stderr)
        return 2
    try:
        contract = _load_yaml(CONTRACT)
        routes_doc = _load_yaml(ROUTES)
        surfaces_doc = _load_yaml(SURFACES)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"page_object_contract: BLOCK: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    if contract.get("schema") != "app_page_object_contract":
        errors.append(
            "page_object_contract.yaml: schema 必须为 app_page_object_contract"
        )
    if contract.get("contract_id") != "app_page_object_contract":
        errors.append(
            "page_object_contract.yaml: contract_id 必须为 app_page_object_contract"
        )
    if contract.get("source_path_root") != "quwoquan_app":
        errors.append("page_object_contract.yaml: source_path_root 必须为 quwoquan_app")
    raw_pages = contract.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        print("page_object_contract: FAIL: pages 必须是非空列表", file=sys.stderr)
        return 1

    pages_by_id: dict[str, dict[str, Any]] = {}
    pages_by_source: dict[str, dict[str, Any]] = {}
    for index, raw_page in enumerate(raw_pages):
        if not isinstance(raw_page, dict):
            errors.append(f"pages[{index}] 必须是 mapping")
            continue
        page_id = raw_page.get("page_id")
        source = raw_page.get("source_path")
        if not _nonempty_string(page_id) or not PAGE_ID_RE.fullmatch(str(page_id)):
            errors.append(f"pages[{index}]: page_id 非法: {page_id!r}")
            continue
        page_id = str(page_id).strip()
        if page_id in pages_by_id:
            errors.append(f"page_id 重复: {page_id}")
            continue
        if not _nonempty_string(source) or not SOURCE_PATH_RE.fullmatch(str(source)):
            errors.append(f"{page_id}: source_path 非法: {source!r}")
            continue
        source = str(source).strip()
        if source in pages_by_source:
            errors.append(
                f"source_path 重复: {source} "
                f"({pages_by_source[source].get('page_id')}, {page_id})"
            )
            continue
        pages_by_id[page_id] = raw_page
        pages_by_source[source] = raw_page
        if not (APP / source).is_file():
            errors.append(f"{page_id}: source_path 不存在: {source}")

    disk_paths = set(matrix_disk_scan_paths(ROOT))
    contract_paths = set(pages_by_source)
    for source in sorted(disk_paths - contract_paths):
        errors.append(f"磁盘页面未登记 canonical contract: {source}")
    for source in sorted(contract_paths - disk_paths):
        errors.append(f"canonical source 不在页面扫描集: {source}")

    raw_routes = routes_doc.get("routes")
    raw_surfaces = surfaces_doc.get("surfaces")
    if not isinstance(raw_routes, list):
        errors.append("app_routes.yaml: routes 必须是列表")
        raw_routes = []
    if not isinstance(raw_surfaces, list):
        errors.append("ui_surfaces.yaml: surfaces 必须是列表")
        raw_surfaces = []

    routes: dict[str, str] = {}
    route_paths: dict[str, str] = {}
    for route in raw_routes:
        if not isinstance(route, dict):
            errors.append("app_routes.yaml: route 必须是 mapping")
            continue
        route_id = route.get("id")
        path = route.get("path")
        if not _nonempty_string(route_id) or not _nonempty_string(path):
            errors.append(f"app_routes.yaml: route id/path 缺失: {route!r}")
            continue
        route_id = str(route_id).strip()
        path = str(path).strip()
        if route_id in routes:
            errors.append(f"app_routes.yaml: route_id 重复: {route_id}")
        if path in route_paths:
            errors.append(
                f"app_routes.yaml: path 重复: {path} ({route_paths[path]}, {route_id})"
            )
        routes[route_id] = path
        route_paths[path] = route_id

    surfaces: dict[str, dict[str, Any]] = {}
    for surface in raw_surfaces:
        if not isinstance(surface, dict):
            errors.append("ui_surfaces.yaml: surface 必须是 mapping")
            continue
        surface_id = surface.get("id")
        route_id = surface.get("route_id")
        path = surface.get("path_template")
        if not all(_nonempty_string(value) for value in (surface_id, route_id, path)):
            errors.append(f"ui_surfaces.yaml: id/route_id/path_template 缺失: {surface!r}")
            continue
        surface_id = str(surface_id).strip()
        route_id = str(route_id).strip()
        path = str(path).strip()
        if surface_id in surfaces:
            errors.append(f"ui_surfaces.yaml: surface id 重复: {surface_id}")
        surfaces[surface_id] = surface
        if route_id not in routes:
            errors.append(f"surface {surface_id}: route_id 不存在: {route_id}")
        elif routes[route_id] != path:
            errors.append(
                f"surface {surface_id}: path_template {path!r} "
                f"与 route {route_id} 的 {routes[route_id]!r} 不一致"
            )

    (
        metadata_objects,
        valid_query_slices,
        object_domains,
        service_domains,
    ) = _metadata_objects_and_slices(errors)
    dart_tokens = _all_dart_type_tokens()
    capability_text = (
        PLATFORM_CAPABILITIES.read_text(encoding="utf-8")
        if PLATFORM_CAPABILITIES.is_file()
        else ""
    )
    valid_capabilities = set(
        re.findall(r"\bfinal\s+bool\s+([A-Za-z][A-Za-z0-9_]*)\s*;", capability_text)
    )
    router_text, router_sources = _router_sources()
    generated_routes_text = (
        GENERATED_ROUTES.read_text(encoding="utf-8")
        if GENERATED_ROUTES.is_file()
        else ""
    )
    generated_route_paths = _generated_route_paths(generated_routes_text)
    generated_surfaces_text = (
        GENERATED_SURFACES.read_text(encoding="utf-8")
        if GENERATED_SURFACES.is_file()
        else ""
    )

    if not GENERATED_ROUTES.is_file():
        errors.append(
            f"generated route 文件缺失: {GENERATED_ROUTES.relative_to(ROOT)}"
        )
    else:
        for route_id in sorted(set(routes) - set(generated_route_paths)):
            errors.append(f"generated AppRoutePaths 缺 route: {route_id}")
        for route_id in sorted(set(generated_route_paths) - set(routes)):
            errors.append(f"generated AppRoutePaths 存在 metadata 外 route: {route_id}")
        for route_id in sorted(set(routes) & set(generated_route_paths)):
            if generated_route_paths[route_id] != routes[route_id]:
                errors.append(
                    f"generated AppRoutePaths route/path 不一致 {route_id}: "
                    f"metadata={routes[route_id]!r}, "
                    f"generated={generated_route_paths[route_id]!r}"
                )

    _validate_parent_graph(pages_by_id, errors)
    _validate_owner_bindings(
        pages_by_id,
        object_domains,
        service_domains,
        errors,
    )
    effective_route_cache: dict[str, set[str]] = {}
    telemetry_namespaces: dict[str, str] = {}

    for page_id, page in pages_by_id.items():
        source = str(page.get("source_path"))
        kind = page.get("page_kind")
        if kind not in PAGE_KINDS:
            errors.append(f"{page_id}: page_kind 非法: {kind!r}")
            continue

        parent = page.get("parent_page_id")
        if kind in {"embedded", "component", "helper"} and not _nonempty_string(parent):
            errors.append(f"{page_id}: {kind} 必须声明 parent_page_id")
        if kind == "helper":
            helper_text = (APP / source).read_text(encoding="utf-8", errors="ignore")
            if "part of " not in helper_text and not re.search(
                r"^\s*export\s+", helper_text, re.MULTILINE
            ):
                errors.append(f"{page_id}: helper 必须是真实 part/export 文件")

        experience_owner = page.get("experience_owner")
        if not _nonempty_string(experience_owner):
            errors.append(f"{page_id}: experience_owner 必填")
        data_owners = _string_list(page.get("data_owners"))
        if data_owners is None:
            errors.append(f"{page_id}: data_owners 必须是非空字符串列表")

        object_ids = _string_list(page.get("object_ids"), allow_empty=True)
        if object_ids is None:
            errors.append(f"{page_id}: object_ids 必须是字符串列表")
            object_ids = []
        elif len(object_ids) != len(set(object_ids)):
            errors.append(f"{page_id}: object_ids 不得重复")
        for object_id in object_ids:
            if object_id not in metadata_objects:
                errors.append(f"{page_id}: object_id 无 object.yaml 定义: {object_id}")

        query_slices = page.get("query_slices")
        typed = page.get("typed_presentation")
        if query_slices == "none" or typed == "none":
            if query_slices != "none" or typed != "none":
                errors.append(
                    f"{page_id}: query_slices/typed_presentation 必须同时为 none"
                )
            if not _nonempty_string(page.get("data_contract_reason")):
                errors.append(f"{page_id}: none 数据契约必须填写 data_contract_reason")
        else:
            parsed_slices = _string_list(query_slices)
            parsed_types = _string_list(typed)
            if parsed_slices is None:
                errors.append(f"{page_id}: 数据页 query_slices 必须是非空具名列表")
                parsed_slices = []
            elif len(parsed_slices) != len(set(parsed_slices)):
                errors.append(f"{page_id}: query_slices 不得重复")
            if parsed_types is None:
                errors.append(f"{page_id}: 数据页 typed_presentation 必须是非空列表")
                parsed_types = []
            elif len(parsed_types) != len(set(parsed_types)):
                errors.append(f"{page_id}: typed_presentation 不得重复")
            for query_slice in parsed_slices:
                if BANNED_PRESENTATION_RE.search(query_slice):
                    errors.append(f"{page_id}: query_slice 禁止弱类型/Generic: {query_slice}")
                    continue
                if LOCAL_SLICE_RE.fullmatch(query_slice):
                    continue
                if query_slice not in valid_query_slices:
                    errors.append(f"{page_id}: Query Slice 引用不存在: {query_slice}")
                    continue
                owning_object = query_slice
                if ".projection." in query_slice:
                    owning_object = query_slice.split(".projection.", 1)[0]
                if owning_object not in object_ids:
                    errors.append(
                        f"{page_id}: Query Slice {query_slice} 的对象 "
                        f"{owning_object} 未列入 object_ids"
                    )
            for type_name in parsed_types:
                if BANNED_PRESENTATION_RE.search(type_name):
                    errors.append(f"{page_id}: typed_presentation 禁止 Map/dynamic/Generic: {type_name}")
                elif not TYPE_NAME_RE.fullmatch(type_name):
                    errors.append(f"{page_id}: typed_presentation 必须是具名强类型: {type_name}")
                elif type_name not in dart_tokens:
                    errors.append(
                        f"{page_id}: typed_presentation 在 App/Contract Dart 中不存在: {type_name}"
                    )

        auth = page.get("auth_requirement")
        if auth not in AUTH_REQUIREMENTS:
            errors.append(f"{page_id}: auth_requirement 非法或缺失: {auth!r}")
        if auth == "inherited" and not _nonempty_string(parent):
            errors.append(f"{page_id}: inherited auth 必须声明 parent_page_id")

        capabilities = page.get("capability_requirements")
        if not isinstance(capabilities, dict):
            errors.append(f"{page_id}: capability_requirements 必须是 mapping")
        else:
            for key in ("all_of", "any_of"):
                values = _string_list(capabilities.get(key), allow_empty=True)
                if values is None:
                    errors.append(
                        f"{page_id}: capability_requirements.{key} 必须是字符串列表"
                    )
                    continue
                for capability in values:
                    if capability not in valid_capabilities:
                        errors.append(
                            f"{page_id}: capability 未在 PlatformCapabilities 定义: "
                            f"{capability}"
                        )

        telemetry = page.get("telemetry_descriptor")
        if not isinstance(telemetry, dict) or not telemetry:
            errors.append(f"{page_id}: telemetry_descriptor 必填且必须是 mapping")
        elif _nonempty_string(telemetry.get("inherit_from")):
            inherited_from = str(telemetry["inherit_from"]).strip()
            valid_parents = {str(parent).strip()} if _nonempty_string(parent) else set()
            valid_parents.update(page.get("additional_parent_page_ids", []) or [])
            if inherited_from not in valid_parents:
                errors.append(
                    f"{page_id}: telemetry inherit_from 必须指向声明的 parent: "
                    f"{inherited_from}"
                )
        else:
            namespace = telemetry.get("event_namespace")
            lifecycle = _string_list(telemetry.get("lifecycle"))
            if not _nonempty_string(namespace) or lifecycle is None:
                errors.append(
                    f"{page_id}: telemetry_descriptor 须含 event_namespace 与 lifecycle"
                )
            elif namespace in telemetry_namespaces:
                errors.append(
                    f"{page_id}: telemetry event_namespace 重复 "
                    f"{namespace}（{telemetry_namespaces[str(namespace)]}）"
                )
            else:
                telemetry_namespaces[str(namespace)] = page_id

        surface_ids = _string_list(page.get("surface_ids"))
        if surface_ids is None:
            errors.append(f"{page_id}: surface_ids 必须是非空字符串列表")
            surface_ids = []
        elif len(surface_ids) != len(set(surface_ids)):
            errors.append(f"{page_id}: surface_ids 不得重复")
        effective_routes = _effective_route_ids(
            page_id, pages_by_id, effective_route_cache, set()
        )
        page_surface_routes: set[str] = set()
        for surface_id in surface_ids:
            surface = surfaces.get(surface_id)
            if surface is None:
                errors.append(f"{page_id}: surface 引用不存在: {surface_id}")
                continue
            surface_route = str(surface.get("route_id", "")).strip()
            page_surface_routes.add(surface_route)
            if surface_route not in effective_routes:
                errors.append(
                    f"{page_id}: surface {surface_id} 的 route {surface_route} "
                    f"不在页面/parent route 集 {sorted(effective_routes)}"
                )

        own_route_ids: list[str] = []
        route_id = page.get("route_id")
        if _nonempty_string(route_id):
            own_route_ids.append(str(route_id).strip())
        additional_routes = page.get("additional_route_ids", [])
        if additional_routes != []:
            parsed_routes = _string_list(additional_routes)
            if parsed_routes is None:
                errors.append(f"{page_id}: additional_route_ids 必须是非空字符串列表")
            else:
                own_route_ids.extend(parsed_routes)
        if kind == "routed" and not own_route_ids:
            errors.append(f"{page_id}: routed 页面必须声明 route_id")
        if kind in {"embedded", "component", "helper"} and own_route_ids:
            errors.append(f"{page_id}: {kind} 不得声明独立 route_id，应通过 parent 装配")
        for own_route in own_route_ids:
            if own_route not in routes:
                errors.append(f"{page_id}: route_id 引用不存在: {own_route}")
            if own_route not in page_surface_routes:
                errors.append(
                    f"{page_id}: route {own_route} 没有对应 Surface 覆盖"
                )

        if own_route_ids and kind in {"routed", "shell"}:
            entry_widget = page.get("entry_widget")
            evidence_paths = _string_list(page.get("route_registration_evidence"))
            if not _nonempty_string(entry_widget):
                errors.append(f"{page_id}: routed/shell 页面必须声明 entry_widget")
            if evidence_paths is None:
                errors.append(
                    f"{page_id}: routed/shell 页面必须声明 route_registration_evidence"
                )
                evidence_paths = []
            evidence_text = ""
            for evidence in evidence_paths:
                evidence_file = APP / evidence
                if not evidence_file.is_file():
                    errors.append(f"{page_id}: route evidence 不存在: {evidence}")
                    continue
                evidence_text += evidence_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
            if not any(
                evidence.startswith("lib/app/navigation/")
                for evidence in evidence_paths
            ):
                errors.append(
                    f"{page_id}: route evidence 至少包含一个生产 navigation 文件"
                )
            if _nonempty_string(entry_widget) and str(entry_widget) not in evidence_text:
                errors.append(
                    f"{page_id}: route evidence 未装配 entry_widget {entry_widget}"
                )
            for own_route in own_route_ids:
                route_token = re.compile(
                    rf"\bAppRoutePaths\.{re.escape(own_route)}"
                    r"(?:PathTemplate|Segment)?\b"
                )
                if not route_token.search(router_text):
                    errors.append(
                        f"{page_id}: production app_router 未注册 route {own_route}"
                    )
                if not route_token.search(evidence_text):
                    errors.append(
                        f"{page_id}: route evidence 未注册 route {own_route}"
                    )
                route_path = routes.get(own_route)
                generated_path = generated_route_paths.get(own_route)
                if route_path and generated_path != route_path:
                    errors.append(
                        f"{page_id}: generated AppRoutePaths route/path 不一致 "
                        f"{own_route}: metadata={route_path!r}, generated={generated_path!r}"
                    )
        elif kind in {"embedded", "component"} or (
            kind == "shell" and _nonempty_string(parent)
        ):
            entry_widget = page.get("entry_widget")
            evidence_paths = _string_list(page.get("mount_evidence"))
            if not _nonempty_string(entry_widget):
                errors.append(f"{page_id}: {kind} 必须声明 entry_widget")
            if evidence_paths is None:
                errors.append(f"{page_id}: {kind} 必须声明 mount_evidence")
                evidence_paths = []
            evidence_text = ""
            for evidence in evidence_paths:
                if evidence == source:
                    errors.append(
                        f"{page_id}: mount_evidence 不得以 source_path 自证装配"
                    )
                evidence_file = APP / evidence
                if not evidence_file.is_file():
                    errors.append(f"{page_id}: mount evidence 不存在: {evidence}")
                    continue
                evidence_text += evidence_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
            if _nonempty_string(entry_widget) and str(entry_widget) not in evidence_text:
                errors.append(
                    f"{page_id}: mount evidence 未消费 entry_widget {entry_widget}"
                )

        source_text = _dart_library_text(APP / source, errors, page_id)
        entry_widget = page.get("entry_widget")
        if _nonempty_string(entry_widget) and not re.search(
            rf"\bclass\s+{re.escape(str(entry_widget))}\b", source_text
        ):
            errors.append(
                f"{page_id}: source_path 未定义 entry_widget {entry_widget}"
            )

    if not GENERATED_SURFACES.is_file():
        errors.append(f"generated surface 文件缺失: {GENERATED_SURFACES.relative_to(ROOT)}")
    else:
        generated_surface_ids = set(
            re.findall(
                r"static const AppUiSurface ([A-Za-z][A-Za-z0-9]*) = "
                r"AppUiSurface\(",
                generated_surfaces_text,
            )
        )
        for surface_id in sorted(set(surfaces) - generated_surface_ids):
            errors.append(f"generated AppUiSurfaces 缺 surface: {surface_id}")
        for surface_id in sorted(generated_surface_ids - set(surfaces)):
            errors.append(
                f"generated AppUiSurfaces 存在 metadata 外 surface: {surface_id}"
            )
        for surface_id, surface in surfaces.items():
            block_match = re.search(
                rf"static const AppUiSurface {re.escape(surface_id)} = "
                r"AppUiSurface\((.*?)\n  \);",
                generated_surfaces_text,
                re.DOTALL,
            )
            if not block_match:
                continue
            block = block_match.group(1)
            expected_route = str(surface.get("route_id", "")).strip()
            expected_path = str(surface.get("path_template", "")).strip()
            if f"routeId: {expected_route!r}" not in block:
                errors.append(
                    f"generated surface {surface_id} routeId 与 metadata 不一致"
                )
            if f"pathTemplate: {expected_path!r}" not in block:
                errors.append(
                    f"generated surface {surface_id} pathTemplate 与 metadata 不一致"
                )
            if f"    {surface_id},\n" not in generated_surfaces_text:
                errors.append(
                    f"generated surface {surface_id} 未进入 AppUiSurfaces.all"
                )
            if (
                f"    {surface_id!r}: {surface_id},\n"
                not in generated_surfaces_text
            ):
                errors.append(
                    f"generated surface {surface_id} 未进入 AppUiSurfaces.byId"
                )

    if errors:
        print("page_object_contract: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "page_object_contract: OK "
        f"({len(pages_by_id)} pages, {len(routes)} routes, "
        f"{len(surfaces)} surfaces, {len(metadata_objects)} objects)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
