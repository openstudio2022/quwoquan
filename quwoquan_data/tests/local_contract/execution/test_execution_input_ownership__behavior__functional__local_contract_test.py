# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-003
"""Reusable input, execution output, and publish ownership contract."""
from __future__ import annotations

import json

from core import paths
from core.control_types import TargetSelector
from content.execution import workspace
from content.execution.execution_terminal import (
    InvalidTerminalExecutionEvidenceError,
    TerminalExecutionEvidence,
)
from content.execution.planning.recipe.model import RuntimeExecutionRequest
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from verify import verify_runtime_input_ownership


EXECUTION_ID = "20260711--travel-homepage-ownership--test-region-a--pilot-001"
INCOMPLETE_EXECUTION_ID = "20260711--travel-video-ownership--test-region-b--pilot-002"
TERMINAL_EXECUTION_ID = "20260711--travel-image-ownership--test-region-c--pilot-003"
TERMINAL_DRIFT_EXECUTION_ID = "20260711--travel-article-ownership--test-region-d--pilot-004"


def test_execution_plan_is_runtime_output_not_control_plane_state():
    spec_path = paths.execution_spec_path(EXECUTION_ID)
    assert spec_path == paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID / "0.plan" / "execution_spec.yaml"
    assert "control_plane/tasks" not in spec_path.as_posix()


def test_execution_root_allowlist_matches_work_package_contract():
    assert paths.EXECUTION_ROOT_ALLOWED_ENTRIES == frozenset(
        {
            "0.plan",
            "sources",
            "entities",
            "posts",
            "_shared",
            "evidence",
            "execution_manifest.json",
            "publish_ref.json",
        }
    )


def test_reusable_inputs_are_repo_owned_and_outside_output():
    for source in (
        paths.FAMILIES_ROOT,
        paths.CONTROL_PLANE_SHARED_ROOT,
        paths.SCHEMA_ROOT,
    ):
        assert not str(source).startswith(str(paths.OUTPUT_ROOT))
        assert not str(source).startswith(str(paths.PUBLISH_ROOT))


def test_publish_does_not_contain_runtime_or_configuration_files():
    if not paths.PUBLISH_ROOT.is_dir():
        return
    forbidden_names = {
        "execution_manifest.json",
        "execution_spec.yaml",
        "runtime_state.json",
        "execution_state.json",
        "prompt.md",
    }
    assert not [path for path in paths.PUBLISH_ROOT.rglob("*") if path.name in forbidden_names]
    assert not list(paths.PUBLISH_ROOT.rglob("*.recipe.yaml"))
    assert not list(paths.PUBLISH_ROOT.rglob("*.schema.json"))


def test_execution_publish_ref_binds_only_canonical_objects(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path)
    root = tmp_path / EXECUTION_ID
    root.mkdir(parents=True)

    path = workspace.write_publish_ref(
        EXECUTION_ID,
        entity_refs=["/entity/地点/景区/验收景区"],
        post_refs=["posts/article/攻略/验收景区/1"],
    )

    payload = workspace.read_json(path)
    assert payload == {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": EXECUTION_ID,
        "canonicalPublishRoot": "canonical-publish",
        "publishedRefs": {
            "entities": ["地点/景区/验收景区"],
            "posts": ["posts/article/攻略/验收景区/1"],
        },
        "publishDiscards": [],
    }
    assert "releaseId" not in payload


def test_runtime_input_gate_uses_the_typed_execution_request_contract(tmp_path, monkeypatch):
    execution_root = tmp_path / EXECUTION_ID
    plan_root = execution_root / "0.plan"
    plan_root.mkdir(parents=True)
    (execution_root / "execution_manifest.json").write_text(
        json.dumps({"executionId": EXECUTION_ID}),
        encoding="utf-8",
    )
    request = RuntimeExecutionRequest(
        family_ref="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector=TargetSelector.SOURCE_READY_PRIORITY,
        count=1,
        quota=1,
        execution_authority=synthetic_governed_execution_authority(),
        topic=None,
        source_providers=(),
        target_names=("测试实体甲",),
    )
    (plan_root / "request.json").write_text(
        json.dumps(request.to_document(), ensure_ascii=False),
        encoding="utf-8",
    )
    (plan_root / "target_set.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)

    assert verify_runtime_input_ownership._request_issues() == []


def test_runtime_input_gate_fails_closed_for_incomplete_execution_work_package(
    tmp_path,
    monkeypatch,
):
    execution_root = tmp_path / INCOMPLETE_EXECUTION_ID
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(verify_runtime_input_ownership, "REPO_ROOT", tmp_path)

    assert verify_runtime_input_ownership._request_issues() == [
        f"{INCOMPLETE_EXECUTION_ID}/0.plan/request.json: execution request is missing"
    ]


def test_runtime_input_gate_skips_current_schema_for_valid_superseded_old_request(
    tmp_path,
    monkeypatch,
):
    execution_root = tmp_path / TERMINAL_EXECUTION_ID
    plan_root = execution_root / "0.plan"
    plan_root.mkdir(parents=True)
    (execution_root / "execution_manifest.json").write_text(
        json.dumps({"executionId": TERMINAL_EXECUTION_ID}),
        encoding="utf-8",
    )
    (plan_root / "request.json").write_text(
        json.dumps(
            {
                "executionAuthority": {
                    "mode": "bounded_explicit",
                    "policyId": "historical-without-current-heartbeats",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "load_terminal_execution_evidence",
        lambda root: TerminalExecutionEvidence(
            decision="superseded",
            receipt={
                "decision": "superseded",
                "evidenceDisposition": "protected_read_only",
            },
            path=root / "_shared" / "reconciliation" / "supersession.json",
        ),
    )

    class CurrentRequestSchemaMustNotRun:
        @staticmethod
        def from_document(_document: object) -> object:
            raise AssertionError("superseded historical request was revalidated")

    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "RuntimeExecutionRequest",
        CurrentRequestSchemaMustNotRun,
    )

    assert verify_runtime_input_ownership._request_issues() == []


def test_runtime_input_gate_reports_only_terminal_evidence_drift(
    tmp_path,
    monkeypatch,
):
    execution_root = tmp_path / TERMINAL_DRIFT_EXECUTION_ID
    plan_root = execution_root / "0.plan"
    plan_root.mkdir(parents=True)
    (execution_root / "execution_manifest.json").write_text(
        json.dumps({"executionId": TERMINAL_DRIFT_EXECUTION_ID}),
        encoding="utf-8",
    )
    (plan_root / "request.json").write_text(
        json.dumps({"executionAuthority": {"mode": "bounded_explicit"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(verify_runtime_input_ownership, "REPO_ROOT", tmp_path)

    def reject_terminal(_root):
        raise InvalidTerminalExecutionEvidenceError(
            "execution supersession root inventory drift"
        )

    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "load_terminal_execution_evidence",
        reject_terminal,
    )

    class CurrentRequestSchemaMustNotRun:
        @staticmethod
        def from_document(_document: object) -> object:
            raise AssertionError(
                "terminal evidence drift must remain the first and only blocker"
            )

    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "RuntimeExecutionRequest",
        CurrentRequestSchemaMustNotRun,
    )

    assert verify_runtime_input_ownership._request_issues() == [
        f"{TERMINAL_DRIFT_EXECUTION_ID}: invalid terminal execution evidence: "
        "execution supersession root inventory drift"
    ]


def test_runtime_input_gate_does_not_hide_live_journal_failure(
    tmp_path,
    monkeypatch,
):
    execution_root = tmp_path / INCOMPLETE_EXECUTION_ID
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(verify_runtime_input_ownership, "REPO_ROOT", tmp_path)

    def reject_live_journal(_root):
        raise ValueError("execution state journal drift")

    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "load_terminal_execution_evidence",
        reject_live_journal,
    )

    assert verify_runtime_input_ownership._request_issues() == [
        f"{INCOMPLETE_EXECUTION_ID}: invalid terminal execution evidence: "
        "execution state journal drift",
        f"{INCOMPLETE_EXECUTION_ID}/0.plan/request.json: execution request is missing",
    ]


def test_runtime_input_gate_ignores_auxiliary_evidence_namespace(tmp_path, monkeypatch):
    evidence_root = tmp_path / "video" / "evidence" / "asset_reviews"
    evidence_root.mkdir(parents=True)
    (evidence_root / "review.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(verify_runtime_input_ownership, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(verify_runtime_input_ownership, "REPO_ROOT", tmp_path)

    assert verify_runtime_input_ownership._request_issues() == []
