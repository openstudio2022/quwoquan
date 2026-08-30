# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t10

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATE = (
    ROOT
    / "quwoquan_service/scripts/runtime/experiments/verify_experiment_single_track.py"
)
CHECKS = (
    "_assert_control_plane_frozen",
    "_assert_canonical_runtime_track",
    "_assert_no_second_resolver",
    "_assert_no_private_runtime_config",
    "_assert_no_direct_storage_seed",
    "_assert_no_assignment_write_api",
)


def _load_gate():
    spec = importlib.util.spec_from_file_location("experiment_single_track_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_isolated_negative(gate, monkeypatch, check: str) -> int:
    for name in CHECKS:
        if name != check:
            monkeypatch.setattr(gate, name, lambda: None)
    return gate.main()


def test_experiment_single_track_accepts_current_tree() -> None:
    assert _load_gate().main() == 0


def test_experiment_single_track_rejects_second_resolver(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    gate = _load_gate()
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _write(
        tmp_path,
        "quwoquan_service/runtime/experiments/shadow_resolver.go",
        "package runtimeexperiments\ntype StaticResolver struct{}\n",
    )

    assert _run_isolated_negative(gate, monkeypatch, "_assert_no_second_resolver") == 1
    assert "second experiment resolver" in capsys.readouterr().err


def test_experiment_single_track_rejects_private_runtime_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    gate = _load_gate()
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _write(
        tmp_path,
        "quwoquan_service/services/search-service/config/schema.yaml",
        "configs:\n- key: sys.search-service.ranking.experiment.enabled\n",
    )

    assert _run_isolated_negative(
        gate,
        monkeypatch,
        "_assert_no_private_runtime_config",
    ) == 1
    assert "service-private experiment runtime config" in capsys.readouterr().err


def test_experiment_single_track_rejects_direct_storage_seed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    gate = _load_gate()
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _write(
        tmp_path,
        "quwoquan_ops/cli/seed_experiment_policy.py",
        'SQL = "INSERT INTO experiments(id, version) VALUES (\\\'shadow\\\', 1)"\n',
    )

    assert _run_isolated_negative(
        gate,
        monkeypatch,
        "_assert_no_direct_storage_seed",
    ) == 1
    assert "direct experiment storage seed" in capsys.readouterr().err


def test_experiment_single_track_rejects_assignment_write_api(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    gate = _load_gate()
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    _write(
        tmp_path,
        "quwoquan_service/services/product-ops-service/contracts/product_ops/"
        "experiment_assignment_fact/operations.yaml",
        """api_routes:
- method: POST
  operation: AssignExperimentVariant
  request_entity: AssignExperimentVariantRequest
  application:
    kind: command
""",
    )

    assert _run_isolated_negative(
        gate,
        monkeypatch,
        "_assert_no_assignment_write_api",
    ) == 1
    assert "assignment write API is frozen" in capsys.readouterr().err
