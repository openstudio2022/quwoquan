from __future__ import annotations

from pathlib import Path

from core.download_diagnostics import entity_download_diagnostics
from core.data_issue import (
    DataIssueCode,
    DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.io import write_json
from content.execution.recovery import download_gate
from content.execution.context import ExecutionContext
from content.source import gate
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_all_download_gate_readers_use_canonical_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_id = "20260712--travel-homepage-coverage--test-region-a--scale-099"
    execution_dir = tmp_path / execution_id
    command_root = execution_dir / "_shared" / "workspace" / "source"
    report_dir = command_root / "results" / "image_fetch_gate"
    write_json(
        report_dir / "歌斐颂巧克力小镇.json",
        {
            "payload": {
                "ref": "歌斐颂巧克力小镇",
                "passed": False,
                "issues": [data_issue(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    stage=DataIssueStage.IMAGE_FETCH,
                    ref="歌斐颂巧克力小镇",
                    lane=DataIssueLane.HOMEPAGE,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="homepageMediaCount: 独立主页媒体仅下到 0 张合格图（要求 >=1）",
                ).as_dict()],
                "evidenceSummary": {
                    "plannedImages": 0,
                    "downloadedImages": 0,
                    "rejectedForQuality": [],
                },
            }
        },
    )
    monkeypatch.setattr(
        download_gate,
        "execution_command_root",
        lambda _execution_id, _command: command_root,
    )
    monkeypatch.setattr(
        gate,
        "execution_command_root",
        lambda _execution_id, _command: command_root,
    )
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=["歌斐颂巧克力小镇"],
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=(
                {"name": "歌斐颂巧克力小镇", "entityType": "地点/景区"},
            ),
        ).spec(),
    )

    workflow_issues = download_gate._download_stage_gate_issues(ctx)
    exit_gate_issues = gate._stage_gate_report_issues(
        execution_id,
        target_entities={"歌斐颂巧克力小镇"},
    )
    diagnostics = entity_download_diagnostics(execution_dir, "歌斐颂巧克力小镇")

    assert any(issue.code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL for issue in workflow_issues)
    assert any(issue.code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL for issue in exit_gate_issues)
    assert diagnostics["plannedImages"] == 0
    assert diagnostics["downloadedImages"] == 0
