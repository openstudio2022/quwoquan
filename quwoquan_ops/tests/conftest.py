"""本地契约测试不得读取或变更真实宿主运行权威。"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_local_runtime_host(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # live integration/UAT 保留其显式环境；local_contract 包括 unittest 测试同样隔离。
    if "local_contract" not in request.node.path.parts:
        return
    tmp_path = tmp_path_factory.mktemp("runtime-host")
    # clear=True 的环境测试也不允许退回真实用户主目录默认值。
    from quwoquan_ops.cli.lib import output_paths, host_locks
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(output_paths, "DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT", tmp_path / "runtime-output")
    monkeypatch.setattr(output_paths, "DEFAULT_DEPLOY_WORK_ROOT", tmp_path / "deploy")
    monkeypatch.setattr(host_locks, "DEFAULT_HOST_LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path / "deploy"))
    monkeypatch.setenv("QWQ_HOST_LOCK_ROOT", str(tmp_path / "locks"))
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/no-live-daemon.sock")
    monkeypatch.setenv("CONTAINER_HOST", f"unix://{tmp_path}/no-live-daemon.sock")
    # 系统观测是显式契约测试替身，绝不调用真实 docker；预算算法仍原样执行。
    from quwoquan_ops.cli.lib import local_runtime_capacity
    monkeypatch.setattr(local_runtime_capacity, "observe_reservation_capacity", lambda: {
        "hostCpu": 64, "hostMemory": 256 * 2**30,
        "vmCpu": 64, "vmMemory": 256 * 2**30, "disk": 1024 * 2**30,
    })
