"""工作区终端激活 CLI 的参数解析、scope 编排与结果投影。"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def merge_outcomes(outcomes: dict[str, str]) -> str:
    changed = [value for value in outcomes.values() if value != "unchanged"]
    if not changed:
        return "unchanged"
    if all(value == "deactivated" for value in changed):
        return "deactivated"
    if any(value == "refreshed" for value in changed):
        return "refreshed"
    return "activated"


def run_cli(
    argv: list[str],
    *,
    description: str | None,
    default_settings_path: Path,
    workspace_entrypoint_inactive_blocker: str,
    cursor_activate: Callable[..., str],
    cursor_deactivate: Callable[..., str],
    cursor_status: Callable[..., dict[str, str]],
    user_zsh_activate: Callable[..., str],
    user_zsh_deactivate: Callable[..., str],
    user_zsh_status: Callable[..., dict[str, str]],
    user_zsh_paths: Callable[..., tuple[Path, Path, Path]],
) -> int:
    """保持稳定 CLI surface，并把实际动作委托给入口模块提供的 API。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--settings",
        type=Path,
        default=default_settings_path,
        help="目标 settings.json（默认本仓库 .vscode/settings.json）",
    )
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--launch", type=Path)
    parser.add_argument(
        "--scope",
        choices=("cursor", "user-zsh", "all"),
        default="cursor",
        help="cursor 为默认注入面；user-zsh 是显式 opt-in",
    )
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--user-zsh-config", type=Path)
    parser.add_argument("--zshrc", type=Path)
    parser.add_argument("--zprofile", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deactivate", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    scopes = ("cursor", "user-zsh") if args.scope == "all" else (args.scope,)
    if args.status:
        payload: dict[str, Any] = {
            "existingShellCommandResolution": "not_observed",
            "scope": args.scope,
        }
        if "cursor" in scopes:
            payload["cursor"] = cursor_status(args.settings, args.tasks, args.launch)
        if "user-zsh" in scopes:
            payload["userZsh"] = user_zsh_status(
                home_path=args.home,
                config_path=args.user_zsh_config,
                zshrc_path=args.zshrc,
                zprofile_path=args.zprofile,
            )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        all_active = all(
            isinstance(scope_payload, dict)
            and scope_payload.get("projectionState") == "active"
            for key, scope_payload in payload.items()
            if key in {"cursor", "userZsh"}
        )
        if not all_active:
            print(
                f"GATE_BLOCK: {workspace_entrypoint_inactive_blocker}; "
                "requested projection scope is not fully active",
                file=sys.stderr,
            )
            return 2
        return 0

    outcomes: dict[str, str] = {}
    if args.deactivate:
        if "cursor" in scopes:
            outcomes["cursor"] = cursor_deactivate(
                args.settings, args.tasks, args.launch
            )
        if "user-zsh" in scopes:
            outcomes["user-zsh"] = user_zsh_deactivate(
                home_path=args.home,
                config_path=args.user_zsh_config,
                zshrc_path=args.zshrc,
                zprofile_path=args.zprofile,
            )
    else:
        if "cursor" in scopes:
            outcomes["cursor"] = cursor_activate(
                args.settings, args.tasks, args.launch
            )
        if "user-zsh" in scopes:
            outcomes["user-zsh"] = user_zsh_activate(
                home_path=args.home,
                config_path=args.user_zsh_config,
                zshrc_path=args.zshrc,
                zprofile_path=args.zprofile,
            )
    outcome = merge_outcomes(outcomes)
    projection_state = "inactive" if args.deactivate else "active"
    print(
        json.dumps(
            {
                "existingShellCommandResolution": "not_observed",
                "outcome": outcome,
                "projectionState": projection_state,
                "scopes": outcomes,
            },
            sort_keys=True,
        )
    )
    print(
        f"[flutter-terminal-injection] projection state={projection_state} "
        f"outcome={outcome}; existing shell command resolution=not_observed.",
        file=sys.stderr,
    )
    if "cursor" in scopes:
        print(
            "[flutter-terminal-injection] Cursor terminal env changed; "
            "Reload Window for new terminals.",
            file=sys.stderr,
        )
    if "user-zsh" in scopes:
        if args.deactivate:
            print(
                "[flutter-terminal-injection] user-zsh projection removed; "
                "open a new shell for complete rollback.",
                file=sys.stderr,
            )
        else:
            generated, _, _ = user_zsh_paths(
                home_path=args.home,
                config_path=args.user_zsh_config,
                zshrc_path=args.zshrc,
                zprofile_path=args.zprofile,
            )
            print(
                "[flutter-terminal-injection] diagnose existing zsh before refresh: "
                "builtin whence -wa -- flutter run.sh; "
                "builtin whence -pa -- flutter run.sh",
                file=sys.stderr,
            )
            print(
                "[flutter-terminal-injection] refresh existing zsh: "
                f"builtin source {shlex.quote(str(generated))} && rehash",
                file=sys.stderr,
            )
    return 0
