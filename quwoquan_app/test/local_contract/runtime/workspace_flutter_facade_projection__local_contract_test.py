# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003
#
# 层：local_contract。工作区终端注入（纯 PATH 注入）契约：
# - activate 写入的 settings 受管块只含受管 PATH 前置与钉定工具链身份变量；
# - 注入幂等、deactivate 逐字回退、status 如实区分 未激活/已激活/漂移；
# - 不再存在 flutter shim、ZDOTDIR bridge、terminal receipt 注入；
# - user-zsh scope 是显式 opt-in 的可识别 managed block，可完整移除。
# 断言面为执行行为、退出码与落盘产物，不做脚本源码文本断言。

import hashlib
import importlib.util
import json
import os
import pty
import re
import select
import shlex
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
FACADE_DIR = APP_DIR / "scripts/tools/flutter_facade"
ACTIVATE_SCRIPT = FACADE_DIR / "activate_cursor_workspace.py"
USER_ZSH_CARRIER = FACADE_DIR / "user_zsh_projection.zsh"
LAUNCHER_BIN = APP_DIR / "scripts/tools/launcher/bin"
SUBPROCESS_TIMEOUT_SECONDS = 30

IDENTITY_ENV_KEYS = (
    "QWQ_REAL_FLUTTER",
    "QWQ_REAL_FLUTTER_VERSION",
    "QWQ_COCOAPODS_EXECUTABLE",
    "QWQ_COCOAPODS_VERSION",
    "QWQ_COCOAPODS_EXECUTABLE_DIGEST",
    "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST",
    "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST",
    "QWQ_COCOAPODS_BINDING_SEAL",
    "QWQ_WORKSPACE_PYTHON",
    "QWQ_WORKSPACE_PYTHON_VERSION",
    "QWQ_USER_ZSH_CARRIER_DIGEST",
    "QWQ_FLUTTER_DISPATCHER_DIGEST",
    "QWQ_RUN_SH_WRAPPER_DIGEST",
)
USER_ZSH_SOURCE_BEGIN = "# >>> qwq flutter facade user-zsh projection >>>"
USER_ZSH_SOURCE_END = "# <<< qwq flutter facade user-zsh projection <<<"


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_fake_real_flutter(root: Path) -> Path:
    payload = json.dumps(
        {
            "frameworkVersion": "3.47.0",
            "frameworkRevision": "fixture-revision",
            "engineRevision": "fixture-engine",
            "dartSdkVersion": "3.10.0",
            "channel": "stable",
        }
    )
    return _write_executable(
        root / "fake-sdk/bin/flutter",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$*" == "--version --machine" ]]; then\n'
        f"  printf '%s' {json.dumps(payload)}\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
    )


def _write_fake_pod(root: Path) -> Path:
    return _write_executable(
        root / "fake-pod/bin/pod",
        "#!/bin/sh\n"
        'SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"\n'
        'if [ "$1" = "--version" ]; then\n'
        "  printf '%s\\n' '1.16.2'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "env" ]; then\n'
        "  printf '### Stack\\nCocoaPods : 1.16.2\\nRuby : 3.3.0\\n"
        "RubyGems : 3.5.0\\n### Plugins\\n"
        "cocoapods-deintegrate : 1.0.5\\nExecutable Path: %s\\n' \"$SELF\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
    )


def _strip_json_comments(text: str) -> dict:
    stripped = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped).strip()
    return json.loads(stripped) if stripped else {}


def _load_activation_module():
    module_name = f"qwq_activation_test_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(module_name, ACTIVATE_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("activation module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class _InteractiveLoginZsh:
    PROMPT = b"__QWQ_TEST_PROMPT__ "
    COMMAND_DONE = b"__QWQ_COMMAND_DONE__"

    def __init__(self, *, home: Path, environment: dict[str, str]) -> None:
        pid, descriptor = pty.fork()
        if pid == 0:  # pragma: no cover - child process is observed through its PTY
            child_environment = dict(environment)
            child_environment.pop("ZDOTDIR", None)
            child_environment.update(
                HOME=str(home),
                TERM="dumb",
                LC_ALL="C",
            )
            os.execve("/bin/zsh", ["/bin/zsh", "-l", "-i"], child_environment)
        self.pid = pid
        self.descriptor = descriptor
        self.startup_output = self._read_until_prompt()

    def _read_until_prompt(self) -> str:
        output = bytearray()
        deadline = time.monotonic() + 10
        while self.PROMPT not in output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "interactive login zsh did not reach its prompt: "
                    + output.decode("utf-8", errors="replace")
                )
            readable, _, _ = select.select([self.descriptor], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = os.read(self.descriptor, 4096)
            except OSError as error:
                raise AssertionError("interactive login zsh closed early") from error
            if not chunk:
                raise AssertionError("interactive login zsh closed early")
            output.extend(chunk)
        return output.decode("utf-8", errors="replace")

    def command(self, command: str) -> str:
        token = f"{self.COMMAND_DONE.decode()}_{time.time_ns()}"
        token_line = ("\r\n" + token + "\r\n").encode("utf-8")
        wrapped = f"{command}; print -r -- {token}\n"
        os.write(self.descriptor, wrapped.encode("utf-8"))
        output = bytearray()
        deadline = time.monotonic() + 15
        while token_line not in output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "interactive zsh command did not finish: "
                    + output.decode("utf-8", errors="replace")
                )
            readable, _, _ = select.select([self.descriptor], [], [], remaining)
            if not readable:
                continue
            try:
                chunk = os.read(self.descriptor, 4096)
            except OSError as error:
                raise AssertionError("interactive zsh command closed early") from error
            if not chunk:
                raise AssertionError("interactive zsh command closed early")
            output.extend(chunk)
        return output.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self.descriptor < 0:
            return
        try:
            os.write(self.descriptor, b"exit\n")
        except OSError:
            pass
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            waited, _ = os.waitpid(self.pid, os.WNOHANG)
            if waited == self.pid:
                break
            time.sleep(0.02)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            kill_deadline = time.monotonic() + 0.5
            while time.monotonic() < kill_deadline:
                waited, _ = os.waitpid(self.pid, os.WNOHANG)
                if waited == self.pid:
                    break
                time.sleep(0.02)
        os.close(self.descriptor)
        self.descriptor = -1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


class WorkspaceTerminalInjectionLocalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.real_flutter = _write_fake_real_flutter(self.root)
        self.pod = _write_fake_pod(self.root)
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.settings = self.root / ".vscode/settings.json"
        self.settings.parent.mkdir(parents=True)

    def _environment(self, **overrides: str) -> dict[str, str]:
        environment = dict(os.environ)
        for key in tuple(environment):
            if key.startswith("QWQ_"):
                environment.pop(key)
        environment.pop("FLUTTER_ROOT", None)
        environment.update(
            HOME=str(self.home),
            QWQ_REAL_FLUTTER=str(self.real_flutter),
            PATH=f"{self.pod.parent}:/usr/bin:/bin",
            PYTHONDONTWRITEBYTECODE="1",
        )
        environment.update(overrides)
        return environment

    def _run_cli(
        self,
        *args: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ACTIVATE_SCRIPT),
                "--settings",
                str(self.settings),
                "--home",
                str(self.home),
                *args,
            ],
            env=environment or self._environment(),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

    def _write_interactive_zsh_startup(
        self,
        *,
        path_prefix: Path,
        alias_override: str = "",
        function_override: str = "",
    ) -> None:
        lines = [
            f"export PATH={shlex.quote(str(path_prefix))}:/usr/bin:/bin",
            "rehash",
            *([alias_override] if alias_override else []),
            *([function_override] if function_override else []),
            "export PS1='__QWQ_TEST_PROMPT__ '",
            "export PROMPT='__QWQ_TEST_PROMPT__ '",
            "unset RPROMPT",
        ]
        self.home.joinpath(".zprofile").write_text(
            "export QWQ_TEST_ZPROFILE_READ=1\n", encoding="utf-8"
        )
        self.home.joinpath(".zshrc").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _interactive_environment(self) -> dict[str, str]:
        environment = self._environment()
        environment["PATH"] = "/usr/bin:/bin"
        return environment

    # ------------------------------------------------------------------
    # 退役面：shim / ZDOTDIR / receipt 不复存在
    # ------------------------------------------------------------------

    def test_retired_shim_zdotdir_and_receipt_artifacts_are_absent(self) -> None:
        for retired in (
            FACADE_DIR / "bin",
            FACADE_DIR / "zsh_projection",
            FACADE_DIR / "cursor_terminal_profile.zsh",
            FACADE_DIR / "terminal_surface_receipt.py",
            FACADE_DIR / "cursor_terminal_surface_state.py",
            FACADE_DIR / "__pycache__",
        ):
            self.assertFalse(
                retired.exists(),
                f"退役产物必须从源码树移除：{retired}",
            )
        self.assertTrue(
            (LAUNCHER_BIN / "run.sh").is_file(),
            "受管 PATH 首目录必须存在全局 run.sh wrapper",
        )
        dispatcher = LAUNCHER_BIN / "flutter"
        self.assertTrue(
            dispatcher.is_file() and os.access(dispatcher, os.X_OK),
            "受管 PATH 首目录必须存在可执行的字面 flutter dispatcher",
        )

    # ------------------------------------------------------------------
    # cursor scope：settings 受管块
    # ------------------------------------------------------------------

    def test_activation_projects_only_path_and_identity_then_restores_bytes(
        self,
    ) -> None:
        original = (
            "{\n"
            "    // 用户已有注释必须保留\n"
            '    "dart.analysisExcludedFolders": ["quwoquan_app/vendor"]\n'
            "}\n"
        )
        self.settings.write_text(original, encoding="utf-8")

        first = self._run_cli()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(
            json.loads(first.stdout),
            {
                "existingShellCommandResolution": "not_observed",
                "outcome": "activated",
                "projectionState": "active",
                "scopes": {"cursor": "activated"},
            },
        )
        merged = self.settings.read_text(encoding="utf-8")
        self.assertIn("用户已有注释必须保留", merged)
        parsed = _strip_json_comments(merged)
        self.assertEqual(parsed.get("dart.addSdkToTerminalPath"), False)
        terminal_env = parsed["terminal.integrated.env.osx"]
        self.assertEqual(
            set(terminal_env),
            {"PATH", *IDENTITY_ENV_KEYS},
            "受管块只允许 PATH 前置与钉定身份变量，不得注入其他键",
        )
        flutter_bin = self.real_flutter.resolve().parent
        pod_bin = self.pod.resolve().parent
        python_bin = Path(
            terminal_env["QWQ_WORKSPACE_PYTHON"]
        ).parent
        self.assertEqual(
            terminal_env["PATH"],
            "${workspaceFolder}/quwoquan_app/scripts/tools/launcher/bin:"
            f"{flutter_bin}:{pod_bin}:{python_bin}:${{env:PATH}}",
            "受管 PATH 必须按序前置 launcher/flutter/pod/python 并保留 ${env:PATH}",
        )
        self.assertEqual(terminal_env["QWQ_REAL_FLUTTER_VERSION"], "3.47.0")
        for retired_fragment in (
            "ZDOTDIR",
            "flutter_facade/bin",
            "terminal.integrated.profiles.osx",
            "terminal.integrated.defaultProfile.osx",
            "QWQ_TERMINAL_SURFACE",
            "QWQ_TERMINAL_PROJECTION",
        ):
            self.assertNotIn(
                retired_fragment,
                merged,
                f"退役机制不得再注入 settings：{retired_fragment}",
            )
        tasks = self.settings.with_name("tasks.json")
        launch = self.settings.with_name("launch.json")
        self.assertTrue(tasks.exists() and launch.exists())

        second = self._run_cli()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            json.loads(second.stdout),
            {
                "existingShellCommandResolution": "not_observed",
                "outcome": "unchanged",
                "projectionState": "active",
                "scopes": {"cursor": "unchanged"},
            },
        )
        self.assertEqual(self.settings.read_text(encoding="utf-8"), merged)

        rollback = self._run_cli("--deactivate")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(
            json.loads(rollback.stdout),
            {
                "existingShellCommandResolution": "not_observed",
                "outcome": "deactivated",
                "projectionState": "inactive",
                "scopes": {"cursor": "deactivated"},
            },
        )
        self.assertEqual(
            self.settings.read_text(encoding="utf-8"),
            original,
            "回退必须逐字恢复用户原有 settings 内容",
        )
        self.assertFalse(tasks.exists())
        self.assertFalse(launch.exists())

    def test_activation_repairs_drifted_managed_block_with_current_identity(
        self,
    ) -> None:
        legacy = (
            "{\n"
            "    // qwq-flutter-facade-begin\n"
            '    "dart.addSdkToTerminalPath": false,\n'
            '    "terminal.integrated.env.osx": {\n'
            '        "PATH": "${workspaceFolder}/quwoquan_app/scripts/tools/'
            'flutter_facade/bin:${env:PATH}",\n'
            '        "ZDOTDIR": "${workspaceFolder}/quwoquan_app/scripts/tools/'
            'flutter_facade/zsh_projection",\n'
            '        "QWQ_REAL_FLUTTER": "/stale/flutter"\n'
            "    },\n"
            '    "terminal.integrated.profiles.osx": {"Legacy": {"path": "zsh"}},\n'
            "    // qwq-flutter-facade-end\n"
            '    "editor.rulers": [100]\n'
            "}\n"
        )
        self.settings.write_text(legacy, encoding="utf-8")

        result = self._run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["scopes"]["cursor"],
            "refreshed",
            "块内漂移必须以当前解析结果直接修复",
        )
        merged = self.settings.read_text(encoding="utf-8")
        parsed = _strip_json_comments(merged)
        self.assertEqual(parsed.get("editor.rulers"), [100], "块外用户配置必须保留")
        self.assertNotIn("ZDOTDIR", merged)
        self.assertNotIn("flutter_facade/bin", merged)
        self.assertNotIn("terminal.integrated.profiles.osx", merged)
        self.assertEqual(
            parsed["terminal.integrated.env.osx"]["QWQ_REAL_FLUTTER"],
            str(self.real_flutter.resolve()),
        )

    def test_activation_refuses_foreign_managed_keys_outside_block(self) -> None:
        foreign = (
            "{\n"
            '    "terminal.integrated.env.osx": {"PATH": "/custom/bin:${env:PATH}"}\n'
            "}\n"
        )
        self.settings.write_text(foreign, encoding="utf-8")
        result = self._run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK", result.stderr)
        self.assertEqual(
            self.settings.read_text(encoding="utf-8"),
            foreign,
            "存在外部管理键时不得改写用户 settings",
        )
        self.assertFalse(self.settings.with_name("tasks.json").exists())

        rollback = self._run_cli("--deactivate")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), foreign)

    def test_activation_fails_before_any_write_without_canonical_real_sdk(
        self,
    ) -> None:
        original = "{\n}\n"
        self.settings.write_text(original, encoding="utf-8")
        result = self._run_cli(
            environment=self._environment(
                QWQ_REAL_FLUTTER=str(self.root / "missing-flutter")
            )
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_flutter_sdk_unavailable", result.stderr)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)
        self.assertFalse(self.settings.with_name("tasks.json").exists())
        self.assertFalse(self.settings.with_name("launch.json").exists())

    def test_wrong_pinned_version_sdk_is_rejected(self) -> None:
        wrong_version = _write_executable(
            self.root / "wrong-sdk/bin/flutter",
            "#!/usr/bin/env bash\n"
            'printf \'%s\' \'{"frameworkVersion": "3.0.0"}\'\n',
        )
        result = self._run_cli(
            environment=self._environment(QWQ_REAL_FLUTTER=str(wrong_version))
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_flutter_sdk_unavailable", result.stderr)

    def test_status_reports_inactive_active_and_drifted_truthfully(self) -> None:
        inactive = self._run_cli("--status")
        self.assertEqual(inactive.returncode, 2)
        payload = json.loads(inactive.stdout)
        self.assertEqual(payload["cursor"]["projectionState"], "inactive")
        self.assertIn("GATE_BLOCK", inactive.stderr)

        activation = self._run_cli()
        self.assertEqual(activation.returncode, 0, activation.stderr)
        active = self._run_cli("--status")
        self.assertEqual(active.returncode, 0, active.stderr)
        payload = json.loads(active.stdout)
        self.assertEqual(payload["cursor"]["projectionState"], "active")
        self.assertEqual(payload["cursor"]["settingsState"], "active")
        self.assertEqual(payload["cursor"]["sdkResolutionState"], "active")
        self.assertEqual(payload["cursor"]["cocoaPodsResolutionState"], "active")
        self.assertEqual(payload["cursor"]["pythonResolutionState"], "active")
        self.assertEqual(payload["cursor"]["workspaceEntrypointState"], "active")
        self.assertEqual(
            set(payload["cursor"]["workspaceEntrypointDigests"]),
            {
                "QWQ_USER_ZSH_CARRIER_DIGEST",
                "QWQ_FLUTTER_DISPATCHER_DIGEST",
                "QWQ_RUN_SH_WRAPPER_DIGEST",
            },
        )

        merged = self.settings.read_text(encoding="utf-8")
        tampered = merged.replace(
            '"QWQ_REAL_FLUTTER_VERSION": "3.47.0"',
            '"QWQ_REAL_FLUTTER_VERSION": "0.0.0"',
        )
        self.assertNotEqual(merged, tampered)
        self.settings.write_text(tampered, encoding="utf-8")
        drifted = self._run_cli("--status")
        self.assertEqual(drifted.returncode, 2)
        payload = json.loads(drifted.stdout)
        self.assertEqual(payload["cursor"]["projectionState"], "drifted")
        self.assertEqual(payload["cursor"]["settingsState"], "drifted")
        self.assertEqual(payload["cursor"]["sdkResolutionState"], "drifted")

        self.settings.write_text(merged, encoding="utf-8")
        self.real_flutter.unlink()
        unavailable = self._run_cli("--status")
        self.assertEqual(unavailable.returncode, 2)
        payload = json.loads(unavailable.stdout)
        self.assertEqual(payload["cursor"]["projectionState"], "drifted")
        self.assertEqual(payload["cursor"]["settingsState"], "unverifiable")
        self.assertEqual(payload["cursor"]["sdkResolutionState"], "unavailable")

    def test_cursor_scope_never_touches_user_home(self) -> None:
        zshrc = self.home / ".zshrc"
        zshrc.write_bytes(b"# user rc must stay untouched\n")
        result = self._run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(zshrc.read_bytes(), b"# user rc must stay untouched\n")
        self.assertFalse((self.home / ".config/quwoquan").exists())
        self.assertFalse((self.home / ".zprofile").exists())

    # ------------------------------------------------------------------
    # user-zsh scope：显式 opt-in managed block
    # ------------------------------------------------------------------

    def test_user_zsh_activation_is_private_idempotent_and_byte_reversible(
        self,
    ) -> None:
        zshrc = self.home / ".zshrc"
        original = b"# user zshrc without trailing newline"
        zshrc.write_bytes(original)

        first = self._run_cli("--scope", "user-zsh")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(
            json.loads(first.stdout),
            {
                "existingShellCommandResolution": "not_observed",
                "outcome": "activated",
                "projectionState": "active",
                "scopes": {"user-zsh": "activated"},
            },
        )
        generated = self.home / ".config/quwoquan/flutter-facade.zsh"
        self.assertIn("projection state=active", first.stderr)
        self.assertIn("existing shell command resolution=not_observed", first.stderr)
        self.assertIn("builtin whence -wa -- flutter run.sh", first.stderr)
        self.assertIn("builtin whence -pa -- flutter run.sh", first.stderr)
        self.assertIn(
            f"builtin source {shlex.quote(str(generated))} && rehash",
            first.stderr,
        )
        self.assertTrue(generated.is_file())
        self.assertEqual(stat.S_IMODE(generated.stat().st_mode), 0o600)
        self.assertEqual(
            stat.S_IMODE(generated.parent.stat().st_mode), 0o700
        )
        generated_text = generated.read_text(encoding="utf-8")
        self.assertTrue(generated_text.startswith("# qwq-user-zsh-projection-v1 "))
        for key in IDENTITY_ENV_KEYS:
            self.assertIn(f"export {key}=", generated_text)
        for key in (
            "QWQ_USER_ZSH_CARRIER_DIGEST",
            "QWQ_FLUTTER_DISPATCHER_DIGEST",
            "QWQ_RUN_SH_WRAPPER_DIGEST",
        ):
            self.assertRegex(generated_text, rf"export {key}=sha256:[0-9a-f]{{64}}")
        self.assertIn(str(USER_ZSH_CARRIER.resolve()), generated_text)
        for retired_fragment in ("ZDOTDIR", "receipt", "QWQ_TERMINAL_"):
            self.assertNotIn(retired_fragment, generated_text)
        zshrc_bytes = zshrc.read_bytes()
        self.assertEqual(zshrc_bytes.count(USER_ZSH_SOURCE_BEGIN.encode()), 1)
        self.assertEqual(zshrc_bytes.count(USER_ZSH_SOURCE_END.encode()), 1)
        self.assertIn(str(generated).encode(), zshrc_bytes)
        self.assertTrue(zshrc_bytes.startswith(original))

        second = self._run_cli("--scope", "user-zsh")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            json.loads(second.stdout)["scopes"]["user-zsh"], "unchanged"
        )
        self.assertEqual(zshrc.read_bytes(), zshrc_bytes)

        rollback = self._run_cli("--scope", "user-zsh", "--deactivate")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(
            json.loads(rollback.stdout)["scopes"]["user-zsh"], "deactivated"
        )
        self.assertEqual(
            zshrc.read_bytes(),
            original,
            "deactivate 必须逐字恢复用户 zshrc（含缺失的行尾换行）",
        )
        self.assertFalse(generated.exists())

    def test_user_zsh_activation_repairs_legacy_blocks_and_zprofile(self) -> None:
        generated = self.home / ".config/quwoquan/flutter-facade.zsh"
        generated.parent.mkdir(mode=0o700, parents=True)
        generated.write_bytes(
            b"# qwq-user-zsh-projection-v1 sha256:" + b"0" * 64 + b"\n"
            b"export QWQ_LEGACY=1\n"
        )
        legacy_block = (
            f"{USER_ZSH_SOURCE_BEGIN}\n"
            "# qwq-user-zsh-prefix-newline preserved\n"
            f"QWQ_USER_ZSH_STARTUP_STAGE=zshrc builtin source '{generated}'\n"
            f"{USER_ZSH_SOURCE_END}\n"
        )
        zshrc = self.home / ".zshrc"
        zshrc.write_bytes(f"# user config\n{legacy_block}".encode())
        zprofile = self.home / ".zprofile"
        zprofile_legacy = legacy_block.replace("zshrc", "zprofile")
        zprofile.write_bytes(f"# user profile\n{zprofile_legacy}".encode())

        result = self._run_cli("--scope", "user-zsh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["scopes"]["user-zsh"], "refreshed"
        )
        self.assertNotIn(b"QWQ_LEGACY", generated.read_bytes())
        self.assertNotIn(b"QWQ_USER_ZSH_STARTUP_STAGE", zshrc.read_bytes())
        self.assertEqual(
            zprofile.read_bytes(),
            b"# user profile\n",
            "新契约只在 zshrc 维护单个 managed block，legacy zprofile 块必须回收",
        )

        rollback = self._run_cli("--scope", "user-zsh", "--deactivate")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(zshrc.read_bytes(), b"# user config\n")
        self.assertEqual(zprofile.read_bytes(), b"# user profile\n")
        self.assertFalse(generated.exists())

    def test_user_zsh_refuses_foreign_generated_file(self) -> None:
        generated = self.home / ".config/quwoquan/flutter-facade.zsh"
        generated.parent.mkdir(mode=0o700, parents=True)
        foreign = b"# hand-written user file\nexport PATH=/custom:$PATH\n"
        generated.write_bytes(foreign)

        activation = self._run_cli("--scope", "user-zsh")
        self.assertEqual(activation.returncode, 2)
        self.assertIn("GATE_BLOCK", activation.stderr)
        self.assertEqual(generated.read_bytes(), foreign)

        rollback = self._run_cli("--scope", "user-zsh", "--deactivate")
        self.assertEqual(rollback.returncode, 2)
        self.assertIn("GATE_BLOCK", rollback.stderr)
        self.assertEqual(generated.read_bytes(), foreign)

    def test_user_zsh_status_reports_inactive_active_and_drifted(self) -> None:
        inactive = self._run_cli("--scope", "user-zsh", "--status")
        self.assertEqual(inactive.returncode, 2)
        payload = json.loads(inactive.stdout)
        self.assertEqual(payload["userZsh"]["projectionState"], "inactive")

        activation = self._run_cli("--scope", "user-zsh")
        self.assertEqual(activation.returncode, 0, activation.stderr)
        active = self._run_cli("--scope", "user-zsh", "--status")
        self.assertEqual(active.returncode, 0, active.stderr)
        payload = json.loads(active.stdout)
        self.assertEqual(payload["userZsh"]["projectionState"], "active")
        self.assertEqual(payload["userZsh"]["generatedProjectionState"], "active")
        self.assertEqual(payload["userZsh"]["zshrcBlockState"], "active")

        zshrc = self.home / ".zshrc"
        zshrc.write_bytes(zshrc.read_bytes().replace(b"builtin source", b"source"))
        drifted = self._run_cli("--scope", "user-zsh", "--status")
        self.assertEqual(drifted.returncode, 2)
        payload = json.loads(drifted.stdout)
        self.assertEqual(payload["userZsh"]["projectionState"], "drifted")
        self.assertEqual(payload["userZsh"]["zshrcBlockState"], "drifted")

    def test_user_zsh_carrier_prepends_managed_path_idempotently(self) -> None:
        activation = self._run_cli("--scope", "user-zsh")
        self.assertEqual(activation.returncode, 0, activation.stderr)
        generated = self.home / ".config/quwoquan/flutter-facade.zsh"
        probe = subprocess.run(
            [
                "zsh",
                "-c",
                f"source {generated}; source {generated}; print -r -- $PATH",
            ],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(self.home),
            },
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        entries = probe.stdout.strip().split(os.pathsep)
        expected_prefix = [
            str(LAUNCHER_BIN.resolve()),
            str(self.real_flutter.resolve().parent),
            str(self.pod.resolve().parent),
        ]
        self.assertEqual(
            entries[:3],
            expected_prefix,
            "carrier 必须按序前置 launcher/flutter/pod bin 目录",
        )
        python_bin = entries[3]
        self.assertTrue(Path(python_bin, "python3").exists() or Path(python_bin).exists())
        self.assertEqual(
            entries[4:],
            ["/usr/bin", "/bin"],
            "重复 source 必须幂等，不得重复前置或丢失原有 PATH",
        )
        self.assertEqual(
            len(entries),
            len(set(entries)),
            "受管前置目录不得重复出现",
        )

    def test_cursor_scope_preflights_launcher_before_any_write(self) -> None:
        module = _load_activation_module()
        original_dispatcher = module.CANONICAL_FLUTTER_DISPATCHER_PATH
        module.CANONICAL_FLUTTER_DISPATCHER_PATH = self.root / "missing-dispatcher"
        original = b"{\n}\n"
        self.settings.write_bytes(original)
        try:
            with self.assertRaisesRegex(
                SystemExit,
                "APP.LAUNCH.workspace_entrypoint_inactive",
            ):
                module.activate(
                    self.settings,
                    environ=self._environment(),
                )
        finally:
            module.CANONICAL_FLUTTER_DISPATCHER_PATH = original_dispatcher
        self.assertEqual(self.settings.read_bytes(), original)
        self.assertFalse(self.settings.with_name("tasks.json").exists())
        self.assertFalse(self.settings.with_name("launch.json").exists())

    def test_launcher_byte_drift_marks_both_projection_scopes_drifted(self) -> None:
        module = _load_activation_module()
        fake_launcher_bin = self.root / "fixture/quwoquan_app/scripts/tools/launcher/bin"
        fake_launcher_bin.mkdir(parents=True)
        fake_dispatcher = fake_launcher_bin / "flutter"
        fake_wrapper = fake_launcher_bin / "run.sh"
        fake_carrier = (
            self.root
            / "fixture/quwoquan_app/scripts/tools/flutter_facade/user_zsh_projection.zsh"
        )
        fake_carrier.parent.mkdir(parents=True)
        for source, target in (
            (LAUNCHER_BIN / "flutter", fake_dispatcher),
            (LAUNCHER_BIN / "run.sh", fake_wrapper),
            (USER_ZSH_CARRIER, fake_carrier),
        ):
            target.write_bytes(source.read_bytes())
            target.chmod(source.stat().st_mode & 0o777)

        original_paths = (
            module.CANONICAL_LAUNCHER_BIN_PATH,
            module.CANONICAL_FLUTTER_DISPATCHER_PATH,
            module.CANONICAL_RUN_SH_WRAPPER_PATH,
            module.USER_ZSH_CARRIER_PATH,
        )
        module.CANONICAL_LAUNCHER_BIN_PATH = fake_launcher_bin
        module.CANONICAL_FLUTTER_DISPATCHER_PATH = fake_dispatcher
        module.CANONICAL_RUN_SH_WRAPPER_PATH = fake_wrapper
        module.USER_ZSH_CARRIER_PATH = fake_carrier
        try:
            self.assertEqual(
                module.activate(self.settings, environ=self._environment()), "activated"
            )
            self.assertEqual(
                module.activate_user_zsh(
                    home_path=self.home, environ=self._environment()
                ),
                "activated",
            )
            fake_dispatcher.write_bytes(fake_dispatcher.read_bytes() + b"# drift\n")
            cursor = module.status(self.settings, environ=self._environment())
            user_zsh = module.user_zsh_status(
                home_path=self.home, environ=self._environment()
            )
        finally:
            (
                module.CANONICAL_LAUNCHER_BIN_PATH,
                module.CANONICAL_FLUTTER_DISPATCHER_PATH,
                module.CANONICAL_RUN_SH_WRAPPER_PATH,
                module.USER_ZSH_CARRIER_PATH,
            ) = original_paths
        self.assertEqual(cursor["projectionState"], "drifted")
        self.assertEqual(cursor["settingsState"], "drifted")
        self.assertEqual(cursor["workspaceEntrypointState"], "drifted")
        self.assertEqual(user_zsh["projectionState"], "drifted")
        self.assertEqual(user_zsh["generatedProjectionState"], "drifted")
        self.assertEqual(user_zsh["workspaceEntrypointState"], "drifted")

    def test_user_zsh_long_lived_shell_refreshes_cached_raw_sdk_then_manages_run(
        self,
    ) -> None:
        raw_bin = self.root / "raw-sdk/bin"
        raw_flutter = _write_executable(
            raw_bin / "flutter",
            "#!/bin/sh\n"
            "if [ \"$*\" = \"--version --machine\" ]; then\n"
            "  printf '%s' '{\"frameworkVersion\":\"3.47.0\","
            "\"frameworkRevision\":\"fixture-revision\"}'\n"
            "  exit 0\n"
            "fi\n"
            "printf 'RAW_SDK %s\\n' \"$*\"\n",
        )
        _write_executable(raw_bin / "run.sh", "#!/bin/sh\nprintf 'RAW_RUN\\n'\n")
        self._write_interactive_zsh_startup(path_prefix=raw_bin)
        with _InteractiveLoginZsh(
            home=self.home,
            environment=self._interactive_environment(),
        ) as shell:
            self.assertIn("QWQ_TEST_ZPROFILE_READ=1", shell.command("export -p"))
            cached = shell.command("flutter run -d cached-before")
            self.assertIn("RAW_SDK run -d cached-before", cached)
            self.assertIn(str(raw_flutter), shell.command("whence -p flutter"))

            # 先缓存 raw SDK 后才创建 dispatcher/carrier 投影；既有 shell 不会被反向改写。
            fake_app = self.root / "fixture/quwoquan_app"
            fake_launcher_bin = fake_app / "scripts/tools/launcher/bin"
            fake_launcher_bin.mkdir(parents=True)
            fake_dispatcher = fake_launcher_bin / "flutter"
            fake_dispatcher.write_bytes((LAUNCHER_BIN / "flutter").read_bytes())
            fake_dispatcher.chmod(0o755)
            fake_wrapper = _write_executable(
                fake_launcher_bin / "run.sh",
                f"#!/bin/sh\nexec {shlex.quote(str(fake_app / 'run.sh'))} \"$@\"\n",
            )
            _write_executable(
                fake_app / "run.sh",
                "#!/bin/sh\nprintf 'CANONICAL_RUN %s %s\\n' "
                '"${QWQ_MANAGED_FLUTTER_ENTRY:-}" "$*"\n',
            )
            fake_app.joinpath("pubspec.yaml").write_text(
                "name: fixture_app\n", encoding="utf-8"
            )
            fake_app.joinpath(".flutter-version").write_text(
                "3.47.0\n", encoding="utf-8"
            )
            fake_stackctl = fake_app.parent / "quwoquan_ops/cli/stackctl.py"
            fake_stackctl.parent.mkdir(parents=True)
            fake_stackctl.touch()
            fake_carrier = fake_app / "scripts/tools/flutter_facade/user_zsh_projection.zsh"
            fake_carrier.parent.mkdir(parents=True)
            fake_carrier.write_bytes(USER_ZSH_CARRIER.read_bytes())
            fake_facade = fake_carrier.with_name("flutter_facade.py")
            fake_facade.write_bytes(
                (FACADE_DIR / "flutter_facade.py").read_bytes()
            )
            physical_python = Path(sys.executable).resolve()
            fake_projection = self.home / ".config/quwoquan/fake-flutter-facade.zsh"
            fake_projection.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fake_projection.write_text(
                f"export QWQ_REAL_FLUTTER={shlex.quote(str(raw_flutter))}\n"
                f"export QWQ_COCOAPODS_EXECUTABLE={shlex.quote(str(self.pod))}\n"
                f"export QWQ_WORKSPACE_PYTHON={shlex.quote(str(physical_python))}\n"
                f"export QWQ_USER_ZSH_CARRIER_DIGEST={_sha256(fake_carrier)}\n"
                f"export QWQ_FLUTTER_DISPATCHER_DIGEST={_sha256(fake_dispatcher)}\n"
                f"export QWQ_RUN_SH_WRAPPER_DIGEST={_sha256(fake_wrapper)}\n"
                f"builtin source {shlex.quote(str(fake_carrier))}\n",
                encoding="utf-8",
            )

            before_refresh = shell.command("flutter run -d still-cached")
            self.assertIn("RAW_SDK run -d still-cached", before_refresh)
            self.assertIn(str(raw_flutter), shell.command("whence -p flutter"))

            refreshed = shell.command(
                f"builtin source {shlex.quote(str(fake_projection))} && rehash"
            )
            self.assertNotIn("GATE_BLOCK", refreshed)
            self.assertIn(str(fake_dispatcher), shell.command("whence -p flutter"))
            self.assertIn(str(fake_wrapper), shell.command("whence -p run.sh"))
            managed = shell.command(
                f"cd {shlex.quote(str(fake_app))} && flutter run -d managed-device"
            )
            self.assertIn(
                "CANONICAL_RUN 1 --env alpha --device managed-device", managed
            )

    def test_user_zsh_fresh_login_shell_auto_projects_commands(self) -> None:
        raw_bin = self.root / "raw-sdk/bin"
        _write_executable(raw_bin / "flutter", "#!/bin/sh\nprintf 'RAW\n'\n")
        self._write_interactive_zsh_startup(path_prefix=raw_bin)
        activation = self._run_cli("--scope", "user-zsh")
        self.assertEqual(activation.returncode, 0, activation.stderr)
        with _InteractiveLoginZsh(
            home=self.home,
            environment=self._interactive_environment(),
        ) as shell:
            self.assertNotIn("GATE_BLOCK", shell.startup_output)
            self.assertIn("QWQ_TEST_ZPROFILE_READ=1", shell.command("export -p"))
            self.assertIn(str(LAUNCHER_BIN / "flutter"), shell.command("whence -p flutter"))
            self.assertIn(str(LAUNCHER_BIN / "run.sh"), shell.command("whence -p run.sh"))

    def test_user_zsh_alias_and_function_overrides_fail_closed(self) -> None:
        raw_bin = self.root / "raw-sdk/bin"
        _write_executable(raw_bin / "flutter", "#!/bin/sh\nprintf 'RAW\n'\n")
        cases = (
            ("alias flutter='print ALIAS'", "", "flutter: alias"),
            ("", "function run.sh() { print FUNCTION; }", "run.sh: function"),
        )
        for alias_override, function_override, expected in cases:
            with self.subTest(expected=expected):
                case_home = self.root / expected.replace(": ", "-")
                case_home.mkdir(mode=0o700)
                self.home = case_home
                self._write_interactive_zsh_startup(
                    path_prefix=raw_bin,
                    alias_override=alias_override,
                    function_override=function_override,
                )
                activation = self._run_cli("--scope", "user-zsh")
                self.assertEqual(activation.returncode, 0, activation.stderr)
                with _InteractiveLoginZsh(
                    home=self.home,
                    environment=self._interactive_environment(),
                ) as shell:
                    self.assertIn("GATE_BLOCK", shell.startup_output)
                    self.assertIn(expected, shell.startup_output)
                    self.assertIn(
                        str(raw_bin / "flutter"),
                        shell.command("whence -p flutter"),
                        "alias/function 阻断不得留下半激活 PATH",
                    )

    def test_user_zsh_carrier_fails_typed_when_pinned_identity_is_missing(
        self,
    ) -> None:
        activation = self._run_cli("--scope", "user-zsh")
        self.assertEqual(activation.returncode, 0, activation.stderr)
        generated = self.home / ".config/quwoquan/flutter-facade.zsh"
        self.real_flutter.unlink()
        probe = subprocess.run(
            ["zsh", "-c", f"source {generated}; print -r -- CONTINUED"],
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.home)},
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertIn("GATE_BLOCK", probe.stderr)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", probe.stderr)

if __name__ == "__main__":
    unittest.main()
