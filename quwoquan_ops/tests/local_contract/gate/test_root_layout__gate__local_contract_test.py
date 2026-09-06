"""local_contract: 仓库根布局门禁的白名单封闭性与源码树缓存判据正负例。"""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_root_layout.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_root_layout", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _materialize_allowed_root(root: Path, module) -> None:
    """按白名单铺出一棵「完全合规」的根，作为全部拒绝用例的对照基线。

    逐条读 `ALLOWED_TOP_LEVEL` 而不是复制一份名单，是为了让白名单增删时对照基线
    自动跟随；否则门禁放宽后这里会退化成一个恒真的空树。
    """
    for name in sorted(module.ALLOWED_TOP_LEVEL):
        entry = root / name
        if name.endswith((".md", ".json", ".code-workspace")) or name in {
            ".gitignore",
            ".dockerignore",
            ".cursorignore",
            "Makefile",
            "LICENSE",
        }:
            entry.write_text("placeholder\n", encoding="utf-8")
        else:
            entry.mkdir(parents=True, exist_ok=True)


class RootLayoutGateTest(unittest.TestCase):
    def test_allowed_top_level_entries_are_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            self.assertEqual(module.top_level_issues(root), [])

    def test_unregistered_top_level_entry_is_rejected(self) -> None:
        """`v/`、`v0/`、`v360p/` 这类被截断的 ffmpeg 参数误建目录曾长期存活。

        白名单封闭是唯一能拦下「从未被预见过的名字」的形态，所以这里用一个不在
        任何黑名单里的新名字取证。
        """
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            (root / "v360p").mkdir()
            issues = module.top_level_issues(root)
            self.assertEqual(len(issues), 1)
            self.assertIn("v360p", issues[0])
            self.assertIn("unregistered top-level entry", issues[0])

    def test_unregistered_top_level_file_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            (root / "gate_summary.txt").write_text("output\n", encoding="utf-8")
            issues = module.top_level_issues(root)
            self.assertEqual(len(issues), 1)
            self.assertIn("gate_summary.txt", issues[0])
            self.assertIn("unregistered top-level entry", issues[0])

    def test_retired_top_level_entry_reports_its_disposition(self) -> None:
        """退役条目要给出比「未登记」更具体的去向，避免重复走一遍归属排查。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            (root / ".ruff_cache").mkdir()
            (root / "artifacts").mkdir()
            issues = module.top_level_issues(root)
            self.assertEqual(len(issues), 2)
            joined = "\n".join(issues)
            self.assertIn("retired top-level entry", joined)
            self.assertIn(
                module.RETIRED_TOP_LEVEL[".ruff_cache"],
                joined,
            )
            self.assertIn(module.RETIRED_TOP_LEVEL["artifacts"], joined)

    def test_multi_root_cursor_workspace_is_retired(self) -> None:
        module = _load_module()
        self.assertNotIn("quwoquan-workspace.code-workspace", module.ALLOWED_TOP_LEVEL)
        self.assertIn("quwoquan-workspace.code-workspace", module.RETIRED_TOP_LEVEL)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            (root / "quwoquan-workspace.code-workspace").write_text(
                '{"folders": [{"path": "."}, {"path": "../other"}]}',
                encoding="utf-8",
            )
            issues = module.top_level_issues(root)
            self.assertTrue(any("multi-root workspace is retired" in issue for issue in issues))

    def test_retired_and_allowed_names_do_not_overlap(self) -> None:
        """白名单先判、退役名单后判：两者相交会让退役提示永远打不出来。"""
        module = _load_module()
        self.assertEqual(
            module.ALLOWED_TOP_LEVEL & set(module.RETIRED_TOP_LEVEL),
            set(),
        )

    def test_source_domain_bytecode_and_caches_are_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate_dir = root / "quwoquan_ops" / "gate"
            gate_dir.mkdir(parents=True)
            (gate_dir / "verify_demo.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(module.source_cache_issues(root), [])

            cache_dir = gate_dir / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "verify_demo.cpython-313.pyc").write_bytes(b"\x00")
            (gate_dir / "stray.pyo").write_bytes(b"\x00")
            issues = module.source_cache_issues(root)
            self.assertEqual(len(issues), 2)
            joined = "\n".join(issues)
            self.assertIn("__pycache__", joined)
            self.assertIn("source cache is forbidden", joined)
            self.assertIn("stray.pyo", joined)
            self.assertIn("Python bytecode is forbidden", joined)

    def test_pycache_contents_are_reported_once_per_directory(self) -> None:
        """`__pycache__` 命中后要剪枝再下钻。

        不剪枝时一个缓存目录会按 `.pyc` 个数刷屏，真正的问题（例如同域里另一处
        散落的 `.pyo`）被淹没在几百行同义输出里。
        """
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "quwoquan_data" / "scripts" / "__pycache__"
            cache_dir.mkdir(parents=True)
            for index in range(5):
                (cache_dir / f"module_{index}.cpython-313.pyc").write_bytes(b"\x00")
            issues = module.source_cache_issues(root)
            self.assertEqual(len(issues), 1)
            self.assertIn("__pycache__", issues[0])

    def test_caches_outside_source_domains_are_not_scanned(self) -> None:
        """判据只覆盖四个源域；`.qwq_output` 下的可弃缓存由输出布局门禁负责。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / ".qwq_output" / "env" / "repo" / "local" / "cache"
            cache_dir.mkdir(parents=True)
            (cache_dir / "compiled.pyc").write_bytes(b"\x00")
            self.assertEqual(module.source_cache_issues(root), [])

    def test_runtime_artifacts_in_source_domains_are_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            (root / "quwoquan_app" / "artifacts").mkdir(parents=True)
            issues = module.root_layout_issues(root)
            self.assertTrue(
                any(
                    "quwoquan_app/artifacts" in issue
                    and "must not contain runtime artifacts" in issue
                    for issue in issues
                ),
                msg=issues,
            )

    def test_retired_feature_island_directory_is_rejected(self) -> None:
        """按业务特性在 ops 下新建脚本岛是反复出现的形态，判据必须是显式路径。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            island = root / "quwoquan_ops" / "assistant"
            island.mkdir(parents=True)
            issues = module.root_layout_issues(root)
            self.assertTrue(
                any(
                    "quwoquan_ops/assistant" in issue
                    and "retired feature island directory" in issue
                    for issue in issues
                ),
                msg=issues,
            )

    def test_forbidden_shim_file_and_portal_output_are_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            shim = root / "quwoquan_ops" / "cli" / "stackctl.sh"
            shim.parent.mkdir(parents=True)
            shim.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            dist = root / "quwoquan_ops" / "portal" / "dist"
            dist.mkdir(parents=True)
            issues = module.root_layout_issues(root)
            joined = "\n".join(issues)
            self.assertIn("forbidden generated or shim file", joined)
            self.assertIn("Portal generated output must not live in source tree", joined)

    def test_clean_synthetic_root_produces_no_issues(self) -> None:
        """全部拒绝用例共享同一棵基线树；基线本身必须干净，否则断言会假阳性。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize_allowed_root(root, module)
            self.assertEqual(module.root_layout_issues(root), [])

    def test_real_repository_tracked_source_tree_layout_holds(self) -> None:
        """版本控制输入必须合规，且不消费共享工作树的并行测试缓存。

        全量 pytest/ruff 可在根或源码域短暂生成未跟踪缓存；真实磁盘扫描属于独立
        gate 的职责。本用例在临时根物化当前 Git index 的受控顶层与源码目录，既保留
        对被跟踪布局回归的阻断，也不因另一会话的运行时残留产生随机假红。
        """
        module = _load_module()
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").split("\0")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in tracked:
                if not relative:
                    continue
                source = ROOT / relative
                target = root / relative
                if source.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
            self.assertEqual(module.top_level_issues(root), [])
            self.assertEqual(module.source_cache_issues(root), [])


if __name__ == "__main__":
    unittest.main()
