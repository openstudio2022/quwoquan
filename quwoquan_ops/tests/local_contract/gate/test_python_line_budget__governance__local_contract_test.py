# spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-004
"""Python 行数硬顶契约：1000 行统一预算、边界豁免与 enforcement 切换。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.gate.python_script_governance import derive_report
from quwoquan_ops.gate.python_script_governance import report as governance_report
from quwoquan_ops.gate.python_script_governance.constants import (
    PYTHON_LINE_BUDGET_MAX_LINES,
)
from quwoquan_ops.gate.python_script_governance.line_budget import (
    line_budget_issues,
    stdin_piped_contract_scripts,
)
from quwoquan_ops.gate.python_script_governance.models import PythonFileRecord

_OVER_BUDGET_BODY = "x = 1\n" * (PYTHON_LINE_BUDGET_MAX_LINES + 1)
_AT_BUDGET_BODY = "x = 1\n" * PYTHON_LINE_BUDGET_MAX_LINES


class PythonLineBudgetContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _write(self, relative: str, text: str = "") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def _budget_entries(report: dict[str, object], key: str) -> set[str]:
        return {
            str(entry["path"])
            for entry in report[key]  # type: ignore[index]
            if entry["code"] == "PYTHON.LINE_BUDGET_EXCEEDED"
        }

    def test_over_budget_script_and_test_block_by_default(self) -> None:
        """存量清零后行数硬顶默认 block：实现与测试超标一律进入阻断 issues。"""
        self._write(
            "quwoquan_ops/gate/verify_oversized_example.py",
            _OVER_BUDGET_BODY,
        )
        self._write(
            "quwoquan_ops/tests/local_contract/gate/"
            "test_oversized__gate__local_contract_test.py",
            _OVER_BUDGET_BODY,
        )
        self._write(
            "quwoquan_ops/gate/verify_at_budget_example.py",
            _AT_BUDGET_BODY,
        )

        report = derive_report(self.root, ("ops",))

        self.assertEqual(
            {
                "quwoquan_ops/gate/verify_oversized_example.py",
                "quwoquan_ops/tests/local_contract/gate/"
                "test_oversized__gate__local_contract_test.py",
            },
            self._budget_entries(report, "issues"),
        )
        self.assertEqual(set(), self._budget_entries(report, "warnings"))
        self.assertEqual(
            2,
            report["summary"]["lineBudgetExceededCount"],  # type: ignore[index]
        )

    def test_warn_enforcement_keeps_findings_advisory(self) -> None:
        """enforcement 回退 warn 时超标只进 warnings，保留分阶段接入的可切换性。"""
        self._write(
            "quwoquan_ops/gate/verify_oversized_example.py",
            _OVER_BUDGET_BODY,
        )

        with mock.patch.object(
            governance_report,
            "PYTHON_LINE_BUDGET_ENFORCEMENT",
            "warn",
        ):
            report = derive_report(self.root, ("ops",))

        self.assertEqual(
            {"quwoquan_ops/gate/verify_oversized_example.py"},
            self._budget_entries(report, "warnings"),
        )
        self.assertEqual(set(), self._budget_entries(report, "issues"))

    def test_generated_vendor_are_exempt_but_data_uses_same_budget(self) -> None:
        records = [
            PythonFileRecord(
                path="quwoquan_service/generated/oversized_generated.py",
                scope="service",
                boundary="generated",
            ),
            PythonFileRecord(
                path="quwoquan_service/vendor/oversized_vendor.py",
                scope="service",
                boundary="vendor",
            ),
            PythonFileRecord(
                path="quwoquan_data/scripts/content/oversized_data_module.py",
                scope="data",
                boundary="managed_script",
            ),
            PythonFileRecord(
                path="quwoquan_data/tests/local_contract/"
                "test_oversized__contract__local_contract_test.py",
                scope="data",
                boundary="test_evidence",
            ),
        ]
        for record in records:
            self._write(record.path, _OVER_BUDGET_BODY)

        issues = line_budget_issues(self.root, records)

        # Data 不存在另一套 600/500/400 行门；所有非 generated/vendor
        # Python 边界使用同一 1000 行事实源。
        self.assertEqual(
            [
                "quwoquan_data/scripts/content/oversized_data_module.py",
                "quwoquan_data/tests/local_contract/"
                "test_oversized__contract__local_contract_test.py",
            ],
            [issue.path for issue in issues],
        )

    def test_stdin_piped_contract_script_is_derived_exempt(self) -> None:
        # spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#sit-002.t1
        # spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#sit-002.t2
        # 被 shell 编排整文件 stdin pipe 到裸 python3 执行的脚本，单文件自包含
        # 是物理契约；豁免从 shell 调用形态派生，不是人工 allowlist（t1），
        # 且同批未被 pipe 的超标文件照常阻断（t2）。
        piped = "quwoquan_ops/cli/prod/remote_ledger_helper.py"
        plain = "quwoquan_ops/cli/prod/oversized_local_helper.py"
        self._write(piped, _OVER_BUDGET_BODY)
        self._write(plain, _OVER_BUDGET_BODY)
        self._write(
            "quwoquan_ops/cli/prod/sync_example_stack.sh",
            "#!/usr/bin/env bash\n"
            f'helper="$ROOT/{piped}"\n'
            'remote_command="python3 -"\n'
            'ssh host "$remote_command" < "$helper"\n',
        )
        records = [
            PythonFileRecord(path=piped, scope="ops", boundary="managed_script"),
            PythonFileRecord(path=plain, scope="ops", boundary="managed_script"),
        ]

        stdin_piped_contract_scripts.cache_clear()
        issues = line_budget_issues(self.root, records)

        # 同为超标：被 pipe 的豁免，未被 pipe 的照常阻断。
        self.assertEqual([plain], [issue.path for issue in issues])
        self.assertEqual(
            frozenset({piped}),
            stdin_piped_contract_scripts(self.root),
        )


if __name__ == "__main__":
    unittest.main()
