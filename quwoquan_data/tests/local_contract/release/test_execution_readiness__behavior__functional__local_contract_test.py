"""Release readiness must bind terminal execution, author, and reviewer evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.article_package import compute_document_sha256  # noqa: E402
from core.control_types import ContentGenerator, ContentType  # noqa: E402
from core.io import read_json  # noqa: E402
from content.execution.closure import post_review as post_review_closure
from content.execution.runtime_contract import canonical_sha256  # noqa: E402
from verify import verify_execution_readiness as gate  # noqa: E402
from content.execution.model_contract import governed_cursor_grok_model


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--pilot-901"


def _readiness_layout_issues(expected_execution_id: str):
    def issues(
        *,
        execution_id: str | None = None,
        allow_succeeded_terminal: bool = False,
    ) -> list[str]:
        assert execution_id == expected_execution_id
        assert allow_succeeded_terminal is True
        return []

    return issues


OBJECT_REF = "/entity/地点/景区/验收景区"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _rights_asset(
    asset_id: str,
    digest_char: str,
    *,
    status: str = "verified",
) -> dict[str, object]:
    proof = f"https://media.example/{asset_id}/authorization" if status == "verified" else ""
    decision = "commercial_allowed" if proof else (
        "blocked" if status == "restricted" else "research_allowed"
    )
    digest = "sha256:" + digest_char * 64
    return {
        "assetId": asset_id,
        "asset": {
            "ref": f"cas/{asset_id}.bin",
            "sha256": digest,
            "bytes": 16,
        },
        "acquisitionStatus": "acquired",
        "rightsStatus": status,
        "authorizationRequired": not bool(proof),
        "distributionDecision": decision,
        "sourceUrl": f"https://media.example/{asset_id}",
        "platform": "test-professional-library",
        "creator": "测试摄影师",
        "capturedAt": "2026-08-05T00:00:00Z",
        "contentSha256": digest,
        "license": "CC BY 4.0" if proof else "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": proof,
        "rightsIssues": [] if proof else ["distribution authorization is unverified"],
    }


def _write_transaction(
    root: Path,
    object_root: Path,
    *,
    content_type: ContentType,
    manifest: dict[str, object],
    rights: list[dict[str, object]],
) -> Path:
    transaction = gate._transaction_object(root, object_root, content_type)
    _write(
        transaction.parent / "object_transaction_package.json",
        {
            "schema": "quwoquan_data.object_transaction_package",
            "executionId": root.name,
            "target": {"packageObjectRef": "object"},
            "objectClosureDigest": "sha256:" + "f" * 64,
        },
    )
    _write(transaction / "manifest.json", manifest)
    _write(
        transaction / "rights.json",
        {"schema": "quwoquan_data.asset_rights_closure", "assets": rights},
    )
    for row in rights:
        blob = row["asset"]
        assert isinstance(blob, dict)
        path = transaction.parent / str(blob["ref"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image-test-bytes")
    return transaction


def _fixture(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / EXECUTION_ID
    monkeypatch.setattr(gate, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(
        gate,
        "content_execution_layout_issues",
        _readiness_layout_issues(EXECUTION_ID),
    )
    monkeypatch.setattr(gate, "load_execution_manifest", lambda execution_id: {"executionId": execution_id})
    monkeypatch.setattr(
        gate,
        "homepage_media_completeness_report",
        lambda execution_id: {"executionId": execution_id, "passed": True, "issues": []},
    )
    monkeypatch.setattr(
        gate,
        "_resolve_homepage_quota_verdict",
        lambda _execution_id: SimpleNamespace(
            qualified_refs=("地点/景区/验收景区",),
            qualified_count=1,
        ),
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
            "semanticSelectionId": "default",
            "provider": "cursor_sdk",
            "ready": True,
            "runtime": "local",
            "author": {
                "model": governed_cursor_grok_model(),
                "modelFamily": "grok",
                "modelParameters": [
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "false"},
                ],
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": governed_cursor_grok_model(),
                    "modelParameters": [
                        {"id": "effort", "value": "high"},
                        {"id": "fast", "value": "false"},
                    ],
                    "cacheHit": False,
                },
            },
            "reviewer": {
                "model": "composer-2.5",
                "modelFamily": "composer",
                "modelParameters": [],
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": "composer-2.5",
                    "modelParameters": [],
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
            "model": governed_cursor_grok_model(),
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
            "model": "composer-2.5",
            "modelFamily": "composer",
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
                "model": "composer-2.5",
                "modelFamily": "composer",
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

    assert gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    ) == []


def test_execution_readiness__accepts_auto_for_distinct_author_and_reviewer_runs__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _fixture(monkeypatch, tmp_path)
    model_path = root / "evidence/model_readiness.json"
    readiness = json.loads(model_path.read_text(encoding="utf-8"))
    for role in ("author", "reviewer"):
        readiness[role]["model"] = "auto"
        readiness[role]["modelFamily"] = "auto"
        readiness[role]["modelParameters"] = []
        readiness[role]["startup"]["model"] = "auto"
        readiness[role]["startup"]["modelParameters"] = []
    _write(model_path, readiness)

    object_root = root / "entities/地点/景区/验收景区"
    draft_path = object_root / "4.draft/draft_meta.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["model"] = "auto"
    _write(draft_path, draft)
    result_path = object_root / "5.review/reviewer_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["model"] = "auto"
    result["modelFamily"] = "auto"
    _write(result_path, result)
    attestation_path = object_root / "5.review/attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["independentReviewer"]["model"] = "auto"
    attestation["independentReviewer"]["modelFamily"] = "auto"
    _write(attestation_path, attestation)

    assert gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    ) == []


def test_execution_readiness__rejects_reviewer_reusing_author_run__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _fixture(monkeypatch, tmp_path)
    object_root = root / "entities/地点/景区/验收景区"
    result_path = object_root / "5.review/reviewer_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["runId"] = "author-run-001"
    _write(result_path, result)
    attestation_path = object_root / "5.review/attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["independentReviewer"]["runId"] = "author-run-001"
    _write(attestation_path, attestation)

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    )

    assert any("reviewer must use a distinct Cursor SDK run" in issue for issue in issues)


def test_execution_readiness__rejects_pending_independent_reviewer__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    root = _fixture(monkeypatch, tmp_path)
    path = root / "entities/地点/景区/验收景区/5.review/attestation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["independentReviewer"]["status"] = "pending"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    )

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

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    )

    assert any("reviewer_result.json: invalid evidence" in issue for issue in issues)
    assert any("attestation.json: invalid evidence" in issue for issue in issues)


def test_execution_readiness__rejects_interrupted_execution__local_contract(monkeypatch, tmp_path: Path) -> None:
    root = _fixture(monkeypatch, tmp_path)
    state_path = root / "_shared/execution_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "manual_required"
    state["waitingCheckpoint"] = "build_validate"
    state["failedObjects"] = ["build_validate interrupted"]
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    )

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
                    "ref": "测试实体甲",
                    "message": "页面图片存在 rate_limited 下载缺口",
                }
            ],
        },
    )

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=True, mode="calibration"
    )

    assert any("homepage media completeness: DATA.MEDIA.DOWNLOAD_INCOMPLETE" in issue for issue in issues)


def _article_fixture(monkeypatch, tmp_path: Path) -> tuple[str, Path]:
    execution_id = "20260722--travel-article-supply--test-region-a--pilot-902"
    root = tmp_path / execution_id
    monkeypatch.setattr(gate, "DATA_EXECUTIONS_ROOT", tmp_path)
    monkeypatch.setattr(
        gate,
        "content_execution_layout_issues",
        _readiness_layout_issues(execution_id),
    )
    monkeypatch.setattr(
        gate,
        "load_execution_manifest",
        lambda value: {"executionId": value},
    )
    monkeypatch.setattr(
        post_review_closure.spec_contract,
        "approved_quota",
        lambda _execution_id: 1,
    )
    _write(
        root / "_shared/execution_state.json",
        {
            "schema": "quwoquan.content.execution_state",
            "executionId": execution_id,
            "completed": ["post_author", "post_review", "publish"],
            "status": "succeeded",
            "updatedAt": "2026-07-22T00:00:00Z",
            "failedObjects": [],
        },
    )
    _write(
        root / "evidence/model_readiness.json",
        {
            "schema": "quwoquan_data.execution_model_readiness",
            "executionId": execution_id,
            "semanticSelectionId": "default",
            "provider": "cursor_sdk",
            "ready": True,
            "runtime": "local",
            "author": {
                "model": governed_cursor_grok_model(),
                "modelFamily": "grok",
                "modelParameters": [
                    {"id": "effort", "value": "high"},
                    {"id": "fast", "value": "false"},
                ],
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": governed_cursor_grok_model(),
                    "modelParameters": [
                        {"id": "effort", "value": "high"},
                        {"id": "fast", "value": "false"},
                    ],
                    "cacheHit": False,
                },
            },
            "reviewer": {
                "model": "composer-2.5",
                "modelFamily": "composer",
                "modelParameters": [],
                "startup": {
                    "ready": True,
                    "status": "finished",
                    "errorClass": "",
                    "errorCode": "",
                    "httpStatus": None,
                    "runtime": "local",
                    "model": "composer-2.5",
                    "modelParameters": [],
                    "cacheHit": False,
                },
            },
        },
    )
    object_ref = "测试实体甲__article_source_a"
    object_root = root / "posts/article/攻略/测试文章/1"
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (object_root / stage).mkdir(parents=True, exist_ok=True)
    draft = "# 测试文章\n\n这是一篇基于来源证据创作的测试文章。\n"
    (object_root / "4.draft/draft.article.md").write_text(draft, encoding="utf-8")
    _write(
        object_root / "4.draft/draft_meta.json",
        {
            "schema": "quwoquan_data.draft_meta",
            "stage": "4.draft",
            "executionId": execution_id,
            "executionBinding": "frozen",
            "objectRef": object_ref,
            "ref": object_ref,
            "generator": "agent",
            "status": "completed",
            "provider": "cursor_sdk",
            "model": governed_cursor_grok_model(),
            "agentRunId": "author-run-902",
            "promptSha256": "sha256:" + "a" * 64,
            "draftSha256": compute_document_sha256(draft),
            "selfCheck": {"status": "passed", "issues": []},
        },
    )
    _write(
        object_root / "manifest.json",
        {
            "generator": "agent",
            "contentType": "article",
            "generatorModel": governed_cursor_grok_model(),
        },
    )
    response = {
        "schema": "quwoquan_data.post_reviewer_response",
        "executionId": execution_id,
        "objectRef": object_ref,
        "decision": "approved",
        "issues": [],
        "findings": ["已核对正文、来源和实体绑定。"],
    }
    result_hash = canonical_sha256(response)
    _write(
        object_root / "5.review/reviewer_result.json",
        {
            "schema": "quwoquan_data.reviewer_result",
            "stage": "5.review",
            "executionId": execution_id,
            "executionBinding": "frozen",
            "objectRef": object_ref,
            "provider": "cursor_sdk",
            "model": "composer-2.5",
            "modelFamily": "composer",
            "runId": "review-run-902",
            "verdict": "passed",
            "issues": [],
            "findings": response["findings"],
            "resultHash": result_hash,
        },
    )
    _write(
        object_root / "5.review/attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "stage": "5.review",
            "executionId": execution_id,
            "executionBinding": "frozen",
            "objectRef": object_ref,
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {
                "status": "passed",
                "provider": "cursor_sdk",
                "model": "composer-2.5",
                "modelFamily": "composer",
                "runId": "review-run-902",
                "resultHash": result_hash,
            },
            "mediaRefReview": {"status": "passed", "issues": []},
            "repair": {"status": "not_required"},
            "finalizationRef": "5.review/finalization_report.json",
            "evidenceIndexRef": "5.review/evidence_index.json",
        },
    )
    _write(
        root / "_shared/post_review_closure.json",
        {
            "schema": "quwoquan_data.post_review_closure",
            "executionId": execution_id,
            "carrier": "article",
            "approvedQuota": 1,
            "objects": [
                {
                    "objectRef": object_ref,
                    "publishRef": "posts/article/攻略/测试文章/1",
                    "disposition": "qualified",
                    "issues": [],
                }
            ],
        },
    )
    cover = _rights_asset("article-cover", "a")
    body = _rights_asset("article-body", "b")
    _write_transaction(
        root,
        object_root,
        content_type=ContentType.ARTICLE,
        manifest={
            "contentType": "article",
            "publishMediaMode": "same_source_illustrated",
            "assets": [
                {
                    "assetId": "article-cover",
                    "kind": "image",
                    "role": "cover",
                    "sourceUnitRef": "sources/article-source-a/source.md",
                    "sha256": cover["contentSha256"],
                },
                {
                    "assetId": "article-body",
                    "kind": "image",
                    "role": "detail",
                    "sourceUnitRef": "sources/article-source-a/source.md",
                    "sha256": body["contentSha256"],
                },
            ],
            "imageBindings": [
                {"assetId": "article-cover"},
                {"assetId": "article-body"},
            ],
        },
        rights=[cover, body],
    )
    return execution_id, object_root


def test_execution_readiness__uses_post_objects_for_article_execution__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, _object_root = _article_fixture(monkeypatch, tmp_path)

    assert gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="research"
    ) == []


def test_commercial_readiness_ignores_discarded_but_calibration_audits_it(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    root = tmp_path / execution_id
    discarded_root = root / "posts/article/攻略/丢弃文章/1"
    for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review"):
        (discarded_root / stage).mkdir(parents=True, exist_ok=True)
    closure_path = root / "_shared/post_review_closure.json"
    closure = read_json(closure_path)
    closure["objects"].append(
        {
            "objectRef": "测试实体乙__article_source_b",
            "publishRef": "posts/article/攻略/丢弃文章/1",
            "disposition": "discarded",
            "issues": ["independent reviewer rejected the object"],
        }
    )
    _write(closure_path, closure)

    assert gate.execution_readiness_issues(
        execution_id,
        require_reviewed=True,
        mode="commercial",
    ) == []
    calibration_issues = gate.execution_readiness_issues(
        execution_id,
        require_reviewed=True,
        mode="calibration",
    )

    assert any("丢弃文章" in issue for issue in calibration_issues)
    assert object_root.is_dir()


def test_calibration_readiness_always_expands_per_object_issues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """删掉 pass_rate 后，calibration 曾是唯一会完全失去 veto 的路径。"""
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    result_path = object_root / "5.review/reviewer_result.json"
    result = read_json(result_path)
    result["verdict"] = "failed"
    result["issues"] = ["calibration review regression"]
    _write(result_path, result)

    issues = gate.execution_readiness_issues(
        execution_id,
        require_reviewed=True,
        mode="calibration",
    )

    assert any("independent reviewer did not pass" in issue for issue in issues)


def test_readiness_reports_rates_as_statistics_without_blocking(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """配图率/合格率只作为趋势统计随 outcome 返回，不参与准出判定。"""
    execution_id, _object_root = _article_fixture(monkeypatch, tmp_path)

    outcome = gate.execution_readiness_outcome(
        execution_id,
        require_reviewed=True,
        mode="research",
    )

    assert outcome.issues == []
    statistics = outcome.statistics or {}
    assert statistics["selectedCount"] == 1
    assert statistics["passedCount"] == 1
    assert statistics["objectPassRate"] == 1.0
    assert statistics["discardedCount"] == 0
    assert "illustratedRate" in statistics
    assert not any(
        "pass rate below contract" in issue or "illustrated rate below contract" in issue
        for issue in outcome.issues
    )


def test_readiness_blocks_only_when_no_qualified_object_remains(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """批次级唯一硬条件是「至少 1 个合格对象」。"""
    execution_id, _object_root = _article_fixture(monkeypatch, tmp_path)
    root = tmp_path / execution_id
    closure_path = root / "_shared/post_review_closure.json"
    closure = read_json(closure_path)
    for row in closure["objects"]:
        row["disposition"] = "discarded"
        row["issues"] = ["independent reviewer rejected the object"]
    _write(closure_path, closure)

    outcome = gate.execution_readiness_outcome(
        execution_id,
        require_reviewed=True,
        mode="commercial",
    )

    assert any(
        "no qualified content object" in issue for issue in outcome.issues
    )


def test_commercial_readiness_still_blocks_issue_on_qualified_object(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    result_path = object_root / "5.review/reviewer_result.json"
    result = read_json(result_path)
    result["verdict"] = "failed"
    result["issues"] = ["commercial review regression"]
    _write(result_path, result)

    issues = gate.execution_readiness_issues(
        execution_id,
        require_reviewed=True,
        mode="commercial",
    )

    assert any("independent reviewer did not pass" in issue for issue in issues)


@pytest.mark.parametrize("status", ["unverified", "unknown"])
def test_research_readiness_accepts_unverified_or_unknown_but_commercial_rejects_it(
    monkeypatch,
    tmp_path: Path,
    status: str,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    transaction = gate._transaction_object(
        tmp_path / execution_id, object_root, ContentType.ARTICLE
    )
    rights_path = transaction / "rights.json"
    rights = read_json(rights_path)
    for row in rights["assets"]:
        row.update(
            {
                "rightsStatus": status,
                "authorizationRequired": True,
                "distributionDecision": "research_allowed",
                "authorizationProof": "",
                "license": "unknown",
                "rightsIssues": ["distribution authorization is unverified"],
            }
        )
    _write(rights_path, rights)

    assert gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="research"
    ) == []
    commercial = gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="commercial"
    )
    assert any("requires verified commercial_allowed" in issue for issue in commercial)


def test_research_readiness_rejects_restricted_generated_or_missing_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    transaction = gate._transaction_object(
        tmp_path / execution_id, object_root, ContentType.ARTICLE
    )
    rights_path = transaction / "rights.json"
    rights = read_json(rights_path)
    rights["assets"][0].update(
        {
            "rightsStatus": "restricted",
            "authorizationRequired": True,
            "distributionDecision": "blocked",
            "authorizationProof": "",
            "rightsIssues": ["platform distribution is restricted"],
            "sourceUseMode": "self_generated_original",
        }
    )
    rights["assets"][1].pop("termsUrl")
    rights["assets"][1].pop("authorizationProof")
    rights["assets"][1].pop("rightsIssues")
    _write(rights_path, rights)

    issues = gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="research"
    )

    assert any("research asset is blocked" in issue for issue in issues)
    assert any("generated image/video asset is blocked" in issue for issue in issues)
    assert any("lacks provenance field termsUrl" in issue for issue in issues)
    assert any("lacks authorizationProof/rightsIssues fields" in issue for issue in issues)


def test_research_readiness_keeps_article_media_and_review_safety_hard_gates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    transaction = gate._transaction_object(
        tmp_path / execution_id, object_root, ContentType.ARTICLE
    )
    manifest_path = transaction / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["assets"][1]["sourceUnitRef"] = "sources/other/source.md"
    _write(manifest_path, manifest)
    attestation_path = object_root / "5.review/attestation.json"
    attestation = read_json(attestation_path)
    attestation["mediaRefReview"] = {
        "status": "failed",
        "issues": ["safety review regression"],
    }
    _write(attestation_path, attestation)

    issues = gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="research"
    )

    assert any("same-source cover and body images" in issue for issue in issues)
    assert any("media/reference review did not pass" in issue for issue in issues)


def test_research_readiness_requires_reviewed_objects(monkeypatch, tmp_path: Path) -> None:
    _fixture(monkeypatch, tmp_path)

    issues = gate.execution_readiness_issues(
        EXECUTION_ID, require_reviewed=False, mode="research"
    )

    assert issues == ["research readiness requires independently reviewed objects"]


def test_research_video_admission_requires_real_playable_bytes(tmp_path: Path) -> None:
    root = tmp_path / "20260805--travel-video-supply--test-region-a--pilot-903"
    object_root = root / "posts/video/体验/测试视频/1"
    video = _rights_asset("video-main", "c")
    poster = _rights_asset("video-poster", "d")
    transaction = _write_transaction(
        root,
        object_root,
        content_type=ContentType.VIDEO,
        manifest={
            "contentType": "video",
            "assets": [
                {
                    "assetId": "video-main",
                    "kind": "video",
                    "mimeType": "video/mp4",
                    "sha256": video["contentSha256"],
                    "durationMs": 3000,
                    "width": 1080,
                    "height": 1920,
                    "codec": "h264",
                    "posterAssetId": "video-poster",
                },
                {
                    "assetId": "video-poster",
                    "kind": "image",
                    "role": "cover",
                    "sha256": poster["contentSha256"],
                },
            ],
        },
        rights=[video, poster],
    )
    video_path = transaction.parent / "cas/video-main.bin"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42data")

    assert gate._asset_admission_issues(
        transaction, content_type=ContentType.VIDEO, mode="research"
    ) == ([], "media")

    video_path.write_bytes(b"x" * 16)
    issues, _state = gate._asset_admission_issues(
        transaction, content_type=ContentType.VIDEO, mode="research"
    )
    assert any("playable MP4/WebM" in issue for issue in issues)


def test_execution_readiness__accepts_structured_image_generator__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    (object_root / "4.draft/draft.article.md").unlink()
    draft_meta_path = object_root / "4.draft/draft_meta.json"
    draft_meta = read_json(draft_meta_path)
    draft_meta["generator"] = ContentGenerator.IMAGE_EVIDENCE_PACK.value
    draft_meta["draftSha256"] = "sha256:" + "b" * 64
    _write(draft_meta_path, draft_meta)
    _write(
        object_root / "manifest.json",
        {
            "generator": ContentGenerator.IMAGE_EVIDENCE_PACK.value,
            "contentType": ContentType.IMAGE.value,
        },
    )
    model_readiness = read_json(
        tmp_path / execution_id / "evidence/model_readiness.json"
    )

    assert gate._reviewed_object_issues(
        tmp_path / execution_id,
        object_root,
        execution_id,
        model_readiness=model_readiness,
        content_type=ContentType.IMAGE,
    ) == []


def test_execution_readiness__rejects_deterministic_post_reviewer__local_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id, object_root = _article_fixture(monkeypatch, tmp_path)
    result_path = object_root / "5.review/reviewer_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["provider"] = "review_controller"
    result["model"] = "deterministic"
    result["modelFamily"] = "deterministic"
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    issues = gate.execution_readiness_issues(
        execution_id, require_reviewed=True, mode="calibration"
    )

    assert any("reviewer model drift" in issue for issue in issues)
