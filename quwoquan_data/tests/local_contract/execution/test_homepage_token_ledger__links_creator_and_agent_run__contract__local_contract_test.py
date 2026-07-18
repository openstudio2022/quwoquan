from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json
from content.execution.context import ExecutionContext
from content.execution.controller import token_ledger
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_homepage_agent_usage_links_published_creator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_id = "20260716--travel-homepage-coverage--cn-zhejiang--canary-909"
    builder = ExecutionFixtureBuilder(execution_id)
    context = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("测试实体",),
        spec=builder.spec(),
    )
    state = builder.state()
    entity_ref = "entities/地点/景区/测试实体"
    write_json(
        tmp_path / entity_ref / "_entity.json",
        {"creatorProfileId": "qwq_creator_geo_editor_001"},
    )
    state.last_agent_run = {
        "stage": "build_homepage",
        "finishedAt": "2026-07-16T00:01:00Z",
        "outcomes": [
            {
                "ref": entity_ref,
                "runId": "run-homepage-001",
                "status": "finished",
                "usageMeasurementMode": "usage",
                "usedTokens": 321,
                "costUsd": 0.0,
            }
        ],
    }
    monkeypatch.setattr(token_ledger, "execution_root", lambda _execution_id: tmp_path)

    entries = token_ledger._managed_entries(
        context,
        state,
        default_budget=12000,
    )

    assert len(entries) == 1
    assert entries[0]["runId"] == "run-homepage-001"
    assert entries[0]["creatorProfileId"] == "qwq_creator_geo_editor_001"
    assert entries[0]["contentType"] == "homepage"
