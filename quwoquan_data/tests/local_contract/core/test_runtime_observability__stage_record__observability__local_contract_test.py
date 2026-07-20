from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from content.execution.controller.orchestrator import _execution_runtime_logger
from core.paths import OUTPUT_ROOT
from core.runtime_observability import DataRuntimeLogResource, DataRuntimeLogger


def test_data_runtime_logger_emits_canonical_redacted_stage_records(
    tmp_path: Path,
) -> None:
    logger = DataRuntimeLogger(
        tmp_path / "runtime.jsonl",
        resource=DataRuntimeLogResource(
            environment="gamma",
            component="execution-controller",
        ),
        execution_id="execution-123",
        work_package_id="work-456",
        environment_run_id="gamma-run-789",
        now=lambda: datetime(2026, 7, 19, tzinfo=UTC),
    )

    record = logger.exception(
        error_code="DATA.RUNTIME.stage_failed",
        message="Bearer token-should-not-appear contact=user@example.com",
        failure_point="post_review",
        attributes={
            "stage": "post_review",
            "outcome": "failed",
            "gate": "review",
            "protocolVersion": "must-not-appear",
            "releaseVersion": "must-not-appear",
            "releaseId": "must-not-appear",
            "unregistered": "must-not-appear",
        },
    )

    assert record["schema"] == "observability.slim"
    assert record["signal"] == "data.exception.stage"
    assert record["correlation"] == {
        "executionId": "execution-123",
        "workPackageId": "work-456",
        "environmentRunId": "gamma-run-789",
    }
    assert record["message"] == "Bearer *** contact=***"
    assert record["attributes"] == {
        "failurePoint": "post_review",
        "gate": "review",
        "outcome": "failed",
        "stage": "post_review",
    }
    stored = json.loads((tmp_path / "runtime.jsonl").read_text(encoding="utf-8"))
    assert stored == record
    assert "protocolVersion" not in stored
    assert "releaseVersion" not in stored
    assert "releaseId" not in stored


def test_execution_controller_uses_the_shared_repo_observability_run() -> None:
    execution_id = "execution-runtime-log-contract"
    logger = _execution_runtime_logger(SimpleNamespace(execution_id=execution_id))

    logger.runtime(
        event="execution_started",
        result="started",
        message="safe",
        attributes={"stage": "execution", "outcome": "started", "gate": "controller"},
    )

    root = OUTPUT_ROOT / "env" / "repo" / "observability" / execution_id
    assert (root / "manifest.json").is_file()
    assert (root / "logs" / "data" / "runtime.log").is_file()
