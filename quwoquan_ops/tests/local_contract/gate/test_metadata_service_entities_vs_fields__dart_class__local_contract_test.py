from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = (
    ROOT
    / "quwoquan_service/scripts/verify/contract_graph"
    / "verify_metadata_service_entities_vs_fields.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_metadata_service_entities_vs_fields_companion",
        GATE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_dart_class_is_a_declared_response_type() -> None:
    gate = _load_gate()

    assert "ChatContractFixtureContainer" in gate.declared_schema_names()
    assert gate.main() == 0
