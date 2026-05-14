#!/usr/bin/env python3
"""
Compare contracts/metadata **/service.yaml api_routes (operation → path) with
quwoquan_app/lib/cloud/runtime/generated/*/*_api_metadata.g.dart operationToPathTemplate.

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
METADATA_DIR = ROOT / "quwoquan_service" / "contracts" / "metadata"
GEN_DIR = ROOT / "quwoquan_app" / "lib" / "cloud" / "runtime" / "generated"


def collect_yaml_routes_by_domain() -> dict[str, dict[str, str]]:
    by_domain: dict[str, dict[str, str]] = {}
    for path in sorted(METADATA_DIR.rglob("service.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            continue
        svc = data.get("service")
        if not isinstance(svc, dict):
            continue
        domain = str(svc.get("domain") or "").strip()
        if not domain:
            continue
        routes = data.get("api_routes")
        if not isinstance(routes, list):
            continue
        bucket = by_domain.setdefault(domain, {})
        for r in routes:
            if not isinstance(r, dict):
                continue
            op = str(r.get("operation") or "").strip()
            pth = str(r.get("path") or "").strip()
            if not op or not pth:
                continue
            prev = bucket.get(op)
            if prev is not None and prev != pth:
                raise SystemExit(
                    f"FAIL: duplicate operation {domain}.{op!r} "
                    f"paths {prev!r} vs {pth!r} in {path}"
                )
            bucket[op] = pth
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
    if not METADATA_DIR.is_dir():
        print(f"FAIL: missing {METADATA_DIR}", file=sys.stderr)
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
            # Domain-only codegen file without metadata service.yaml (yet)
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
                f"metadata service.yaml for domain {domain!r}"
            )

        for op in sorted(yaml_ops & dart_ops):
            yp, dp = ymap[op], dart_map[op]
            if yp != dp:
                errors.append(
                    f"{domain}: operation {op!r} path mismatch metadata={yp!r} "
                    f"dart={dp!r}"
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
