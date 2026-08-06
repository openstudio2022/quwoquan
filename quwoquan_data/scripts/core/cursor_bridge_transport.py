"""Protected process transport for the pinned Cursor SDK bridge.

``cursor_sdk.Client.launch_bridge`` in 1.0.26 creates a host tool callback on
every launch and passes its bearer token in the bridge process argv.  Data
execution does not use host custom tools or a host-owned custom store, so this
adapter starts the official bridge without either callback.  The bridge's own
one-time discovery credential is read from its private stderr pipe and is
never placed in argv, stdin, the environment, or a filesystem artifact.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.runtime_policy import active_runtime_policy

_DISCOVERY_PREFIX = "cursor-sdk-bridge ready "
_PROCESS_TERMINATION_TIMEOUT_SECONDS = (
    active_runtime_policy().process_termination_timeout_seconds
)
_CURSOR_BRIDGE_HANDSHAKE_TIMEOUT_SECONDS = (
    active_runtime_policy().cursor_bridge_handshake_timeout_seconds
)
_CURSOR_BRIDGE_MAX_RETRIES = active_runtime_policy().cursor_bridge_max_retries
_SCRUBBED_ENV_KEYS = frozenset(
    {
        "CURSOR_API_KEY",
        "QWQ_CURSOR_API_KEY_FD",
        "CURSOR_SDK_BRIDGE_TOKEN",
        "CURSOR_SDK_BRIDGE_AUTH_TOKEN",
        "CURSOR_SDK_STORE_CALLBACK_AUTH_TOKEN",
        "CURSOR_SDK_STORE_CALLBACK_URL",
        "CURSOR_SDK_TOOL_CALLBACK_AUTH_TOKEN",
        "CURSOR_SDK_TOOL_CALLBACK_URL",
    }
)


def cursor_bridge_command() -> tuple[Path, Path]:
    """Resolve the pinned wheel's Node runtime and bridge entrypoint.

    The wheel's console entry adds a shell parent that does not ``exec`` Node;
    terminating that parent can orphan the real bridge. Owning Node directly
    gives Data execution an exact process-lifecycle boundary.
    """
    import cursor_sdk

    package_root = Path(cursor_sdk.__file__).resolve().parent
    bridge_root = package_root / "_vendor" / "bridge"
    node = bridge_root / "bin" / "node"
    entrypoint = bridge_root / "dist" / "bin" / "cursor-sdk-bridge.js"
    if not node.is_file() or not entrypoint.is_file():
        raise RuntimeError(
            "pinned cursor-sdk wheel is missing its bundled bridge runtime"
        )
    return node, entrypoint


def protected_bridge_environment(base: Mapping[str, str]) -> dict[str, str]:
    """Return a bridge environment with every supported credential path removed."""
    return {
        str(name): str(value)
        for name, value in base.items()
        if str(name) not in _SCRUBBED_ENV_KEYS
    }


def protected_bridge_argv(*, command: Sequence[Path], workspace: Path) -> list[str]:
    """Build the only permitted bridge argv: executable plus non-secret scope."""
    if len(command) != 2:
        raise ValueError("Cursor bridge command must contain Node and one entrypoint")
    return [
        *(str(item.resolve()) for item in command),
        "--workspace",
        str(workspace.resolve()),
    ]


def _discovery_endpoint(payload: Mapping[str, Any]):
    from cursor_sdk import BridgeEndpoint

    if payload.get("authToken"):
        raise RuntimeError("Cursor bridge must not emit an inline discovery token")
    raw_token_file = str(payload.get("authTokenFile") or "").strip()
    if not raw_token_file:
        raise RuntimeError("Cursor bridge discovery requires a protected token file")
    token_file = Path(raw_token_file).resolve()
    token_parent = token_file.parent
    expected_tmp = Path(tempfile.gettempdir()).resolve()
    if (
        token_parent.parent != expected_tmp
        or not token_parent.name.startswith("cursor-sdk-bridge-")
        or token_file.name != "auth-token"
    ):
        raise RuntimeError(
            "Cursor bridge token file is outside the protected temp scope"
        )
    stat = token_file.stat()
    if not token_file.is_file() or stat.st_mode & 0o077:
        raise RuntimeError("Cursor bridge token file must be a restricted regular file")
    cleanup_error: OSError | None = None
    try:
        endpoint = BridgeEndpoint.from_discovery(payload)
    finally:
        try:
            token_file.unlink()
            token_parent.rmdir()
        except OSError as exc:
            cleanup_error = exc
    if cleanup_error is not None:
        raise RuntimeError("Cursor bridge token file cleanup failed") from cleanup_error
    parsed = urlparse(endpoint.url)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise RuntimeError("Cursor bridge discovery must resolve to loopback HTTP")
    return endpoint


def _read_discovery(process: subprocess.Popen[str], *, timeout_seconds: float):
    if process.stderr is None:
        raise RuntimeError("Cursor bridge stderr discovery pipe is unavailable")
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    fd = process.stderr.fileno()
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(timeout=min(0.1, remaining)):
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Cursor bridge exited before discovery: status={process.returncode}"
                    )
                continue
            line = process.stderr.readline()
            if not line:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Cursor bridge exited before discovery: status={process.returncode}"
                    )
                continue
            if not line.startswith(_DISCOVERY_PREFIX):
                continue
            try:
                payload = json.loads(line[len(_DISCOVERY_PREFIX) :])
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Cursor bridge emitted invalid discovery JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise TypeError("Cursor bridge discovery payload must be an object")
            return _discovery_endpoint(payload)
    raise TimeoutError("Timed out waiting for protected Cursor bridge discovery")


def _discard_remaining_stderr(process: subprocess.Popen[str]) -> None:
    stream = process.stderr
    if stream is None:
        return
    try:
        for _line in stream:
            pass
    except (OSError, ValueError):
        return


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS)


@contextmanager
def protected_cursor_client(
    *,
    workspace: str | os.PathLike[str],
    timeout: float = _CURSOR_BRIDGE_HANDSHAKE_TIMEOUT_SECONDS,
    max_retries: int = _CURSOR_BRIDGE_MAX_RETRIES,
) -> Iterator[Any]:
    """Yield a public Cursor client backed by a credential-free bridge argv."""
    from cursor_sdk import Client

    workspace_path = Path(workspace).resolve()
    argv = protected_bridge_argv(
        command=cursor_bridge_command(),
        workspace=workspace_path,
    )
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=protected_bridge_environment(os.environ),
        close_fds=True,
    )
    client: Any | None = None
    try:
        endpoint = _read_discovery(process, timeout_seconds=timeout)
        threading.Thread(
            target=_discard_remaining_stderr,
            args=(process,),
            name="cursor-bridge-stderr-drain",
            daemon=True,
        ).start()
        client = Client(
            endpoint,
            max_retries=max_retries,
            allow_api_key_env_fallback=False,
        )
        yield client
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            _terminate(process)
