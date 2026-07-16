"""搜索运维脚本的输出目录契约。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_search_scripts_use_environment_scoped_observability_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))

    load = _load_module(
        "search_load_benchmark_output_contract",
        SCRIPTS_ROOT / "search" / "search_load_benchmark.py",
    )
    rollback = _load_module(
        "search_rollback_rehearsal_output_contract",
        SCRIPTS_ROOT / "search" / "search_rollback_rehearsal.py",
    )
    capacity = _load_module(
        "verify_search_local_gamma_capacity_output_contract",
        SCRIPTS_ROOT / "search" / "verify_search_local_gamma_capacity.py",
    )

    root = tmp_path / "output" / "env" / "gamma"
    assert Path(load.DEFAULT_OUT_DIR) == root / "observability" / "search-load"
    assert rollback.DEFAULT_REPORT == (
        root / "observability" / "search-rollback" / "search_rollback_rehearsal_report.json"
    )
    assert capacity.DEFAULT_OUT == (
        root / "observability" / "search-capacity" / "search_r_s06_s1_local_gamma_report.json"
    )
    assert capacity.DEFAULT_LOAD_DIR == root / "observability" / "search-load" / "local-gamma"
