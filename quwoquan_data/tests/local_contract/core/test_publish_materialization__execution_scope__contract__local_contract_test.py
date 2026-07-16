from __future__ import annotations

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
