"""同 target 的 mutable test_live 栈与 immutable candidate 栈互斥。

两种运行形态共享同一 canonical 端口段；历史上 candidate `up` 在 test_live
活跃时只会在 Compose 中途以 "Bind ... port is already allocated" 隐晦失败并
回收现场，报告里没有可诊断证据。该合约钉住启动前的显式 fail-fast 语义。
"""

from __future__ import annotations

import pytest

from quwoquan_ops.cli.lib.local_runtime_reservation import (
    assert_no_running_mutable_runtime,
)


@pytest.mark.parametrize(
    "status",
    [
        # running：容器全量健康运行。
        "running",
        # partial：dev-session 中断后容器仍占端口的常见形态；机械判 running
        # 会漏拦并复现隐晦的 Compose 端口失败。
        "partial",
        # prepared：计划已登记，资源归属未释放。
        "prepared",
    ],
)
def test_unreleased_mutable_runtime_blocks_candidate_startup(status) -> None:
    attempt = {
        "status": status,
        "attemptId": "alpha-test-live-0123456789abcdef",
    }

    with pytest.raises(RuntimeError) as excinfo:
        assert_no_running_mutable_runtime(attempt, "alpha-local")

    message = str(excinfo.value)
    assert "alpha-local" in message
    assert "alpha-test-live-0123456789abcdef" in message
    assert status in message
    assert "down --target alpha-local" in message


@pytest.mark.parametrize(
    "attempt",
    [
        None,
        {"status": "stopped", "attemptId": "alpha-test-live-old"},
    ],
)
def test_released_mutable_runtime_allows_candidate_startup(attempt) -> None:
    assert_no_running_mutable_runtime(attempt, "alpha-local")
