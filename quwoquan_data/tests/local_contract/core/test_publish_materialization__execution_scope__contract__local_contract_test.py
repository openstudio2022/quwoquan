from __future__ import annotations

import json
from pathlib import Path

import core.publish_materialization as publish_materialization


def test_publish_materialization_reads_only_requested_execution(monkeypatch) -> None:
    roots_seen: list[str] = []
    monkeypatch.setattr(
        publish_materialization,
        "collect_execution_entity_objects",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        publish_materialization,
        "execution_post_roots",
        lambda execution_id: roots_seen.append(execution_id) or [],
    )

    result = publish_materialization.collect_task_publish_inputs("current-execution")

    assert roots_seen == ["current-execution"]
    assert result["postCount"] == 0


def test_publish_materialization_only_counts_qualified_closure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    posts_root = tmp_path / "posts"
    for title in ("qualified", "discarded"):
        object_root = posts_root / f"article/攻略/{title}/1"
        object_root.mkdir(parents=True)
        (object_root / "manifest.json").write_text(
            json.dumps({"tagRefs": [f"/tag/{title}"]}),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        publish_materialization,
        "collect_execution_entity_objects",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        publish_materialization,
        "execution_post_roots",
        lambda _execution_id: [posts_root],
    )

    result = publish_materialization.collect_task_publish_inputs(
        "current-execution",
        qualified_post_refs={"posts/article/攻略/qualified/1"},
    )

    assert result["postCount"] == 1
    assert result["tagRows"] == [
        {
            "tagRef": "/tag/qualified",
            "label": "qualified",
            "objectCount": 1,
            "entityCount": 0,
            "postCount": 1,
        }
    ]
