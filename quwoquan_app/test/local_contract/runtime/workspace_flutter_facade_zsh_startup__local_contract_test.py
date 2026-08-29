#!/usr/bin/env python3
"""Real-zsh contract for the version-controlled workspace ZDOTDIR bridge."""

from __future__ import annotations

import os
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


if __name__ == "__main__":
    unittest.main()
