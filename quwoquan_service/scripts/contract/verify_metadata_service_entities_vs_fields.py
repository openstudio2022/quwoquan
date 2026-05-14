#!/usr/bin/env python3
"""
Ensure contracts/metadata/**/service.yaml request_entity / response_entity names
are defined in the sibling fields.yaml (entities.* or current top-level entity + fields).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
# Scope: assistant metadata bundles (F0 backlog); extend to other domains as fields.yaml catches up.
ASSISTANT_METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata" / "assistant"


def entity_names_from_fields_yaml(data: dict) -> set[str]:
    out: set[str] = set()
    ents = data.get("entities")
    if isinstance(ents, dict):
        out.update(str(k) for k in ents.keys())
    single = data.get("entity")
    if isinstance(single, str) and single.strip():
        out.add(single.strip())
    return out


def referenced_entities_from_service_yaml(data: dict) -> set[str]:
    out: set[str] = set()
    routes = data.get("api_routes")
    if isinstance(routes, list):
        for r in routes:
            if not isinstance(r, dict):
                continue
            for key in ("request_entity", "response_entity"):
                v = r.get(key)
                if isinstance(v, str) and v.strip():
                    out.add(v.strip())
    return out


def main() -> int:
    failures: list[str] = []
    if not ASSISTANT_METADATA.is_dir():
        print(f"FAIL: missing {ASSISTANT_METADATA}", file=sys.stderr)
        return 1
    for svc_path in sorted(ASSISTANT_METADATA.rglob("service.yaml")):
        parent = svc_path.parent
        fields_path = parent / "fields.yaml"
        if not fields_path.is_file():
            continue
        svc_raw = yaml.safe_load(svc_path.read_text(encoding="utf-8"))
        fld_raw = yaml.safe_load(fields_path.read_text(encoding="utf-8"))
        if not isinstance(svc_raw, dict) or not isinstance(fld_raw, dict):
            continue
        # Only check service bundles that declare api_routes with entity refs
        need = referenced_entities_from_service_yaml(svc_raw)
        if not need:
            continue
        have = entity_names_from_fields_yaml(fld_raw)
        missing = sorted(need - have)
        if missing:
            rel = svc_path.relative_to(ROOT)
            failures.append(f"{rel}: entities missing in fields.yaml: {', '.join(missing)}")

    if failures:
        print(
            "verify_metadata_service_entities_vs_fields: FAIL\n  "
            + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
