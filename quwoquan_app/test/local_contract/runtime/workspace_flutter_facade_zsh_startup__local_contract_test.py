#!/usr/bin/env python3
"""Real-zsh contract for the version-controlled workspace ZDOTDIR bridge."""

from __future__ import annotations

import importlib.util
import os
import sys
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PROJECTION_DIR = (
    REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/zsh_projection"
)
ZSH = shutil.which("zsh")


@unittest.skipIf(ZSH is None, "zsh is required for the macOS workspace projection")
class WorkspaceFlutterFacadeZshStartupLocalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home"
        self.user_zdotdir = self.root / "user-zdotdir"
        self.facade_bin = self.root / "facade-bin"
        self.real_sdk_bin = self.root / "real-sdk-bin"
        self.log = self.root / "stages.log"
        for directory in (
            self.home,
            self.user_zdotdir,
            self.facade_bin,
            self.real_sdk_bin,
        ):
            directory.mkdir(parents=True)
        for directory in (self.facade_bin, self.real_sdk_bin):
            flutter = directory / "flutter"
            flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            flutter.chmod(flutter.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _environment(self, original_zdotdir: Path) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(self.home),
                "PATH": f"{self.facade_bin}:{self.real_sdk_bin}:/usr/bin:/bin",
                "QWQ_TEST_LOG": str(self.log),
                "QWQ_TEST_REAL_SDK_BIN": str(self.real_sdk_bin),
                "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": str(self.facade_bin),
                "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": str(original_zdotdir),
                "ZDOTDIR": str(PROJECTION_DIR),
            }
        )
        return environment

    def _write_rc(self, directory: Path, name: str, *, next_zdotdir: Path | None = None) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        lines = [
            f"print -r -- '{name}|'$$'|'$ZDOTDIR >> \"$QWQ_TEST_LOG\"",
            'path=("$QWQ_TEST_REAL_SDK_BIN" "$QWQ_WORKSPACE_FLUTTER_FACADE_BIN" "${path[@]}")',
        ]
        if next_zdotdir is not None:
            lines.append(f"ZDOTDIR={next_zdotdir!s}")
        (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run(self, *flags: str, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ZSH), "-d", *flags, "-c", command],
            env=self._environment(self.user_zdotdir),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    @staticmethod
    def _result_fields(result: subprocess.CompletedProcess[str]) -> list[str]:
        result_line = next(
            line for line in result.stdout.splitlines() if line.startswith("QWQ_RESULT|")
        )
        return result_line.split("|")

    def test_non_login_interactive_proxies_user_rc_in_same_shell_and_deduplicates(self) -> None:
        self._write_rc(self.user_zdotdir, ".zshenv")
        self._write_rc(self.user_zdotdir, ".zshrc")
        result = self._run(
            "-i",
            command=(
                'print -r -- "QWQ_RESULT|$$|$ZDOTDIR|'
                '${QWQ_WORKSPACE_ORIGINAL_ZDOTDIR}|${path[1]}|${(j.:.)path}"'
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        fields = self._result_fields(result)
        self.assertEqual(fields[2], str(PROJECTION_DIR))
        self.assertEqual(fields[3], str(self.user_zdotdir))
        self.assertEqual(fields[4], str(self.facade_bin))
        self.assertEqual(fields[5].split(":").count(str(self.facade_bin)), 1)
        stages = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split("|")[0] for line in stages], [".zshenv", ".zshrc"])
        self.assertTrue(all(line.split("|")[1] == fields[1] for line in stages))

    def test_login_proxies_every_stage_and_captures_custom_zdotdir_changes(self) -> None:
        profile_dir = self.root / "profile-zdotdir"
        rc_dir = self.root / "rc-zdotdir"
        login_dir = self.root / "login-zdotdir"
        self._write_rc(self.user_zdotdir, ".zshenv", next_zdotdir=profile_dir)
        self._write_rc(profile_dir, ".zprofile", next_zdotdir=rc_dir)
        self._write_rc(rc_dir, ".zshrc", next_zdotdir=login_dir)
        self._write_rc(login_dir, ".zlogin")
        self._write_rc(login_dir, ".zlogout")

        result = self._run(
            "-l",
            "-i",
            command=(
                'print -r -- "QWQ_RESULT|$$|$ZDOTDIR|'
                '${QWQ_WORKSPACE_ORIGINAL_ZDOTDIR}|${path[1]}|${(j.:.)path}"'
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        fields = self._result_fields(result)
        self.assertEqual(fields[2], str(PROJECTION_DIR))
        self.assertEqual(fields[3], str(login_dir))
        self.assertEqual(fields[4], str(self.facade_bin))
        stages = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [line.split("|")[0] for line in stages],
            [".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zlogout"],
        )
        self.assertTrue(all(line.split("|")[1] == fields[1] for line in stages))

    def test_no_user_rc_and_explicit_nested_shell_stay_on_bridge_without_recursion(self) -> None:
        command = (
            "zmodload zsh/system; "
            'print -r -- "QWQ_RESULT|outer|$sysparams[pid]|$ZDOTDIR|${path[1]}"; '
            "zsh -d -c 'zmodload zsh/system; print -r -- "
            "\"QWQ_RESULT|inner|$sysparams[pid]|$ZDOTDIR|${path[1]}\"'; :"
        )
        result = self._run(command=command)

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [
            line.split("|")
            for line in result.stdout.splitlines()
            if line.startswith("QWQ_RESULT|")
        ]
        self.assertEqual([line[1] for line in lines], ["outer", "inner"])
        self.assertNotEqual(lines[0][2], lines[1][2])
        self.assertTrue(all(line[3] == str(PROJECTION_DIR) for line in lines))
        self.assertTrue(all(line[4] == str(self.facade_bin) for line in lines))
        self.assertFalse(self.log.exists())


@unittest.skipIf(ZSH is None, "zsh is required for the macOS workspace profile")
class WorkspaceFlutterFacadeCursorProfileLocalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.home = self.root / "home"
        self.facade_dir = self.repo / "quwoquan_app/scripts/tools/flutter_facade"
        self.facade_bin = self.facade_dir / "bin"
        self.projection = self.facade_dir / "zsh_projection"
        self.real_sdk_bin = self.root / "real-sdk/bin"
        self.receipts = self.repo / ".qwq_output/env/repo/local/flutter-facade-terminal-receipts"
        for directory in (
            self.home,
            self.facade_bin,
            self.projection,
            self.real_sdk_bin,
        ):
            directory.mkdir(parents=True)
        self.launcher = self.facade_dir / "cursor_terminal_profile.zsh"
        self.receipt_tool = self.facade_dir / "terminal_surface_receipt.py"
        shutil.copy2(
            REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/cursor_terminal_profile.zsh",
            self.launcher,
        )
        shutil.copy2(
            REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/terminal_surface_receipt.py",
            self.receipt_tool,
        )
        source_projection = (
            REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/zsh_projection"
        )
        for name in (
            "bridge.zsh",
            ".zshenv",
            ".zprofile",
            ".zshrc",
            ".zlogin",
            ".zlogout",
        ):
            shutil.copy2(source_projection / name, self.projection / name)
        flutter = self.facade_bin / "flutter"
        flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        flutter.chmod(0o755)
        self.real_flutter = self.real_sdk_bin / "flutter"
        self.real_flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.real_flutter.chmod(0o755)
        self.pod = self.root / "cocoapods/bin/pod"
        self.pod.parent.mkdir(parents=True)
        self.pod.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.pod.chmod(0o755)
        self.pod_binding = {
            "QWQ_COCOAPODS_EXECUTABLE": str(self.pod),
            "QWQ_COCOAPODS_VERSION": "1.16.2",
            "QWQ_COCOAPODS_EXECUTABLE_DIGEST": "sha256:" + "d" * 64,
            "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST": "sha256:" + "e" * 64,
            "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST": "sha256:" + "f" * 64,
            "QWQ_COCOAPODS_BINDING_SEAL": "sha256:" + "a" * 64,
        }
        package_root = self.repo / "quwoquan_ops/cli/lib"
        package_root.mkdir(parents=True)
        for package in (
            self.repo / "quwoquan_ops",
            self.repo / "quwoquan_ops/cli",
            package_root,
        ):
            (package / "__init__.py").touch()
        (package_root / "app_dependency_toolchain.py").write_text(
            "from pathlib import Path\n"
            "import shutil\n"
            "import sys\n"
            "KEYS = (\n"
            "    'QWQ_COCOAPODS_EXECUTABLE',\n"
            "    'QWQ_COCOAPODS_VERSION',\n"
            "    'QWQ_COCOAPODS_EXECUTABLE_DIGEST',\n"
            "    'QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST',\n"
            "    'QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST',\n"
            "    'QWQ_COCOAPODS_BINDING_SEAL',\n"
            ")\n"
            "def validate_cocoapods_child_environment(environment):\n"
            "    values = {key: environment.get(key, '') for key in KEYS}\n"
            "    if any(not value for value in values.values()):\n"
            "        raise RuntimeError('incomplete CocoaPods identity')\n"
            "    resolved = shutil.which('pod', path=environment.get('PATH', ''))\n"
            "    if not resolved:\n"
            "        raise RuntimeError('pod is absent')\n"
            "    if Path(resolved).resolve() != Path(values[KEYS[0]]).resolve():\n"
            "        raise RuntimeError('child PATH resolves another pod')\n"
            "    log = environment.get('QWQ_TEST_VALIDATION_LOG', '')\n"
            "    if log:\n"
            "        with Path(log).open('a', encoding='utf-8') as handle:\n"
            "            handle.write('|'.join(values[key] for key in KEYS) + '\\n')\n"
            "        with Path(log).with_suffix('.python').open('a', encoding='utf-8') as handle:\n"
            "            handle.write(str(Path(sys.executable).resolve()) + '|' + '.'.join(str(value) for value in sys.version_info[:3]) + '\\n')\n"
            "    return None, dict(environment)\n",
            encoding="utf-8",
        )
        self.validation_log = self.root / "validation.log"
        self.hostile_bin = self.root / "hostile/bin"
        self.hostile_bin.mkdir(parents=True)
        for command in ("flutter", "pod"):
            executable = self.hostile_bin / command
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        self.system_python_bin = self.root / "system-python/bin"
        self.trusted_python_bin = self.root / "trusted-python/bin"
        self.system_python = self._write_python(
            self.system_python_bin, version=(3, 9, 6), identity="system-3.9"
        )
        self.trusted_python = Path(sys.executable).resolve()

    @staticmethod
    def _write_python(
        directory: Path, *, version: tuple[int, int, int], identity: str
    ) -> Path:
        directory.mkdir(parents=True)
        executable = directory / "python3"
        executable.write_text(
            "#!/bin/sh\n"
            f"export QWQ_TEST_PYTHON_VERSION='{version[0]}.{version[1]}.{version[2]}'\n"
            f"export QWQ_TEST_PYTHON_IDENTITY='{identity}'\n"
            f"exec {str(Path(sys.executable).resolve())!r} \"$@\"\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(self.home),
                "PATH": (
                    f"{self.system_python_bin}:{self.hostile_bin}:"
                    f"{self.trusted_python.parent}:/usr/bin:/bin:{self.hostile_bin}"
                ),
                "QWQ_TERMINAL_SURFACE": "unknown",
                "QWQ_TERMINAL_PROJECTION_SEAL": "sha256:" + "a" * 64,
                "QWQ_TERMINAL_PROJECTION_GENERATION": "sha256:" + "b" * 64,
                "QWQ_TERMINAL_WORKSPACE_URI": str(self.repo),
                "FLUTTER_ROOT": str(self.real_sdk_bin.parent),
                "QWQ_REAL_FLUTTER": str(self.real_flutter),
                "QWQ_REAL_FLUTTER_VERSION": "3.47.0",
                "QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST": "sha256:" + "c" * 64,
                "QWQ_WORKSPACE_PYTHON": str(self.trusted_python),
                "QWQ_WORKSPACE_PYTHON_VERSION": (
                    f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                ),
                "QWQ_TEST_RECEIPT_ROOT": str(self.receipts),
                "QWQ_TEST_HOSTILE_BIN": str(self.hostile_bin),
                "QWQ_TEST_VALIDATION_LOG": str(self.validation_log),
                **self.pod_binding,
            }
        )
        return environment

    def _write_user_rc(self, name: str, *, delete_facade: bool = False) -> None:
        receipt_glob = '$QWQ_TEST_RECEIPT_ROOT/*.json'
        lines = [
            f'receipts=({receipt_glob}(N))',
            f'print -r -- "{name}|$$|${{#receipts}}" >> "$QWQ_TEST_LOG"',
            'path=("$QWQ_TEST_HOSTILE_BIN" "$QWQ_REAL_FLUTTER:h" '
            '"$QWQ_WORKSPACE_FLUTTER_FACADE_BIN" "$QWQ_TEST_HOSTILE_BIN" '
            '"$QWQ_COCOAPODS_EXECUTABLE:h" "${path[@]}" '
            '"$QWQ_REAL_FLUTTER:h")',
        ]
        if delete_facade:
            lines.append('rm -f "$QWQ_WORKSPACE_FLUTTER_FACADE_BIN/flutter"')
        (self.home / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run_launcher(
        self, *flags: str, command: str, overrides: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = self._environment()
        environment["QWQ_TEST_LOG"] = str(self.root / "profile-stages.log")
        environment.update(overrides or {})
        return subprocess.run(
            [str(self.launcher), *flags, "-c", command],
            cwd=self.repo,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_launcher_derives_workspace_sets_facade_and_preserves_shell_args(self) -> None:
        result = subprocess.run(
            [
                str(self.launcher),
                "-d",
                "-c",
                'print -r -- "QWQ_RESULT|$QWQ_WORKSPACE_FLUTTER_FACADE_BIN|$ZDOTDIR|${path[1]}|${path[2]}|${path[3]}|$QWQ_TERMINAL_SHELL_PID"',
            ],
            cwd=self.repo,
            env=self._environment(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = next(
            line for line in result.stdout.splitlines() if line.startswith("QWQ_RESULT|")
        ).split("|")
        self.assertEqual(Path(fields[1]).resolve(), self.facade_bin.resolve())
        self.assertEqual(Path(fields[2]).resolve(), self.projection.resolve())
        self.assertEqual(Path(fields[3]).resolve(), self.facade_bin.resolve())
        self.assertEqual(Path(fields[4]).resolve(), self.real_sdk_bin.resolve())
        self.assertEqual(Path(fields[5]).resolve(), self.pod.parent.resolve())
        self.assertTrue(fields[6].isdigit())
        self.assertEqual(
            self.validation_log.with_suffix(".python").read_text(encoding="utf-8"),
            (
                f"{self.trusted_python}|"
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}\n"
            ),
        )
        receipt = next(self.receipts.glob("folder-new-terminal--*.json"))
        payload = __import__("json").loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["surface"], "folder-new-terminal")
        self.assertIs(payload["finalStateValidated"], True)
        self.assertEqual(
            Path(payload["workspaceLogicalRoot"]).resolve(), self.repo.resolve()
        )
        self.assertEqual(payload["workspacePhysicalRoot"], str(self.repo.resolve()))
        self.assertEqual(payload["facadeRealpath"], str((self.facade_bin / "flutter").resolve()))
        self.assertEqual(set(payload["qwqIdentity"]), {
            "facadeBinRealpath",
            "realFlutterRealpath",
            "realFlutterVersion",
            "commandResolutionDigest",
        })

    def test_receipt_python_rejects_system_3_9_and_uses_projected_physical_3_13(
        self,
    ) -> None:
        result = self._run_launcher(
            "-d",
            command="exit 0",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            Path(self._environment()["PATH"].split(":", 1)[0]) / "python3",
            self.system_python,
        )
        self.assertNotEqual(self.system_python.resolve(), self.trusted_python)
        self.assertEqual(
            self.validation_log.with_suffix(".python").read_text(encoding="utf-8"),
            (
                f"{self.trusted_python}|"
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}\n"
            ),
        )
        self.assertEqual(len(list(self.receipts.glob("*.json"))), 1)

    def test_hostile_non_login_interactive_rc_is_repaired_before_final_receipt(self) -> None:
        self._write_user_rc(".zshenv")
        self._write_user_rc(".zshrc")
        result = self._run_launcher(
            "-d",
            "-i",
            command=(
                'print -r -- "QWQ_FINAL|$$|${path[1]}|${path[2]}|${path[3]}|'
                '$(whence -p flutter)|$(whence -p pod)|${(j.:.)path}"'
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        fields = next(
            line.split("|")
            for line in result.stdout.splitlines()
            if line.startswith("QWQ_FINAL|")
        )
        self.assertEqual(Path(fields[2]).resolve(), self.facade_bin.resolve())
        self.assertEqual(Path(fields[3]).resolve(), self.real_sdk_bin.resolve())
        self.assertEqual(Path(fields[4]).resolve(), self.pod.parent.resolve())
        self.assertEqual(Path(fields[5]).resolve(), (self.facade_bin / "flutter").resolve())
        self.assertEqual(Path(fields[6]).resolve(), self.pod.resolve())
        final_path = fields[7].split(":")
        self.assertEqual(len(final_path), len({str(Path(item).resolve()) for item in final_path}))
        stages = (self.root / "profile-stages.log").read_text(encoding="utf-8").splitlines()
        carrier_stages = [line for line in stages if line.split("|")[1] == fields[1]]
        carrier_stage_names = [line.split("|")[0] for line in carrier_stages]
        self.assertEqual(carrier_stage_names, [".zshenv", ".zshrc"])
        self.assertTrue(all(line.endswith("|0") for line in carrier_stages))
        receipt = next(self.receipts.glob("folder-new-terminal--*.json"))
        payload = __import__("json").loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["shellPid"], int(fields[1]))
        self.assertIs(payload["finalStateValidated"], True)
        self.assertEqual(len(self.validation_log.read_text(encoding="utf-8").split("|")), 6)

    def test_login_receipt_waits_for_zlogin_and_zlogout_does_not_write(self) -> None:
        for name in (".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zlogout"):
            self._write_user_rc(name)
        result = self._run_launcher(
            "-d",
            "-l",
            "-i",
            command='print -r -- "QWQ_LOGIN|$$|${path[1]}|${path[2]}|${path[3]}"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        stages = (self.root / "profile-stages.log").read_text(encoding="utf-8").splitlines()
        carrier_pid = next(
            line.split("|")[1]
            for line in result.stdout.splitlines()
            if line.startswith("QWQ_LOGIN|")
        )
        carrier_stages = [line for line in stages if line.split("|")[1] == carrier_pid]
        carrier_stage_names = [line.split("|")[0] for line in carrier_stages]
        self.assertEqual(
            carrier_stage_names,
            [".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zlogout"],
        )
        self.assertEqual(
            [line.split("|")[2] for line in carrier_stages],
            ["0", "0", "0", "0", "1"],
        )
        self.assertEqual(len(list(self.receipts.glob("*.json"))), 1)
        self.assertEqual(len(self.validation_log.read_text(encoding="utf-8").splitlines()), 1)

    def test_final_live_validation_failure_is_typed_and_writes_no_receipt(self) -> None:
        self._write_user_rc(".zshenv", delete_facade=True)
        result = self._run_launcher("-d", command="exit 0")

        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", result.stderr)
        self.assertFalse(list(self.receipts.glob("*.json")))

        shutil.copy2(
            REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter",
            self.facade_bin / "flutter",
        )
        (self.root / "profile-stages.log").unlink(missing_ok=True)
        result = self._run_launcher(
            "-d",
            command="exit 0",
            overrides={"QWQ_COCOAPODS_VERSION": ""},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", result.stderr)
        self.assertFalse(list(self.receipts.glob("*.json")))

    def test_launcher_fails_closed_for_wrong_cwd_root_or_recursion(self) -> None:
        cases = {
            "wrong-cwd": (self.root, {}),
            "wrong-root": (self.repo, {"QWQ_TERMINAL_WORKSPACE_URI": str(self.root)}),
            "recursion": (self.repo, {"QWQ_CURSOR_TERMINAL_PROFILE_ACTIVE": "1"}),
        }
        for name, (cwd, overrides) in cases.items():
            with self.subTest(case=name):
                environment = self._environment()
                environment.update(overrides)
                result = subprocess.run(
                    [str(self.launcher), "-d", "-c", "exit 0"],
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", result.stderr)


if __name__ == "__main__":
    unittest.main()
