from __future__ import annotations

import os
from pathlib import Path

from content.execution.agent import agent_worker
from content.execution.context import ExecutionContext
from content.execution.workspace import execution_root
from core.control_types import AgentFailureKind, AgentRunStatus
from core.runtime_policy import active_runtime_policy
from support.execution_manifest_fixture import ExecutionFixtureBuilder


class _CompletedProcess:
    pid = 4242
    returncode = 0

    def poll(self) -> int:
        return 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return "", ""


def test_managed_agent_subprocess_imports_from_the_data_scripts_root(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        captured["stdin"] = kwargs["stdin"]
        return _CompletedProcess()

    monkeypatch.setattr(agent_worker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(agent_worker, "_register_managed_agent_subprocess", lambda _pid: None)
    monkeypatch.setattr(agent_worker, "_unregister_managed_agent_subprocess", lambda _pid: None)
    ctx = ExecutionContext(
        execution_id="20260715--travel-homepage-coverage--test-region-a--pilot-001",
        entity_ids=["测试实体甲"],
        spec=ExecutionFixtureBuilder(
            "20260715--travel-homepage-coverage--test-region-a--pilot-001",
            targets=({"name": "测试实体甲", "entityType": "地点/景区"},),
        ).spec(),
        managed=True,
    )

    outcome = agent_worker._default_managed_agent_runner_isolated(ctx, "contract prompt")

    assert outcome.status is AgentRunStatus.ERROR
    assert outcome.failure_kind is AgentFailureKind.SUBPROCESS_EXITED
    python_path = str(captured["env"]["PYTHONPATH"]).split(os.pathsep)[0]
    assert Path(python_path) == Path(__file__).resolve().parents[3] / "scripts"
    assert Path(str(captured["cwd"])) == execution_root(ctx.execution_id)
    assert captured["stdin"] is agent_worker.subprocess.DEVNULL
    assert "CURSOR_API_KEY" not in captured["env"]
    assert "QWQ_CURSOR_API_KEY_FD" not in captured["env"]


def test_source_review_timeout_reports_progress_without_reaping_sibling_bridges(
    monkeypatch,
    capsys,
) -> None:
    class HangingProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

        def communicate(self, timeout=None):
            return "", "bridge stalled"

    kills: list[tuple[int, int]] = []
    cleanup: list[Path] = []
    monkeypatch.setattr(
        agent_worker.subprocess,
        "Popen",
        lambda *_args, **_kwargs: HangingProcess(),
    )
    monkeypatch.setattr(
        agent_worker.os,
        "killpg",
        lambda pid, signal: kills.append((pid, signal)),
    )
    monkeypatch.setattr(
        "content.execution.agent.managed_workspace.terminate_workspace_cursor_bridges",
        lambda workspace: cleanup.append(Path(workspace)),
    )
    monkeypatch.setattr(
        agent_worker,
        "_register_managed_agent_subprocess",
        lambda _pid: None,
    )
    monkeypatch.setattr(
        agent_worker,
        "_unregister_managed_agent_subprocess",
        lambda _pid: None,
    )

    selection = active_runtime_policy().explicit_semantic_selection(
        "cursor_grok"
    ).binding.selection
    outcome = agent_worker.run_source_review_agent_isolated(
        runtime="local",
        model_selection=selection,
        prompt="review exact evidence",
        timeout_seconds=0.01,
    )

    assert outcome.status is AgentRunStatus.ERROR
    assert outcome.failure_kind is AgentFailureKind.SUBPROCESS_TIMEOUT
    assert outcome.error_code == "semantic_provider_transport_timeout"
    assert outcome.retryable is True
    assert kills and kills[0][0] == 4242
    assert cleanup == []
    stderr = capsys.readouterr().err
    assert "[source-review] started" in stderr
    assert "[source-review] timed out" in stderr
