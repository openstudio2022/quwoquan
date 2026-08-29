#!/usr/bin/env python3
"""工作区 flutter facade 的受版本控制激活入口。

把 facade 的 PATH、受控 ZDOTDIR bridge 与 Dart-Code PATH 策略合并进本机
`.vscode/settings.json`（gitignore 的本地投影）。同一个 zsh 先代理用户原有
startup files，再把 facade 放回 PATH 首位，使本 Cursor 工作区新开的终端把
字面 `flutter run` 归一化进 canonical launcher；仓库外终端、全局 PATH 与
系统 Flutter 完全不受影响。

- 激活：python3 quwoquan_app/scripts/tools/flutter_facade/activate_cursor_workspace.py
- 回退：同命令加 `--deactivate`，随后重载编辑器窗口即回到真实 SDK 直连。
- 本地投影可随时删除；凭本脚本可完全重建，符合「激活面可凭受版本控制
  真相源重建」的规格要求（environment-topology-and-packaging REQ-003）。

合并策略是标记块文本级增删：保留用户注释与既有配置；发现非本工具管理的
`dart.addSdkToTerminalPath` 或 `terminal.integrated.env.osx` 时拒绝静默覆盖。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SETTINGS_PATH = REPO_ROOT / ".vscode/settings.json"
DEFAULT_TASKS_PATH = REPO_ROOT / ".vscode/tasks.json"
DEFAULT_LAUNCH_PATH = REPO_ROOT / ".vscode/launch.json"
BEGIN_MARKER = "// qwq-flutter-facade-begin"
END_MARKER = "// qwq-flutter-facade-end"
MANAGED_DART_KEY = "dart.addSdkToTerminalPath"
MANAGED_ENV_KEY = "terminal.integrated.env.osx"
MANAGED_KEYS = (MANAGED_DART_KEY, MANAGED_ENV_KEY)
GENERATED_MARKER = "// qwq-workspace-launch-projection"
FACADE_PATH_VALUE = (
    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/bin:${env:PATH}"
)
FACADE_BIN_VALUE = (
    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/bin"
)
ZDOTDIR_VALUE = (
    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/zsh_projection"
)


def _managed_block(indent: str = "    ") -> str:
    lines = [
        f"{indent}{BEGIN_MARKER}",
        f"{indent}// 由 activate_cursor_workspace.py 管理，勿手改；"
        "回退：--deactivate 后重载窗口。",
        f'{indent}"{MANAGED_DART_KEY}": false,',
        f'{indent}"{MANAGED_ENV_KEY}": {{',
        f'{indent}    "PATH": {json.dumps(FACADE_PATH_VALUE)},',
        f'{indent}    "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": '
        f"{json.dumps(FACADE_BIN_VALUE)},",
        f'{indent}    "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${{env:ZDOTDIR}}",',
        f'{indent}    "ZDOTDIR": {json.dumps(ZDOTDIR_VALUE)}',
        f"{indent}}},",
        f"{indent}{END_MARKER}",
    ]
    return "\n".join(lines)


def _managed_segment() -> str:
    # 两侧换行都属于投影本身，回退时可逐字删除并恢复任意原始 JSONC，
    # 包括紧凑的 ``{}``。
    return "\n" + _managed_block() + "\n"


def _strip_line_comments(text: str) -> str:
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _parse_settings(text: str) -> dict:
    stripped = _strip_line_comments(text)
    # VSCode settings 是 JSONC：容忍尾逗号，校验时同样容忍。
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped).strip()
    if not stripped:
        return {}
    return json.loads(stripped)


def _remove_managed_block(text: str) -> str:
    segment = _managed_segment()
    if text.count(segment) == 1:
        return text.replace(segment, "", 1)
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    inside = False
    for line in lines:
        if BEGIN_MARKER in line:
            inside = True
            continue
        if END_MARKER in line:
            inside = False
            continue
        if not inside:
            output.append(line)
    return "".join(output)


def _has_managed_block(text: str) -> bool:
    return BEGIN_MARKER in text and END_MARKER in text


def _has_any_managed_marker(text: str) -> bool:
    return BEGIN_MARKER in text or END_MARKER in text


def _has_exact_managed_block(text: str) -> bool:
    return (
        text.count(BEGIN_MARKER) == 1
        and text.count(END_MARKER) == 1
        and text.count(_managed_segment()) == 1
    )


def _tasks_projection() -> str:
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


def _launch_projection() -> str:
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


def _assert_projection_owned(
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


def _atomic_write(path: Path, content: str) -> None:
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


def _settings_baseline_for_activation(settings_path: Path, original: str) -> str:
    begin_count = original.count(BEGIN_MARKER)
    end_count = original.count(END_MARKER)
    if begin_count != end_count or begin_count > 1:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} contains a malformed managed settings block"
        )
    baseline = _remove_managed_block(original)
    parsed = _parse_settings(baseline)
    foreign = [key for key in MANAGED_KEYS if key in parsed]
    if foreign:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} already contains foreign managed keys: "
            + ",".join(sorted(foreign))
        )
    return baseline


def activate(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
) -> str:
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    if settings_path.exists():
        original = settings_path.read_text(encoding="utf-8")
    else:
        original = "{\n}\n"

    # 三份本地投影构成一个入口。先验证全部 ownership，再写任一字节，避免
    # settings 已激活而 tasks/launch 因外来配置拒绝后的半激活状态。
    tasks_content = _tasks_projection()
    launch_content = _launch_projection()
    _assert_projection_owned(tasks_path, tasks_content, allow_managed_drift=True)
    _assert_projection_owned(launch_path, launch_content, allow_managed_drift=True)
    baseline = _settings_baseline_for_activation(settings_path, original)

    opening = baseline.index("{")
    updated = baseline[: opening + 1] + _managed_segment() + baseline[opening + 1 :]
    _parse_settings(updated)
    settings_outcome = "unchanged"
    if updated != original:
        _atomic_write(settings_path, updated)
        settings_outcome = "refreshed" if _has_managed_block(original) else "activated"
    task_outcome = "unchanged"
    if not tasks_path.exists() or tasks_path.read_text(encoding="utf-8") != tasks_content:
        _atomic_write(tasks_path, tasks_content)
        task_outcome = "projected"
    launch_outcome = "unchanged"
    if not launch_path.exists() or launch_path.read_text(encoding="utf-8") != launch_content:
        _atomic_write(launch_path, launch_content)
        launch_outcome = "projected"
    if settings_outcome == task_outcome == launch_outcome == "unchanged":
        return "unchanged"
    return "activated" if settings_outcome == "activated" else "refreshed"


def deactivate(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
) -> str:
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    _assert_projection_owned(tasks_path, _tasks_projection(), deleting=True)
    _assert_projection_owned(launch_path, _launch_projection(), deleting=True)
    settings_original = ""
    settings_updated = ""
    settings_changed = False
    if settings_path.exists():
        settings_original = settings_path.read_text(encoding="utf-8")
        if _has_any_managed_marker(settings_original):
            if not _has_exact_managed_block(settings_original):
                raise SystemExit(
                    "GATE_BLOCK: refusing to delete drifted managed settings projection"
                )
            settings_updated = settings_original.replace(_managed_segment(), "", 1)
            _parse_settings(settings_updated)
            parsed = _parse_settings(settings_updated)
            if any(key in parsed for key in MANAGED_KEYS):
                raise SystemExit(
                    "GATE_BLOCK: refusing to delete settings with foreign managed keys"
                )
            settings_changed = True
    changed = False
    for projection in (tasks_path, launch_path):
        if not projection.exists():
            continue
        projection.unlink()
        changed = True
    if not settings_path.exists():
        return "deactivated" if changed else "unchanged"
    if not settings_changed:
        return "deactivated" if changed else "unchanged"
    _atomic_write(settings_path, settings_updated)
    return "deactivated"


def status(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
) -> dict[str, str]:
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    settings_text = (
        settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    )
    settings_active = False
    if _has_exact_managed_block(settings_text):
        try:
            baseline = settings_text.replace(_managed_segment(), "", 1)
            parsed = _parse_settings(baseline)
            settings_active = not any(key in parsed for key in MANAGED_KEYS)
        except (json.JSONDecodeError, ValueError):
            settings_active = False
    tasks_active = (
        tasks_path.exists()
        and tasks_path.read_text(encoding="utf-8") == _tasks_projection()
    )
    launch_active = (
        launch_path.exists()
        and launch_path.read_text(encoding="utf-8") == _launch_projection()
    )
    resolved = shutil.which("flutter")
    expected = REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
    if resolved is None:
        command_state = "missing"
    else:
        try:
            command_state = (
                "facade" if Path(resolved).resolve() == expected.resolve() else "real_sdk"
            )
        except OSError:
            command_state = "unresolved"
    projection_active = settings_active and tasks_active and launch_active
    projection_present = (
        _has_any_managed_marker(settings_text)
        or tasks_path.exists()
        or launch_path.exists()
    )
    projection_state = (
        "active" if projection_active else "partial" if projection_present else "inactive"
    )
    ide_state = (
        "active"
        if tasks_active and launch_active
        else "partial"
        if tasks_path.exists() or launch_path.exists()
        else "inactive"
    )
    if projection_active and command_state == "facade":
        effective_state = "active"
    elif projection_active:
        effective_state = "reload_required"
    elif projection_present or command_state == "facade":
        effective_state = "inconsistent"
    else:
        effective_state = "inactive"
    return {
        "projectionState": projection_state,
        "terminalCommandResolution": command_state,
        "ideProfileState": ide_state,
        "effectiveState": effective_state,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="目标 settings.json（默认本仓库 .vscode/settings.json）",
    )
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--launch", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deactivate", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if args.status:
        status_payload = status(args.settings, args.tasks, args.launch)
        print(
            json.dumps(
                status_payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if status_payload["effectiveState"] != "active":
            print(
                "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; "
                "run `make app-activate-flutter-facade`, Reload Window, then "
                "open a new workspace terminal and verify "
                "`command -v flutter` resolves to the workspace facade",
                file=sys.stderr,
            )
            return 2
        return 0
    if args.deactivate:
        outcome = deactivate(args.settings, args.tasks, args.launch)
    else:
        outcome = activate(args.settings, args.tasks, args.launch)
    print(outcome)
    if outcome in ("activated", "refreshed", "deactivated"):
        print(
            "[flutter-facade] 请重载编辑器窗口（Reload Window）使新终端 PATH 生效。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
