# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003
"""run.sh 依赖 bundle stale 的一次性交互式自动同步契约。

驱动方式：从 run.sh 原字节提取 ``enter_workspace_launch_projection`` 函数，
在沙箱 ROOT_DIR/APP_DIR/QWQ_OUTPUT_ROOT 下以真实 bash 子进程执行；
projection/stackctl/readback 全部用可计数 stub 注入。正例用 pty 提供真实
双 TTY，负例用管道子进程证明非交互路径 fail-closed 且不触发 auto-sync。
"""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[3]
LAUNCHER = APP_DIR / "run.sh"

_EXEC_MARKER = "PROJECTED_RUN_SH_EXECUTED"
_SYNC_NOTICE = "完成后自动重试一次启动投影"

_PREPARE_STUB = '''\
import json
import os
import pathlib
import sys

state = pathlib.Path(os.environ["STUB_STATE_DIR"])
counter = state / "projection_calls"
count = int(counter.read_text(encoding="ascii")) if counter.exists() else 0
count += 1
counter.write_text(str(count), encoding="ascii")
mode = os.environ.get("STUB_PREPARE_MODE", "always_stale")
if mode == "stale_then_ok" and count >= 2:
    print(
        json.dumps(
            {
                "projectionRoot": os.environ["STUB_PROJECTION_ROOT"],
                "sourceCapsuleManifest": os.environ["STUB_PROJECTION_ROOT"]
                + "/input-capsule/manifest.json",
                "sourceRevision": "1" * 40,
                "sourceCapsuleDigest": "sha256:" + "2" * 64,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0)
if mode == "generic_failure":
    print(
        json.dumps(
            {
                "status": "failed",
                "errorCode": "APP.LAUNCH.workspace_projection_failed",
            },
            sort_keys=True,
        )
    )
    print(
        "APP.LAUNCH.workspace_projection_failed: fixture generic failure",
        file=sys.stderr,
    )
    raise SystemExit(2)
print(
    json.dumps(
        {
            "status": "failed",
            "errorCode": "APP.DEPENDENCY.bundle_stale",
            "errorField": "nativeResolutionInputDigest",
        },
        sort_keys=True,
    )
)
print(
    "APP.DEPENDENCY.bundle_stale: App dependency bundle is stale for "
    "nativeResolutionInputDigest",
    file=sys.stderr,
)
raise SystemExit(2)
'''

_STACKCTL_STUB = '''\
import json
import os
import pathlib
import sys

state = pathlib.Path(os.environ["STUB_STATE_DIR"])
counter = state / "sync_calls"
count = int(counter.read_text(encoding="ascii")) if counter.exists() else 0
count += 1
counter.write_text(str(count), encoding="ascii")
(state / f"sync_argv_{count}.json").write_text(
    json.dumps(sys.argv[1:]), encoding="utf-8"
)
mode = os.environ.get("STUB_SYNC_MODE", "committed")
if mode == "invalid_json":
    print("not-json")
    raise SystemExit(2)
if mode == "mixed_json":
    print('{"exitCode":2,"summary":"blocked","details":[]}', "trailing-noise")
    raise SystemExit(2)
if mode == "exit0_invalid_json":
    print("not-json")
    raise SystemExit(0)
if mode == "empty_json":
    raise SystemExit(2)
if mode == "exit0_nonzero_json":
    print(
        json.dumps(
            {
                "exitCode": 2,
                "summary": "App dependency sync blocked",
                "details": ["APP.DEPENDENCY.sync_blocked: invalid zero process status"],
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0)
if mode in {"shell_fail", "details_fail"}:
    print(
        json.dumps(
            {
                "exitCode": 2,
                "summary": "App dependency sync blocked",
                "details": [
                    "APP.DEPENDENCY.sync_failed: production Pub failed",
                    "APP.DEPENDENCY.lock_readback_failed: pubspec.lock drifted",
                ],
            },
            sort_keys=True,
        )
    )
    raise SystemExit(2)
if mode == "ambiguous":
    print(
        json.dumps(
            {
                "exitCode": 2,
                "summary": "App dependency sync blocked",
                "details": [
                    "APP.DEPENDENCY.activation_commit_ambiguous: "
                    "readback=unknown; generation preserved"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(2)
attempt = "feedc0defeedc0de"
activation = {"attemptId": attempt, "status": "committed"}
if mode == "not_committed":
    activation["status"] = "prepared"
else:
    (state / "active_attempt").write_text(attempt, encoding="ascii")
print(
    json.dumps(
        {
            "activation": activation,
            "exitCode": 0,
            "summary": "App dependency sync completed",
            "details": ["attemptId=" + attempt],
        },
        indent=2,
        sort_keys=True,
    )
)
raise SystemExit(0)
'''

_BUNDLE_STUB = '''\
import os
import pathlib
import types


def load_active_dependency_bundle(*, repo_root):
    del repo_root
    state = pathlib.Path(os.environ["STUB_STATE_DIR"])
    counter = state / "readback_calls"
    count = int(counter.read_text(encoding="ascii")) if counter.exists() else 0
    counter.write_text(str(count + 1), encoding="ascii")
    mode = os.environ.get("STUB_READBACK_MODE", "consistent")
    if mode == "error":
        raise ValueError("App dependency bundle active pointer fields mismatch")
    path = state / "active_attempt"
    attempt = path.read_text(encoding="ascii").strip() if path.exists() else ""
    if mode == "mismatch":
        attempt = "deadbeefdeadbeef"
    return types.SimpleNamespace(active={"attemptId": attempt})
'''

_PROJECTED_RUN_SH = '#!/usr/bin/env bash\necho "PROJECTED_RUN_SH_EXECUTED args:$*"\nexit 0\n'


def _extracted_projection_function() -> str:
    source = LAUNCHER.read_text(encoding="utf-8")
    start = source.index("enter_workspace_launch_projection() {")
    end = source.index("\n}\n", start)
    return source[start : end + len("\n}\n")]


def _build_sandbox(
    tmp_path: Path,
    *,
    prepare_mode: str,
    sync_mode: str = "committed",
    readback_mode: str = "consistent",
) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "root"
    state = tmp_path / "state"
    output = tmp_path / "output"
    projected = tmp_path / "projected"
    home = tmp_path / "home"
    tmpdir = tmp_path / "tmp"
    for path in (root, state, output, projected / "quwoquan_app", home, tmpdir):
        path.mkdir(parents=True)
    (root / ".git").mkdir()

    prepare = (
        root / "quwoquan_app/scripts/device/prepare_workspace_launch_projection.py"
    )
    prepare.parent.mkdir(parents=True)
    prepare.write_text(_PREPARE_STUB, encoding="utf-8")

    stackctl = root / "quwoquan_ops/cli/stackctl.py"
    stackctl.parent.mkdir(parents=True)
    stackctl.write_text(_STACKCTL_STUB, encoding="utf-8")
    bundle = root / "quwoquan_ops/cli/lib/package_reuse/dependency_bundle.py"
    bundle.parent.mkdir(parents=True)
    bundle.write_text(_BUNDLE_STUB, encoding="utf-8")
    for package in (
        root / "quwoquan_ops",
        root / "quwoquan_ops/cli",
        root / "quwoquan_ops/cli/lib",
        root / "quwoquan_ops/cli/lib/package_reuse",
    ):
        (package / "__init__.py").write_text("", encoding="utf-8")

    exec_target = projected / "quwoquan_app/run.sh"
    exec_target.write_text(_PROJECTED_RUN_SH, encoding="utf-8")
    exec_target.chmod(0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'ROOT_DIR="{root}"\n'
        f'APP_DIR="{root / "quwoquan_app"}"\n'
        f'QWQ_OUTPUT_ROOT="{output}"\n'
        'ORIGINAL_LAUNCH_ARGUMENTS=(--probe-arg)\n'
        + _extracted_projection_function()
        + '\nenter_workspace_launch_projection --probe-arg\n'
        'echo "FUNCTION_RETURNED_WITHOUT_EXEC"\n',
        encoding="utf-8",
    )
    driver.chmod(0o755)

    interpreter = Path(sys.executable).resolve()
    # 环境从零构造：不继承宿主 QWQ_*，QWQ_OUTPUT_ROOT 只在 driver 内指向私有沙箱。
    env = {
        "PATH": os.pathsep.join((str(interpreter.parent), "/usr/bin", "/bin")),
        "HOME": str(home),
        "TMPDIR": str(tmpdir),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "en_US.UTF-8",
        "STUB_STATE_DIR": str(state),
        "STUB_PREPARE_MODE": prepare_mode,
        "STUB_SYNC_MODE": sync_mode,
        "STUB_READBACK_MODE": readback_mode,
        "STUB_PROJECTION_ROOT": str(projected),
    }
    return driver, env, state


def _count(state: Path, name: str) -> int:
    path = state / name
    return int(path.read_text(encoding="ascii")) if path.exists() else 0


def _run_driver_in_pty(
    driver: Path,
    env: dict[str, str],
    *,
    cwd: Path,
    timeout: float = 60.0,
) -> tuple[int, str]:
    pid, fd = pty.fork()
    if pid == 0:
        # 子进程 stdin/stdout/stderr 全部绑定 pty slave：-t 0 与 -t 2 为真。
        try:
            os.chdir(cwd)
            os.execve("/bin/bash", ["/bin/bash", str(driver)], env)
        finally:
            os._exit(127)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                os.kill(pid, signal.SIGKILL)
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
    finally:
        os.close(fd)
    _pid, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), output.decode("utf-8", errors="replace")



def _run_driver_with_streams(
    driver: Path,
    env: dict[str, str],
    *,
    cwd: Path,
    stdin_tty: bool,
    stderr_tty: bool,
    timeout: float = 60.0,
) -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    stdin = slave_fd if stdin_tty else subprocess.DEVNULL
    stderr = slave_fd if stderr_tty else subprocess.PIPE
    process = subprocess.Popen(
        ["/bin/bash", str(driver)],
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=False,
    )
    os.close(slave_fd)
    try:
        stdout, piped_stderr = process.communicate(timeout=timeout)
        tty_output = bytearray()
        if stderr_tty:
            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                tty_output.extend(chunk)
        return (
            process.returncode,
            (stdout or b"").decode("utf-8", errors="replace")
            + (piped_stderr or b"").decode("utf-8", errors="replace")
            + tty_output.decode("utf-8", errors="replace"),
        )
    finally:
        os.close(master_fd)


class TestStaticContract:
    def test_recovery_block_is_single_shot_and_isolated_from_dependency_retry(
        self,
    ) -> None:
        section = _extracted_projection_function()
        assert "WORKSPACE_DEPENDENCY_AUTO_SYNC_USED=0" in section
        assert "WORKSPACE_DEPENDENCY_AUTO_SYNC_USED=1" in section
        assert "while :" not in section
        assert "-initial" in section and "-retry" in section
        assert "-t 0 && -t 2" in section
        assert "--output-format json app-dependency-sync" in section
        assert "load_active_dependency_bundle" in section
        assert '"APP.DEPENDENCY.bundle_stale"' in section
        # 不复用/污染后文 iOS 重试的 DEPENDENCY_RETRY 状态机（注释提及除外）。
        assert "$DEPENDENCY_RETRY" not in section
        assert "DEPENDENCY_RETRY=" not in section
        source = LAUNCHER.read_text(encoding="utf-8")
        assert "DEPENDENCY_RETRY=0" in source

    def test_recovery_requires_live_workspace_outer_entry(self) -> None:
        section = _extracted_projection_function()
        recovery_guard = section.index('!= "APP.DEPENDENCY.bundle_stale"')
        guard_block = section[recovery_guard : section.index("mktemp", recovery_guard)]
        assert "QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST" in guard_block
        assert '.git' in guard_block


class TestRealSubprocess:
    def test_non_tty_stale_fails_closed_without_auto_sync(
        self, tmp_path: Path
    ) -> None:
        driver, env, state = _build_sandbox(tmp_path, prepare_mode="always_stale")

        result = subprocess.run(
            ["/bin/bash", str(driver)],
            cwd=tmp_path,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert result.returncode == 2
        assert _count(state, "projection_calls") == 1
        assert _count(state, "sync_calls") == 0
        stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
        assert stderr_lines[0].startswith("APP.DEPENDENCY.bundle_stale:")
        assert "APP.LAUNCH.workspace_entrypoint_inactive" in result.stderr
        assert _EXEC_MARKER not in result.stdout

    def test_tty_stale_syncs_once_then_retries_projection_once(
        self, tmp_path: Path
    ) -> None:
        driver, env, state = _build_sandbox(tmp_path, prepare_mode="stale_then_ok")

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 0, output
        assert _EXEC_MARKER in output
        assert "args:--probe-arg" in output
        assert _count(state, "projection_calls") == 2
        assert _count(state, "sync_calls") == 1
        assert _count(state, "readback_calls") == 1
        argv = json.loads(
            (state / "sync_argv_1.json").read_text(encoding="utf-8")
        )
        assert argv == ["--output-format", "json", "app-dependency-sync"]
        # 先原样输出 stale blocker 行，再出现中文同步说明。
        stale_at = output.index("APP.DEPENDENCY.bundle_stale:")
        notice_at = output.index(_SYNC_NOTICE)
        assert stale_at < notice_at

    @pytest.mark.parametrize(
        "sync_mode", ["shell_fail", "ambiguous", "not_committed"]
    )
    def test_tty_sync_failure_or_ambiguity_never_retries(
        self, tmp_path: Path, sync_mode: str
    ) -> None:
        driver, env, state = _build_sandbox(
            tmp_path, prepare_mode="stale_then_ok", sync_mode=sync_mode
        )

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        # stub 第二次 projection 本可成功；恰好 1 次即证明失败后没有重试。
        assert _count(state, "projection_calls") == 1
        assert _count(state, "sync_calls") == 1
        assert _EXEC_MARKER not in output
        assert "APP.LAUNCH.workspace_entrypoint_inactive" in output

    @pytest.mark.parametrize("readback_mode", ["mismatch", "error"])
    def test_tty_readback_inconsistency_never_retries(
        self, tmp_path: Path, readback_mode: str
    ) -> None:
        driver, env, state = _build_sandbox(
            tmp_path, prepare_mode="stale_then_ok", readback_mode=readback_mode
        )

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        assert _count(state, "projection_calls") == 1
        assert _count(state, "sync_calls") == 1
        assert _count(state, "readback_calls") == 1
        assert _EXEC_MARKER not in output

    def test_tty_second_stale_does_not_sync_again(self, tmp_path: Path) -> None:
        driver, env, state = _build_sandbox(tmp_path, prepare_mode="always_stale")

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        assert _count(state, "projection_calls") == 2
        assert _count(state, "sync_calls") == 1
        assert output.count(_SYNC_NOTICE) == 1
        assert _EXEC_MARKER not in output

    @pytest.mark.parametrize(
        ("stdin_tty", "stderr_tty"),
        [(True, False), (False, True), (False, False)],
    )
    def test_mixed_or_non_tty_stale_never_auto_syncs(
        self,
        tmp_path: Path,
        stdin_tty: bool,
        stderr_tty: bool,
    ) -> None:
        driver, env, state = _build_sandbox(tmp_path, prepare_mode="always_stale")

        exit_code, output = _run_driver_with_streams(
            driver,
            env,
            cwd=tmp_path,
            stdin_tty=stdin_tty,
            stderr_tty=stderr_tty,
        )

        assert exit_code == 2, output
        assert _count(state, "projection_calls") == 1
        assert _count(state, "sync_calls") == 0

    def test_tty_real_failure_json_prints_every_detail_in_order(
        self, tmp_path: Path
    ) -> None:
        driver, env, state = _build_sandbox(
            tmp_path, prepare_mode="stale_then_ok", sync_mode="details_fail"
        )

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        first = output.index("APP.DEPENDENCY.sync_failed: production Pub failed")
        second = output.index("APP.DEPENDENCY.lock_readback_failed: pubspec.lock drifted")
        assert first < second
        assert "invalid or empty JSON" not in output
        assert _count(state, "sync_calls") == 1
        assert _count(state, "readback_calls") == 0

    @pytest.mark.parametrize(
        "sync_mode",
        [
            "invalid_json",
            "mixed_json",
            "exit0_invalid_json",
            "empty_json",
        ],
    )
    def test_tty_invalid_or_empty_sync_json_uses_generic_blocker(
        self, tmp_path: Path, sync_mode: str
    ) -> None:
        driver, env, state = _build_sandbox(
            tmp_path, prepare_mode="stale_then_ok", sync_mode=sync_mode
        )

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        if sync_mode == "exit0_nonzero_json":
            assert (
                "dependency sync detail: APP.DEPENDENCY.sync_blocked: "
                "invalid zero process status"
            ) in output
            assert "APP.DEPENDENCY.sync_result_exit_mismatch: process=0 result=2" in output
        else:
            assert "canonical dependency sync returned invalid or empty JSON" in output
            assert "dependency sync detail:" not in output
        assert _count(state, "sync_calls") == 1
        assert _count(state, "readback_calls") == 0

    def test_tty_valid_failure_json_with_zero_process_status_keeps_details(
        self, tmp_path: Path
    ) -> None:
        driver, env, state = _build_sandbox(
            tmp_path,
            prepare_mode="stale_then_ok",
            sync_mode="exit0_nonzero_json",
        )

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        assert "APP.DEPENDENCY.sync_blocked: invalid zero process status" in output
        assert "APP.DEPENDENCY.sync_result_exit_mismatch: process=0 result=2" in output
        assert "invalid or empty JSON" not in output
        assert _count(state, "sync_calls") == 1
        assert _count(state, "readback_calls") == 0

    def test_tty_generic_failure_does_not_auto_sync(self, tmp_path: Path) -> None:
        driver, env, state = _build_sandbox(tmp_path, prepare_mode="generic_failure")

        exit_code, output = _run_driver_in_pty(driver, env, cwd=tmp_path)

        assert exit_code == 2, output
        assert _count(state, "projection_calls") == 1
        assert _count(state, "sync_calls") == 0
        assert "APP.LAUNCH.workspace_entrypoint_inactive" in output
