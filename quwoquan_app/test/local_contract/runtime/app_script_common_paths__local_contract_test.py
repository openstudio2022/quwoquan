#!/usr/bin/env python3
"""Moved App scripts must resolve roots via _common.paths, not parents[N]."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = REPO_ROOT / "quwoquan_app" / "scripts"
PATHS_PY = SCRIPTS_ROOT / "_common" / "paths.py"
LOGIN_LOOP = (
    SCRIPTS_ROOT / "runtime" / "auth" / "verify_login_entry_loop_contract.py"
)
PAGEFLIP = (
    SCRIPTS_ROOT
    / "content_service"
    / "content"
    / "post"
    / "verify_pageflip_backward_mainline.py"
)
MOVED_SCOPES = (
    "content_service",
    "chat_service",
    "tag_service",
    "user_service",
    "runtime",
    "tools",
)


class AppScriptCommonPathsContractTest(unittest.TestCase):
    def test_locate_scripts_root_is_depth_independent(self) -> None:
        sys.path.insert(0, str(SCRIPTS_ROOT))
        from _common.paths import APP_ROOT, REPO_ROOT as COMMON_REPO
        from _common.paths import SCRIPTS_ROOT as COMMON_SCRIPTS
        from _common.paths import locate_scripts_root

        nested = (
            SCRIPTS_ROOT
            / "content_service"
            / "content"
            / "post"
            / "verify_pageflip_backward_mainline.py"
        )
        self.assertEqual(locate_scripts_root(nested), COMMON_SCRIPTS)
        self.assertEqual(COMMON_SCRIPTS, SCRIPTS_ROOT)
        self.assertEqual(APP_ROOT, REPO_ROOT / "quwoquan_app")
        self.assertEqual(COMMON_REPO, REPO_ROOT)

    def test_moved_scripts_avoid_parent_index_root_lookups(self) -> None:
        offenders: list[str] = []
        for scope in MOVED_SCOPES:
            for path in sorted((SCRIPTS_ROOT / scope).rglob("*.py")):
                if path.name == "page_disk_scan_paths.py":
                    continue
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Subscript):
                        continue
                    # Path(__file__).resolve().parents[N]
                    value = node.value
                    if not isinstance(value, ast.Attribute) or value.attr != "parents":
                        continue
                    resolve_call = value.value
                    if not isinstance(resolve_call, ast.Call):
                        continue
                    func = resolve_call.func
                    if not isinstance(func, ast.Attribute) or func.attr != "resolve":
                        continue
                    offenders.append(
                        f"{path}:{node.lineno}: parents[N] root lookup"
                    )
        self.assertEqual(offenders, [])

    def test_login_loop_gate_runs_from_foreign_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", str(LOGIN_LOOP)],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("登录入口无死循环契约一致", result.stdout)

    # spec_ref: specs/feature-tree/discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md#gwt-003
    def test_login_loop_gate_rejects_early_gate_and_missing_terminal_auth(self) -> None:
        spec = importlib.util.spec_from_file_location("login_loop_under_test", LOGIN_LOOP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_read = module.read
        cases = (
            ("quwoquan_app/lib/runtime/auth/auth_gate.dart", None),
            ("quwoquan_app/lib/service/content_service/content/post/presentation/create_page_state_media_helpers.dart", "_requireCreateActionLogin("),
            ("quwoquan_app/lib/service/content_service/content/post/presentation/create_page_state_draft_helpers.dart", "_requireCreateActionLogin("),
        )
        for path, removed in cases:
            with self.subTest(path=path):
                def changed_read(rel: str) -> str:
                    text = original_read(rel)
                    if rel != path:
                        return text
                    if removed is None:
                        return text + "\nloc == AppRoutePaths.createPathTemplate\n"
                    self.assertIn(removed, text)
                    return text.replace(removed, "removedLoginProtection(")

                with mock.patch.object(module, "read", side_effect=changed_read):
                    self.assertEqual(module.main(), 1)

    def test_deeply_nested_pageflip_gate_uses_common_repo_root(self) -> None:
        source = PAGEFLIP.read_text(encoding="utf-8")
        self.assertIn("from _common.paths import", source)
        self.assertIn("ROOT = REPO_ROOT", source)
        self.assertNotIn("Path(__file__).resolve().parents[", source)
        self.assertTrue(PATHS_PY.is_file())


if __name__ == "__main__":
    unittest.main()
