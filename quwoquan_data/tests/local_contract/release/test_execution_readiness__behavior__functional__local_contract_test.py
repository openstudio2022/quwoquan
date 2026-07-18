"""Release readiness must bind terminal execution, author, and reviewer evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.article_package import compute_document_sha256  # noqa: E402
from content.execution.runtime_contract import canonical_sha256  # noqa: E402
from verify import verify_execution_readiness as gate  # noqa: E402


EXECUTION_ID = "20260713--travel-homepage-coverage--cn-zhejiang--canary-901"
OBJECT_REF = "/entity/地点/景区/验收景区"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / EXECUTION_ID
    monkeypatch.setattr(gate, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(gate, "content_execution_layout_issues", lambda: [])
    monkeypatch.setattr(gate, "load_execution_manifest", lambda execution_id: {"executionId": execution_id})
    monkeypatch.setattr(
        gate,
        "homepage_media_completeness_report",
        lambda execution_id: {"executionId": execution_id, "passed": True, "issues": []},
    )
    _write(
        root / "_shared/execution_state.json",
        {
            "schema": "quwoquan.content.execution_state",
            "executionId": EXECUTION_ID,
            "completed": ["download_fetch", "build_homepage", "build_validate"],
            "status": "succeeded",
            "updatedAt": "2026-07-13T00:00:00Z",
            "failedObjects": [],
        },
    )
    _write(
        root / "evidence/model_readiness.json",
        {
            "schema": "quwoquan_data.execution_model_readiness",
            "executionId": EXECUTION_ID,
            "ready": True,
            "runtime": "local",
            "author": {
                "model": "composer",
                "modelFamily": "composer",
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": "composer",
                    "cacheHit": False,
                },
            },
            "reviewer": {
                "model": "gpt-5.5",
                "modelFamily": "gpt",
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": "gpt-5.5",
                    "cacheHit": False,
                },
            },
        },
    )
    object_root = root / "entities/地点/景区/验收景区"
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (object_root / stage).mkdir(parents=True, exist_ok=True)
    draft = "# 验收景区\n\n这是一份可追溯的实体主页正文。\n"
    (object_root / "4.draft/page.md").write_text(draft, encoding="utf-8")
    _write(
        object_root / "4.draft/draft_meta.json",
        {
            "schema": "quwoquan_data.draft_meta",
            "stage": "4.draft",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "status": "completed",
            "provider": "cursor_sdk",
            "model": "composer",
            "agentRunId": "author-run-001",
            "promptSha256": "sha256:" + "a" * 64,
            "draftSha256": compute_document_sha256(draft),
            "selfCheck": {"status": "passed", "issues": []},
        },
    )
    _write(
        object_root / "manifest.json",
        {"generator": "agent", "agentRunId": "author-run-001"},
    )
    reviewer_response = {
        "schema": "quwoquan_data.homepage_reviewer_response",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "approved",
        "issues": [],
        "findings": ["内容、素材处置与证据绑定均已独立复核。"],
    }
    result_hash = canonical_sha256(reviewer_response)
    _write(
        object_root / "5.review/reviewer_result.json",
        {
            "schema": "quwoquan_data.reviewer_result",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "provider": "cursor_sdk",
            "model": "gpt-5.5",
            "modelFamily": "gpt",
            "runId": "review-run-001",
            "verdict": "passed",
            "issues": [],
            "findings": reviewer_response["findings"],
            "resultHash": result_hash,
        },
    )
    _write(
        object_root / "5.review/attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {
                "status": "passed",
                "provider": "cursor_sdk",
                "model": "gpt-5.5",
                "modelFamily": "gpt",
                "runId": "review-run-001",
                "resultHash": result_hash,
            },
            "mediaRefReview": {"status": "passed", "issues": []},
            "repair": {"status": "not_required"},
            "finalizationRef": "5.review/finalization_report.json",
            "evidenceIndexRef": "5.review/evidence_index.json",
        },
    )
    return root


def test_execution_readiness__requires_terminal_bound_author_and_reviewer_evidence__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    _fixture(monkeypatch, tmp_path)

    assert gate.execution_readiness_issues(EXECUTION_ID, require_reviewed=True) == []


def test_execution_readiness__rejects_pending_independent_reviewer__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    root = _fixture(monkeypatch, tmp_path)
    path = root / "entities/地点/景区/验收景区/5.review/attestation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["independentReviewer"]["status"] = "pending"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(EXECUTION_ID, require_reviewed=True)

    assert any("independent reviewer is not passed" in issue for issue in issues)


def test_execution_readiness__rejects_synthetic_independent_reviewer_run_id__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    root = _fixture(monkeypatch, tmp_path)
    review_dir = root / "entities/地点/景区/验收景区/5.review"
    reviewer_result_path = review_dir / "reviewer_result.json"
    reviewer_result = json.loads(reviewer_result_path.read_text(encoding="utf-8"))
    reviewer_result["runId"] = f"contract-output:{EXECUTION_ID}"
    reviewer_result_path.write_text(json.dumps(reviewer_result, ensure_ascii=False), encoding="utf-8")
    attestation_path = review_dir / "attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["independentReviewer"]["runId"] = f"contract-output:{EXECUTION_ID}"
    attestation_path.write_text(json.dumps(attestation, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(EXECUTION_ID, require_reviewed=True)

    assert any("runId must be a real Cursor SDK run" in issue for issue in issues)


def test_execution_readiness__rejects_interrupted_execution__local_contract(monkeypatch, tmp_path: Path) -> None:
    root = _fixture(monkeypatch, tmp_path)
    state_path = root / "_shared/execution_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "manual_required"
    state["waitingCheckpoint"] = "build_validate"
    state["failedObjects"] = ["build_validate interrupted"]
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(EXECUTION_ID, require_reviewed=True)

    assert any("execution status is not succeeded" in issue for issue in issues)
    assert any("execution still waiting" in issue for issue in issues)


def test_execution_readiness__requires_homepage_media_closure__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        gate,
        "homepage_media_completeness_report",
        lambda _execution_id: {
            "passed": False,
            "issues": [
                {
                    "code": "DATA.MEDIA.DOWNLOAD_INCOMPLETE",
                    "ref": "普陀山",
                    "message": "页面图片存在 rate_limited 下载缺口",
                }
            ],
        },
    )

    issues = gate.execution_readiness_issues(EXECUTION_ID, require_reviewed=True)

    assert any("homepage media completeness: DATA.MEDIA.DOWNLOAD_INCOMPLETE" in issue for issue in issues)
