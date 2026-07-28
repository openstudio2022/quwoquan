from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops" / "gate" / "scaffold" / "verify_test_coverage_map.py"
SPEC = importlib.util.spec_from_file_location("verify_test_coverage_map", MODULE_PATH)
assert SPEC and SPEC.loader
coverage_map = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage_map
SPEC.loader.exec_module(coverage_map)


def test_spec_ref_pattern_includes_app_root_uat_and_nested_acceptance() -> None:
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#gwt-001
    source = "\n".join(
        (
            "// " + "spec_" + "ref: specs/feature-tree/spec.md#uat-009",
            "// "
            + "spec_"
            + "ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001",
        )
    )

    assert coverage_map.SPEC_REF.findall(source) == [
        ("specs/feature-tree/spec.md", "uat-009"),
        (
            "specs/feature-tree/runtime/runtime-test-pyramid/spec.md",
            "sit-001",
        ),
    ]
