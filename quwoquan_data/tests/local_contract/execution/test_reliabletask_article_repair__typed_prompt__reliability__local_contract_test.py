"""Article ReliableTask retries consume only bound typed repair evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.queue.reliabletask import (
    author as reliabletask_author,
)
from content.execution.stage_reports import build_repair_report
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        carrier=SimpleNamespace(value="article"),
        ref="杭州西湖__article_frontier",
        execution_id="20260808--travel-article-m1--china-beta-bootstrap-not-m100--scale-023",
        job_id="article-author-job",
        content_object_dir="posts/article/攻略/杭州西湖/1",
    )


def _seed_prompt(root: Path, job: SimpleNamespace) -> Path:
    object_dir = root / job.content_object_dir
    draft_dir = object_dir / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "prompt.md").write_text("依据冻结底稿局部修订文章。", encoding="utf-8")
    (draft_dir / "author_job_packet.json").write_text(
        json.dumps(
            {
                "executionId": job.execution_id,
                "objectRef": job.ref,
                "promptRef": "4.draft/prompt.md",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return object_dir


def _typed_report(job: SimpleNamespace) -> dict[str, object]:
    return build_repair_report(
        execution_id=job.execution_id,
        command="post",
        ref=job.ref,
        failed_stage=DataIssueStage.REVIEW.value,
        failed_gate="post_verify",
        issues=(
            data_issue(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.REVIEW,
                lane=DataIssueLane.ARTICLE,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                ref=job.ref,
                message=(
                    "closing figure is a shopping-street image and cannot anchor "
                    "the West Lake article"
                ),
            ),
        ),
        fallback_stage=DataIssueStage.AGENT_COMPOSE.value,
        rerun_chain=["agent_compose", "review", "materialize"],
    )


def _stage_envelope(
    job: SimpleNamespace,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.stage_envelope",
        "executionId": job.execution_id,
        "step": "repair_report",
        "ref": job.ref,
        "payload": payload,
    }


def test_article_author_prompt_binds_typed_figure_repair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job = _job()
    object_dir = _seed_prompt(tmp_path, job)
    repair = object_dir / "5.review" / "repair_report.json"
    repair.parent.mkdir(parents=True)
    repair.write_text(
        json.dumps(_stage_envelope(job, _typed_report(job)), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_author, "execution_root", lambda _execution_id: tmp_path)

    checkpoint, prompt = reliabletask_author._author_prompt(SimpleNamespace(), job)

    assert checkpoint == "post_author"
    assert "[DATA.QUALITY.FAILED] closing figure" in prompt
    assert "先删除该错误 figure 块" in prompt
    assert "另一 assetId 替换" in prompt
    assert "没有合格替代图时必须移除正文 figure" in prompt


def test_article_author_prompt_rejects_untyped_repair_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job = _job()
    object_dir = _seed_prompt(tmp_path, job)
    payload = _typed_report(job)
    payload["fallbackStage"] = "download"
    repair = object_dir / "5.review" / "repair_report.json"
    repair.parent.mkdir(parents=True)
    repair.write_text(
        json.dumps(_stage_envelope(job, payload), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_author, "execution_root", lambda _execution_id: tmp_path)

    with pytest.raises(ValueError, match="article repair report binding mismatch"):
        reliabletask_author._author_prompt(SimpleNamespace(), job)


def test_article_author_prompt_rejects_raw_repair_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job = _job()
    object_dir = _seed_prompt(tmp_path, job)
    repair = object_dir / "5.review" / "repair_report.json"
    repair.parent.mkdir(parents=True)
    repair.write_text(
        json.dumps(_typed_report(job), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_author, "execution_root", lambda _execution_id: tmp_path)

    with pytest.raises(ValueError, match="article repair envelope binding mismatch"):
        reliabletask_author._author_prompt(SimpleNamespace(), job)
