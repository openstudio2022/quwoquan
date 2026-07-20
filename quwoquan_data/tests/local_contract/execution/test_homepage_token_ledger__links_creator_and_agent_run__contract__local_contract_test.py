from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json
from core.control_types import AgentProvider, ExecutionStage
from content.execution.agent.history import ManagedAgentRunRecord, ManagedAgentScheduler
from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
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
    state.last_agent_run = ManagedAgentRunRecord(
        stage=ExecutionStage.BUILD_HOMEPAGE,
        job_count=1,
        planned_job_count=1,
        scheduler=ManagedAgentScheduler(
            requested_max_workers=1,
            effective_worker_count=1,
            local_cursor_max_workers=1,
            runtime="managed-local",
            prompt_count=1,
            estimated_min_waves=1,
            lane_limits=(("homepage", 1),),
            provider=AgentProvider.CURSOR_SDK,
            started_at="2026-07-16T00:00:00Z",
            finished_at="2026-07-16T00:01:00Z",
            elapsed_seconds=60.0,
        ),
        refs=(entity_ref,),
        started_count=1,
        finished_count=1,
        infrastructure_failures=0,
        outcomes=(
            ManagedAgentJobOutcome(
                outcome=AgentRunOutcome.finished(
                    run_id="run-homepage-001",
                    used_tokens=321,
                    usage_measurement_mode="usage",
                    cost_usd=0.0,
                ),
                job_index=0,
                lane="homepage",
                ref=entity_ref,
            ),
        ),
        finished_at="2026-07-16T00:01:00Z",
    ).to_document()
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
