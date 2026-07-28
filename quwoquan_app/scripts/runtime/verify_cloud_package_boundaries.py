#!/usr/bin/env python3
"""验证 pure contracts、对象级 test double 与四环境 Remote 依赖边界。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
CONTRACTS = APP / "packages/quwoquan_cloud_contracts"
RETIRED_AGGREGATE_MOCK_PACKAGE = APP / "packages/quwoquan_cloud_mock"
FORBIDDEN_AGGREGATE_PACKAGE_NAMES = frozenset({"quwoquan_cloud_mock"})
FORBIDDEN_CONTRACT_TOKENS = (
    "package:quwoquan_app/",
    "package:flutter/",
    "package:flutter_",
    "dart:io",
    "package:hive",
    "package:shared_preferences",
    "package:http",
    "package:riverpod",
)


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path.relative_to(ROOT)} 必须为 YAML object")
    return value


def package_catalog() -> dict[str, tuple[Path, dict]]:
    roots = [APP, *sorted((APP / "packages").glob("*"))]
    roots.extend(sorted((APP / "runners").glob("*")))
    catalog: dict[str, tuple[Path, dict]] = {}
    for package_root in roots:
        pubspec = package_root / "pubspec.yaml"
        if not pubspec.is_file():
            continue
        data = load_yaml(pubspec)
        name = str(data.get("name", "")).strip()
        if not name or name in catalog:
            raise AssertionError(f"Dart package name 缺失或重复: {name!r}")
        catalog[name] = (package_root, data)
    return catalog


def local_dependency_graph(
    catalog: dict[str, tuple[Path, dict]],
    *,
    include_dev: bool,
) -> dict[str, set[str]]:
    """path 依赖图。production 可达性只看 dependencies（release 构建不含
    dev_dependencies）；完整性与环检测使用全图。"""
    graph = {name: set() for name in catalog}
    for name, (package_root, data) in catalog.items():
        dependencies = dict(data.get("dependencies") or {})
        if include_dev:
            dependencies.update(data.get("dev_dependencies") or {})
        for dependency, descriptor in dependencies.items():
            if not isinstance(descriptor, dict) or "path" not in descriptor:
                continue
            target = (package_root / str(descriptor["path"])).resolve()
            target_data = load_yaml(target / "pubspec.yaml")
            target_name = str(target_data.get("name", "")).strip()
            if target_name not in catalog:
                continue
            graph[name].add(target_name)
    return graph


def verify_acyclic(graph: dict[str, set[str]]) -> None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            cycle = visiting[start:] + [node]
            raise AssertionError(f"Dart package 依赖循环: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.append(node)
        for dependency in sorted(graph[node]):
            visit(dependency)
        visiting.pop()
        visited.add(node)

    for package in sorted(graph):
        visit(package)


def reachable(graph: dict[str, set[str]], root: str) -> set[str]:
    result: set[str] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        for dependency in graph[current]:
            if dependency not in result:
                result.add(dependency)
                pending.append(dependency)
    return result


def verify_contracts_purity(catalog: dict[str, tuple[Path, dict]]) -> None:
    _, pubspec = catalog["quwoquan_cloud_contracts"]
    dependencies = pubspec.get("dependencies") or {}
    if set(dependencies) - {"meta"}:
        raise AssertionError(
            "quwoquan_cloud_contracts 只能依赖 pure Dart meta，当前为 "
            f"{sorted(dependencies)}"
        )
    for source in sorted((CONTRACTS / "lib").rglob("*.dart")):
        text = source.read_text(encoding="utf-8")
        found = [token for token in FORBIDDEN_CONTRACT_TOKENS if token in text]
        if found:
            raise AssertionError(
                f"pure contracts 反向依赖: {source.relative_to(ROOT)} -> {found}"
            )


def verify_aggregate_mock_package_retired(
    catalog: dict[str, tuple[Path, dict]],
) -> None:
    if RETIRED_AGGREGATE_MOCK_PACKAGE.exists():
        raise AssertionError(
            "聚合 Mock package 必须物理删除: "
            f"{RETIRED_AGGREGATE_MOCK_PACKAGE.relative_to(ROOT)}"
        )
    present = FORBIDDEN_AGGREGATE_PACKAGE_NAMES.intersection(catalog)
    if present:
        raise AssertionError(f"聚合 Mock package 仍在 package catalog: {sorted(present)}")

    _, app_pubspec = catalog["quwoquan_app"]
    declared = {
        *dict(app_pubspec.get("dependencies") or {}),
        *dict(app_pubspec.get("dev_dependencies") or {}),
    }
    forbidden = FORBIDDEN_AGGREGATE_PACKAGE_NAMES.intersection(declared)
    if forbidden:
        raise AssertionError(
            f"App pubspec 不得声明聚合 Mock package: {sorted(forbidden)}"
        )


def verify_composition_graph(
    graph: dict[str, set[str]],
    production_graph: dict[str, set[str]],
) -> None:
    full = reachable(graph, "quwoquan_app")
    production = reachable(production_graph, "quwoquan_app")
    forbidden_full = FORBIDDEN_AGGREGATE_PACKAGE_NAMES.intersection(full)
    if forbidden_full:
        raise AssertionError(
            f"App 完整依赖图不得包含聚合 Mock package: {sorted(forbidden_full)}"
        )
    forbidden_production = FORBIDDEN_AGGREGATE_PACKAGE_NAMES.intersection(production)
    if forbidden_production:
        raise AssertionError(
            "production App package graph 不得包含聚合 Mock package: "
            f"{sorted(forbidden_production)}"
        )
    main_prod = (APP / "lib/main_prod.dart").read_text(encoding="utf-8")
    if "quwoquan_cloud_mock" in main_prod:
        raise AssertionError("main_prod 不得 import alpha/test Mock package")


def main() -> int:
    catalog = package_catalog()
    required = {
        "quwoquan_app",
        "quwoquan_cloud_contracts",
    }
    if not required.issubset(catalog):
        raise AssertionError(
            f"Cloud package catalog 缺失: {sorted(required - set(catalog))}"
        )
    graph = local_dependency_graph(catalog, include_dev=True)
    production_graph = local_dependency_graph(catalog, include_dev=False)
    verify_acyclic(graph)
    verify_contracts_purity(catalog)
    verify_aggregate_mock_package_retired(catalog)
    verify_composition_graph(graph, production_graph)
    print(
        "PASS: pure contracts + no aggregate Mock package + four-environment Remote graph "
        f"({json.dumps({k: sorted(v) for k, v in graph.items()}, ensure_ascii=False)})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
