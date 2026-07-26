"""Homepage author evidence cannot bypass deterministic materialization."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution import reliabletask_worker  # noqa: E402


def _homepage_job() -> SimpleNamespace:
    return SimpleNamespace(
        carrier=SimpleNamespace(value="homepage"),
        ref="/entity/地点/景区/测试实体甲",
        execution_id="20260722--travel-homepage-generate--test-region-a--pilot-901",
        job_id="homepage-job",
        content_object_dir="entities/地点/景区/测试实体甲",
    )


def _article_job() -> SimpleNamespace:
    return SimpleNamespace(
        carrier=SimpleNamespace(value="article"),
        ref="测试文章",
        execution_id="20260722--travel-article-generate--test-region-a--pilot-901",
        job_id="article-job",
        content_object_dir="posts/article/攻略/测试文章/1",
    )


def test_failed_homepage_materialization_invalidates_author_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "agent_result_envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    from content.homepage import homepage_release

    monkeypatch.setattr(
        homepage_release,
        "materialize_entity_page",
        lambda *_args: ["base draft fidelity below policy"],
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        _homepage_job(),
        envelope_path,
    ) is False
    assert not envelope_path.exists()


def test_materialized_homepage_may_reuse_author_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "agent_result_envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    from content.homepage import homepage_release

    monkeypatch.setattr(
        homepage_release,
        "materialize_entity_page",
        lambda *_args: [],
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        _homepage_job(),
        envelope_path,
    ) is True
    assert envelope_path.is_file()


def test_post_repair_newer_than_author_envelope_requires_fresh_agent_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    job = _article_job()
    envelope_path = task_root / job.content_object_dir / "4.draft" / "agent_result_envelope.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    repair_path = task_root / job.content_object_dir / "5.review" / "repair_report.json"
    repair_path.parent.mkdir(parents=True)
    repair_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reliabletask_worker, "execution_root", lambda _execution_id: task_root)
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        job,
        envelope_path,
    ) is False
    assert not envelope_path.exists()
