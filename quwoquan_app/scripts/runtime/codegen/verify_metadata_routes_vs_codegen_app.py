#!/usr/bin/env python3
"""
Compare each service's canonical contracts/**/operations.yaml api_routes
(operation -> path) with App CloudOperationContract.pathTemplate values in
quwoquan_app/packages/quwoquan_cloud_contracts/.../operation_contracts.g.dart.

Legacy per-domain *_api_metadata.g.dart maps are retired; App-exposed operations
must still match metadata paths. Internal-only yaml operations are allowed to
remain outside the App contract surface.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = REPO_ROOT
SERVICE_DIR = ROOT / "quwoquan_service"
OPERATION_CONTRACTS = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "generated"
    / "operation_contracts.g.dart"
)


def domain_contract_roots() -> dict[str, list[Path]]:
    roots: dict[str, list[Path]] = {}
    for path in sorted(SERVICE_DIR.glob("**/contracts/domain.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        domain = str(data.get("domain") or "").strip()
        if not domain:
            continue
        roots.setdefault(domain, []).append(path.parent)
    return roots


def collect_yaml_routes_by_domain() -> dict[str, dict[str, str]]:
    by_domain: dict[str, dict[str, str]] = {}
    for domain, contract_roots in domain_contract_roots().items():
        bucket = by_domain.setdefault(domain, {})
        operation_paths = sorted(
            path
            for contract_root in contract_roots
            for path in contract_root.rglob("operations.yaml")
        )
        for path in operation_paths:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            routes = data.get("api_routes")
            if not isinstance(routes, list):
                continue
            declared_paths: set[str] = set()
            for route in routes:
                if not isinstance(route, dict):
                    continue
                op = str(route.get("operation") or "").strip()
                route_path = str(route.get("path") or "").strip()
                if not op or not route_path:
                    continue
                declared_paths.add(route_path)
                previous = bucket.get(op)
                if previous is not None and previous != route_path:
                    raise SystemExit(
                        f"FAIL: duplicate operation {domain}.{op!r} paths "
                        f"{previous!r} vs {route_path!r} in {path}"
                    )
                bucket[op] = route_path

            graphql_queries = data.get("graphql_queries")
            if not isinstance(graphql_queries, list) or not graphql_queries:
                continue
            app_boundary_queries = [
                query
                for query in graphql_queries
                if isinstance(query, dict)
                and str(query.get("request_entity") or "").strip()
            ]
            if not app_boundary_queries:
                continue
            if len(declared_paths) != 1:
                raise SystemExit(
                    "FAIL: App-bound graphql_queries must share exactly one canonical "
                    f"api_routes path in {path}; found {sorted(declared_paths)!r}"
                )
            graphql_path = next(iter(declared_paths))
            for query in app_boundary_queries:
                op = str(query.get("operation") or "").strip()
                if not op:
                    continue
                previous = bucket.get(op)
                if previous is not None and previous != graphql_path:
                    raise SystemExit(
                        f"FAIL: duplicate operation {domain}.{op!r} paths "
                        f"{previous!r} vs {graphql_path!r} in {path}"
                    )
                bucket[op] = graphql_path
    return by_domain


def parse_app_operation_routes(dart_path: Path) -> dict[str, dict[str, str]]:
    """domain -> {localOperationId -> pathTemplate}."""

    text = dart_path.read_text(encoding="utf-8")
    block = re.search(
        r"const appCloudOperationContracts = <String, CloudOperationContract>\{([\s\S]*)\n\};",
        text,
    )
    if not block:
        return {}
    by_domain: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r'"[^"]+": CloudOperationContract\(\n(?P<body>.*?)(?=\n  "[^"]+": CloudOperationContract\(|\n\};)',
        block.group(0),
        re.S,
    ):
        body = match.group("body")
        domain_match = re.search(r'domain: "([^"]+)"', body)
        local_match = re.search(r'localOperationId: "([^"]+)"', body)
        path_match = re.search(r'pathTemplate: "([^"]*)"', body)
        if not domain_match or not local_match or not path_match:
            continue
        domain = domain_match.group(1)
        local = local_match.group(1)
        path = path_match.group(1)
        bucket = by_domain.setdefault(domain, {})
        previous = bucket.get(local)
        if previous is not None and previous != path:
            raise SystemExit(
                f"FAIL: duplicate App localOperationId {domain}.{local!r} "
                f"paths {previous!r} vs {path!r}"
            )
        bucket[local] = path
    return by_domain


def main() -> int:
    if not SERVICE_DIR.is_dir():
        print(f"FAIL: missing {SERVICE_DIR}", file=sys.stderr)
        return 1
    if not OPERATION_CONTRACTS.is_file():
        print(f"FAIL: missing {OPERATION_CONTRACTS}", file=sys.stderr)
        return 1

    yaml_routes = collect_yaml_routes_by_domain()
    app_routes = parse_app_operation_routes(OPERATION_CONTRACTS)

    errors: list[str] = []
    checked = 0

    for domain, dart_map in sorted(app_routes.items()):
        ymap = yaml_routes.get(domain)
        if not ymap:
            errors.append(
                f"{domain}: App operation contracts have no canonical service contracts"
            )
            continue
        checked += 1
        for op, dart_path in sorted(dart_map.items()):
            yaml_path = ymap.get(op)
            if yaml_path is None:
                errors.append(
                    f"{domain}: App operation {op!r} missing from canonical "
                    f"operations.yaml (path {dart_path!r})"
                )
                continue
            if yaml_path != dart_path:
                errors.append(
                    f"{domain}: operation {op!r} path mismatch metadata={yaml_path!r} "
                    f"app={dart_path!r}"
                )

    if checked == 0:
        errors.append(
            "zero domains were checked; App CloudOperationContract surface must never produce an empty green gate"
        )

    if errors:
        print("verify_metadata_routes_vs_codegen_app: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_metadata_routes_vs_codegen_app: OK "
        f"({checked} App contract domains cross-checked with metadata)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
