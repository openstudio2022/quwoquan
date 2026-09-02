# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 层：local_contract。受管 PATH 字面 `flutter` dispatcher 契约：
# - 本 App 的 `run` 白名单翻译后以 QWQ_MANAGED_FLUTTER_ENTRY=1 前台 exec
#   canonical run.sh（--env alpha --device <id>）；-v 翻译为 attach --verbose；
#   无 -d 时委托 canonical device authority；固定选择器冲突必须 typed 阻断；
# - 外部 Flutter project 的 `run` 与非 `run` 子命令均解析真实 SDK 后 exact
#   argv/env/cwd 透传并保留退出码；
# - 真实 SDK 解析跳过 dispatcher 自身（防递归），失败输出 typed
#   APP.LAUNCH.workspace_flutter_sdk_unavailable；
# - 白名单外参数输出一行 APP.LAUNCH.managed_argument_unsupported 并 exit 2；
# - dispatcher 按自身物理路径定位仓库根，任意 cwd 可用。
# 断言面为执行行为、退出码与捕获产物；stub 在假工作树内，不改共享环境。

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
DISPATCHER_SOURCE = APP_DIR / "scripts/tools/launcher/bin/flutter"
FACADE_SOURCE = APP_DIR / "scripts/tools/flutter_facade/flutter_facade.py"
SUBPROCESS_TIMEOUT_SECONDS = 30
PINNED_VERSION = "3.47.0"


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


class ManagedFlutterDispatcherContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.app_root = self.root / "worktree/quwoquan_app"
        self.launcher_bin = self.app_root / "scripts/tools/launcher/bin"
        self.launcher_bin.mkdir(parents=True)
        # dispatcher 与解析库按仓库真实相对位置复制进假工作树：
        # dispatcher 必须按自身物理路径定位 run.sh / facade / device authority。
        shutil.copy2(DISPATCHER_SOURCE, self.launcher_bin / "flutter")
        _write_executable(
            self.launcher_bin / "run.sh",
            "#!/usr/bin/env bash\nexit 99\n",
        )
        facade_dir = self.app_root / "scripts/tools/flutter_facade"
        facade_dir.mkdir(parents=True)
        shutil.copy2(FACADE_SOURCE, facade_dir / "flutter_facade.py")
        (self.app_root / ".flutter-version").write_text(
            f"{PINNED_VERSION}\n", encoding="utf-8"
        )
        (self.app_root / "pubspec.yaml").write_text(
            "name: quwoquan_app\n"
            "dependencies:\n"
            "  flutter:\n"
            "    sdk: flutter\n",
            encoding="utf-8",
        )
        stackctl = self.app_root.parent / "quwoquan_ops/cli/stackctl.py"
        stackctl.parent.mkdir(parents=True)
        stackctl.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.dispatcher = self.launcher_bin / "flutter"
        self.run_capture = self.root / "run-sh-capture.txt"
        self.sdk_capture = self.root / "real-flutter-capture.txt"
        self.device_capture = self.root / "device-authority-capture.json"

    # ------------------------------------------------------------------
    # stubs
    # ------------------------------------------------------------------

    def _install_run_sh_stub(self) -> Path:
        return _write_executable(
            self.app_root / "run.sh",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "{\n"
            "  printf 'cwd=%s\\n' \"$PWD\"\n"
            "  printf 'managed=%s\\n' \"${QWQ_MANAGED_FLUTTER_ENTRY:-}\"\n"
            "  printf 'marker=%s\\n' \"${QWQ_TEST_MANAGED_MARKER:-}\"\n"
            "  for argument in \"$@\"; do printf 'arg=%s\\n' \"$argument\"; done\n"
            f"}} > {json.dumps(str(self.run_capture))}\n"
            "exit 0\n",
        )

    def _install_real_flutter_stub(self, *, exit_code: int = 0) -> Path:
        payload = json.dumps({"frameworkVersion": PINNED_VERSION})
        return _write_executable(
            self.root / "real-sdk/bin/flutter",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [[ "$*" == "--version --machine" ]]; then\n'
            f"  printf '%s' {json.dumps(payload)}\n"
            "  exit 0\n"
            "fi\n"
            "{\n"
            "  printf 'cwd=%s\\n' \"$PWD\"\n"
            "  printf 'marker=%s\\n' \"${QWQ_TEST_PASSTHROUGH_MARKER:-}\"\n"
            "  printf 'managed=%s\\n' \"${QWQ_MANAGED_FLUTTER_ENTRY:-}\"\n"
            "  printf 'environment=%s\\n' \"${QWQ_ENVIRONMENT:-}\"\n"
            "  for argument in \"$@\"; do printf 'arg=%s\\n' \"$argument\"; done\n"
            f"}} > {json.dumps(str(self.sdk_capture))}\n"
            f"exit {exit_code}\n",
        )

    def _install_device_authority_stub(
        self,
        *,
        device_id: str = "",
        exit_code: int = 0,
        stderr_line: str = "",
    ) -> Path:
        return _write_executable(
            self.app_root / "scripts/tools/device/discover_flutter_mobile_devices.py",
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"Path({json.dumps(str(self.device_capture))}).write_text(\n"
            "    json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            ")\n"
            + (
                f"print({json.dumps(device_id)})\n" if device_id else ""
            )
            + (
                f"print({json.dumps(stderr_line)}, file=sys.stderr)\n"
                if stderr_line
                else ""
            )
            + f"raise SystemExit({exit_code})\n",
        )

    def _environment(self, **overrides: str) -> dict[str, str]:
        environment = dict(os.environ)
        for key in tuple(environment):
            if key.startswith("QWQ_"):
                environment.pop(key)
        environment.pop("FLUTTER_ROOT", None)
        environment["PATH"] = "/usr/bin:/bin"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment.update(overrides)
        return environment

    def _run_dispatcher(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.dispatcher), *arguments],
            cwd=cwd or self.root,
            env=environment or self._environment(),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

    def _captured_lines(self, capture: Path) -> list[str]:
        return capture.read_text(encoding="utf-8").splitlines()

    # ------------------------------------------------------------------
    # run：managed 链
    # ------------------------------------------------------------------

    def test_run_with_device_id_execs_canonical_launcher_managed(self) -> None:
        self._install_run_sh_stub()
        # 显式 -d 时不得触碰 device authority：stub 一旦被调用即留下捕获文件。
        self._install_device_authority_stub(exit_code=9)
        for flag in (("-d", "emulator-5554"), ("--device-id", "emulator-5554"),
                     ("--device-id=emulator-5554",)):
            with self.subTest(flag=flag):
                self.run_capture.unlink(missing_ok=True)
                result = self._run_dispatcher("run", *flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = self._captured_lines(self.run_capture)
                self.assertIn("managed=1", lines)
                self.assertEqual(
                    [line for line in lines if line.startswith("arg=")],
                    [
                        "arg=--env",
                        "arg=alpha",
                        "arg=--device",
                        "arg=emulator-5554",
                    ],
                    "-d/--device-id 必须 exact 翻译为 canonical --device",
                )
        self.assertFalse(
            self.device_capture.exists(),
            "显式 -d 时不得调用 device authority",
        )

    def test_run_verbose_is_translated_to_canonical_attach_argument(self) -> None:
        self._install_run_sh_stub()
        for flag in ("-v", "--verbose"):
            with self.subTest(flag=flag):
                self.run_capture.unlink(missing_ok=True)
                result = self._run_dispatcher(
                    "run", "-d", "R5CT10ABCDE", flag
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = self._captured_lines(self.run_capture)
                self.assertIn("managed=1", lines)
                self.assertEqual(
                    [line for line in lines if line.startswith("arg=")],
                    [
                        "arg=--env",
                        "arg=alpha",
                        "arg=--device",
                        "arg=R5CT10ABCDE",
                        "arg=--verbose",
                    ],
                    "verbosity 必须进入 canonical run.sh attach argv",
                )

    def test_run_blocks_noncanonical_ambient_selectors_before_device_or_run(
        self,
    ) -> None:
        self._install_run_sh_stub()
        self._install_device_authority_stub(device_id="must-not-be-used")
        unsupported_selectors = (
            ("QWQ_ENVIRONMENT", "beta"),
            ("QWQ_RUN_MODE", "ui-only"),
            ("QWQ_APP_RUNTIME_ENV", "gamma"),
            ("QWQ_APP_RUN_MODE", "ui-only"),
            ("QWQ_LAUNCH_TARGET", "beta-local"),
        )
        for name, value in unsupported_selectors:
            with self.subTest(selector=name):
                result = self._run_dispatcher(
                    "run", environment=self._environment(**{name: value})
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(
                    result.stderr.strip(),
                    f"APP.LAUNCH.managed_argument_unsupported: {name}={value}",
                )
                self.assertFalse(self.run_capture.exists())
                self.assertFalse(self.device_capture.exists())

    def test_run_accepts_matching_ambient_selectors_and_preserves_other_env(
        self,
    ) -> None:
        self._install_run_sh_stub()
        result = self._run_dispatcher(
            "run",
            "-d",
            "canonical-device",
            environment=self._environment(
                QWQ_ENVIRONMENT="alpha",
                QWQ_RUN_MODE="content-live",
                QWQ_APP_RUNTIME_ENV="alpha",
                QWQ_APP_RUN_MODE="content-live",
                QWQ_LAUNCH_TARGET="alpha-local",
                QWQ_TEST_MANAGED_MARKER="keep-user-env",
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self._captured_lines(self.run_capture)
        self.assertIn("managed=1", lines)
        self.assertIn("marker=keep-user-env", lines)

    def test_run_without_device_delegates_to_canonical_device_authority(self) -> None:
        self._install_run_sh_stub()
        real_flutter = self._install_real_flutter_stub()
        self._install_device_authority_stub(device_id="stub-device-1")
        result = self._run_dispatcher(
            "run",
            environment=self._environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        authority_argv = json.loads(self.device_capture.read_text(encoding="utf-8"))
        self.assertEqual(
            authority_argv,
            ["--pick", "--real-flutter", str(real_flutter.resolve())],
            "无 -d 时必须以解析后的绝对真实 SDK 调用 device authority --pick",
        )
        lines = self._captured_lines(self.run_capture)
        self.assertIn("managed=1", lines)
        self.assertEqual(
            [line for line in lines if line.startswith("arg=")],
            ["arg=--env", "arg=alpha", "arg=--device", "arg=stub-device-1"],
        )

    def test_run_propagates_device_authority_typed_block(self) -> None:
        # 非 TTY 多设备（或无设备）时 canonical device authority typed 阻断；
        # dispatcher 必须保留其退出码且不得进入 canonical launcher。
        self._install_run_sh_stub()
        real_flutter = self._install_real_flutter_stub()
        self._install_device_authority_stub(
            exit_code=2,
            stderr_line=(
                "GATE_BLOCK: multiple mobile devices are visible; "
                "re-run with -d <device-id>"
            ),
        )
        result = self._run_dispatcher(
            "run",
            environment=self._environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK", result.stderr)
        self.assertFalse(
            self.run_capture.exists(),
            "device authority 阻断后不得进入 canonical launcher",
        )

    def test_run_blocks_every_unsupported_argument_class_with_exit_2(self) -> None:
        self._install_run_sh_stub()
        self._install_device_authority_stub(exit_code=9)
        unsupported_cases = (
            ("--target", "lib/main_dev.dart"),
            ("-t", "lib/main_dev.dart"),
            ("--flavor", "prod"),
            ("--dart-define=APP_RUNTIME_ENV=beta",),
            ("--dart-define-from-file=defines.json",),
            ("--profile",),
            ("--release",),
            ("--host-vmservice-port", "8181"),
            ("--dds-port", "8282"),
            ("--pub",),
            ("--no-pub",),
        )
        for case in unsupported_cases:
            with self.subTest(argument=case[0]):
                result = self._run_dispatcher("run", "-d", "emulator-5554", *case)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(
                    result.stderr.strip(),
                    f"APP.LAUNCH.managed_argument_unsupported: {case[0]}",
                    "白名单外参数必须输出单行 typed 阻断",
                )
                self.assertFalse(self.run_capture.exists())
                self.assertFalse(self.device_capture.exists())

    def test_run_blocks_conflicting_device_selectors(self) -> None:
        self._install_run_sh_stub()
        self._install_device_authority_stub(exit_code=9)
        result = self._run_dispatcher(
            "run", "-d", "device-a", "--device-id=device-b"
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            result.stderr.strip(),
            "APP.LAUNCH.managed_argument_unsupported: --device-id=device-b",
        )
        self.assertFalse(self.run_capture.exists())
        self.assertFalse(self.device_capture.exists())

    def test_run_with_missing_canonical_launcher_is_typed_entrypoint_block(self) -> None:
        # 假工作树没有可执行 run.sh 时 managed 链必须 typed fail-closed。
        result = self._run_dispatcher("run", "-d", "emulator-5554")
        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", result.stderr)

    def test_dispatcher_works_from_any_cwd(self) -> None:
        self._install_run_sh_stub()
        foreign_cwd = self.root / "some/unrelated/deep/cwd"
        foreign_cwd.mkdir(parents=True)
        result = self._run_dispatcher(
            "run", "-d", "emulator-5554", cwd=foreign_cwd
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self._captured_lines(self.run_capture)
        self.assertIn("managed=1", lines)
        self.assertIn(
            f"cwd={foreign_cwd.resolve()}",
            lines,
            "managed exec 必须在前台保留调用方 cwd",
        )

    def test_run_does_not_follow_symlinked_pubspec(self) -> None:
        self._install_run_sh_stub()
        unsafe_root = self.root / "unsafe-project"
        unsafe_root.mkdir()
        outside_pubspec = self.root / "outside-pubspec.yaml"
        outside_pubspec.write_text(
            "name: unsafe_app\ndependencies:\n  flutter:\n    sdk: flutter\n",
            encoding="utf-8",
        )
        (unsafe_root / "pubspec.yaml").symlink_to(outside_pubspec)
        result = self._run_dispatcher(
            "run", "-d", "safe-device", cwd=unsafe_root
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.run_capture.exists())
        self.assertFalse(self.sdk_capture.exists())

    def test_run_from_canonical_app_path_remains_managed(self) -> None:
        self._install_run_sh_stub()
        app_cwd = self.app_root / "lib/service"
        app_cwd.mkdir(parents=True)
        result = self._run_dispatcher(
            "run", "-d", "app-device", cwd=app_cwd
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self._captured_lines(self.run_capture)
        self.assertIn("managed=1", lines)
        self.assertIn(f"cwd={app_cwd.resolve()}", lines)
        self.assertFalse(self.sdk_capture.exists())

    def test_run_follows_app_tree_under_cwd_not_dispatcher_tree(self) -> None:
        self._install_run_sh_stub()
        other_app = self.root / "other/quwoquan_app"
        other_cwd = other_app / "lib/deep"
        other_cwd.mkdir(parents=True)
        (other_app / "pubspec.yaml").write_text("name: quwoquan_app\n", encoding="utf-8")
        other_capture = self.root / "other-run-capture.txt"
        _write_executable(
            other_app / "run.sh",
            "#!/usr/bin/env bash\nprintf '%s\n' \"$0\" > " + str(other_capture) + "\n",
        )
        stackctl = other_app.parent / "quwoquan_ops/cli/stackctl.py"
        stackctl.parent.mkdir(parents=True)
        stackctl.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

        result = self._run_dispatcher("run", "-d", "cwd-device", cwd=other_cwd)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(other_capture.read_text(encoding="utf-8").strip(), str(other_app / "run.sh"))
        self.assertFalse(self.run_capture.exists())

    # ------------------------------------------------------------------
    # 真实 SDK：非 run 与 foreign Flutter project exact passthrough
    # ------------------------------------------------------------------

    def test_foreign_flutter_project_run_passes_through_exactly(self) -> None:
        real_flutter = self._install_real_flutter_stub(exit_code=7)
        pubspec_variants = {
            "block": (
                "name: foreign_app\n"
                "dependencies:\n"
                "  flutter:\n"
                "    sdk: flutter\n"
            ),
            "quoted": (
                "name: foreign_app\n"
                "dependencies:\n"
                "  'flutter':\n"
                "    sdk: \"flutter\"\n"
            ),
            "flow": (
                "{name: foreign_app, dependencies: "
                "{flutter: {sdk: flutter}}}\n"
            ),
        }
        for variant, pubspec in pubspec_variants.items():
            with self.subTest(pubspec=variant):
                self.sdk_capture.unlink(missing_ok=True)
                foreign_root = self.root / f"foreign/{variant}/flutter_app"
                foreign_cwd = foreign_root / "lib/deep"
                foreign_cwd.mkdir(parents=True)
                (foreign_root / "pubspec.yaml").write_text(
                    pubspec, encoding="utf-8"
                )
                result = self._run_dispatcher(
                    "run",
                    "--target",
                    "lib/foreign.dart",
                    "-d",
                    "foreign-device",
                    "-v",
                    environment=self._environment(
                        QWQ_REAL_FLUTTER=str(real_flutter),
                        QWQ_ENVIRONMENT="beta",
                        QWQ_TEST_PASSTHROUGH_MARKER="foreign-marker",
                    ),
                    cwd=foreign_cwd,
                )
                self.assertEqual(
                    result.returncode, 7, "透传必须保留真实 SDK 退出码"
                )
                lines = self._captured_lines(self.sdk_capture)
                self.assertEqual(
                    [line for line in lines if line.startswith("arg=")],
                    [
                        "arg=run",
                        "arg=--target",
                        "arg=lib/foreign.dart",
                        "arg=-d",
                        "arg=foreign-device",
                        "arg=-v",
                    ],
                )
                self.assertIn(f"cwd={foreign_cwd.resolve()}", lines)
                self.assertIn("marker=foreign-marker", lines)
                self.assertIn("environment=beta", lines)
                self.assertIn("managed=", lines)
                self.assertFalse(self.run_capture.exists())

    def test_non_run_subcommands_pass_through_argv_env_cwd_and_exit_code(self) -> None:
        real_flutter = self._install_real_flutter_stub(exit_code=7)
        foreign_cwd = self.root / "passthrough/cwd"
        foreign_cwd.mkdir(parents=True)
        result = self._run_dispatcher(
            "doctor",
            "--android-licenses",
            "-v",
            environment=self._environment(
                QWQ_REAL_FLUTTER=str(real_flutter),
                QWQ_TEST_PASSTHROUGH_MARKER="marker-sentinel",
            ),
            cwd=foreign_cwd,
        )
        self.assertEqual(result.returncode, 7, "透传必须保留真实 SDK 退出码")
        lines = self._captured_lines(self.sdk_capture)
        self.assertEqual(
            [line for line in lines if line.startswith("arg=")],
            ["arg=doctor", "arg=--android-licenses", "arg=-v"],
            "argv 必须逐字透传",
        )
        self.assertIn(f"cwd={foreign_cwd.resolve()}", lines)
        self.assertIn("marker=marker-sentinel", lines, "env 必须逐字透传")
        self.assertIn("managed=", lines, "透传不得注入 QWQ_MANAGED_FLUTTER_ENTRY")

    def test_version_style_flags_are_passthrough_not_managed(self) -> None:
        real_flutter = self._install_real_flutter_stub()
        result = self._run_dispatcher(
            "--version",
            environment=self._environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self._captured_lines(self.sdk_capture)
        self.assertEqual(
            [line for line in lines if line.startswith("arg=")],
            ["arg=--version"],
        )
        self.assertFalse(self.run_capture.exists())

    # ------------------------------------------------------------------
    # SDK 解析：typed 失败与防递归
    # ------------------------------------------------------------------

    def test_unresolvable_sdk_is_typed_blocker(self) -> None:
        result = self._run_dispatcher("--version")
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "APP.LAUNCH.workspace_flutter_sdk_unavailable:", result.stderr
        )

    def test_path_resolution_skips_dispatcher_itself(self) -> None:
        # 受管 PATH 首位就是 launcher bin：解析必须跳过 dispatcher 自身，
        # 命中后续真实 SDK，而不是递归回自己。
        real_flutter = self._install_real_flutter_stub(exit_code=7)
        environment = self._environment(
            PATH=f"{self.launcher_bin}:{real_flutter.parent}:/usr/bin:/bin"
        )
        result = self._run_dispatcher("--version", environment=environment)
        self.assertEqual(result.returncode, 7)
        lines = self._captured_lines(self.sdk_capture)
        self.assertEqual(
            [line for line in lines if line.startswith("arg=")],
            ["arg=--version"],
        )

    def test_path_with_only_dispatcher_fails_typed_instead_of_recursing(self) -> None:
        environment = self._environment(
            PATH=f"{self.launcher_bin}:/usr/bin:/bin"
        )
        result = self._run_dispatcher("--version", environment=environment)
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "APP.LAUNCH.workspace_flutter_sdk_unavailable:", result.stderr
        )

    def test_explicit_identity_pointing_at_dispatcher_is_rejected(self) -> None:
        environment = self._environment(QWQ_REAL_FLUTTER=str(self.dispatcher))
        result = self._run_dispatcher("--version", environment=environment)
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "APP.LAUNCH.workspace_flutter_sdk_unavailable:", result.stderr
        )


if __name__ == "__main__":
    unittest.main()
