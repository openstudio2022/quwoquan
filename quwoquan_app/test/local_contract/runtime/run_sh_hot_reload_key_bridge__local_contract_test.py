# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""run.sh 前台会话的 r/R/q 键位桥与无 -d 交互设备选择契约。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from canonical_app_instance.launch_io import flutter_daemon_app_id

LAUNCHER = APP_DIR / "run.sh"
RUN_INSTANCE = APP_DIR / "scripts/device/run_app_instance.py"
ATTACH_SESSION = (
    APP_DIR / "scripts/device/canonical_app_instance/attach_session.py"
)
GLOBAL_WRAPPER = APP_DIR / "scripts/tools/launcher/bin/run.sh"


class FlutterDaemonAppIdTest(unittest.TestCase):
    def test_extracts_app_id_from_daemon_event_lines(self) -> None:
        self.assertEqual(
            flutter_daemon_app_id(
                '[{"event":"app.start","params":{"appId":"abc-123"}}]'
            ),
            "abc-123",
        )
        self.assertEqual(
            flutter_daemon_app_id(
                '[{"event":"app.started","params":{"appId":"abc-123"}}]'
            ),
            "abc-123",
        )

    def test_non_daemon_lines_yield_empty_app_id(self) -> None:
        for line in (
            "Performing hot restart...",
            "not json",
            "[]",
            "[1, 2]",
            '[{"event":"daemon.connected","params":{}}]',
            '[{"event":"app.start","params":{"appId":42}}]',
        ):
            with self.subTest(line=line):
                self.assertEqual(flutter_daemon_app_id(line), "")


class HotReloadKeyBridgeContractTest(unittest.TestCase):
    def test_attach_bridges_keys_to_daemon_json_rpc(self) -> None:
        source = ATTACH_SESSION.read_text(encoding="utf-8")
        owner = RUN_INSTANCE.read_text(encoding="utf-8")
        # executor 只委托单一 attach-session owner，不能复制键位状态机。
        self.assertIn("return attach_command_platform_driver(", owner)
        self.assertNotIn('send_daemon_request("app.stop", {})', owner)
        # r/R/q 分别映射 hot reload / hot restart / stop 的 daemon 正门。
        self.assertIn('"app.restart", {"fullRestart": False}', source)
        self.assertIn('"app.restart", {"fullRestart": True}', source)
        self.assertIn('send_daemon_request("app.stop", {})', source)
        # 整行 JSON 请求原样透传，保持 PTY 驱动的 smoke 协议不变。
        self.assertIn('elif char in (b"[", b"{"):', source)
        # 键位桥只在 TTY 前台启用，flutter attach 的 stdin 才转为 PIPE。
        self.assertIn("interactive_tty = os.isatty(0)", source)
        self.assertIn(
            "stdin=subprocess.PIPE if interactive_tty else None", source
        )
        # cbreak 保留 ISIG，Ctrl-C 收尾路径不变；退出时恢复 termios。
        self.assertIn("tty.setcbreak(0)", source)
        self.assertIn("termios.tcsetattr(0, termios.TCSADRAIN, stdin_termios)", source)

    def test_app_id_is_captured_from_output_stream(self) -> None:
        source = ATTACH_SESSION.read_text(encoding="utf-8")
        owner = RUN_INSTANCE.read_text(encoding="utf-8")
        self.assertIn("flutter_daemon_app_id=_flutter_daemon_app_id", owner)
        self.assertIn('daemon_app_id_holder["appId"] = candidate_app_id', source)


class RunShDevicePickerContractTest(unittest.TestCase):
    def test_interactive_picker_delegates_to_canonical_device_authority(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        # 无 -d 且 stdin/stderr 为 TTY 时，委托 dev_up.pick_device 出编号列表。
        picker = source.index('if [[ -z "$DEVICE_ID" && -t 0 && -t 2 ]]')
        self.assertIn("from quwoquan_ops.cli.lib.dev_up import discover_flutter_devices, pick_device", source)
        # 非 TTY 保持显式 -d fail-closed，且门禁在交互选择之后仍然存在。
        fail_closed = source.index(
            "GATE_BLOCK: pass -d/--device-id so runtime ports and the consumer lease bind to one device."
        )
        self.assertLess(picker, fail_closed)
        # 选择程序经 -c 传入而非 heredoc，stdin 必须保留给 TTY 读取。
        picker_block = source[picker:fail_closed]
        self.assertIn("python3 -c", picker_block)
        self.assertNotIn("<<'PY'", picker_block)

    def test_usage_documents_optional_device_and_alpha_default(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("[-d <device>]", source)
        self.assertIn("Defaults to --env alpha.", source)

    def test_global_wrapper_follows_cwd_app_tree_then_execs_launcher(self) -> None:
        wrapper = GLOBAL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn('scripts/tools/launcher/worktree_selection.py', wrapper)
        self.assertIn('exec "$launcher" "${passthrough[@]}"', wrapper)
        self.assertTrue(GLOBAL_WRAPPER.stat().st_mode & 0o111)
        with tempfile.TemporaryDirectory(prefix="qwq-wrapper-contract-") as temporary:
            root = Path(temporary).resolve()
            apps = []
            for name in ("anchor tree", "selected tree"):
                repo = root / name
                app = repo / "quwoquan_app"
                (app / "lib/nested").mkdir(parents=True)
                (repo / "quwoquan_ops/cli").mkdir(parents=True)
                (repo / "quwoquan_ops/cli/stackctl.py").touch()
                (app / "pubspec.yaml").write_text("name: launcher_contract\n")
                # 替身最终执行体输出路径与 argv，用专属退出码证明已 exec。
                run_sh = app / "run.sh"
                run_sh.write_text(
                    '#!/usr/bin/env bash\n'
                    'printf "%s\\0" "$0" "$PWD" "$@"\n'
                    'exit 17\n'
                )
                run_sh.chmod(0o755)
                apps.append(app)
            anchor, selected = apps
            tool_dir = anchor / "scripts/tools/launcher"
            (tool_dir / "bin").mkdir(parents=True)
            copied_wrapper = tool_dir / "bin/run.sh"
            shutil.copy2(GLOBAL_WRAPPER, copied_wrapper)
            shutil.copy2(
                APP_DIR / "scripts/tools/launcher/worktree_selection.py",
                tool_dir / "worktree_selection.py",
            )
            # 不创建真实 linked worktree，仅替身 Git 的只读枚举；selector 使用真实字节。
            bin_dir = root / "bin"
            bin_dir.mkdir()
            git = bin_dir / "git"
            git.write_text(
                '#!/usr/bin/env bash\n'
                '[[ "$1" == "-C" && "$3" == "worktree" && "$4" == "list" '
                '&& "$5" == "--porcelain" ]] || exit 91\n'
                'printf "%s" "$CONTRACT_WORKTREES"\n'
            )
            git.chmod(0o755)
            environment = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "CONTRACT_WORKTREES": "".join(
                    f"worktree {app.parent}\nbranch refs/heads/lane/{name}\n\n"
                    for app, name in zip(apps, ("anchor", "selected"))
                ),
            }
            arguments = ["--env", "beta", "-d", "device with spaces", "", "*.dart", "--verbose"]
            cases = [
                (selected.parent, []),
                (selected, []),
                (selected / "lib/nested", []),
                (anchor, ["--worktree", "lane/selected"]),
                (anchor, ["--worktree=" + str(selected.parent)]),
            ]
            for cwd, selector_arguments in cases:
                with self.subTest(cwd=cwd, selector=selector_arguments):
                    result = subprocess.run(
                        [str(copied_wrapper), *selector_arguments, *arguments],
                        cwd=cwd, env=environment, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 17, result.stderr.decode())
                    self.assertEqual(
                        result.stdout.decode().split("\0")[:-1],
                        [str(selected / "run.sh"), str(cwd), *arguments],
                    )
            blocked = subprocess.run(
                [str(copied_wrapper), *arguments], cwd=root, env=environment,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", blocked.stderr)
            self.assertIn("multiple App worktrees", blocked.stderr)
            self.assertEqual(blocked.stdout, "")


if __name__ == "__main__":
    unittest.main()
