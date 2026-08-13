"""parent/mount evidence、root shell 与页面归属的判定规则。"""

from __future__ import annotations

from typing import Any

from .context import _nonempty_string, _string_list
from .dart_scan import _direct_app_dart_closure, _direct_constructor_sites


def _declared_parent_mount_closures(
    page: dict[str, Any],
    pages_by_id: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    parent_ids: list[str] = []
    parent = page.get("parent_page_id")
    if _nonempty_string(parent):
        parent_ids.append(str(parent).strip())
    for candidate in page.get("additional_parent_page_ids", []) or []:
        if _nonempty_string(candidate):
            parent_ids.append(str(candidate).strip())
    closures: dict[str, set[str]] = {}
    for parent_id in parent_ids:
        parent_page = pages_by_id.get(parent_id)
        if parent_page is None:
            continue
        seeds: list[str] = []
        source = parent_page.get("source_path")
        if _nonempty_string(source):
            seeds.append(str(source).strip())
        # A routed parent may inject an embedded child through a typed DI slot
        # instead of importing the child from its presentation source.  The
        # route-registration evidence is already an authored, fail-closed page
        # binding, so accept only its direct library/import/part closure; never
        # walk arbitrary transitive imports or scan the whole runtime/di tree.
        route_evidence = _string_list(
            parent_page.get("route_registration_evidence")
        )
        if route_evidence is not None:
            seeds.extend(route_evidence)
        closure: set[str] = set()
        for seed in seeds:
            closure.update(_direct_app_dart_closure(seed))
        closures[parent_id] = closure
    return closures


def _is_route_less_root_shell(
    *,
    kind: object,
    parent: object,
    own_route_ids: list[str],
    source: object,
    experience_owner: object,
) -> bool:
    return (
        kind == "shell"
        and not _nonempty_string(parent)
        and not own_route_ids
        and _nonempty_string(source)
        and str(source).startswith("lib/runtime/shell/")
        and experience_owner == "app"
    )


def _parent_mount_evidence_errors(
    page_id: str,
    *,
    parent_closures: dict[str, set[str]],
    evidence_paths: list[str],
) -> list[str]:
    errors: list[str] = []
    for evidence in evidence_paths:
        if parent_closures and not any(
            evidence in closure for closure in parent_closures.values()
        ):
            errors.append(
                f"{page_id}: mount evidence {evidence} 不属于任何声明 parent "
                "的 canonical source/route registration direct import/part closure"
            )
    for parent_id, closure in parent_closures.items():
        if not any(evidence in closure for evidence in evidence_paths):
            errors.append(f"{page_id}: parent {parent_id} 没有独立 mount_evidence")
    return errors


def _root_shell_mount_errors(
    page_id: str,
    *,
    entry_widget: str,
    source: str,
    evidence_paths: list[str],
) -> list[str]:
    actual_constructor_sites = _direct_constructor_sites(
        entry_widget,
        source=source,
    )
    declared_sites = set(evidence_paths)
    errors: list[str] = []
    missing_sites = sorted(actual_constructor_sites - declared_sites)
    extra_sites = sorted(declared_sites - actual_constructor_sites)
    if missing_sites:
        errors.append(
            f"{page_id}: root shell mount_evidence 漏掉生产 direct "
            f"constructor sites: {missing_sites}"
        )
    if extra_sites:
        errors.append(
            f"{page_id}: root shell mount_evidence 含非 constructor "
            f"sites: {extra_sites}"
        )
    return errors


def _root_shell_surface_owner_errors(
    page_id: str,
    *,
    surface_ids: list[str],
    surfaces: dict[str, dict[str, Any]],
    experience_owner: object,
) -> list[str]:
    errors: list[str] = []
    for surface_id in surface_ids:
        surface = surfaces.get(surface_id)
        if surface is None:
            continue
        surface_owner = str(surface.get("owner", "")).strip()
        if surface_owner != str(experience_owner).strip():
            errors.append(
                f"{page_id}: root shell surface {surface_id} owner "
                f"{surface_owner!r} 与 experience_owner {experience_owner!r} 不一致"
            )
    return errors


def _surface_route_membership_error(
    page_id: str,
    *,
    surface_id: str,
    surface_route: str,
    effective_routes: set[str],
    is_route_less_root_shell: bool,
) -> str | None:
    if is_route_less_root_shell or surface_route in effective_routes:
        return None
    return (
        f"{page_id}: surface {surface_id} 的 route {surface_route} "
        f"不在页面/parent route 集 {sorted(effective_routes)}"
    )


def _page_source_ownership_errors(
    *,
    disk_paths: set[str],
    source_owner_ids: dict[str, list[str]],
) -> list[str]:
    """Compare the live disk page set with canonical contract ownership."""

    errors: list[str] = []
    contract_paths = set(source_owner_ids)
    for source in sorted(disk_paths - contract_paths):
        errors.append(f"磁盘页面未登记 canonical contract: {source}")
    for source, owner_ids in sorted(source_owner_ids.items()):
        if len(owner_ids) > 1:
            errors.append(
                f"source_path 重复: {source} ({', '.join(owner_ids)})"
            )
    for source in sorted(contract_paths - disk_paths):
        errors.append(f"canonical source 不在页面扫描集: {source}")
    return errors
