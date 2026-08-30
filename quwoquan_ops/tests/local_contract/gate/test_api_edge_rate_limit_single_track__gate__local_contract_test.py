from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_service/scripts/verify/structure/verify_api_edge_rate_limit_single_track.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("api_edge_rate_limit_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_edge_rate_limit_single_track_accepts_current_tree() -> None:
    assert _load_gate().collect_issues() == []


def test_api_edge_rate_limit_single_track_rejects_owner_limiter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gate = _load_gate()
    owner = tmp_path / "cmd/api/main.go"
    owner.parent.mkdir(parents=True)
    owner.write_text("package main\nfunc main() { NewRateLimiter() }\n", encoding="utf-8")
    monkeypatch.setattr(gate, "_owner_composition_files", lambda: (owner,))
    monkeypatch.setattr(gate, "_relative", lambda path: path.as_posix())
    assert any("per-process arrival limiter" in issue for issue in gate.collect_issues())
