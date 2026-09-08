# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
#
# 全局 `run.sh` wrapper 与受管 `flutter` dispatcher 启动"当前所站的那棵树"；cwd 不在任何
# App 树内时按同仓 worktree 枚举选择（显式 --worktree / TTY 数字 / 非 TTY typed 阻断），
# 不再静默退回 wrapper 自身所在树。user-zsh 生成投影在载体缺失时只打印 typed 一行并
# 完全回退，不留下"身份变量已导出、PATH 未前置"的半激活 shell。

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
SELECTOR = APP_DIR / "scripts/tools/launcher/worktree_selection.py"
WRAPPER = APP_DIR / "scripts/tools/launcher/bin/run.sh"
DISPATCHER = APP_DIR / "scripts/tools/launcher/bin/flutter"
USER_ZSH_ACTIVATION = APP_DIR / "scripts/tools/flutter_facade/user_zsh_activation.py"
USER_ZSH_CARRIER = APP_DIR / "scripts/tools/flutter_facade/user_zsh_projection.zsh"
INSTALL_HOOKS = APP_DIR.parent / "quwoquan_ops/hooks/run_install_hooks.sh"


def _load_selector():
    spec = importlib.util.spec_from_file_location("qwq_test_worktree_selection", SELECTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )


def _make_app_tree(root: Path) -> None:
    app = root / "quwoquan_app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "pubspec.yaml").write_text("name: fixture\n", encoding="utf-8")
    run_sh = app / "run.sh"
    run_sh.write_text("#!/bin/sh\nprintf 'RUN %s\\n' \"$*\"\n", encoding="utf-8")
    run_sh.chmod(0o755)
    stackctl = root / "quwoquan_ops/cli/stackctl.py"
    stackctl.parent.mkdir(parents=True, exist_ok=True)
    stackctl.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


class LauncherWorktreeSelectionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="qwq-worktrees-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.primary = self.root / "product-mainline"
        _make_app_tree(self.primary)
        _git(self.primary, "init", "-q", "-b", "lane/product-mainline")
        _git(self.primary, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
        _git(
            self.primary, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-q", "-m", "fixture",
        )
        self.secondary = self.root / "engineering"
        _git(self.primary, "worktree", "add", "-q", "-b", "lane/engineering", str(self.secondary))
        self.selector = _load_selector()

    def test_cwd_inside_a_tree_selects_that_tree_without_prompt(self) -> None:
        chosen = self.selector.resolve_launch_app_dir(
            cwd=self.secondary / "quwoquan_app/lib",
            anchor_app_dir=self.primary / "quwoquan_app",
            interactive=False,
        )
        self.assertEqual(chosen, self.secondary / "quwoquan_app")

    def test_outside_any_tree_lists_all_worktrees_and_requires_a_choice(self) -> None:
        anchor = self.primary / "quwoquan_app"
        candidates = self.selector.list_app_worktrees(self.primary)
        self.assertEqual(
            sorted(candidate.branch for candidate in candidates),
            ["lane/engineering", "lane/product-mainline"],
        )
        with self.assertRaises(self.selector.WorktreeSelectionError) as blocked:
            self.selector.resolve_launch_app_dir(
                cwd=self.root, anchor_app_dir=anchor, interactive=False
            )
        self.assertIn("--worktree", str(blocked.exception))
        self.assertIn("engineering [lane/engineering]", str(blocked.exception))
        # 显式 --worktree 接受目录名、分支名与去掉 lane/ 前缀的短名。
        for explicit in ("engineering", "lane/engineering", str(self.secondary)):
            self.assertEqual(
                self.selector.resolve_launch_app_dir(
                    cwd=self.root, anchor_app_dir=anchor, explicit=explicit, interactive=False
                ),
                self.secondary / "quwoquan_app",
                explicit,
            )
        # TTY 数字选择。
        prompt = io.StringIO()
        chosen = self.selector.select_worktree(
            candidates,
            interactive=True,
            prompt_stream=prompt,
            input_stream=io.StringIO("2\n"),
        )
        self.assertEqual(chosen, candidates[1])
        self.assertIn("1)", prompt.getvalue())
        self.assertIn("2)", prompt.getvalue())

    def test_anchor_outside_git_falls_back_to_anchor_tree(self) -> None:
        plain = self.root / "plain-copy"
        _make_app_tree(plain)
        chosen = self.selector.resolve_launch_app_dir(
            cwd=self.root, anchor_app_dir=plain / "quwoquan_app", interactive=False
        )
        self.assertEqual(chosen, plain / "quwoquan_app")

    def test_wrapper_and_dispatcher_accept_worktree_option(self) -> None:
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("worktree_selection.py", wrapper)
        self.assertIn("--worktree", wrapper)
        dispatcher = DISPATCHER.read_text(encoding="utf-8")
        self.assertIn("strip_worktree_option", dispatcher)
        self.assertIn("resolve_launch_app_dir", dispatcher)
        explicit, remaining = self.selector.strip_worktree_option(
            ["--worktree", "engineering", "-d", "sim", "--worktree=ops"]
        )
        self.assertEqual(explicit, "ops")
        self.assertEqual(remaining, ["-d", "sim"])

    def test_user_zsh_projection_guards_carrier_before_exporting_identity(self) -> None:
        source = USER_ZSH_ACTIVATION.read_text(encoding="utf-8")
        guard = source.index("if [[ ! -r {quoted_carrier} ]]; then")
        exports = source.index("body_lines.extend(")
        self.assertLess(guard, exports)
        self.assertIn("APP.LAUNCH.workspace_entrypoint_inactive", source)
        self.assertIn("make app-activate-flutter-facade", source)
        carrier = USER_ZSH_CARRIER.read_text(encoding="utf-8")
        # 载体自身校验失败时也要撤回已导出的钉定身份，避免半激活。
        failure_block = carrier[carrier.index("if (( _qwq_user_zsh_projection_status != 0 )); then") :]
        for variable in (
            "QWQ_COCOAPODS_BINDING_SEAL",
            "QWQ_REAL_FLUTTER",
            "QWQ_FLUTTER_DISPATCHER_DIGEST",
        ):
            self.assertIn(variable, failure_block)

    def test_install_hooks_reports_facade_drift_without_mutating_shell(self) -> None:
        source = INSTALL_HOOKS.read_text(encoding="utf-8")
        self.assertIn("activate_cursor_workspace.py\" --scope all --status", source)
        self.assertIn("drifted|missing|inactive", source)
        self.assertNotIn("--scope all\"$", source.replace("FACADE_ACTION=\\\"--scope all\\\"", ""))
        self.assertIn("不阻断", source)


if __name__ == "__main__":
    unittest.main()
