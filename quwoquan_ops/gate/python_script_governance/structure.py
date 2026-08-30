"""App/Service/Ops/Data 目录结构规则。"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Sequence

from quwoquan_ops.gate import object_path_map

from .bootstrap import DEFAULT_ROOT
from .constants import (
    APP_CLOUD_LAYOUT_SEGMENTS,
    APP_CONCERN_ROOTS,
    APP_RUNTIME_CONCERNS,
    OPS_ALLOWED_TOP_LEVEL,
    SERVICE_CONCERN_ROOTS,
    SERVICE_RUNTIME_CONCERNS,
)
from .inventory import script_files
from .models import Issue, Warning, relative_path
from .references import read_text


def app_structure_issues(root: Path, scripts: Sequence[Path]) -> list[Issue]:
    issues: list[Issue] = []
    scripts_root = root / "quwoquan_app/scripts"
    app_service_root = (
        root
        / "quwoquan_app/lib"
        / object_path_map.APP_SERVICE_ROOT_SEGMENT
    )
    service_names = {
        path.name for path in app_service_root.iterdir() if path.is_dir()
    } if app_service_root.is_dir() else set()

    for path in scripts:
        local = path.relative_to(scripts_root)
        if len(local.parts) == 1:
            if local.name != "cli.py":
                issues.append(
                    Issue(
                        code="APP.SCRIPT_ROOT_FILE",
                        path=relative_path(root, path),
                        message="only cli.py may live directly under app/scripts",
                    )
                )
            continue

        top = local.parts[0]
        if top == "service":
            issues.append(
                Issue(
                    code="APP.SERVICE_WRAPPER_FORBIDDEN",
                    path=relative_path(root, path),
                    message=(
                        "scripts/service/ wrapper is forbidden; "
                        "use scripts/<snake>_service/ as L1"
                    ),
                )
            )
            continue

        if any(segment in APP_CLOUD_LAYOUT_SEGMENTS for segment in local.parts):
            issues.append(
                Issue(
                    code="APP.CLOUD_LAYOUT_COPY_FORBIDDEN",
                    path=relative_path(root, path),
                    message=(
                        "App scripts must not copy cloud config/deploy/"
                        "environments layout; use env/ or gamma/ concerns"
                    ),
                )
            )
            continue

        if top not in APP_CONCERN_ROOTS and top not in service_names:
            issues.append(
                Issue(
                    code="APP.SCRIPT_ROOT_UNSUPPORTED",
                    path=relative_path(root, path),
                    message=(
                        f"{top} is neither a canonical App service segment "
                        "nor an approved cross-cutting concern"
                    ),
                )
            )
            continue

        if top == "runtime":
            if len(local.parts) == 2 and local.name not in {"__init__.py"}:
                issues.append(
                    Issue(
                        code="APP.RUNTIME_FLAT_SCRIPT",
                        path=relative_path(root, path),
                        message="runtime scripts must declare a concern directory",
                    )
                )
            elif (
                len(local.parts) >= 3
                and local.parts[1] not in APP_RUNTIME_CONCERNS
            ):
                issues.append(
                    Issue(
                        code="APP.RUNTIME_CONCERN_UNKNOWN",
                        path=relative_path(root, path),
                        message=f"unknown runtime concern {local.parts[1]}",
                    )
                )
            continue

        if top not in service_names:
            continue
        if len(local.parts) >= 3:
            context_root = app_service_root / top / local.parts[1]
            if not context_root.is_dir():
                issues.append(
                    Issue(
                        code="APP.CONTEXT_OWNER_MISSING",
                        path=relative_path(root, path),
                        message=f"missing App context owner {context_root.relative_to(root)}",
                    )
                )
                continue
        if len(local.parts) >= 4:
            object_root = app_service_root / top / local.parts[1] / local.parts[2]
            if not object_root.is_dir():
                issues.append(
                    Issue(
                        code="APP.OBJECT_OWNER_MISSING",
                        path=relative_path(root, path),
                        message=f"missing App object owner {object_root.relative_to(root)}",
                    )
                )
    return issues


def service_structure_issues(
    root: Path,
    scripts: Sequence[Path],
) -> list[Issue]:
    issues: list[Issue] = []
    scripts_root = root / "quwoquan_service/scripts"
    services_root = root / "quwoquan_service/services"
    service_names = {
        path.name for path in services_root.iterdir() if path.is_dir()
    } if services_root.is_dir() else set()

    for path in scripts:
        local = path.relative_to(scripts_root)
        if len(local.parts) == 1:
            issues.append(
                Issue(
                    code="SERVICE.SCRIPT_ROOT_FILE",
                    path=relative_path(root, path),
                    message="service scripts must declare a concern or service owner",
                )
            )
            continue
        top = local.parts[0]
        if top not in SERVICE_CONCERN_ROOTS and top not in service_names:
            issues.append(
                Issue(
                    code="SERVICE.SCRIPT_ROOT_UNSUPPORTED",
                    path=relative_path(root, path),
                    message=(
                        f"{top} is neither a canonical kebab service nor a "
                        "service-script concern"
                    ),
                )
            )
            continue
        if top == "contracts" and path.name.startswith("verify_"):
            issues.append(
                Issue(
                    code="SERVICE.CONTRACTS_VERIFY_MIXED",
                    path=relative_path(root, path),
                    message="contracts contains build/sync/generate only; verifier belongs in verify",
                )
            )
        if top == "runtime":
            if len(local.parts) == 2 and local.name not in {"__init__.py"}:
                issues.append(
                    Issue(
                        code="SERVICE.RUNTIME_FLAT_SCRIPT",
                        path=relative_path(root, path),
                        message="runtime scripts must declare a concern directory",
                    )
                )
            elif (
                len(local.parts) >= 3
                and local.parts[1] not in SERVICE_RUNTIME_CONCERNS
            ):
                issues.append(
                    Issue(
                        code="SERVICE.RUNTIME_CONCERN_UNKNOWN",
                        path=relative_path(root, path),
                        message=f"unknown runtime concern {local.parts[1]}",
                    )
                )
            continue
        if top not in service_names:
            continue
        # Service-local tools/ is a canonical manual-tool pocket; it does not
        # require a matching internal/<context> owner.
        if len(local.parts) >= 2 and local.parts[1] == "tools":
            continue
        internal_root = services_root / top / "internal"
        if len(local.parts) >= 3:
            context_root = internal_root / local.parts[1]
            if not context_root.is_dir():
                issues.append(
                    Issue(
                        code="SERVICE.CONTEXT_OWNER_MISSING",
                        path=relative_path(root, path),
                        message=f"missing service context owner {context_root.relative_to(root)}",
                    )
                )
                continue
        if len(local.parts) >= 4:
            object_root = internal_root / local.parts[1] / local.parts[2]
            if not object_root.is_dir():
                issues.append(
                    Issue(
                        code="SERVICE.OBJECT_OWNER_MISSING",
                        path=relative_path(root, path),
                        message=f"missing service object owner {object_root.relative_to(root)}",
                    )
                )
    return issues


def service_verify_single_owner_warnings(
    root: Path,
    scripts: Sequence[Path],
) -> list[Warning]:
    """Warn when ``scripts/verify/`` hosts a single-service scan root."""

    warnings: list[Warning] = []
    scripts_root = root / "quwoquan_service/scripts"
    services_root = root / "quwoquan_service/services"
    if not scripts_root.is_dir() or not services_root.is_dir():
        return warnings
    service_names = sorted(
        path.name for path in services_root.iterdir() if path.is_dir()
    )
    if not service_names:
        return warnings
    alt = "|".join(re.escape(name) for name in service_names)
    joined_pat = re.compile(
        rf"(?:quwoquan_service/)?services/({alt})(?:/|\b)"
    )
    split_pat = re.compile(
        rf"""["']services["']\s*/\s*["']({alt})["']"""
    )
    multi_walk_pat = re.compile(
        r"(services.*iterdir|for\s+\w+\s+in\s+.*services|"
        r"SERVICES_ROOT|service_names\s*=|services_root)",
        re.IGNORECASE,
    )
    other_package_pat = re.compile(
        r"quwoquan_app|quwoquan_ops|quwoquan_data"
    )
    runtime_tools_pat = re.compile(
        r"""["']/runtime/|/tools/|["']runtime["']\s*/"""
    )

    for path in scripts:
        try:
            local = path.relative_to(scripts_root)
        except ValueError:
            continue
        if len(local.parts) < 2 or local.parts[0] != "verify":
            continue
        if path.suffix != ".py":
            continue
        text = read_text(path)
        hits = set(joined_pat.findall(text)) | set(split_pat.findall(text))
        if len(hits) != 1:
            continue
        if multi_walk_pat.search(text):
            continue
        if other_package_pat.search(text):
            continue
        if runtime_tools_pat.search(text):
            continue
        owner = next(iter(hits))
        warnings.append(
            Warning(
                code="SERVICE.VERIFY_SINGLE_SERVICE_OWNER",
                path=relative_path(root, path),
                message=(
                    f"scan root only targets {owner}; move to "
                    f"scripts/{owner}/ (verify/ is for multi-service gates)"
                ),
            )
        )
    return warnings


def ops_structure_issues(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    ops_root = root / "quwoquan_ops"
    if not ops_root.is_dir():
        return issues
    for child in sorted(ops_root.iterdir()):
        if not child.is_dir() or child.name in OPS_ALLOWED_TOP_LEVEL:
            continue
        if script_files(child):
            issues.append(
                Issue(
                    code="OPS.SCRIPT_ROOT_UNSUPPORTED",
                    path=relative_path(root, child),
                    message="Ops Python belongs to concern roots, not a business script island",
                )
            )
    return issues


def data_architecture_issues(root: Path) -> list[Issue]:
    if root.resolve() != DEFAULT_ROOT.resolve():
        return []
    module_path = (
        root / "quwoquan_data/scripts/verify/verify_script_architecture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_quwoquan_data_script_architecture",
        module_path,
    )
    if spec is None or spec.loader is None:
        return [
            Issue(
                code="DATA.SCRIPT_ARCHITECTURE_UNAVAILABLE",
                path=relative_path(root, module_path),
                message="unable to load canonical Data script architecture gate",
            )
        ]
    module = importlib.util.module_from_spec(spec)
    scripts_root = str(module_path.parents[1])
    inserted = scripts_root not in sys.path
    if inserted:
        sys.path.insert(0, scripts_root)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            try:
                sys.path.remove(scripts_root)
            except ValueError:
                pass
    return [
        Issue(
            code="DATA.SCRIPT_ARCHITECTURE",
            path="quwoquan_data/scripts",
            message=str(message),
        )
        for message in module.script_architecture_issues()
    ]
