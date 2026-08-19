#!/usr/bin/env python3
"""Remove one hermetic packaging-test workspace, including read-only capsules."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


_WORKSPACE_NAME = re.compile(r"quwoquan-deploy\.[A-Za-z0-9]{6}")


def validated_deployment_test_workspace(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("deployment test workspace must be an absolute path")
    if path.is_symlink():
        raise ValueError("deployment test workspace must not be a symlink")
    resolved = path.resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if resolved.parent != temporary_root or not _WORKSPACE_NAME.fullmatch(
        resolved.name
    ):
        raise ValueError(
            "deployment test workspace must be a direct child of the system "
            "temporary directory with the quwoquan-deploy.XXXXXX name"
        )
    return resolved


def cleanup_deployment_test_workspace(raw_path: str) -> None:
    workspace = validated_deployment_test_workspace(raw_path)
    if not workspace.exists():
        return
    if not workspace.is_dir():
        raise ValueError("deployment test workspace must be a directory")

    for directory, child_directories, _ in os.walk(
        workspace, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        mode = directory_path.stat(follow_symlinks=False).st_mode
        os.chmod(
            directory_path,
            mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
            follow_symlinks=False,
        )
        child_directories[:] = [
            name
            for name in child_directories
            if not (directory_path / name).is_symlink()
        ]
    shutil.rmtree(workspace)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace")
    args = parser.parse_args()
    try:
        cleanup_deployment_test_workspace(args.workspace)
    except (OSError, ValueError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
