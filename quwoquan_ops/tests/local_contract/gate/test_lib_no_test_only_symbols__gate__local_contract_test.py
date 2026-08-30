from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/runtime/architecture/verify_lib_no_test_only_symbols.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("lib_no_test_only_symbols_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lib_gate_accepts_production_entrypoint_and_rejects_test_backdoor(tmp_path: Path) -> None:
    gate = _load_gate()
    app_lib = tmp_path / "lib"
    source = app_lib / "runtime/config/cloud_runtime_config.dart"
    source.parent.mkdir(parents=True)
    source.write_text(
        "void hydrateFromNativeRuntimePackage(Map<String, String> value) {}",
        encoding="utf-8",
    )
    assert gate.collect_violations(app_lib) == []

    source.write_text(
        "void hydrateFromNativeRuntimePackageForTest(Map<String, String> value) {}",
        encoding="utf-8",
    )
    assert any(
        "hydrateFromNativeRuntimePackageForTest" in issue
        for issue in gate.collect_violations(app_lib)
    )
