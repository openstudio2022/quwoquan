"""内容生产有限提交的代次写围栏。

锁顺序必须是 ``coordination DB -> execution/publish lock``：调用方只能在
``CoordinationStore.fenced_write`` 的 callable 内取得 execution 或 publish 锁，
禁止持有这些外部锁后再进入 coordination DB，否则会形成锁顺序反转。

本围栏只协调遵守该 API 的进程，不提供宿主身份或操作系统级安全隔离。同一 OS
用户可以绕过 CLI/API 直接修改 execution、publish 根或 SQLite，因此该机制不能
被宣称为对恶意或不受控本机进程安全。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WriteFenceToken:
    """把一次有限写入绑定到 exact claim generation 和 target。"""

    iteration_id: str
    shard_id: str
    deployment_id: str
    team: str
    generation: int
    target_ref: str
