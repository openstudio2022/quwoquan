"""spec_ref: multi-carrier-release GWT-020/GWT-030/GWT-034。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution import stage_authority, stage_semantic_recorder, task_init
from core import paths
from core.source_digest import current_execution_bundle_identity, current_source_definition_snapshot

EXECUTION_ID = "20260901--travel-article-semantic-recorder--china--pilot-001"


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    release = output / "data/releases"
    for module in (paths, task_init.paths, stage_authority.paths, stage_semantic_recorder.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
        monkeypatch.setattr(module, "RELEASE_ROOT", release)
    demand = {
        "schema": "quwoquan_data.carrier_demand", "status": "confirmed",
        "executionId": EXECUTION_ID, "carrier": "article",
        "familyRef": "content/travel/article/article", "quota": 1,
        "workRequestRef": "data/local/workspace/wr.json", "workRequestDigest": "sha256:" + "1" * 64,
        "sourceDigest": current_source_definition_snapshot().to_document(),
        "executionBundle": current_execution_bundle_identity().to_document(),
        "entityCatalogDigest": "sha256:" + "2" * 64, "retryOf": None,
    }
    candidates = {
        "schema": "quwoquan_data.immutable_candidate_bindings", "executionId": EXECUTION_ID,
        "carrier": "article", "sourceRef": "data/local/source-pool.json",
        "entityCatalogDigest": demand["entityCatalogDigest"], "candidateCount": 1,
        "targets": [{"name": "西湖", "entityType": "地点/景区", "publishAngle": "攻略", "publishTitle": "西湖攻略", "publishSeq": 1}],
    }
    demand_path = output / "inputs/demand.json"
    candidate_path = output / "inputs/candidates.json"
    _json(demand_path, demand)
    _json(candidate_path, candidates)
    task_init.initialize_task(carrier_demand_path=demand_path, candidate_bindings_path=candidate_path)
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    stage_authority.run_stage_gate(EXECUTION_ID, "0.plan", runner=lambda _argv: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    stage_authority.close_stage(EXECUTION_ID, "0.plan")
    stage_authority.open_stage(EXECUTION_ID, "sources")
    return tasks / EXECUTION_ID


def _result_input(request_path: Path, *, refs: list[str], family: str = "gpt", host: str = "cursor") -> dict:
    request = json.loads(request_path.read_text())
    return {
        "schema": "quwoquan_data.stage_semantic_result_input",
        "requestRef": request_path.relative_to(request_path.parents[3]).as_posix(),
        "requestDigest": request["requestDigest"],
        "actor": {
            "host": host, "modelFamily": family, "sessionId": "semantic-session",
            "invocation": {"provider": "cursor", "model": family, "runId": "semantic-run"},
        },
        "resultRefs": sorted(refs),
    }


def _source_closure(root: Path) -> list[str]:
    unit = root / "sources/source-001"
    values = {
        "meta.json": {
            "schema": "quwoquan_data.source_unit", "stage": "1.download", "executionId": EXECUTION_ID,
            "executionBinding": "frozen", "sourceUnitId": "source-001", "entityName": "西湖", "title": "西湖",
            "sourceKind": "wikipedia", "extractor": "wikipedia_api", "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖",
            "finalUrl": "https://zh.wikipedia.org/wiki/西湖", "fetchedAt": "2026-09-01T00:00:00Z",
            "rawSha256": "sha256:" + "1" * 64, "cleanSha256": "sha256:" + "2" * 64,
            "policyRevision": "encyclopedia-primary", "sourceUseMode": "factual_reference_only", "rightsMode": "factual_reference_only",
        },
        "source.md": "source", "source.clean.md": "clean", "source.layout.json": {},
        "source.quality.json": {}, "assets/index.json": {},
    }
    refs = []
    for name, value in values.items():
        path = unit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((json.dumps(value) if isinstance(value, dict) else value) + "\n", encoding="utf-8")
        refs.append(path.relative_to(root).as_posix())
    return sorted(refs)


def _advance_sources_to_stage(root: Path, target_stage: str) -> None:
    refs = _source_closure(root)
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    result = stage_semantic_recorder.record_stage_semantic_result(
        EXECUTION_ID, "sources", _result_input(request, refs=refs)
    )
    context = {
        "semanticResultRef": result.relative_to(root).as_posix(),
        "semanticResultDigest": stage_authority._sha256(result.read_bytes()),
    }
    runner = lambda _argv: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    stage_authority.run_stage_gate(EXECUTION_ID, "sources", close_context=context, runner=runner)
    stage_authority.close_stage(EXECUTION_ID, "sources")
    if target_stage == "1.download":
        stage_authority.open_stage(EXECUTION_ID, "1.download")
        return
    stage_authority.open_stage(EXECUTION_ID, "1.download")
    _json(root / "posts/article/攻略/西湖攻略/1/1.download/source_refs.json", {"sources": []})
    artifact_ref = "posts/article/攻略/西湖攻略/1/1.download/source_refs.json"
    stage_authority.run_stage_gate(
        EXECUTION_ID, "1.download",
        close_context={"artifactRefs": [{"scope": "execution", "ref": artifact_ref}]},
        runner=runner,
    )
    stage_authority.close_stage(EXECUTION_ID, "1.download")
    stage_authority.open_stage(EXECUTION_ID, target_stage)


def _quality_document() -> dict:
    return {
        "schema": "quwoquan_data.quality_analysis", "stage": "2.quality",
        "executionId": EXECUTION_ID, "executionBinding": "frozen",
        "sourcePolicyRevision": "encyclopedia-primary", "sourceRevision": "sha256:" + "1" * 64,
        "recommendation": "proceed", "sourcePaths": ["sources/source-001/source.clean.md"],
        "sourceAdmissions": [{"sourceRef": "sources/source-001", "decision": "selected", "evidenceHash": "sha256:" + "2" * 64}],
        "rejectionReasons": [], "evidenceHashes": ["sha256:" + "2" * 64],
    }


def test_prepare_detects_frozen_input_drift(root: Path) -> None:
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    (root / "0.plan/target_set.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(stage_semantic_recorder.StageSemanticConflict, match="conflict"):
        stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    assert request.is_file()


def test_record_rejects_request_actor_and_result_ref_boundaries(root: Path) -> None:
    refs = _source_closure(root)
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    value = _result_input(request, refs=refs)
    value["requestDigest"] = "sha256:" + "9" * 64
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="requestDigest"):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)
    value = _result_input(request, refs=refs, host="provider-sdk")
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="schema violation"):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)
    value = _result_input(request, refs=refs, family="auto")
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="schema violation"):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)
    outside = root.parent / "outside.json"
    _json(outside, {})
    value = _result_input(request, refs=["../outside.json"])
    with pytest.raises(stage_semantic_recorder.StageSemanticError):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)


def test_record_exact_replay_conflict_and_gate_drift(root: Path) -> None:
    refs = _source_closure(root)
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    value = _result_input(request, refs=refs)
    first = stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)
    before = first.read_bytes()
    assert stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value) == first
    replay = dict(value)
    assert stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", replay) == first
    assert first.read_bytes() == before
    changed = dict(value)
    changed["actor"] = {**value["actor"], "sessionId": "other"}
    with pytest.raises(stage_semantic_recorder.StageSemanticConflict):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", changed)
    context = {
        "semanticResultRef": first.relative_to(root).as_posix(),
        "semanticResultDigest": stage_authority._sha256(first.read_bytes()),
    }
    gate = stage_authority.run_stage_gate(
        EXECUTION_ID, "sources", close_context=context,
        runner=lambda _argv: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    first.write_text("{}\n", encoding="utf-8")
    with pytest.raises(stage_authority.StageAuthorityError, match="semantic result"):
        stage_authority.close_stage(EXECUTION_ID, "sources")
    assert gate.is_file()


def test_gate_requires_semantic_result_and_random_actor_json_cannot_substitute(root: Path) -> None:
    fake = root / "sources/actor.json"
    _json(fake, {"host": "cursor", "modelFamily": "gpt", "sessionId": "fake"})
    with pytest.raises(stage_authority.StageAuthorityError, match="semanticResultRef"):
        stage_authority.run_stage_gate(
            EXECUTION_ID, "sources",
            close_context={"artifactRefs": [{"scope": "execution", "ref": "sources/actor.json"}]},
            runner=lambda _argv: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        )


def test_wrong_stage_and_schema_invalid_result_are_rejected(root: Path) -> None:
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "sources")
    wrong = root / "2.quality/quality_analysis.json"
    _json(wrong, {})
    value = _result_input(request, refs=[wrong.relative_to(root).as_posix()])
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="semantic closure"):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "sources", value)


def test_quality_result_ref_wrong_stage_and_schema_invalid(root: Path) -> None:
    _advance_sources_to_stage(root, "2.quality")
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "2.quality")
    wrong = root / "3.compose/quality_analysis.json"
    _json(wrong, _quality_document())
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="outside 2.quality allowlist"):
        stage_semantic_recorder.record_stage_semantic_result(
            EXECUTION_ID, "2.quality", _result_input(request, refs=[wrong.relative_to(root).as_posix()])
        )
    invalid = root / "posts/article/攻略/西湖攻略/1/2.quality/quality_analysis.json"
    _json(invalid, {})
    with pytest.raises(ValueError, match="schema violation"):
        stage_semantic_recorder.record_stage_semantic_result(
            EXECUTION_ID, "2.quality", _result_input(request, refs=[invalid.relative_to(root).as_posix()])
        )
