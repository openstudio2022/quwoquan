from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution.planning import task_init_projection
from content.execution.planning.request_envelope import _sha256
from content.execution.source_pool import binding as source_pool_binding
from core import paths
from core.source_digest import current_execution_bundle_identity, current_source_definition_snapshot


EXECUTION_ID = "20260901--travel-article-workload-article-1--china--scale-001"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture(root: Path) -> tuple[Path, Path]:
    source = current_source_definition_snapshot().to_document()
    bundle = current_execution_bundle_identity().to_document()
    entity_digest = "sha256:" + "2" * 64
    plan_ref = "data/local/workspace/source-acquisition/scale-source-pools/workload/plan.json"
    evidence_ref = "data/local/workspace/source-acquisition/evidence"
    candidate = {
        "candidateId": "article-candidate-1",
        "carrier": "article",
        "objectRef": "posts/article/article-candidate-1",
        "entityRef": "/entity/地点/景区/青城山",
        "observedEntityRef": "/entity/地点/景区/青城山",
        "sourceRevision": "sha256:" + "3" * 64,
        "sourceDigest": source["digest"],
        "entityCatalogDigest": entity_digest,
    }
    plan = {"candidates": [candidate]}
    plan_path = root / plan_ref
    _write_json(plan_path, plan)
    binding = {
        "poolId": "pool-1",
        "targetScale": "WORKLOAD",
        "workloadMode": "explicit",
        "activeCarriers": ["article"],
        "workloadTargets": {"article": 1},
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": source["digest"],
        "entityCatalogDigest": entity_digest,
        "planRef": plan_ref,
        "planDigest": "sha256:" + "4" * 64,
        "planFileSha256": "sha256:" + "5" * 64,
    }
    selection_stable = {
        "carrier": "article",
        "candidateIds": ["article-candidate-1"],
        "candidateCount": 1,
    }
    selection = {**selection_stable, "selectionDigest": _sha256(selection_stable)}
    envelope_ref = "data/local/workspace/content-campaign-envelopes/travel/M1/china/sequence-001/article.json"
    envelope = {
        "carrier": "article",
        "executionId": EXECUTION_ID,
        "familyRef": "content/travel/article/article",
        "quota": 1,
        "count": 1,
        "retryOf": None,
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": source,
        "executionBundle": bundle,
        "entityCatalogDigest": entity_digest,
        "scaleSourcePool": binding,
        "sourcePoolEvidenceRootRef": evidence_ref,
        "sourcePoolSelection": selection,
    }
    envelope["requestDigest"] = "sha256:" + "6" * 64
    envelope_path = root / envelope_ref
    _write_json(envelope_path, envelope)
    request = {
        "activeCarriers": ["article"],
        "sourceDigest": source["digest"],
        "entityCatalogDigest": entity_digest,
        "sourcePool": {
            "poolId": "pool-1",
            "targetScale": "WORKLOAD",
            "planRef": plan_ref,
            "planDigest": binding["planDigest"],
            "evidenceRootRef": evidence_ref,
        },
        "carrierEnvelopes": [{
            "carrier": "article",
            "executionId": EXECUTION_ID,
            "envelopeRef": envelope_ref,
            "requestDigest": envelope["requestDigest"],
        }],
    }
    request_path = root / envelope_ref.replace("article.json", "work-request.json")
    _write_json(request_path, request)
    (root / evidence_ref).mkdir(parents=True)
    return request_path, root / "data/local/workspace/task-init-inputs/test"


def test_projects_selected_candidates_and_replays_exact_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".qwq_output"
    request_path, destination = _fixture(root)
    request_digest = "sha256:" + "7" * 64
    monkeypatch.setattr(task_init_projection, "_assert_work_request_identity", lambda value: request_digest)
    monkeypatch.setattr(task_init_projection, "load_campaign_envelope", lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(source_pool_binding, "validate_bound_scale_source_pool", lambda *args, **kwargs: None)
    monkeypatch.setattr(task_init_projection, "validate_bound_scale_source_pool", lambda *args, **kwargs: json.loads((root / "data/local/workspace/source-acquisition/scale-source-pools/workload/plan.json").read_text()))
    monkeypatch.setattr(task_init_projection, "validate_lane_source_pool_selection", lambda value, **kwargs: dict(value))

    first = task_init_projection.project_task_init_inputs(
        work_request_path=request_path,
        output_dir=destination,
        output_root=root,
    )
    second = task_init_projection.project_task_init_inputs(
        work_request_path=request_path,
        output_dir=destination,
        output_root=root,
    )

    assert first == second
    artifact = first["artifacts"][0]
    demand = json.loads((root / artifact["carrierDemandRef"]).read_text())
    bindings = json.loads((root / artifact["candidateBindingsRef"]).read_text())
    assert artifact["executionId"] == EXECUTION_ID
    assert demand["executionId"] == artifact["executionId"]
    assert demand["workRequestDigest"] == request_digest
    assert demand["quota"] == 1
    assert bindings["candidateCount"] == 1
    assert artifact["quota"] == demand["quota"]
    assert artifact["candidateCount"] == bindings["candidateCount"]
    assert bindings["targets"] == [{
        "entityType": "地点/景区",
        "name": "青城山",
        "publishAngle": "攻略",
        "publishTitle": "article-candidate-1",
        "publishSeq": 1,
    }]


def test_rejects_selected_candidate_identity_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".qwq_output"
    request_path, destination = _fixture(root)
    plan_path = root / "data/local/workspace/source-acquisition/scale-source-pools/workload/plan.json"
    plan = json.loads(plan_path.read_text())
    plan["candidates"][0]["sourceDigest"] = "sha256:" + "9" * 64
    _write_json(plan_path, plan)
    monkeypatch.setattr(task_init_projection, "_assert_work_request_identity", lambda value: "sha256:" + "7" * 64)
    monkeypatch.setattr(task_init_projection, "load_campaign_envelope", lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(task_init_projection, "validate_bound_scale_source_pool", lambda *args, **kwargs: plan)
    monkeypatch.setattr(task_init_projection, "validate_lane_source_pool_selection", lambda value, **kwargs: dict(value))

    with pytest.raises(task_init_projection.TaskInitProjectionError, match="source identity drift"):
        task_init_projection.project_task_init_inputs(
            work_request_path=request_path,
            output_dir=destination,
            output_root=root,
        )
