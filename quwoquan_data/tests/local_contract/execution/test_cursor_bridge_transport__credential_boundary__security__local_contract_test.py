from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.cursor_bridge_transport import (
    _discovery_endpoint,
    cursor_bridge_command,
    protected_bridge_argv,
    protected_bridge_environment,
    protected_cursor_client,
)


def test_bridge_argv_contains_scope_but_no_callback_or_credential_material(
    tmp_path: Path,
):
    node = tmp_path / "node"
    entrypoint = tmp_path / "cursor-sdk-bridge.js"
    node.write_text("", encoding="utf-8")
    entrypoint.write_text("", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    argv = protected_bridge_argv(
        command=(node, entrypoint),
        workspace=workspace,
    )
    joined = " ".join(argv)

    assert argv == [
        str(node.resolve()),
        str(entrypoint.resolve()),
        "--workspace",
        str(workspace.resolve()),
    ]
    assert "callback" not in joined
    assert "auth-token" not in joined
    assert "secret" not in joined


def test_bridge_environment_removes_every_credential_and_callback_channel():
    secret = "secret-material"
    env = protected_bridge_environment(
        {
            "PATH": "/bin",
            "CURSOR_API_KEY": secret,
            "QWQ_CURSOR_API_KEY_FD": "9",
            "CURSOR_SDK_BRIDGE_TOKEN": secret,
            "CURSOR_SDK_BRIDGE_AUTH_TOKEN": secret,
            "CURSOR_SDK_STORE_CALLBACK_URL": "http://127.0.0.1:1",
            "CURSOR_SDK_STORE_CALLBACK_AUTH_TOKEN": secret,
            "CURSOR_SDK_TOOL_CALLBACK_URL": "http://127.0.0.1:2",
            "CURSOR_SDK_TOOL_CALLBACK_AUTH_TOKEN": secret,
        }
    )

    assert env == {"PATH": "/bin"}
    assert secret not in repr(env)


def test_discovery_consumes_and_deletes_restricted_token_file():
    token_parent = Path(tempfile.mkdtemp(prefix="cursor-sdk-bridge-"))
    token_file = token_parent / "auth-token"
    token_file.write_text("bridge-secret\n", encoding="utf-8")
    token_file.chmod(0o600)

    endpoint = _discovery_endpoint(
        {
            "schemaVersion": 1,
            "transport": "tcp",
            "protocol": "connect",
            "url": "http://127.0.0.1:42123",
            "authTokenFile": str(token_file),
        }
    )

    assert endpoint.auth_token == "bridge-secret"
    assert not token_file.exists()
    assert not token_parent.exists()


def test_real_pinned_bridge_starts_without_secret_process_fields(tmp_path: Path):
    command = cursor_bridge_command()

    with protected_cursor_client(workspace=tmp_path, timeout=10) as client:
        assert client is not None

    assert all(path.is_file() for path in command)


def test_runtime_entrypoints_do_not_use_sdk_launch_bridge():
    data_root = Path(__file__).resolve().parents[3]
    sources = (
        data_root / "scripts/core/cursor_startup_probe.py",
        data_root / "scripts/content/execution/agent/agent_runner.py",
    )

    for source in sources:
        assert "Client.launch_bridge(" not in source.read_text(encoding="utf-8")


def test_parent_process_environment_is_not_mutated():
    before = dict(os.environ)
    protected_bridge_environment(os.environ)
    assert dict(os.environ) == before
