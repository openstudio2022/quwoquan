#!/usr/bin/env python3
"""
Ensure contracts/metadata/**/operations.yaml response_entity names resolve to
an object fields type, shared schema, or projection read model.
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
    types = data.get("types")
    if isinstance(types, dict):
        out.update(str(k) for k in types.keys())
    single = data.get("entity")
    if isinstance(single, str) and single.strip():
        out.add(single.strip())
    return out


def object_name_from_directory(bundle_dir: Path) -> str:
    return "".join(part[:1].upper() + part[1:] for part in bundle_dir.name.split("_") if part)


def shared_schema_entity_names() -> set[str]:
    names: set[str] = set()
    for schema_path in sorted(ASSISTANT_METADATA.glob("*/schema.yaml")):
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        contract = raw.get("contract")
        if isinstance(contract, str) and contract.strip():
            names.add(
                "".join(
                    part[:1].upper() + part[1:]
                    for part in contract.strip().split("_")
                    if part
                )
            )
    return names


def entity_names_from_projections(bundle_dir: Path) -> set[str]:
    out: set[str] = set()
    projections_dir = bundle_dir / "projections"
    if not projections_dir.is_dir():
        return out
    for projection_path in sorted(projections_dir.glob("*.yaml")):
        raw = yaml.safe_load(projection_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        read_model = raw.get("read_model")
        if isinstance(read_model, str) and read_model.strip():
            out.add(read_model.strip())
    return out


def referenced_entities_from_operations_yaml(data: dict) -> set[str]:
    out: set[str] = set()
    routes = data.get("api_routes")
    if isinstance(routes, list):
        for r in routes:
            if not isinstance(r, dict):
                continue
            v = r.get("response_entity")
            if isinstance(v, str) and v.strip():
                out.add(v.strip())
    return out


def main() -> int:
    failures: list[str] = []
    if not ASSISTANT_METADATA.is_dir():
        print(f"FAIL: missing {ASSISTANT_METADATA}", file=sys.stderr)
        return 1
    shared_entities = shared_schema_entity_names()
    for operations_path in sorted(ASSISTANT_METADATA.rglob("operations.yaml")):
        parent = operations_path.parent
        fields_path = parent / "fields.yaml"
        if not fields_path.is_file():
            continue
        operations_raw = yaml.safe_load(operations_path.read_text(encoding="utf-8"))
        fld_raw = yaml.safe_load(fields_path.read_text(encoding="utf-8"))
        if not isinstance(operations_raw, dict) or not isinstance(fld_raw, dict):
            continue
        # Only check object bundles that declare api_routes with entity refs.
        need = referenced_entities_from_operations_yaml(operations_raw)
        if not need:
            continue
        have = entity_names_from_fields_yaml(fld_raw)
        have.add(object_name_from_directory(parent))
        have.update(shared_entities)
        have.update(entity_names_from_projections(parent))
        missing = sorted(need - have)
        if missing:
            rel = operations_path.relative_to(ROOT)
            failures.append(f"{rel}: entities missing in fields.yaml: {', '.join(missing)}")

    if failures:
        print(
            "verify_metadata_operation_entities_vs_fields: FAIL\n  "
            + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
