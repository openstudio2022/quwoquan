"""Cursor bridge cleanup is scoped to the explicit workspace boundary."""
from __future__ import annotations

from types import SimpleNamespace

from content.execution.agent import agent_runner, agent_worker, managed_workspace
from content.execution.controller import preflight


def test_bridge_cleanup_respects_explicit_workspace_boundary(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    foreign = tmp_path / "repo-other"
    foreign.mkdir()
    rows = "\n".join(
        (
            f"101 cursor-sdk-bridge --workspace {workspace}",
            f"102 cursor-sdk-bridge --workspace {foreign}",
            f"103 cursor-sdk-bridge --workspace={workspace / 'detached'}",
        )
    )
    terminated: list[int] = []
    monkeypatch.setattr(
        managed_workspace.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=rows),
    )
    monkeypatch.setattr(preflight, "_process_cwd", lambda _pid: "")
    monkeypatch.setattr(
        agent_worker,
        "_terminate_pid_tree_if_alive",
        lambda pid: terminated.append(pid),
    )

    managed_workspace.terminate_workspace_cursor_bridges(workspace)

    assert terminated == [101, 103]


def test_client_close_reaps_managed_local_bridge_even_after_success(
    monkeypatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    events: list[tuple[str, object]] = []

    class Client:
        def close(self) -> None:
            events.append(("close", None))

        def __exit__(
            self,
            _exc_type: object,
            _exc_value: object,
            _traceback: object,
        ) -> None:
            self.close()

    monkeypatch.setattr(
        agent_runner,
        "_terminate_workspace_cursor_bridges",
        lambda path: events.append(("terminate", path)),
    )

    agent_runner._close_cursor_client(
        Client(),
        workspace=workspace,
        terminate_bridges=True,
    )

    assert events == [("close", None), ("terminate", workspace)]
