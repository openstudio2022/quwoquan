"""Support functions for managed agent execution."""

from __future__ import annotations

from content.execution.agent.agent_runner import (
    AgentFailureKind,
    Any,
    Path,
    _terminate_workspace_cursor_bridges,
    classify_provider_failure,
    sys,
)


def _cursor_provider_rejection(message: str, *, code: str = "") -> bool:
    """Identify non-retryable account/quota rejection from the public SDK."""
    classified = classify_provider_failure(message, code=code)
    return (
        classified.kind is AgentFailureKind.PROVIDER_REJECTED
        and not classified.retryable
    )


def _close_cursor_client(
    client_context: Any,
    *,
    workspace: Path,
    terminate_bridges: bool,
) -> None:
    """Close the public client and reap any managed-local bridge it leaves behind."""
    try:
        client_context.__exit__(None, None, None)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[cursor-agent] client close failed: {type(exc).__name__}",
            file=sys.stderr,
        )
    finally:
        if terminate_bridges:
            _terminate_workspace_cursor_bridges(workspace)


def _prompt_cursor_agent(
    agent_cls: Any,
    prompt: str,
    agent_options: Any,
    *,
    client: Any,
) -> tuple[Any, str]:
    """Run one prompt and preserve the SDK terminal status explanation."""
    agent = agent_cls.create(agent_options, client=client)
    try:
        run = agent.send(prompt)
        terminal_message = ""
        for event in run.events():
            message = getattr(event, "sdk_message", None)
            if (
                getattr(message, "type", "") == "status"
                and str(getattr(message, "status", "")).casefold() == "error"
            ):
                terminal_message = str(getattr(message, "message", "") or "").strip()
        return run.wait(), terminal_message
    finally:
        agent.close()
