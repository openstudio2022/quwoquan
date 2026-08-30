"""loop_driver 单轮 hard timeout 的终止范围与 claim TTL 约束（DEC-005）。

绑定验收：multi-carrier-release `GWT-020.t4`。超时只杀直接子进程时，宿主派生的
孙进程会带着 lane claim 继续跑，驱动以为这一轮已经结束——两个写者同时在场。
本测试用一个真实派生孙进程的假宿主命令，断言超时终止落到整个进程组。

spec_ref: multi-carrier-release GWT-020.t4
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

DRIVER = SCRIPTS_ROOT / "content" / "execution" / "runner" / "loop_driver.sh"
EXEC_ID = "20260827--travel-homepage-coverage--test-region--pilot-901"


def _stub_cli(root: Path, *, next_stage: str, claim_active: bool) -> Path:
    """一个只回答 lane-claim/fleet-status 的假 data CLI。

    驱动只从 CLI 读两件事就决定是否再起一轮，所以复现超时行为不需要真实工作包；
    真实工作包会把「进程组是否被杀干净」和「receipt 链是否正确」两件事混在一起。
    """
    stub = root / "cli.py"
    stub.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if 'lane-claim' in args:\n"
        f"    active = {claim_active!r}\n"
        "    print(json.dumps({'active': active, 'claim': None}))\n"
        "    sys.exit(3 if active else 0)\n"
        "if 'fleet-status' in args:\n"
        "    print(json.dumps({'executions': [\n"
        f"        {{'verdict': 'pass', 'next': {next_stage!r}}}\n"
        "    ]}))\n"
        "    sys.exit(0)\n"
        "sys.exit(64)\n",
        encoding="utf-8",
    )
    return stub


def _run_driver(
    *,
    stub: Path,
    host_cmd: str,
    round_timeout: int,
    tmp_path: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    # 驱动自己从脚本位置上溯五层推导 REPO_ROOT，所以副本必须放在同构深度上，
    # 否则失败原因会是「找不到 loop-prompt」而不是被测的超时行为。
    runner_root = (
        tmp_path
        / "repo"
        / "quwoquan_data"
        / "scripts"
        / "content"
        / "execution"
        / "runner"
    )
    runner_root.mkdir(parents=True, exist_ok=True)
    prompt = (
        tmp_path
        / "repo"
        / ".agents"
        / "skills"
        / "content-production"
        / "references"
        / "loop-prompt.md"
    )
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("---\nstub prompt for <executionId>\n", encoding="utf-8")
    driver = runner_root / "loop_driver.sh"
    driver.write_text(
        DRIVER.read_text(encoding="utf-8").replace(
            '"$REPO_ROOT/quwoquan_data/scripts/cli.py"', f'"{stub}"'
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "bash",
            str(driver),
            "--execution-id",
            EXEC_ID,
            "--host-cmd",
            host_cmd,
            "--max-rounds",
            "1",
            "--round-timeout",
            str(round_timeout),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_round_timeout_kills_the_whole_session_process_group(tmp_path: Path) -> None:
    stub = _stub_cli(tmp_path, next_stage="1.download", claim_active=False)
    marker = tmp_path / "grandchild.pid"
    # 宿主会话派生一个比 round timeout 活得久的孙进程，自己也留在前台——无人值守
    # 会话被超时打断时就是这个形态：孙进程还握着工作包，父会话已经不在了。
    host_cmd = f"bash -c 'sleep 120 & echo $! > {marker}; sleep 120' #"

    started = time.monotonic()
    result = _run_driver(
        stub=stub, host_cmd=host_cmd, round_timeout=3, tmp_path=tmp_path, timeout=30
    )
    elapsed = time.monotonic() - started

    assert marker.is_file(), f"假宿主未派生孙进程: {result.stderr}"
    grandchild = int(marker.read_text(encoding="utf-8").strip())
    still_alive = _alive(grandchild)
    if still_alive:  # 清理后再断言，避免残留进程污染后续测试
        os.kill(grandchild, 9)
    assert not still_alive, "超时终止必须覆盖宿主派生的孙进程，而不只是直接子进程"
    assert elapsed < 20, "驱动必须在 round timeout 之后就交回控制权"


def test_round_timeout_longer_than_claim_ttl_refuses_to_start(tmp_path: Path) -> None:
    from content.execution.stage_receipt import (
        CLAIM_TTL_SAFETY_MARGIN_MINUTES,
        DEFAULT_CLAIM_TTL_MINUTES,
    )

    # 假 CLI 不判 timeout，所以这里换成真实 CLI：本轮要验的正是那条判据。
    beyond = (DEFAULT_CLAIM_TTL_MINUTES - CLAIM_TTL_SAFETY_MARGIN_MINUTES) * 60 + 1
    result = subprocess.run(
        [
            "bash",
            str(DRIVER),
            "--execution-id",
            EXEC_ID,
            "--host-cmd",
            "true #",
            "--max-rounds",
            "1",
            "--round-timeout",
            str(beyond),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
        cwd=DATA_ROOT.parent,
    )

    assert result.returncode == 64, result.stderr
    assert "claim TTL" in result.stderr


def test_admitted_round_timeout_is_not_refused(tmp_path: Path) -> None:
    from content.execution.stage_receipt import (
        CLAIM_TTL_SAFETY_MARGIN_MINUTES,
        DEFAULT_CLAIM_TTL_MINUTES,
    )

    stub = _stub_cli(tmp_path, next_stage="END", claim_active=False)
    inside = (DEFAULT_CLAIM_TTL_MINUTES - CLAIM_TTL_SAFETY_MARGIN_MINUTES) * 60
    result = _run_driver(
        stub=stub, host_cmd="true #", round_timeout=inside, tmp_path=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "execution completed" in result.stdout


def test_active_claim_still_stops_the_driver_before_any_round(tmp_path: Path) -> None:
    stub = _stub_cli(tmp_path, next_stage="1.download", claim_active=True)
    result = _run_driver(
        stub=stub, host_cmd="true #", round_timeout=60, tmp_path=tmp_path
    )

    assert result.returncode == 4, result.stderr
    assert "not taking over" in result.stderr
