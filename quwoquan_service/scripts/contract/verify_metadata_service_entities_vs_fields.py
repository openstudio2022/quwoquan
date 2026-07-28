#!/usr/bin/env python3
"""Ensure every ContractGraph response entity resolves to a declared contract type."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "quwoquan_service"
CONTRACT_GRAPH = SERVICE_ROOT / "generated" / "contract_graph.json"


def entity_names_from_fields_yaml(data: dict) -> set[str]:
    names: set[str] = set()
    for key in ("entities", "types"):
        values = data.get(key)
        if isinstance(values, dict):
            names.update(str(name) for name in values)
    single = data.get("entity")
    if isinstance(single, str) and single.strip():
        names.add(single.strip())
    return names


def contract_roots() -> list[Path]:
    roots = [
        *SERVICE_ROOT.glob("services/*/contracts"),
        *SERVICE_ROOT.glob("control-plane/*/contracts"),
    ]
    return sorted(path for path in roots if path.is_dir())


def declared_schema_names() -> set[str]:
    names: set[str] = set()
    for contracts in contract_roots():
        for schema_path in sorted(contracts.rglob("schema.yaml")):
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
        for fields_path in sorted(contracts.rglob("fields.yaml")):
            raw = yaml.safe_load(fields_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                names.update(entity_names_from_fields_yaml(raw))
    return names


def load_contract_graph() -> dict:
    try:
        graph = json.loads(CONTRACT_GRAPH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"ContractGraph unreadable: {error}") from error
    if not isinstance(graph, dict):
        raise ValueError("ContractGraph root must be an object")
    if not isinstance(graph.get("objects"), list):
        raise ValueError("ContractGraph objects must be a list")
    if not isinstance(graph.get("operations"), list):
        raise ValueError("ContractGraph operations must be a list")
    if not isinstance(graph.get("projections"), list):
        raise ValueError("ContractGraph projections must be a list")
    return graph


def main() -> int:
    try:
        graph = load_contract_graph()
    except ValueError as error:
        print(f"verify_metadata_operation_entities_vs_fields: FAIL: {error}", file=sys.stderr)
        return 1

    declared = declared_schema_names()
    declared.update(
        str(item.get("name") or "").strip()
        for item in graph["objects"]
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    )
    declared.update(
        str(item.get("readModel") or "").strip()
        for item in graph["projections"]
        if isinstance(item, dict) and str(item.get("readModel") or "").strip()
    )

    failures: list[str] = []
    for operation in graph["operations"]:
        if not isinstance(operation, dict):
            failures.append("ContractGraph contains a non-object operation")
            continue
        response_entity = str(operation.get("responseEntity") or "").strip()
        if not response_entity or response_entity in declared:
            continue
        operation_id = str(operation.get("id") or "<unknown-operation>")
        source_path = str(operation.get("sourcePath") or "<unknown-source>")
        failures.append(
            f"{source_path}: {operation_id} response entity is undeclared: {response_entity}"
        )

    if failures:
        print(
            "verify_metadata_operation_entities_vs_fields: FAIL\n  "
            + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1
    print(
        "verify_metadata_operation_entities_vs_fields: OK "
        f"(objects={len(graph['objects'])}, operations={len(graph['operations'])}, "
        f"declaredTypes={len(declared)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
