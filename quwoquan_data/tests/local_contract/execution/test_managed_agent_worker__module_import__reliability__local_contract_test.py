from __future__ import annotations

import os
from pathlib import Path

from content.execution.agent import agent_worker
from content.execution.context import ExecutionContext


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
        return _CompletedProcess()

    monkeypatch.setattr(agent_worker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(agent_worker, "_register_managed_agent_subprocess", lambda _pid: None)
    monkeypatch.setattr(agent_worker, "_unregister_managed_agent_subprocess", lambda _pid: None)
    ctx = ExecutionContext(
        execution_id="20260715--travel-homepage-coverage--cn-zhejiang--canary-001",
        entity_ids=["普陀山"],
        spec={},
        managed=True,
    )

    outcome = agent_worker._default_managed_agent_runner_isolated(ctx, "contract prompt")

    assert outcome["status"] == "error"
    python_path = str(captured["env"]["PYTHONPATH"]).split(os.pathsep)[0]
    assert Path(python_path) == Path(__file__).resolve().parents[3] / "scripts"
