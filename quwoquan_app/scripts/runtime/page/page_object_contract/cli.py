"""页面对象契约门禁主流程（原 ``main``，逐字搬移）。"""

from __future__ import annotations

import re
import sys
from typing import Any

from .context import (
    APP,
    AUTH_REQUIREMENTS,
    BANNED_PRESENTATION_RE,
    CONTRACT,
    GENERATED_ROUTES,
    GENERATED_SURFACES,
    LOCAL_SLICE_RE,
    PAGE_ID_RE,
    PAGE_KINDS,
    PLATFORM_CAPABILITIES,
    ROOT,
    ROUTER_EVIDENCE_PREFIXES,
    ROUTES,
    SOURCE_PATH_RE,
    SURFACES,
    TYPE_NAME_RE,
    _load_yaml,
    _nonempty_string,
    _string_list,
    yaml,
)
from .dart_scan import (
    _all_dart_type_tokens,
    _dart_library_text,
    _mounts_entry_widget,
)
from .metadata_sources import (
    _effective_route_ids,
    _generated_route_paths,
    _metadata_objects_and_slices,
    _router_sources,
    _validate_owner_bindings,
    _validate_parent_graph,
)
from .mount_rules import (
    _declared_parent_mount_closures,
    _is_route_less_root_shell,
    _page_source_ownership_errors,
    _parent_mount_evidence_errors,
    _root_shell_mount_errors,
    _root_shell_surface_owner_errors,
    _surface_route_membership_error,
)

from page_disk_scan_paths import matrix_disk_scan_paths  # same runtime/page dir


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
    source_owner_ids: dict[str, list[str]] = {}
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
        source_owner_ids.setdefault(source, []).append(page_id)
        if source in pages_by_source:
            continue
        pages_by_id[page_id] = raw_page
        pages_by_source[source] = raw_page
        if not (APP / source).is_file():
            errors.append(f"{page_id}: source_path 不存在: {source}")

    disk_paths = set(matrix_disk_scan_paths(ROOT))
    errors.extend(
        _page_source_ownership_errors(
            disk_paths=disk_paths,
            source_owner_ids=source_owner_ids,
        )
    )

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
        has_route_less_shell_shape = (
            kind == "shell"
            and not _nonempty_string(parent)
            and not own_route_ids
        )
        is_route_less_root_shell = _is_route_less_root_shell(
            kind=kind,
            parent=parent,
            own_route_ids=own_route_ids,
            source=source,
            experience_owner=experience_owner,
        )
        if has_route_less_shell_shape and not is_route_less_root_shell:
            errors.append(
                f"{page_id}: route-less root shell 仅允许 experience_owner=app "
                "且 source_path 位于 lib/runtime/shell/**"
            )
        if is_route_less_root_shell:
            for forbidden_key in (
                "parent_page_id",
                "additional_parent_page_ids",
                "route_id",
                "additional_route_ids",
                "route_registration_evidence",
            ):
                if forbidden_key in page:
                    errors.append(
                        f"{page_id}: route-less root shell 不得声明 {forbidden_key}"
                    )

        surface_ids = _string_list(page.get("surface_ids"))
        if surface_ids is None:
            errors.append(f"{page_id}: surface_ids 必须是非空字符串列表")
            surface_ids = []
        elif len(surface_ids) != len(set(surface_ids)):
            errors.append(f"{page_id}: surface_ids 不得重复")
        if is_route_less_root_shell:
            errors.extend(
                _root_shell_surface_owner_errors(
                    page_id,
                    surface_ids=surface_ids,
                    surfaces=surfaces,
                    experience_owner=experience_owner,
                )
            )
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
            # Root recovery can paint before Router exists and therefore
            # consumes a surface identity without owning that surface's route.
            # _surface_route_membership_error never adds it to effective_routes.
            route_error = _surface_route_membership_error(
                page_id,
                surface_id=surface_id,
                surface_route=surface_route,
                effective_routes=effective_routes,
                is_route_less_root_shell=is_route_less_root_shell,
            )
            if route_error is not None:
                errors.append(route_error)

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
                evidence.startswith(ROUTER_EVIDENCE_PREFIXES)
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
        elif kind in {"embedded", "component", "shell"}:
            entry_widget = page.get("entry_widget")
            evidence_paths = _string_list(page.get("mount_evidence"))
            if not _nonempty_string(entry_widget):
                errors.append(f"{page_id}: {kind} 必须声明 entry_widget")
            if evidence_paths is None:
                errors.append(f"{page_id}: {kind} 必须声明 mount_evidence")
                evidence_paths = []
            elif len(evidence_paths) != len(set(evidence_paths)):
                errors.append(f"{page_id}: mount_evidence 不得重复")

            parent_closures = _declared_parent_mount_closures(
                page,
                pages_by_id,
            )
            for evidence in evidence_paths:
                if evidence == source:
                    errors.append(
                        f"{page_id}: mount_evidence 不得以 source_path 自证装配"
                    )
                evidence_file = APP / evidence
                if not evidence_file.is_file():
                    errors.append(f"{page_id}: mount evidence 不存在: {evidence}")
                    continue
                evidence_text = evidence_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
                if _nonempty_string(entry_widget) and not _mounts_entry_widget(
                    evidence_text,
                    str(entry_widget),
                ):
                    errors.append(
                        f"{page_id}: mount evidence {evidence} "
                        f"未构造或显式继承 entry_widget {entry_widget}"
                    )
            errors.extend(
                _parent_mount_evidence_errors(
                    page_id,
                    parent_closures=parent_closures,
                    evidence_paths=evidence_paths,
                )
            )

            if is_route_less_root_shell and _nonempty_string(entry_widget):
                errors.extend(
                    _root_shell_mount_errors(
                        page_id,
                        entry_widget=str(entry_widget),
                        source=source,
                        evidence_paths=evidence_paths,
                    )
                )
            elif not parent_closures:
                errors.append(
                    f"{page_id}: 非 root {kind} 没有可验证的 parent mount closure"
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
