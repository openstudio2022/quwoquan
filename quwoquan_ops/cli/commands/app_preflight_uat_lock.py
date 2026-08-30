"""stackctl App content UAT 外层运行时锁封装。"""

from __future__ import annotations

import argparse
from typing import Any


def command_app_content_uat(args: argparse.Namespace) -> dict[str, Any]:
    """持有目标运行时锁后委托 stackctl 可 monkeypatch 的 UAT 实现。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    device_id = str(getattr(args, "device_id", "") or "").strip()
    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run or not targets or not device_id:
        return _stackctl._command_app_content_uat(args)
    try:
        runtime_use_lock = _stackctl.acquire_local_runtime_use_lock(
            target=",".join(targets),
            purpose=f"app-content-uat:{args.platform}:{device_id}",
        )
    except RuntimeError as error:
        return _stackctl._command_app_content_uat(args, initial_issues=(str(error),))
    try:
        return _stackctl._command_app_content_uat(args)
    finally:
        runtime_use_lock.close()


__all__ = ["command_app_content_uat"]
