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
    from quwoquan_ops.cli.commands.app_preflight_uat_orchestration import APP_CONTENT_UAT_TARGETS
    # 非法/重复目标交领域入口给出 typed 拒绝，不能先占用任何本地 runtime。
    if (dry_run or not targets or not device_id or len(targets) != len(set(targets))
            or not set(targets).issubset(APP_CONTENT_UAT_TARGETS)):
        return _stackctl._command_app_content_uat(args)
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import content_source_for_target
    try:
        remote_targets = [target for target in targets if content_source_for_target(target) == "remote"]
    except ValueError as error:
        return _stackctl._command_app_content_uat(args, initial_issues=(str(error),))
    if not remote_targets:
        return _stackctl._command_app_content_uat(args)
    try:
        runtime_use_lock = _stackctl.acquire_local_runtime_use_lock(
            target=",".join(remote_targets),
            purpose=f"app-content-uat:{args.platform}:{device_id}",
        )
    except RuntimeError as error:
        return _stackctl._command_app_content_uat(args, initial_issues=(str(error),))
    try:
        return _stackctl._command_app_content_uat(args)
    finally:
        runtime_use_lock.close()


__all__ = ["command_app_content_uat"]
