"""六步协议 seal 内核契约：三份 receipt 连续、review 机械字段由 seal 补齐、author≠reviewer。"""
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
    validate_live_receipt_chain,
    validate_publish_review_chain,
)
from core import paths  # noqa: E402

EXECUTION_ID = "20260906--travel-article-six-step--hangzhou--pilot-001"
TARGET_REF = "posts/article/导览/西湖速览/1"
AUTHOR = {
    "host": "cursor",
    "modelFamily": "gpt",
    "sessionId": "author-session",
    "invocation": {"provider": "openai", "model": "gpt-5", "runId": "run-author"},
}
REVIEWER = {
    "host": "cursor",
    "modelFamily": "gpt",
    "sessionId": "reviewer-session",
    "invocation": {"provider": "openai", "model": "gpt-5", "runId": "run-reviewer"},
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


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
        "candidateBinding": {"scope": "output", "ref": "data/local/workspace/x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1,
        "targetRefs": [TARGET_REF],
        "targets": [{"name": "西湖", "entityType": "地点/景区", "publishAngle": "导览", "publishTitle": "西湖速览", "publishSeq": 1}],
    }
    _write(root / "0.plan/target_set.json", _canonical(target_set))

    unit = root / "sources/zh_wikipedia__abc"
    source_md = "# 西湖\n\n西湖位于杭州。\n"
    image = b"\x89PNGfakebytes"
    _write(unit / "source.md", source_md)
    _write(unit / "snapshot.raw", b"{}")
    _write(unit / "assets/001_xihu.png", image)
    asset_row = {
        "sourceAssetId": "zh_wikipedia__abc", "fileName": "001_xihu.png", "assetRole": "image",
        "mimeType": "image/png", "bytes": len(image), "sha256": _sha(image), "contentSha256": _sha(image),
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Xihu.png", "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "authorizationProof": None,
        "creator": "Someone", "platform": "Wikimedia Commons",
    }
    _write(unit / "assets/index.json", _canonical({"assets": [asset_row]}))
    plan_ref = "sources/plans/" + "a" * 64 + ".json"
    _write(root / plan_ref, _canonical({"schema": "quwoquan_data.acquire_request", "sources": []}))
    meta = {
        "schema": "quwoquan_data.atomic_source_unit", "stage": "1.download", "executionId": EXECUTION_ID,
        "executionBinding": "frozen", "sourceUnitId": "zh_wikipedia__abc", "sourcePlanRef": plan_ref,
        "sourcePlanDigest": "sha256:" + "b" * 64, "chosenCandidateDigest": "sha256:" + "c" * 64,
        "sourceId": "zh_wikipedia", "targetRef": TARGET_REF, "carrier": "article", "title": "西湖",
        "sourceClass": "encyclopedia", "sourceUseMode": "factual_reference_only", "purpose": "主题条目",
        "rightsClue": "CC BY-SA 4.0", "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖",
        "fetchedAt": "2026-09-06T00:00:00+00:00", "rawSha256": _sha(b"{}"),
        "sourceMarkdownSha256": _sha(source_md.encode("utf-8")),
    }
    _write(unit / "meta.json", _canonical(meta))
    refs = {
        "schema": "quwoquan_data.object_source_refs", "executionId": EXECUTION_ID, "objectRef": TARGET_REF,
        "sources": [{
            "sourceUnitId": "zh_wikipedia__abc", "sourceRef": "sources/zh_wikipedia__abc/source.md",
            "metaRef": "sources/zh_wikipedia__abc/meta.json", "sourcePlanRef": plan_ref,
            "sourcePlanDigest": "sha256:" + "b" * 64, "chosenCandidateDigest": "sha256:" + "c" * 64,
            "sourceId": "zh_wikipedia", "sourceClass": "encyclopedia", "targetRefs": [TARGET_REF],
        }],
    }
    _write(root / TARGET_REF / "1.download/source_refs.json", _canonical(refs))
    return root


def _seal(root: Path, stage: str, actor: dict, verdict: str = "pass") -> dict:
    seal_input = root.parent / f"{stage}.seal.json"
    _write(seal_input, _canonical({"actor": actor, "verdict": verdict}))
    return seal_module.seal_stage(execution_id=EXECUTION_ID, stage=stage, input_path=seal_input)


def test_three_seals_form_chain_and_seal_completes_review_fields(execution: Path) -> None:
    acquire = _seal(execution, "1.download", AUTHOR)
    assert acquire["status"] == "created" and acquire["resultRefs"] == 1

    _write(execution / TARGET_REF / "4.draft/draft.article.md", "---\ntitle: 西湖速览\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n西湖位于杭州。\n")
    author = _seal(execution, "4.draft", AUTHOR)
    assert author["receipt"] == "_shared/receipts/002-4.draft.json"

    review = {
        "decision": "approved",
        "dimensions": [{"name": "证据", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [{"assetRef": "001_xihu.png", "decision": "approved", "issues": [], "usageScope": "research"}],
        "safety": "ok",
        "advisories": ["标题可更具体"],
    }
    review_path = execution / TARGET_REF / "5.review/content_review.json"
    _write(review_path, _canonical(review))
    sealed = _seal(execution, "5.review", REVIEWER)
    assert sealed["status"] == "created"

    completed = json.loads(review_path.read_bytes())
    assert completed["schema"] == "quwoquan_data.content_review"
    assert completed["stage"] == "5.review"
    assert completed["executionId"] == EXECUTION_ID
    assert completed["objectRef"] == TARGET_REF
    assert completed["draft"]["ref"] == "4.draft/draft.article.md"
    rights = completed["assetRights"][0]
    assert rights["assetRef"] == "sources/zh_wikipedia__abc/assets/001_xihu.png"
    assert rights["sourceUrl"] == "https://commons.wikimedia.org/wiki/File:Xihu.png"
    assert rights["license"] == "CC BY-SA 4.0"
    assert rights["termsUrl"].startswith("https://")
    assert rights["authorizationProof"] is None

    chain = validate_live_receipt_chain(execution_id=EXECUTION_ID, execution_root=execution, expected_count=3, terminal_verdict="pass")
    assert [r["stage"] for r in chain.receipts] == ["1.download", "4.draft", "5.review"]
    _chain, approved_review = validate_publish_review_chain(execution_id=EXECUTION_ID, execution_root=execution, target_ref=TARGET_REF)
    assert approved_review["decision"] == "approved"

    # replay：同输入再次 seal 不报错；不同输入冲突
    assert _seal(execution, "5.review", REVIEWER)["status"] == "replayed"
    with pytest.raises(seal_module.SealConflict):
        _seal(execution, "5.review", {**REVIEWER, "sessionId": "another"})


def test_review_rejects_same_actor_as_author_and_out_of_order_seal(execution: Path) -> None:
    with pytest.raises(seal_module.SealError, match="连续前缀"):
        _seal(execution, "4.draft", AUTHOR)
    _seal(execution, "1.download", AUTHOR)
    _write(execution / TARGET_REF / "4.draft/draft.article.md", "# 西湖速览\n\n正文。\n")
    _seal(execution, "4.draft", AUTHOR)
    _write(execution / TARGET_REF / "5.review/content_review.json", _canonical({
        "decision": "approved", "dimensions": [{"name": "证据", "decision": "approved", "issues": []}],
        "blockingIssues": [], "assetRights": [],
    }))
    with pytest.raises(seal_module.SealError, match="同一 host/sessionId"):
        _seal(execution, "5.review", AUTHOR)
    with pytest.raises(ReceiptChainError):
        validate_publish_review_chain(execution_id=EXECUTION_ID, execution_root=execution, target_ref=TARGET_REF)


def test_acquire_seal_rejects_asset_digest_drift(execution: Path) -> None:
    (execution / "sources/zh_wikipedia__abc/assets/001_xihu.png").write_bytes(b"tampered")
    with pytest.raises(seal_module.SealError, match="资产字节或摘要漂移"):
        _seal(execution, "1.download", AUTHOR)
