"""搜索运维脚本的输出目录契约。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = ROOT / "quwoquan_service" / "scripts"


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


def test_search_capacity_uses_canonical_stackctl_release_profile():
    source = (
        SCRIPTS_ROOT / "search" / "verify_search_local_gamma_capacity.py"
    ).read_text(encoding="utf-8")
    assert '"--profile"' in source
    assert '"release"' in source


def test_search_capacity_uses_canonical_cloud_target_aliases():
    source = (
        SCRIPTS_ROOT / "search" / "verify_search_local_gamma_capacity.py"
    ).read_text(encoding="utf-8")
    assert '"objectTypes": ["article", "entity", "location"]' in source
    assert '.get("provider")' in source


def test_local_gamma_consumes_immutable_search_release_without_seed_backfill():
    source = (
        ROOT / "quwoquan_app" / "scripts" / "gamma" / "start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    assert "immutable release activation owns business data and search projections" in source
    for command in (
        "./services/content-service/cmd/search-backfill",
        "./services/entity-service/cmd/search-backfill",
        "./services/circle-service/cmd/search-backfill",
        "./services/user-service/cmd/search-backfill",
    ):
        assert command not in source
