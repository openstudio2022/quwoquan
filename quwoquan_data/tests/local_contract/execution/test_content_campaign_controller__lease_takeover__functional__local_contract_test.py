# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from content.execution.campaign.runtime import (
    CampaignFenceError,
    CampaignLeaseTakeoverError,
    assert_campaign_fence,
    campaign_run_session,
    read_lane_checkpoint,
    read_runtime_snapshot,
    runtime_events_path,
    runtime_snapshot_path,
)
from content.execution.campaign.runtime_process import (
    begin_stale_controller_termination,
)
from content.execution.campaign.workspace import CampaignRuntimePaths
from core.io import read_json, write_json
from support.campaign_lanes_fixture import (  # noqa: F401
    ROOT_ID,
    _create_repo,
    _events,
    _execution_id,
    _restore_capsule_permissions_for_pytest_cleanup,
    _runtime,
)


def test_killed_controller_is_reconciled_and_old_generation_is_fenced(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    ready_path = tmp_path / "controller-ready.json"
    orphan_cli = tmp_path / "orphan/quwoquan_data/scripts/cli.py"
    orphan_cli.parent.mkdir(parents=True)
    orphan_cli.write_text(
        "import time\ntime.sleep(120)\n",
        encoding="utf-8",
    )
    lane_execution = _execution_id("article")
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child_code = f"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=60) as session:
    lane_root = Path({json.dumps(str(tmp_path / "orphan-lane-root"))})
    lane_root.mkdir(parents=True, exist_ok=True)
    lane = subprocess.Popen(
        [sys.executable, {json.dumps(str(orphan_cli))}, "--execution-id", {json.dumps(lane_execution)}],
        start_new_session=True,
    )
    session.lane_checkpoint(
        carrier="article",
        execution_id={json.dumps(lane_execution)},
        phase="review-only",
        status="running",
        capsule_ref="test-capsule",
        execution_root=lane_root,
        pid=lane.pid,
        pgid=os.getpgid(lane.pid),
    )
    Path({json.dumps(str(ready_path))}).write_text(json.dumps({{
        "runId": session.run_id,
        "generation": session.generation,
        "fencingToken": session.fencing_token,
        "lanePid": lane.pid,
    }}), encoding="utf-8")
    while True:
        time.sleep(1)
"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(scripts_root)
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"controller child exited early rc={child.returncode}: {stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    first = json.loads(ready_path.read_text(encoding="utf-8"))
    os.kill(child.pid, signal.SIGKILL)
    child.wait(timeout=5)
    killed_snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert killed_snapshot is not None
    assert killed_snapshot["status"] == "active"

    with campaign_run_session(runtime, ROOT_ID, lease_seconds=60) as restarted:
        assert restarted.generation == int(first["generation"]) + 1
        assert restarted.run_id != first["runId"]
        with pytest.raises(CampaignFenceError, match="DATA.CAMPAIGN.FENCED"):
            assert_campaign_fence(
                runtime,
                ROOT_ID,
                run_id=str(first["runId"]),
                generation=int(first["generation"]),
                fencing_token=str(first["fencingToken"]),
            )
        restarted.finish(status="blocked", phase="test", failure=None)

    reconciled = read_runtime_snapshot(runtime, ROOT_ID)
    assert reconciled is not None
    assert reconciled["generation"] == 2
    assert reconciled["status"] == "blocked"
    reconciled_lane = read_lane_checkpoint(runtime, ROOT_ID, "article")
    assert reconciled_lane is not None
    assert reconciled_lane["status"] == "interrupted"
    assert reconciled_lane["termination"] in {"terminated", "killed"}
    lane_pid = int(first["lanePid"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        observed = subprocess.run(
            ["ps", "-p", str(lane_pid), "-o", "stat="],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not observed or observed.startswith("Z"):
            break
        time.sleep(0.05)
    assert not observed or observed.startswith("Z")
    event_types = {
        row["eventType"] for row in _events(runtime_events_path(runtime, ROOT_ID))
    }
    assert "stale_generation_reconciled" in event_types


def _spawn_live_stall_controller(
    tmp_path: Path,
    runtime: CampaignRuntimePaths,
    *,
    label: str,
    stall: bool = True,
) -> tuple[subprocess.Popen[str], dict[str, object]]:
    ready_path = tmp_path / f"{label}-controller-ready.json"
    controller_cli = tmp_path / label / "quwoquan_data/scripts/cli.py"
    controller_cli.parent.mkdir(parents=True)
    controller_cli.write_text(
        f"""
import json
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=1) as session:
    Path({json.dumps(str(ready_path))}).write_text(json.dumps({{
        "runId": session.run_id,
        "generation": session.generation,
        "fencingToken": session.fencing_token,
    }}), encoding="utf-8")
    while True:
        time.sleep(1)
""",
        encoding="utf-8",
    )
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(controller_cli),
            "campaign",
            "run",
            "--root-execution-id",
            ROOT_ID,
        ],
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(scripts_root),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"live-stall controller exited early rc={child.returncode}: "
                f"{stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    initial = json.loads(ready_path.read_text(encoding="utf-8"))
    if stall:
        os.kill(child.pid, signal.SIGSTOP)
        time.sleep(1.25)
    return child, initial


def _force_stop_controller(child: subprocess.Popen[str]) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=5)


def test_fresh_live_controller_lease_blocks_takeover_without_signalling(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, _first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="fresh-controller",
        stall=False,
    )
    try:
        with (
            pytest.raises(
                CampaignLeaseTakeoverError,
                match="DATA.CAMPAIGN.LEASE_ACTIVE",
            ),
            campaign_run_session(
                runtime,
                ROOT_ID,
                lease_seconds=1,
                process_termination_timeout_seconds=0.2,
            ),
        ):
            raise AssertionError("fresh controller lease must remain authoritative")
        assert child.poll() is None
    finally:
        _force_stop_controller(child)


def test_expired_live_controller_is_identity_checked_terminated_and_fenced(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="live-stall",
    )
    try:
        stalled = read_runtime_snapshot(runtime, ROOT_ID)
        assert stalled is not None
        assert stalled["pid"] == child.pid
        assert stalled["pgid"] == child.pid
        assert stalled["controllerProcessIdentity"].startswith("sha256:")

        with campaign_run_session(
            runtime,
            ROOT_ID,
            lease_seconds=1,
            process_termination_timeout_seconds=0.2,
        ) as restarted:
            assert restarted.generation == int(first["generation"]) + 1
            with pytest.raises(CampaignFenceError, match="DATA.CAMPAIGN.FENCED"):
                assert_campaign_fence(
                    runtime,
                    ROOT_ID,
                    run_id=str(first["runId"]),
                    generation=int(first["generation"]),
                    fencing_token=str(first["fencingToken"]),
                )
            restarted.finish(status="blocked", phase="test", failure=None)

        child.wait(timeout=5)
        assert child.returncode == -signal.SIGKILL
        takeover_events = [
            row
            for row in _events(runtime_events_path(runtime, ROOT_ID))
            if row["eventType"] == "stale_controller_takeover"
        ]
        assert len(takeover_events) == 1
        assert takeover_events[0]["controllerTermination"] == "killed"
    finally:
        _force_stop_controller(child)


def test_live_controller_identity_drift_blocks_takeover_without_signalling(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, _first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="live-stall-identity-drift",
    )
    try:
        snapshot_path = runtime_snapshot_path(runtime, ROOT_ID)
        snapshot = read_json(snapshot_path)
        snapshot["controllerProcessIdentity"] = "sha256:" + ("0" * 64)
        write_json(snapshot_path, snapshot)

        with (
            pytest.raises(
                CampaignLeaseTakeoverError,
                match="DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            ),
            campaign_run_session(
                runtime,
                ROOT_ID,
                lease_seconds=1,
                process_termination_timeout_seconds=0.2,
            ),
        ):
            raise AssertionError("identity-drifted controller must not be replaced")
        assert child.poll() is None
    finally:
        _force_stop_controller(child)


@pytest.mark.parametrize(
    ("pid", "pgid"),
    ((1, 1), (os.getpid(), os.getpgrp()), (os.getpid(), os.getpgrp() + 1)),
)
def test_controller_takeover_never_signals_unsafe_process_groups(
    monkeypatch: pytest.MonkeyPatch,
    pid: int,
    pgid: int,
) -> None:
    signalled: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda group, _signal: signalled.append(group))
    snapshot = {
        "rootExecutionId": ROOT_ID,
        "runId": "unsafe-controller",
        "generation": 1,
        "fencingToken": "sha256:" + ("1" * 64),
        "controllerProcessIdentity": "sha256:" + ("2" * 64),
        "hostname": subprocess.check_output(["hostname"], text=True).strip(),
        "pid": pid,
        "pgid": pgid,
    }

    with pytest.raises(
        CampaignLeaseTakeoverError,
        match="DATA.CAMPAIGN.TAKEOVER_PROCESS_GROUP_UNSAFE",
    ):
        begin_stale_controller_termination(snapshot, root_execution_id=ROOT_ID)
    assert signalled == []


def test_sigterm_unwinds_controller_and_stops_owned_lane_process_group(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    ready_path = tmp_path / "sigterm-controller-ready.json"
    lane_cli = tmp_path / "sigterm/quwoquan_data/scripts/cli.py"
    lane_cli.parent.mkdir(parents=True)
    lane_cli.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    lane_execution = _execution_id("video")
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child_code = f"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=60) as session:
    lane_root = Path({json.dumps(str(tmp_path / "sigterm-lane-root"))})
    lane_root.mkdir(parents=True, exist_ok=True)
    lane = subprocess.Popen(
        [sys.executable, {json.dumps(str(lane_cli))}, "--execution-id", {json.dumps(lane_execution)}],
        start_new_session=True,
    )
    session.lane_checkpoint(
        carrier="video",
        execution_id={json.dumps(lane_execution)},
        phase="review-only",
        status="running",
        capsule_ref="test-capsule",
        execution_root=lane_root,
        pid=lane.pid,
        pgid=os.getpgid(lane.pid),
    )
    Path({json.dumps(str(ready_path))}).write_text(
        json.dumps({{"lanePid": lane.pid}}), encoding="utf-8"
    )
    while True:
        time.sleep(1)
"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(scripts_root),
    }
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"controller child exited early rc={child.returncode}: "
                f"{stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    lane_pid = int(json.loads(ready_path.read_text(encoding="utf-8"))["lanePid"])

    os.kill(child.pid, signal.SIGTERM)
    child.wait(timeout=10)
    assert child.returncode != 0
    snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert snapshot is not None
    assert snapshot["status"] == "interrupted"
    assert "CampaignControllerTerminated" in str(snapshot["failure"])
    checkpoint = read_lane_checkpoint(runtime, ROOT_ID, "video")
    assert checkpoint is not None
    assert checkpoint["status"] == "interrupted"
    assert checkpoint["termination"] in {"terminated", "killed"}
    observed = subprocess.run(
        ["ps", "-p", str(lane_pid), "-o", "stat="],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not observed or observed.startswith("Z")
