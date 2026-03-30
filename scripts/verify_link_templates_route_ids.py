#!/usr/bin/env python3
"""Ensure link_templates.yaml navigation.route_id and param_bindings match app_routes.yaml."""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover
    print("verify_link_templates_route_ids: PyYAML required", file=sys.stderr)
    raise SystemExit(2) from e

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared"
ROUTES_PATH = META / "app_routes.yaml"
LINK_PATH = META / "link_templates.yaml"


def path_params(path: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", path or ""))


def main() -> int:
    if not ROUTES_PATH.is_file():
        print(f"[verify] FAIL: missing {ROUTES_PATH}", file=sys.stderr)
        return 1
    if not LINK_PATH.is_file():
        print(f"[verify] OK: no {LINK_PATH.name} — skip")
        return 0

    routes_doc = yaml.safe_load(ROUTES_PATH.read_text(encoding="utf-8")) or {}
    routes = {r["id"]: r for r in (routes_doc.get("routes") or []) if r.get("id")}

    link_doc = yaml.safe_load(LINK_PATH.read_text(encoding="utf-8")) or {}
    entities = link_doc.get("entities") or {}

    errors: list[str] = []
    for key, ent in sorted(entities.items()):
        nav = ent.get("navigation") or {}
        rid = (nav.get("route_id") or "").strip()
        if not rid:
            errors.append(f"entity {key!r}: empty navigation.route_id")
            continue
        route = routes.get(rid)
        if not route:
            errors.append(f"entity {key!r}: route_id {rid!r} not in app_routes.yaml")
            continue
        ppath = route.get("path") or ""
        allowed = path_params(ppath)
        bindings = nav.get("param_bindings") or {}
        for link_name, route_param in sorted(bindings.items()):
            if route_param not in allowed:
                errors.append(
                    f"entity {key!r}: param_bindings {link_name!r} -> {route_param!r} "
                    f"not in route {rid!r} path params {sorted(allowed)} (path={ppath!r})"
                )

    if errors:
        print("[verify] FAIL: link_templates vs app_routes", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("[verify] OK: link_templates route_id / param_bindings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
