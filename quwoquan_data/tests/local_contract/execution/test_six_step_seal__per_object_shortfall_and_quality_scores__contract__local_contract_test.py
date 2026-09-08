# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038.t7
"""4.draft 逐对象短缺、review 覆盖集合以 002 resultRefs 为准、qualityScores 只记录透传。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.execution import seal as seal_module  # noqa: E402
from content.execution.receipt_chain import (  # noqa: E402
    ReceiptChainError,
    validate_publish_review_chain,
)
from core import paths  # noqa: E402
from core.control_types import QUALITY_DIMENSIONS_BY_CARRIER  # noqa: E402
from verify import stage_artifacts  # noqa: E402

EXECUTION_ID = "20260907--travel-article-six-step-m1000--shortfall--pilot-001"
GOOD = "posts/article/导览/西湖速览/1"
BAD_TAG = "posts/article/导览/灵隐寺速览/1"
EMPTY = "posts/article/导览/六和塔速览/1"
TARGETS = [GOOD, BAD_TAG, EMPTY]
AUTHOR = {
    "host": "cursor",
    "modelFamily": "claude",
    "sessionId": "author-session",
    "invocation": {"provider": "anthropic", "model": "claude", "runId": "run-author"},
}
REVIEWER = {
    "host": "cursor",
    "modelFamily": "claude",
    "sessionId": "reviewer-session",
    "invocation": {"provider": "anthropic", "model": "claude", "runId": "run-reviewer"},
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _source_unit(root: Path, target_ref: str, unit_id: str, plan_ref: str) -> None:
    unit = root / "sources" / unit_id
    source_md = f"# {target_ref.split('/')[3]}\n\n正文。\n"
    _write(unit / "source.md", source_md)
    _write(unit / "snapshot.raw", b"{}")
    _write(unit / "assets/index.json", _canonical({"assets": []}))
    meta = {
        "schema": "quwoquan_data.atomic_source_unit", "stage": "1.download", "executionId": EXECUTION_ID,
        "executionBinding": "frozen", "sourceUnitId": unit_id, "sourcePlanRef": plan_ref,
        "sourcePlanDigest": "sha256:" + "b" * 64, "chosenCandidateDigest": "sha256:" + "c" * 64,
        "sourceId": "zh_wikipedia", "targetRef": target_ref, "carrier": "article", "title": "条目",
        "sourceClass": "encyclopedia", "sourceUseMode": "factual_reference_only", "purpose": "主题条目",
        "rightsClue": "CC BY-SA 4.0", "canonicalUrl": "https://zh.wikipedia.org/wiki/x",
        "fetchedAt": "2026-09-07T00:00:00+00:00", "rawSha256": _sha(b"{}"),
        "sourceMarkdownSha256": _sha(source_md.encode("utf-8")),
    }
    _write(unit / "meta.json", _canonical(meta))
    refs = {
        "schema": "quwoquan_data.object_source_refs", "executionId": EXECUTION_ID, "objectRef": target_ref,
        "sources": [{
            "sourceUnitId": unit_id, "sourceRef": f"sources/{unit_id}/source.md",
            "metaRef": f"sources/{unit_id}/meta.json", "sourcePlanRef": plan_ref,
            "sourcePlanDigest": "sha256:" + "b" * 64, "chosenCandidateDigest": "sha256:" + "c" * 64,
            "sourceId": "zh_wikipedia", "sourceClass": "encyclopedia", "targetRefs": [target_ref],
        }],
    }
    _write(root / target_ref / "1.download/source_refs.json", _canonical(refs))


@pytest.fixture()
def execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tasks = tmp_path / "data/tasks"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks)
    root = tasks / EXECUTION_ID
    _write(root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": EXECUTION_ID}))
    target_set = {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "data/local/workspace/x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 3},
        "targetCount": 3,
        "targetRefs": TARGETS,
        "targets": [
            {"name": "西湖", "entityType": "地点/景区", "publishAngle": "导览", "publishTitle": "西湖速览", "publishSeq": 1},
            {"name": "灵隐寺", "entityType": "地点/景区", "publishAngle": "导览", "publishTitle": "灵隐寺速览", "publishSeq": 1},
            {"name": "六和塔", "entityType": "地点/景区", "publishAngle": "导览", "publishTitle": "六和塔速览", "publishSeq": 1},
        ],
    }
    _write(root / "0.plan/target_set.json", _canonical(target_set))
    plan_ref = "sources/plans/" + "a" * 64 + ".json"
    _write(root / plan_ref, _canonical({"schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID, "targets": []}))
    for index, target in enumerate(TARGETS):
        _source_unit(root, target, f"zh_wikipedia__{index:016x}", plan_ref)
    return root


def _seal(root: Path, stage: str, actor: dict, verdict: str = "pass", reviews: dict | None = None, typed_issues: list | None = None) -> dict:
    seal_input = root.parent / f"{stage}.seal.json"
    payload: dict = {"actor": actor, "verdict": verdict}
    if reviews is not None:
        payload["reviews"] = reviews
    if typed_issues is not None:
        payload["typedIssues"] = typed_issues
    _write(seal_input, _canonical(payload))
    return seal_module.seal_stage(execution_id=EXECUTION_ID, stage=stage, input_path=seal_input)


def _write_drafts(root: Path) -> None:
    _write(root / GOOD / "4.draft/draft.article.md", "---\ntitle: 西湖速览\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n正文。\n")
    _write(root / BAD_TAG / "4.draft/draft.article.md", "---\ntitle: 灵隐寺速览\ntagRefs: [Entity/地点/不存在的叶子]\n---\n# 灵隐寺速览\n\n正文。\n")
    _write(root / EMPTY / "4.draft/draft.article.md", "")


def _receipt(root: Path, name: str) -> dict:
    return json.loads((root / "_shared/receipts" / name).read_bytes())


def test_author_seal_retires_invalid_objects_and_reports_all_violations_at_once(execution: Path) -> None:
    _seal(execution, "1.download", AUTHOR)
    _write_drafts(execution)
    sealed = _seal(execution, "4.draft", AUTHOR)
    assert sealed["verdict"] == "pass" and sealed["resultRefs"] == 1

    receipt = _receipt(execution, "002-4.draft.json")
    assert [row["ref"] for row in receipt["resultRefs"]] == [f"{GOOD}/4.draft/draft.article.md"]
    issues = {issue["ref"]: issue for issue in receipt["typedIssues"]}
    assert set(issues) == {BAD_TAG, EMPTY}, "两条违规必须同时报出"
    assert all(issue["code"] == "DATA.SEAL.DRAFT_INVALID" for issue in issues.values())
    assert "tagRef 不在 taxonomy 中" in issues[BAD_TAG]["message"]
    assert "author 产物为空" in issues[EMPTY]["message"]

    # 只读复核把退轮对象点名而不计为缺产物。
    report = stage_artifacts.verify_stage_artifacts(execution_id=EXECUTION_ID, through="4.draft")
    assert report["passed"] is True
    assert report["retiredAtDraft"] == sorted([BAD_TAG, EMPTY])


def test_acquire_seal_retires_targets_without_sources_and_author_seal_only_sees_acquired(execution: Path) -> None:
    # EMPTY 的 ingest 失败：没有 source_refs.json，acquire seal 只把它退轮。
    import shutil
    shutil.rmtree(execution / EMPTY / "1.download")
    sealed = _seal(execution, "1.download", AUTHOR)
    assert sealed["verdict"] == "pass" and sealed["resultRefs"] == 2
    receipt = _receipt(execution, "001-1.download.json")
    assert [issue["ref"] for issue in receipt["typedIssues"]] == [EMPTY]
    assert receipt["typedIssues"][0]["code"] == "DATA.SEAL.ACQUIRE_INVALID"

    # 4.draft 只校验已取得来源的两个对象；EMPTY 没产物也不再被报为违规。
    _write(execution / GOOD / "4.draft/draft.article.md", "---\ntitle: 西湖速览\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n正文。\n")
    _write(execution / BAD_TAG / "4.draft/draft.article.md", "---\ntitle: 灵隐寺速览\ntagRefs: [Entity/地点/景区]\n---\n# 灵隐寺速览\n\n正文。\n")
    author = _seal(execution, "4.draft", AUTHOR)
    assert author["resultRefs"] == 2 and _receipt(execution, "002-4.draft.json")["typedIssues"] == []
    report = stage_artifacts.verify_stage_artifacts(execution_id=EXECUTION_ID, through="4.draft")
    assert report["passed"] is True and report["retiredAtDraft"] == [EMPTY]


def test_author_seal_with_zero_valid_drafts_requires_blocked_verdict(execution: Path) -> None:
    _seal(execution, "1.download", AUTHOR)
    _write(execution / GOOD / "4.draft/draft.article.md", "")
    _write(execution / BAD_TAG / "4.draft/draft.article.md", "")
    _write(execution / EMPTY / "4.draft/draft.article.md", "")
    with pytest.raises(seal_module.SealError, match="至少有一个合规产物"):
        _seal(execution, "4.draft", AUTHOR)
    blocked = _seal(
        execution, "4.draft", AUTHOR, verdict="blocked",
        typed_issues=[{"code": "DATA.SEAL.DRAFT_INVALID", "message": "全部产物为空"}],
    )
    assert blocked["verdict"] == "blocked" and blocked["resultRefs"] == 0
    receipt = _receipt(execution, "002-4.draft.json")
    assert {issue["ref"] for issue in receipt["typedIssues"] if issue.get("ref")} == set(TARGETS)


def test_review_coverage_follows_author_result_refs_and_retired_objects_cannot_publish(execution: Path) -> None:
    _seal(execution, "1.download", AUTHOR)
    _write_drafts(execution)
    _seal(execution, "4.draft", AUTHOR)
    judgement = {"decision": "approved", "blockingIssues": [], "advisories": []}

    # 多出退轮对象 → fail closed；漏评合规对象 → fail closed。
    with pytest.raises(seal_module.SealError, match="恰好覆盖 002-4.draft 合规对象集合"):
        _seal(execution, "5.review", REVIEWER, reviews={GOOD: judgement, BAD_TAG: judgement})
    with pytest.raises(seal_module.SealError, match="恰好覆盖 002-4.draft 合规对象集合"):
        _seal(execution, "5.review", REVIEWER, reviews={BAD_TAG: judgement})

    sealed = _seal(execution, "5.review", REVIEWER, reviews={GOOD: judgement})
    assert sealed["resultRefs"] == 1
    assert (execution / GOOD / "5.review/content_review.json").is_file()
    assert not (execution / BAD_TAG / "5.review").exists()
    assert not (execution / EMPTY / "5.review").exists()

    # 退轮对象在 publish 前置链上结构化拒绝；合规对象照常通过。
    validate_publish_review_chain(execution_id=EXECUTION_ID, execution_root=execution, target_ref=GOOD)
    with pytest.raises(ReceiptChainError, match="author receipt 未绑定该对象的产物"):
        validate_publish_review_chain(execution_id=EXECUTION_ID, execution_root=execution, target_ref=BAD_TAG)


def test_quality_scores_pass_through_verbatim_without_touching_decision(execution: Path) -> None:
    _seal(execution, "1.download", AUTHOR)
    _write(execution / GOOD / "4.draft/draft.article.md", "---\ntitle: 西湖速览\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n正文。\n")
    _write(execution / BAD_TAG / "4.draft/draft.article.md", "---\ntitle: 灵隐寺速览\ntagRefs: [Entity/地点/景区]\n---\n# 灵隐寺速览\n\n正文。\n")
    _write(execution / EMPTY / "4.draft/draft.article.md", "")
    _seal(execution, "4.draft", AUTHOR)

    scored = {
        "decision": "rejected",
        "blockingIssues": ["关键论断缺证据"],
        "advisories": [],
        "qualityScores": {dimension: 1 for dimension in QUALITY_DIMENSIONS_BY_CARRIER["article"]},
        "qualityNotes": "评分只记录，不改变 rejected。",
    }
    unscored = {"decision": "approved", "blockingIssues": [], "advisories": []}
    _seal(execution, "5.review", REVIEWER, reviews={GOOD: scored, BAD_TAG: unscored})

    good_review = json.loads((execution / GOOD / "5.review/content_review.json").read_bytes())
    assert good_review["qualityScores"] == scored["qualityScores"]
    assert good_review["qualityNotes"] == scored["qualityNotes"]
    assert good_review["decision"] == "rejected"
    other_review = json.loads((execution / BAD_TAG / "5.review/content_review.json").read_bytes())
    assert "qualityScores" not in other_review and "qualityNotes" not in other_review
    assert other_review["decision"] == "approved"


def test_quality_scores_outside_closed_set_are_rejected(execution: Path) -> None:
    _seal(execution, "1.download", AUTHOR)
    _write(execution / GOOD / "4.draft/draft.article.md", "---\ntitle: 西湖速览\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n正文。\n")
    _write(execution / BAD_TAG / "4.draft/draft.article.md", "")
    _write(execution / EMPTY / "4.draft/draft.article.md", "")
    _seal(execution, "4.draft", AUTHOR)
    base = {"decision": "approved", "blockingIssues": [], "advisories": []}

    # 分值越界与未知维度名由 seal_input schema 拒绝；跨载体维度与空对象由 seal 按载体闭集拒绝。
    with pytest.raises(ValueError, match="seal input"):
        _seal(execution, "5.review", REVIEWER, reviews={GOOD: {**base, "qualityScores": {"fact_traceability": 6}}})
    with pytest.raises(ValueError, match="seal input"):
        _seal(execution, "5.review", REVIEWER, reviews={GOOD: {**base, "qualityScores": {"not_a_dimension": 3}}})
    with pytest.raises(seal_module.SealError, match="不属于该载体闭集"):
        _seal(execution, "5.review", REVIEWER, reviews={GOOD: {**base, "qualityScores": {"visual_quality": 3}}})
    with pytest.raises(seal_module.SealError, match="非空对象"):
        _seal(execution, "5.review", REVIEWER, reviews={GOOD: {**base, "qualityScores": {}}})
    assert not (execution / GOOD / "5.review/content_review.json").exists()
