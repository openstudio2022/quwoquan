from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution import task_init
from core import paths
from core.source_digest import current_execution_bundle_identity, current_source_definition_snapshot


EXECUTION_ID = "20260831--travel-article-host-init--china--pilot-001"


def _write_inputs(root: Path, *, execution_id: str = EXECUTION_ID) -> tuple[Path, Path]:
    family = "content/travel/article/article"
    demand = {
        "schema": "quwoquan_data.carrier_demand",
        "status": "confirmed",
        "executionId": execution_id,
        "carrier": "article",
        "familyRef": family,
        "quota": 1,
        "workRequestRef": "data/local/workspace/work-requests/wr.json",
        "workRequestDigest": "sha256:" + "1" * 64,
        "sourceDigest": current_source_definition_snapshot().to_document(),
        "executionBundle": current_execution_bundle_identity().to_document(),
        "entityCatalogDigest": "sha256:" + "2" * 64,
        "retryOf": None,
    }
    candidates = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": execution_id,
        "carrier": "article",
        "sourceRef": "data/local/workspace/source-pools/article.json",
        "entityCatalogDigest": demand["entityCatalogDigest"],
        "candidateCount": 1,
        "targets": [{
            "name": "西湖",
            "entityType": "地点/景区",
            "publishAngle": "攻略",
            "publishTitle": "西湖一日游",
            "publishSeq": 1,
        }],
    }
    demand_path = root / "inputs/carrier-demand.json"
    candidate_path = root / "inputs/candidate-bindings.json"
    demand_path.parent.mkdir(parents=True)
    demand_path.write_text(json.dumps(demand, ensure_ascii=False), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    return demand_path, candidate_path


@pytest.fixture
def isolated_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output = tmp_path / ".qwq_output"
    tasks = output / "data/tasks"
    monkeypatch.setattr(paths, "OUTPUT_ROOT", output)
    local = output / "data/local"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", local)
    monkeypatch.setattr(task_init.paths, "OUTPUT_ROOT", output)
    monkeypatch.setattr(task_init.paths, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.setattr(task_init.paths, "DATA_LOCAL_ROOT", local)
    return output


def test_task_init_atomically_creates_exactly_three_files_without_stage_side_effects(isolated_output: Path) -> None:
    demand, candidates = _write_inputs(isolated_output)
    result = task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    root = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID

    assert result["status"] == "created"
    assert sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()) == [
        "0.plan/request.json",
        "0.plan/target_set.json",
        "execution_manifest.json",
    ]
    assert not (root / "_shared").exists()
    assert not (root / "sources").exists()
    assert not (root / "evidence").exists()
    assert not (isolated_output / "data/releases").exists()

    manifest = json.loads((root / "execution_manifest.json").read_text())
    request = json.loads((root / "0.plan/request.json").read_text())
    target_set = json.loads((root / "0.plan/target_set.json").read_text())
    assert manifest["hostRuntime"] == "external_host_agent"
    assert "modelBinding" not in manifest and "semanticSelectionId" not in manifest
    assert request["quota"] == 1 and request["workUnitCount"] == 1
    assert target_set["candidateBinding"]["candidateCount"] == 1


def test_task_init_same_bytes_replay_is_idempotent_and_drift_writes_nothing(isolated_output: Path) -> None:
    demand, candidates = _write_inputs(isolated_output)
    first = task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    root = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID
    before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    replay = task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    assert first["status"] == "created" and replay["status"] == "replayed"
    assert before == {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    payload = json.loads(candidates.read_text())
    payload["targets"][0]["publishTitle"] = "漂移标题"
    candidates.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(task_init.TaskInitError, match="different bytes"):
        task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    assert before == {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_task_init_invalid_candidate_binding_leaves_no_execution_visible(isolated_output: Path) -> None:
    demand, candidates = _write_inputs(isolated_output)
    payload = json.loads(candidates.read_text())
    payload["candidateCount"] = 2
    candidates.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(task_init.TaskInitError, match="candidateCount"):
        task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    assert not (paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID).exists()
