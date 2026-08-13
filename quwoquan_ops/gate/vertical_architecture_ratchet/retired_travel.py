"""已退役 travel-service 残影与五类调用方依赖扫描。"""

from __future__ import annotations

import os
from pathlib import Path

from .constants import (
    APP_CONTRACT_LOCK,
    APP_GENERATED_MANIFEST,
    APP_TRAVEL_DEPENDENCY_RE,
    CODE_SUFFIXES,
    CONTRACT_GRAPH,
    OUTPUT_ROOT,
    RETIRED_APP_ARTIFACTS,
    RETIRED_APP_OUTPUT_RE,
    RETIRED_OUTPUT_NAME_RE,
    SERVICE_TRAVEL_DEPENDENCY_RE,
    TEXT_SUFFIXES,
    TRAVEL_DOMAIN,
)
from .fsscan import (
    _iter_files,
    _load_json_mapping,
    _load_yaml_mapping,
    _relative,
    _scan_identifier_hits,
)
from .models import HitSummary


def _is_retired_graph_identity(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return (
        normalized == TRAVEL_DOMAIN
        or normalized.startswith(f"{TRAVEL_DOMAIN}.")
        or normalized == "travel-service"
        or normalized.startswith("travel-service/")
    )


def _is_retired_graph_source_path(value: object) -> bool:
    normalized = str(value or "").strip().replace("\\", "/").lstrip("./").lower()
    return (
        normalized == TRAVEL_DOMAIN
        or normalized.startswith(f"{TRAVEL_DOMAIN}/")
        or normalized == "travel-service"
        or normalized.startswith("travel-service/")
        or "/travel-service/" in f"/{normalized}/"
    )


def scan_contract_graph_travel_ghosts(root: Path) -> list[str]:
    path = root / CONTRACT_GRAPH
    if not path.is_file():
        return []
    document = _load_json_mapping(path, label="ContractGraph")
    issues: list[str] = []
    for section in ("objects", "operations"):
        entries = document.get(section)
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            identity_fields = ("domain", "id", "objectId")
            if any(_is_retired_graph_identity(entry.get(field)) for field in identity_fields):
                issues.append(
                    f"{CONTRACT_GRAPH.as_posix()}:{section}[{index}] "
                    "仍包含已退役 travel domain identity"
                )
                continue
            if _is_retired_graph_source_path(entry.get("sourcePath")):
                issues.append(
                    f"{CONTRACT_GRAPH.as_posix()}:{section}[{index}] "
                    "仍引用已退役 travel sourcePath"
                )
    for section in ("sources", "documents"):
        entries = document.get(section)
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if _is_retired_graph_source_path(entry.get("path")):
                issues.append(
                    f"{CONTRACT_GRAPH.as_posix()}:{section}[{index}] "
                    "仍包含已退役 travel contract document"
                )
    return issues


def scan_app_travel_contract_ghosts(root: Path) -> list[str]:
    issues: list[str] = []
    lock_path = root / APP_CONTRACT_LOCK
    if lock_path.is_file():
        lock = _load_json_mapping(lock_path, label="App ContractGraph lock")
        operations = lock.get("appExposedOperations")
        if isinstance(operations, list):
            for index, entry in enumerate(operations):
                if not isinstance(entry, dict):
                    continue
                if any(
                    _is_retired_graph_identity(entry.get(field))
                    for field in (
                        "domain",
                        "canonicalOperationId",
                        "objectId",
                    )
                ) or _is_retired_graph_source_path(entry.get("sourcePath")):
                    issues.append(
                        f"{APP_CONTRACT_LOCK.as_posix()}:appExposedOperations"
                        f"[{index}] 仍包含已退役 travel operation"
                    )
    manifest_path = root / APP_GENERATED_MANIFEST
    if manifest_path.is_file():
        manifest = _load_json_mapping(
            manifest_path,
            label="App generated manifest",
        )
        outputs = manifest.get("outputs")
        if isinstance(outputs, list):
            for index, entry in enumerate(outputs):
                if not isinstance(entry, dict):
                    continue
                output_path = str(entry.get("path") or "").replace("\\", "/")
                if RETIRED_APP_OUTPUT_RE.search(output_path):
                    issues.append(
                        f"{APP_GENERATED_MANIFEST.as_posix()}:outputs[{index}] "
                        f"仍登记已退役 travel 产物 {output_path}"
                    )
    for relative in RETIRED_APP_ARTIFACTS:
        candidate = root / relative
        if os.path.lexists(candidate):
            issues.append(f"{relative.as_posix()}: 已退役 App travel 产物必须不存在")
    return issues


def scan_materialized_travel_owners(root: Path) -> list[str]:
    output_root = root / OUTPUT_ROOT
    if not output_root.is_dir():
        return []

    issues: list[str] = []
    materialized_roots: list[Path] = []
    containers = (
        output_root,
        output_root / "env" / "repo" / "local",
    )
    for container in containers:
        if not container.is_dir():
            continue
        with os.scandir(container) as entries:
            for entry in entries:
                candidate = Path(entry.path)
                name = entry.name
                normalized_name = name.lower()
                if RETIRED_OUTPUT_NAME_RE.search(normalized_name):
                    issues.append(
                        f"{_relative(root, candidate)}: "
                        "可复活 travel-service 的 materialized/aside 目录必须不存在"
                    )
                if (
                    entry.is_dir(follow_symlinks=False)
                    and (
                        "materialized" in normalized_name
                        or normalized_name == "service-contract-view"
                    )
                ):
                    materialized_roots.append(candidate)

    for materialized_root in materialized_roots:
        for directory, _, filenames in os.walk(
            materialized_root,
            followlinks=False,
        ):
            if "domain.yaml" not in filenames:
                continue
            domain_path = Path(directory) / "domain.yaml"
            relative = domain_path.relative_to(root)
            if "contracts" not in relative.parts:
                continue
            try:
                document = _load_yaml_mapping(
                    domain_path,
                    label="materialized domain owner",
                )
            except ValueError as exc:
                issues.append(str(exc))
                continue
            if str(document.get("domain") or "").strip().lower() == TRAVEL_DOMAIN:
                issues.append(
                    f"{relative.as_posix()}: .qwq_output 不得保存可编译的 travel domain owner"
                )
    return issues


def scan_travel_dependencies(root: Path) -> dict[str, dict[str, HitSummary]]:
    app = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_app/lib"),),
            suffixes=CODE_SUFFIXES,
            exclude_copy=True,
        ),
        APP_TRAVEL_DEPENDENCY_RE,
    )
    assistant = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_service/services/assistant-service"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    api_edge = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_service/services/api-edge"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    runtime = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_service/runtime"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    ops = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_ops/cli"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    return {
        "app": app,
        "assistant": assistant,
        "api_edge": api_edge,
        "runtime": runtime,
        "ops": ops,
    }
