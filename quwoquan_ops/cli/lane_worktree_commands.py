#!/usr/bin/env python3
"""Render reviewed six-lane bootstrap/resync commands without executing mutation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

import local_worktree_inventory as inventory  # noqa: E402


def render(action: str) -> list[str]:
    policy = inventory.load_policy()
    project_root = inventory.resolve_project_root(ROOT, policy)
    hub = project_root / policy.bare_hub_directory
    commands: list[str] = []
    for branch, directory in policy.lane_worktree_directories:
        path = project_root / directory
        if action == "bootstrap":
            commands.append(
                f'QWQ_WORKTREE_AUTHZ="<reason>" git -C {hub} worktree add {path} {branch}'
            )
        else:
            commands.append(f"git -C {path} merge --ff-only {policy.integration_branch}")
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "resync"))
    args = parser.parse_args(argv)
    for command in render(args.action):
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
