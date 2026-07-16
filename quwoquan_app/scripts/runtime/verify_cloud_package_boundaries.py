#!/usr/bin/env python3
"""验证 pure contracts、alpha Mock package 与 production 依赖边界。"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
CONTRACTS = APP / "packages/quwoquan_cloud_contracts"
MOCK = APP / "packages/quwoquan_cloud_mock"
ALPHA_RUNNER = APP / "runners/alpha"
FIXTURE_BUILDER = APP / "scripts/env/build_alpha_fixture_bundle.py"
FIXTURE_BUNDLE = (
    MOCK / "lib/src/generated/alpha_fixture_bundle.g.dart"
)
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
) -> dict[str, set[str]]:
    graph = {name: set() for name in catalog}
    for name, (package_root, data) in catalog.items():
        dependencies = {
            **(data.get("dependencies") or {}),
            **(data.get("dev_dependencies") or {}),
        }
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


def verify_composition_graph(graph: dict[str, set[str]]) -> None:
    production = reachable(graph, "quwoquan_app")
    if "quwoquan_cloud_mock" in production:
        raise AssertionError("production App package graph 不得包含 cloud mock")
    alpha = reachable(graph, "quwoquan_app_alpha_runner")
    required = {"quwoquan_app", "quwoquan_cloud_mock", "quwoquan_cloud_contracts"}
    if not required.issubset(alpha):
        raise AssertionError(f"alpha runner composition 不完整: {sorted(alpha)}")
    main_prod = (APP / "lib/main_prod.dart").read_text(encoding="utf-8")
    if "quwoquan_cloud_mock" in main_prod:
        raise AssertionError("main_prod 不得 import alpha/test Mock package")


def verify_fixture_rebuild() -> None:
    committed = FIXTURE_BUNDLE.read_bytes()
    with tempfile.TemporaryDirectory(prefix="qwq-alpha-fixture-") as temp:
        output = Path(temp) / "alpha_fixture_bundle.g.dart"
        result = subprocess.run(
            ["python3", str(FIXTURE_BUILDER), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"alpha fixture bundle rebuild 失败:\n{result.stdout}\n{result.stderr}"
            )
        if output.read_bytes() != committed:
            raise AssertionError("alpha fixture bundle 不是 seed manifest 可重建产物")
    header = committed[:300].decode("utf-8", errors="replace")
    if "Source manifest SHA256:" not in header:
        raise AssertionError("alpha fixture bundle 缺内容寻址 manifest hash")

def verify_override_sync() -> None:
    source = load_yaml(APP / "pubspec.yaml").get("dependency_overrides") or {}
    for target in (MOCK, ALPHA_RUNNER):
        generated = load_yaml(target / "pubspec_overrides.yaml").get(
            "dependency_overrides"
        ) or {}
        if set(source) != set(generated):
            raise AssertionError(
                f"{target.relative_to(ROOT)} dependency override 名单漂移"
            )
        for name, source_descriptor in source.items():
            target_descriptor = generated[name]
            if isinstance(source_descriptor, dict) and "path" in source_descriptor:
                if not isinstance(target_descriptor, dict):
                    raise AssertionError(f"{name} path override 结构漂移")
                source_path = (APP / str(source_descriptor["path"])).resolve()
                target_path = (
                    target / str(target_descriptor.get("path", ""))
                ).resolve()
                if source_path != target_path:
                    raise AssertionError(f"{name} path override 目标漂移")
            elif source_descriptor != target_descriptor:
                raise AssertionError(f"{name} dependency override 版本漂移")


def main() -> int:
    catalog = package_catalog()
    required = {
        "quwoquan_app",
        "quwoquan_cloud_contracts",
        "quwoquan_cloud_mock",
        "quwoquan_app_alpha_runner",
    }
    if not required.issubset(catalog):
        raise AssertionError(
            f"Cloud package catalog 缺失: {sorted(required - set(catalog))}"
        )
    graph = local_dependency_graph(catalog)
    verify_acyclic(graph)
    verify_contracts_purity(catalog)
    verify_composition_graph(graph)
    verify_override_sync()
    verify_fixture_rebuild()
    print(
        "PASS: pure contracts + alpha Mock package + production package graph "
        f"({json.dumps({k: sorted(v) for k, v in graph.items()}, ensure_ascii=False)})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
