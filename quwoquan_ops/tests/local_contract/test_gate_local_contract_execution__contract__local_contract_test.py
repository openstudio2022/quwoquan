from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
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
                "quwoquan_ops/tests/local_contract/"
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
            "quwoquan_ops/tests/local_contract/"
            "test_single_track_contracts__contract__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/"
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
            "external_provider_governance__local_contract_test.py",
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
        self.assertEqual(module.main([]), 0)

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


if __name__ == "__main__":
    unittest.main()
