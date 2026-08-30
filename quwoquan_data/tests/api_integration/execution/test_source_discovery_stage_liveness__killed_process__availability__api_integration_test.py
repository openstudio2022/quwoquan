"""真实进程被强制杀死后的来源发现阶段存活判定。

这里不使用可控时钟：心跳由一个真实子进程持续写盘，进程被 SIGKILL 杀死，随后越过
冻结的过期阈值。判定只读统一进度面，不查进程表也不看文件 mtime。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t8
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.source.research.stage_liveness import (  # noqa: E402
    StageLivenessKind,
    StageStatus,
    read_stage_liveness,
)

FROZEN_HEARTBEAT_INTERVAL_SECONDS = 1
FROZEN_HEARTBEAT_STALE_AFTER_SECONDS = 2
EXECUTION_ID = "20260807--travel-homepage-m100-root-cause--test-region-a--scale-001"

_HEARTBEAT_WRITER = """
import sys
import time

sys.path.insert(0, {scripts_root!r})

from content.source.research.stage_liveness import (
    StageStatus,
    write_source_discovery_progress,
)

path = __import__("pathlib").Path({progress_path!r})
index = 0
while True:
    write_source_discovery_progress(
        {execution_id!r},
        status=StageStatus.RUNNING,
        candidate_entity_count=180,
        terminal_entity_count=0,
        running_entity_ids=("来源发现候选-000",),
        frozen_max_concurrent_workers=8,
        heartbeat_interval_seconds={interval},
        heartbeat_stale_after_seconds={stale_after},
        elapsed_seconds=float(index),
        now_epoch_seconds=int(time.time()),
        path=path,
    )
    index += 1
    time.sleep({interval})
"""


def _last_heartbeat(path: Path) -> int:
    return int(json.loads(path.read_text(encoding="utf-8"))["lastHeartbeatEpochSeconds"])


def test_a_killed_stage_process_stops_heartbeating_and_reads_as_typed_stale(
    tmp_path: Path,
) -> None:
    progress_path = tmp_path / "auto_research_progress.json"
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-c",
            _HEARTBEAT_WRITER.format(
                scripts_root=str(SCRIPTS_ROOT),
                progress_path=str(progress_path),
                execution_id=EXECUTION_ID,
                interval=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
                stale_after=FROZEN_HEARTBEAT_STALE_AFTER_SECONDS,
            ),
        ],
        env={**os.environ, "PYTHONPATH": str(SCRIPTS_ROOT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not progress_path.is_file():
            if time.monotonic() > deadline or child.poll() is not None:
                _stdout, stderr = child.communicate(timeout=5)
                raise AssertionError(
                    f"heartbeat writer never produced a progress surface: {stderr}"
                )
            time.sleep(0.05)

        first = _last_heartbeat(progress_path)
        # 进程活着的时候心跳确实在前移。
        while _last_heartbeat(progress_path) == first:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        alive = read_stage_liveness(progress_path, now_epoch_seconds=int(time.time()))
        assert alive.kind is StageLivenessKind.PROGRESSING
        assert alive.status is StageStatus.RUNNING

        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
        killed_at_heartbeat = _last_heartbeat(progress_path)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)

    # 心跳确实停了：越过一个冻结间隔之后，最近心跳时刻没有再前移。
    time.sleep(FROZEN_HEARTBEAT_INTERVAL_SECONDS + 0.5)
    assert _last_heartbeat(progress_path) == killed_at_heartbeat

    # 越过冻结的过期阈值：判定为「运行中未按间隔心跳」，而不是「已终止不会再心跳」。
    while (
        int(time.time()) - killed_at_heartbeat
        <= FROZEN_HEARTBEAT_STALE_AFTER_SECONDS
    ):
        time.sleep(0.2)
    stale = read_stage_liveness(progress_path, now_epoch_seconds=int(time.time()))
    assert stale.kind is StageLivenessKind.STALE_WHILE_RUNNING
    assert stale.kind is not StageLivenessKind.TERMINATED_NO_FURTHER_HEARTBEAT
    assert stale.kind is not StageLivenessKind.PROGRESS_ABSENT
    assert not stale.is_failure

    # 最后一次心跳的事实仍然可读，没有被清零或覆盖为空。
    assert stale.last_heartbeat_epoch_seconds == killed_at_heartbeat
    assert stale.last_heartbeat_at != ""
    assert stale.silence_seconds > FROZEN_HEARTBEAT_STALE_AFTER_SECONDS
    assert stale.heartbeat_interval_seconds == FROZEN_HEARTBEAT_INTERVAL_SECONDS
    assert stale.heartbeat_stale_after_seconds == FROZEN_HEARTBEAT_STALE_AFTER_SECONDS
    assert stale.candidate_entity_count == 180
    assert stale.terminal_entity_count == 0
    assert stale.execution_id == EXECUTION_ID
