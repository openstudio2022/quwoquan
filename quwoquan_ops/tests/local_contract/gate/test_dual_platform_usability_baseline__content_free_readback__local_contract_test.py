from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = (
    ROOT
    / "quwoquan_app/scripts/runtime/platform"
    / "verify_dual_platform_usability_baseline.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_dual_platform_usability_baseline_companion",
        GATE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dual_platform_gate_requires_both_content_and_content_free_readback() -> None:
    gate = _load_gate()

    assert gate.BASIC_READBACK_PATROL.is_file()
    assert gate.CORE_READBACK_PATROL.is_file()
    assert gate.main() == 0
