#!/usr/bin/env python3
"""
Compare each service's canonical contracts/**/operations.yaml api_routes
(operation -> path) with quwoquan_app/lib/cloud/runtime/generated/*/
*_api_metadata.g.dart operationToPathTemplate.

Fails on missing/extra operations or path template mismatches (per domain).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = ROOT / "quwoquan_service"
GEN_DIR = ROOT / "quwoquan_app" / "lib" / "cloud" / "runtime" / "generated"


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
            for route in routes:
                if not isinstance(route, dict):
                    continue
                op = str(route.get("operation") or "").strip()
                route_path = str(route.get("path") or "").strip()
                if not op or not route_path:
                    continue
                previous = bucket.get(op)
                if previous is not None and previous != route_path:
                    raise SystemExit(
                        f"FAIL: duplicate operation {domain}.{op!r} paths "
                        f"{previous!r} vs {route_path!r} in {path}"
                    )
                bucket[op] = route_path
    return by_domain


def parse_dart_operation_map(dart_path: Path) -> dict[str, str]:
    text = dart_path.read_text(encoding="utf-8")
    m = re.search(
        r"static const Map<String, String> operationToPathTemplate = <String, String>\{([\s\S]*?)\};",
        text,
    )
    if not m:
        return {}
    out: dict[str, str] = {}
    for mo in re.finditer(r"'([^']+)':\s*'([^']+)'", m.group(1)):
        out[mo.group(1)] = mo.group(2)
    return out


def main() -> int:
    if not SERVICE_DIR.is_dir():
        print(f"FAIL: missing {SERVICE_DIR}", file=sys.stderr)
        return 1
    if not GEN_DIR.is_dir():
        print(f"FAIL: missing {GEN_DIR}", file=sys.stderr)
        return 1

    yaml_routes = collect_yaml_routes_by_domain()
    dart_files = sorted(GEN_DIR.glob("*/*_api_metadata.g.dart"))

    errors: list[str] = []
    checked = 0

    for dart_path in dart_files:
        domain = dart_path.parent.name
        dart_map = parse_dart_operation_map(dart_path)
        if not dart_map:
            continue
        ymap = yaml_routes.get(domain)
        if not ymap:
            errors.append(
                f"{domain}: generated operation map has no canonical service contracts"
            )
            continue

        checked += 1
        yaml_ops = set(ymap)
        dart_ops = set(dart_map)

        missing_in_dart = sorted(yaml_ops - dart_ops)
        extra_in_dart = sorted(dart_ops - yaml_ops)

        for op in missing_in_dart:
            errors.append(
                f"{domain}: operation {op!r} in metadata but missing in "
                f"{dart_path.relative_to(ROOT)} (path {ymap[op]!r})"
            )
        for op in extra_in_dart:
            errors.append(
                f"{domain}: operation {op!r} in {dart_path.name} but not in "
                f"canonical operations.yaml for domain {domain!r}"
            )

        for op in sorted(yaml_ops & dart_ops):
            yp, dp = ymap[op], dart_map[op]
            if yp != dp:
                errors.append(
                    f"{domain}: operation {op!r} path mismatch metadata={yp!r} "
                    f"dart={dp!r}"
                )

    for domain, routes in sorted(yaml_routes.items()):
        if routes and not (GEN_DIR / domain / f"{domain}_api_metadata.g.dart").is_file():
            errors.append(
                f"{domain}: {len(routes)} canonical routes have no generated App metadata"
            )

    if checked == 0:
        errors.append(
            "zero domains were checked; canonical service contracts must never produce an empty green gate"
        )

    if errors:
        print("verify_metadata_routes_vs_codegen_app: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        f"verify_metadata_routes_vs_codegen_app: OK "
        f"({checked} codegen domains cross-checked with metadata)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
