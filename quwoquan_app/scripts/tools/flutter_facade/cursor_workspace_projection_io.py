"""Cursor workspace tasks/launch 投影与可替换原子写入。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

GENERATED_MARKER = "// qwq-workspace-launch-projection"


def tasks_projection() -> str:
    payload = {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "qwq: canonical IDE launch",
                "type": "shell",
                "command": "python3",
                "args": [
                    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/run_workspace_ide_debug.py",
                    "--env",
                    "${input:qwqEnvironment}",
                    "--device",
                    "${input:qwqDeviceId}",
                    "--mode",
                    "${input:qwqRunMode}",
                ],
                "options": {"cwd": "${workspaceFolder}"},
                "isBackground": True,
                "problemMatcher": {
                    "owner": "qwq-workspace-ide",
                    "pattern": {"regexp": "^(?!)$"},
                    "background": {
                        "activeOnStart": True,
                        "beginsPattern": "^\\[workspace-ide\\] START ",
                        "endsPattern": "^QWQ_APP_LAUNCH_PHASE status=launched$",
                    },
                },
                "presentation": {
                    "reveal": "always",
                    "panel": "dedicated",
                    "clear": True,
                },
            }
        ],
        "inputs": [
            {
                "id": "qwqEnvironment",
                "type": "pickString",
                "description": "QuWoQuan runtime environment",
                "options": ["alpha", "beta", "gamma"],
                "default": "alpha",
            },
            {
                "id": "qwqDeviceId",
                "type": "promptString",
                "description": "Exact Android/iOS device id (from the device picker)",
            },
            {
                "id": "qwqRunMode",
                "type": "pickString",
                "description": "test_live App mode",
                "options": ["content-live", "ui-only"],
                "default": "content-live",
            },
        ],
    }
    return GENERATED_MARKER + "\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def launch_projection() -> str:
    payload = {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "QuWoQuan: canonical launch + IDE attach",
                "type": "dart",
                "request": "attach",
                "cwd": "${workspaceFolder}/quwoquan_app",
                "program": "${workspaceFolder}/quwoquan_app/lib/main_prod.dart",
                "vmServiceInfoFile": "${workspaceFolder}/.qwq_output/env/repo/local/ide/current-vm-service-info.json",
                "deleteServiceInfoFile": False,
                "preLaunchTask": "qwq: canonical IDE launch",
            }
        ],
    }
    return GENERATED_MARKER + "\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def assert_projection_owned(
    path: Path,
    expected: str,
    *,
    deleting: bool = False,
    allow_managed_drift: bool = False,
) -> None:
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    if content == expected:
        return
    if allow_managed_drift and GENERATED_MARKER in content:
        return
    action = "delete" if deleting else "replace"
    raise SystemExit(
        f"GATE_BLOCK: refusing to {action} foreign or drifted IDE projection {path}"
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
