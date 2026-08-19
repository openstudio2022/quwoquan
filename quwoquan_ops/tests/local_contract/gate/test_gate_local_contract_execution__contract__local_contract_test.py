from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_gate_local_contract_execution.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_gate_local_contract_execution",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GateLocalContractExecutionContractTest(unittest.TestCase):
    def test_gate_chain_expansion_reaches_make_target_recipes(self) -> None:
        """gate 链可达集合必须穿透 Make target，而不是只看 gate_repo.sh 字面量。

        `verify_vertical_architecture_ratchet.py` 的配套测试只经
        `make test-vertical-architecture-ratchet-local-contract` 执行；解析器不展开
        Make recipe 就会把它误报成缺口。
        """
        module = _load_verifier()
        commands = module._collect_reachable_commands()
        scripts, pytest_paths, unittest_modules = (
            module._reachable_scripts_and_test_paths(commands)
        )
        self.assertIn(
            "quwoquan_ops/gate/verify_single_track_contracts.py",
            scripts,
        )
        self.assertTrue(
            module._test_is_executed(
                # 1000 行硬顶治理后该套件已迁入 gate/ concern 目录。
                "quwoquan_ops/tests/local_contract/gate/"
                "test_vertical_architecture_ratchet__local_contract_test.py",
                scripts,
                pytest_paths,
                unittest_modules,
            ),
            "经 Make target 进入的 pytest 参数必须算作已执行",
        )

    def test_directly_invoked_test_counts_as_executed(self) -> None:
        """正例：门禁旁边直接 `python3 <test>` 的配套测试不算缺口。"""
        module = _load_verifier()
        commands = module._collect_reachable_commands()
        scripts, pytest_paths, unittest_modules = (
            module._reachable_scripts_and_test_paths(commands)
        )
        for executed in (
            # 1000 行硬顶治理后该套件已迁入 gate/ concern 目录。
            "quwoquan_ops/tests/local_contract/gate/"
            "test_single_track_contracts__contract__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/gate/"
            "test_emitted_error_code_declaration__contract__local_contract_test.py",
        ):
            with self.subTest(test=executed):
                self.assertTrue(
                    module._test_is_executed(
                        executed,
                        scripts,
                        pytest_paths,
                        unittest_modules,
                    )
                )

    def test_unexecuted_companion_test_is_detected(self) -> None:
        """负例：配套测试不在任何 gate 链上时必须被判定为缺口。"""
        module = _load_verifier()
        self.assertFalse(
            module._test_is_executed(
                "quwoquan_ops/tests/local_contract/"
                "test_git_branch_policy__local_contract_test.py",
                {"quwoquan_ops/gate/verify_git_branch_policy.py"},
                {"quwoquan_app/test/local_contract"},
                set(),
            )
        )
        self.assertTrue(
            module._test_is_executed(
                "quwoquan_app/test/local_contract/runtime/demo__local_contract_test.py",
                set(),
                {"quwoquan_app/test/local_contract"},
                set(),
            ),
            "pytest 目录参数必须覆盖其下全部测试文件",
        )

    def test_companion_pairing_follows_the_repository_naming_convention(
        self,
    ) -> None:
        """配套关系只按 subject 判定，不按「名字里出现过」判定。"""
        module = _load_verifier()
        tests = [
            "quwoquan_ops/tests/local_contract/"
            "test_single_track_contracts__contract__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/"
            "test_directory_layout__canonical_service_tests__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/"
            "test_external_provider_governance__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/"
            "test_single_track_contracts_unrelated_subject__local_contract_test.py",
        ]
        self.assertEqual(
            module._companion_tests(
                "quwoquan_ops/gate/verify_single_track_contracts.py",
                tests,
            ),
            [tests[0]],
        )
        # `verify_test_directory_layout.py` 的 `test_` 是 subject 自己的第一个词。
        self.assertEqual(
            module._companion_tests(
                "quwoquan_ops/gate/scaffold/verify_test_directory_layout.py",
                tests,
            ),
            [tests[1]],
        )
        # 没有 `test_` 前缀的 canonical 测试名同样要配上。
        self.assertEqual(
            module._companion_tests(
                "quwoquan_ops/gate/verify_external_provider_governance.py",
                tests,
            ),
            [tests[2]],
        )

    def test_companion_gaps_are_zero_without_any_allowance_baseline(self) -> None:
        """缺口容忍基线已删除：门禁转零容忍，缺口必须真的为 0 而不是等于基线。"""
        module = _load_verifier()
        self.assertFalse(
            module.BASELINE_PATH.exists(),
            "缺口容忍基线不得重新引入；新增门禁请补 test-gate-companion-local-contract",
        )
        baseline_keys, problems = module._load_baseline()
        self.assertEqual(problems, [])
        self.assertEqual(baseline_keys, set())
        head_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            module.main(["--base-sha", head_sha, "--head-sha", head_sha]),
            0,
            "判据 A 的零容忍自检不得混入当前分支相对 main 的历史变更面",
        )

    def test_missing_governance_keys_are_blocking(self) -> None:
        """负例：基线缺 governance 三键必须阻断，不能悄悄放行。"""
        module = _load_verifier()
        original = module.BASELINE_PATH
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "baseline.yaml"
            broken.write_text(
                "schema: gate-local-contract-execution-baseline\n"
                "governance:\n  owner: someone\n"
                "unexecuted_companion_tests: []\n",
                encoding="utf-8",
            )
            module.BASELINE_PATH = broken
            try:
                _, problems = module._load_baseline()
            finally:
                module.BASELINE_PATH = original
        self.assertIn("baseline governance 缺少 reason", problems)
        self.assertIn("baseline governance 缺少 expires_when", problems)


class ChangedGateNeedsCompanionTest(unittest.TestCase):
    """判据 B：本次已提交增量里的门禁必须有被执行的 companion。

    判据 A 只在「恰好有同名测试」时才生效——一个门禁完全没有配套测试时，配套集合是
    空的，循环体一次都不执行，门禁反而放行。这里用真实 git 仓库跑完整 diff 路径，
    而不是 monkeypatch 掉 `changed_gate_scripts`：被绕过的恰恰是 diff 那一段。
    """

    def _repository(self) -> Path:
        import subprocess
        import tempfile

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)

        def git(*arguments: str) -> None:
            subprocess.run(
                ("git", *arguments),
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

        git("init", "-q", "-b", "main")
        git("config", "user.email", "gate@example.com")
        git("config", "user.name", "gate")
        (root / "README.md").write_text("base\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "feature")
        self._git = git
        return root

    def _committed_gate(self, name: str) -> tuple[object, Path]:
        root = self._repository()
        target = root / "quwoquan_ops/gate" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self._git("add", str(target.relative_to(root)))
        self._git("commit", "-q", "-m", f"add {name}")

        module = _load_verifier()
        module.ROOT = root
        module.BASE_CANDIDATES = ("main",)
        return module, root

    def test_newly_committed_gate_without_companion_is_reported(self) -> None:
        module, _ = self._committed_gate("verify_brand_new_thing.py")
        changed = module.changed_gate_scripts()
        self.assertEqual(["quwoquan_ops/gate/verify_brand_new_thing.py"], changed)
        # 没有任何同名测试时配套集合是空的——判据 A 在这里什么都不会说。
        self.assertEqual([], module._companion_tests(changed[0], []))

    def test_non_gate_python_changes_are_out_of_scope(self) -> None:
        module, root = self._committed_gate("verify_brand_new_thing.py")
        for noise in ("quwoquan_ops/gate/helper_lib.py", "docs/notes.md"):
            path = root / noise
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
            self._git("add", noise)
        self._git("commit", "-q", "-m", "noise")
        self.assertEqual(
            ["quwoquan_ops/gate/verify_brand_new_thing.py"],
            module.changed_gate_scripts(),
            "只有 verify_ 前缀的门禁脚本进入判据 B",
        )

    def test_explicit_dev_push_range_does_not_reaudit_dev1_history(self) -> None:
        root = self._repository()
        historical = root / "quwoquan_ops/gate/verify_historical_gate.py"
        historical.parent.mkdir(parents=True, exist_ok=True)
        historical.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self._git("add", str(historical.relative_to(root)))
        self._git("commit", "-q", "-m", "historical dev1 gate")
        dev1_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (root / "README.md").write_text("current PR\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-q", "-m", "non-gate PR")
        head_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        module = _load_verifier()
        module.ROOT = root
        self.assertEqual([], module.changed_gate_scripts(dev1_sha, head_sha))
        self.assertEqual(
            ["quwoquan_ops/gate/verify_historical_gate.py"],
            module.changed_gate_scripts(
                subprocess.run(
                    ("git", "rev-parse", "main"),
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                head_sha,
            ),
            "main -> dev1 promotion 仍必须审计历史 gate",
        )

    def test_explicit_range_reports_only_the_gate_changed_by_this_pr(self) -> None:
        module, root = self._committed_gate("verify_brand_new_thing.py")
        head_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        base_sha = subprocess.run(
            ("git", "rev-parse", "main"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            ["quwoquan_ops/gate/verify_brand_new_thing.py"],
            module.changed_gate_scripts(base_sha, head_sha),
        )

    def test_explicit_range_fails_closed_for_missing_or_invalid_identity(self) -> None:
        module, root = self._committed_gate("verify_brand_new_thing.py")
        head_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        base_sha = subprocess.run(
            ("git", "rev-parse", "main"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        with self.assertRaisesRegex(module.ChangeRangeError, "成对提供"):
            module.changed_gate_scripts(base_sha, None)
        with self.assertRaisesRegex(module.ChangeRangeError, "40 位"):
            module.changed_gate_scripts("not-a-sha", head_sha)
        with self.assertRaisesRegex(module.ChangeRangeError, "当前 checkout HEAD"):
            module.changed_gate_scripts(base_sha, base_sha)

        self._git("checkout", "-q", "main")
        self._git("checkout", "-q", "-b", "sibling")
        (root / "README.md").write_text("sibling\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-q", "-m", "sibling")
        sibling_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with self.assertRaisesRegex(module.ChangeRangeError, "必须是 head_sha 的祖先"):
            module.changed_gate_scripts(head_sha, sibling_sha)

        original_git = module._git

        def fail_diff(*arguments: str):
            if arguments[:2] == ("diff", "--name-only"):
                return None
            return original_git(*arguments)

        module._git = fail_diff
        with self.assertRaisesRegex(module.ChangeRangeError, "git diff"):
            module.changed_gate_scripts(base_sha, sibling_sha)

        self.assertEqual(
            2,
            module.main(
                ["--print-current", "--base-sha", "not-a-sha", "--head-sha", sibling_sha]
            ),
            "诊断输出也不得绕过显式 change range 的 fail-closed 校验",
        )

    def test_uncommitted_worktree_changes_are_not_counted(self) -> None:
        """脏工作树是本仓库常态，把它计入会让判据 B 长期为别人的改动报红。"""
        module, root = self._committed_gate("verify_brand_new_thing.py")
        dirty = root / "quwoquan_ops/gate/verify_someone_elses_parallel_work.py"
        dirty.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self.assertEqual(
            ["quwoquan_ops/gate/verify_brand_new_thing.py"],
            module.changed_gate_scripts(),
        )

    def test_app_gate_tree_is_in_scope_for_changed_gates(self) -> None:
        """判据 B 的范围比判据 A 宽：App 门禁改了同样要证明自己。"""
        root = self._repository()
        target = root / "quwoquan_app/scripts/runtime/observability/verify_thing.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        self._git("add", str(target.relative_to(root)))
        self._git("commit", "-q", "-m", "add app gate")

        module = _load_verifier()
        module.ROOT = root
        module.BASE_CANDIDATES = ("main",)
        self.assertEqual(
            ["quwoquan_app/scripts/runtime/observability/verify_thing.py"],
            module.changed_gate_scripts(),
        )

    def test_non_git_tree_skips_criterion_b(self) -> None:
        """打包产物里 diff 无从计算，强行报错只会制造另一种假红灯。"""
        import tempfile

        module = _load_verifier()
        with tempfile.TemporaryDirectory() as tmp:
            module.ROOT = Path(tmp)
            self.assertIsNone(module.changed_gate_scripts())

    def _isolated_chain(self, gate_name: str, companion: str | None):
        """一条最小 gate 链：只挂 `gate_name`，可选地挂上它的 companion。"""
        root = self._repository()
        entry = root / "quwoquan_ops/gate/gate_repo.sh"
        entry.parent.mkdir(parents=True, exist_ok=True)
        commands = [f"python3 quwoquan_ops/gate/{gate_name}"]
        gate = root / "quwoquan_ops/gate" / gate_name
        gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        if companion is not None:
            test_path = root / "quwoquan_ops/tests/local_contract/gate" / companion
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text("", encoding="utf-8")
            commands.append(
                f"python3 quwoquan_ops/tests/local_contract/gate/{companion}"
            )
        entry.write_text("\n".join(commands) + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "wire gate chain")

        module = _load_verifier()
        module.ROOT = root
        module.GATE_ENTRY = entry
        module.BASE_CANDIDATES = ("main",)
        module.BASELINE_PATH = root / "does-not-exist.yaml"
        module.MAKEFILE_BY_DIR = {}
        return module

    def test_main_blocks_when_a_changed_gate_has_no_companion(self) -> None:
        """端到端：缺 companion 时门禁自身必须失败，而不是打印 OK。"""
        import contextlib
        import io

        module = self._isolated_chain("verify_brand_new_thing.py", companion=None)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(
            io.StringIO()
        ):
            exit_code = module.main([])
        self.assertEqual(1, exit_code)
        message = stderr.getvalue()
        self.assertIn("verify_brand_new_thing.py", message)
        self.assertIn("没有任何同名 companion 测试", message)

    def test_main_passes_when_the_companion_is_on_the_chain(self) -> None:
        """正例：companion 补齐并挂上链后同一条链必须放行。"""
        import contextlib
        import io

        module = self._isolated_chain(
            "verify_brand_new_thing.py",
            companion="test_brand_new_thing__gate__local_contract_test.py",
        )
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(
            io.StringIO()
        ):
            self.assertEqual(0, module.main([]))

    def test_main_blocks_when_the_companion_exists_but_is_never_run(self) -> None:
        """companion 躺在树里但没有任何 gate 链执行，同样不算证明。"""
        import contextlib
        import io

        module = self._isolated_chain("verify_brand_new_thing.py", companion=None)
        orphan = (
            module.ROOT
            / "quwoquan_ops/tests/local_contract/gate"
            / "test_brand_new_thing__gate__local_contract_test.py"
        )
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(
            io.StringIO()
        ):
            self.assertEqual(1, module.main([]))
        self.assertIn("没有任何 gate 链执行", stderr.getvalue())

    def test_this_rounds_three_gates_have_executed_companions(self) -> None:
        """本轮三道门禁在真实仓库里必须已满足判据 B。"""
        module = _load_verifier()
        commands = module._collect_reachable_commands()
        scripts, pytest_paths, unittest_modules = (
            module._reachable_scripts_and_test_paths(commands)
        )
        tests = module._local_contract_tests()
        for gate in (
            "quwoquan_service/scripts/verify/structure/verify_nil_semantics.py",
            "quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py",
            "quwoquan_ops/gate/verify_ratchet_baseline_governance.py",
        ):
            with self.subTest(gate=gate):
                companions = module._companion_tests(gate, tests)
                self.assertTrue(companions, f"{gate} 缺 companion 测试")
                self.assertTrue(
                    any(
                        module._test_is_executed(
                            test, scripts, pytest_paths, unittest_modules
                        )
                        for test in companions
                    ),
                    f"{gate} 的 companion 没有被 gate 链执行：{companions}",
                )


if __name__ == "__main__":
    unittest.main()
