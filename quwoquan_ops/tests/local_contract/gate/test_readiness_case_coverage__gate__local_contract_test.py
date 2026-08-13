"""verify_readiness_case_coverage 的棘轮与 fail-closed 合约。

覆盖：空扫描必须 ScanError、UA runner 路径指向不存在文件必须 strict 阻断、
棘轮新增缺口阻断且 stale 基线条目阻断、门禁与本测试必须留在 gate 链上。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_readiness_case_coverage.py"
BASELINE = ROOT / "quwoquan_ops/policies/gates/readiness_case_coverage_baseline.json"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"

SPEC = importlib.util.spec_from_file_location("verify_readiness_case_coverage", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


class FailClosedContract(unittest.TestCase):
    def test_missing_app_uat_root_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.app_uat_objects(Path(empty))

    def test_missing_ops_root_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.ops_uat_services(Path(empty))

    def test_missing_service_root_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.operations_documents(Path(empty))


class DeclarationTruthContract(unittest.TestCase):
    def test_ua_case_with_ghost_runner_blocks(self) -> None:
        documents = {
            ("user-service", "account", "user_settings"): (
                ROOT
                / "quwoquan_service/services/user-service/contracts/account/user_settings/operations.yaml",
                {
                    "readiness_cases": [
                        {
                            "case_id": "demo_uat",
                            "layer": "user_acceptance",
                            "producer": "app",
                            "runner_source_path": "quwoquan_app/test/user_acceptance/ghost__user_acceptance_test.dart",
                        }
                    ]
                },
            )
        }
        _, _, failures = gate.declared_layers(documents)
        self.assertTrue(any("does not exist on disk" in item for item in failures))

    def test_ua_case_without_runner_blocks(self) -> None:
        documents = {
            ("user-service", "account", "user_settings"): (
                ROOT
                / "quwoquan_service/services/user-service/contracts/account/user_settings/operations.yaml",
                {
                    "readiness_cases": [
                        {"case_id": "demo_uat", "layer": "user_acceptance"}
                    ]
                },
            )
        }
        _, _, failures = gate.declared_layers(documents)
        self.assertTrue(any("unfalsifiable" in item for item in failures))

    def test_real_ua_declaration_passes(self) -> None:
        documents = gate.operations_documents(ROOT)
        ua_objects, _, failures = gate.declared_layers(documents)
        self.assertIn(("user-service", "account", "user_settings"), ua_objects)
        self.assertEqual(failures, [])


class RatchetContract(unittest.TestCase):
    def test_baseline_requires_governance(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            baseline = repo_root / gate.BASELINE_RELATIVE
            baseline.parent.mkdir(parents=True)
            baseline.write_text(json.dumps({"missing_user_acceptance_objects": []}))
            _, _, problems = gate.load_baseline(repo_root)
            self.assertTrue(any("_governance" in item for item in problems))

    def test_live_repository_gaps_match_baseline_exactly(self) -> None:
        """棘轮闭合：缺口清零后基线文件必须缺席，实际缺口与基线（或零容忍）完全一致。"""
        import json

        if BASELINE.is_file():
            baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
            expected_ua = sorted(baseline["missing_user_acceptance_objects"])
            expected_ops = sorted(baseline["missing_ops_producer_services"])
        else:
            expected_ua, expected_ops = [], []
        uat_tests = gate.app_uat_objects(ROOT)
        ops_disk = gate.ops_uat_services(ROOT)
        documents = gate.operations_documents(ROOT)
        ua_declared, ops_declared, _ = gate.declared_layers(documents)
        missing_ua = sorted(
            f"{gate.app_service_to_cloud(svc)}/{ctx}/{obj}"
            for (svc, ctx, obj) in uat_tests
            if (gate.app_service_to_cloud(svc), ctx, obj) not in ua_declared
        )
        missing_ops = sorted(s for s in ops_disk if s not in ops_declared)
        self.assertEqual(missing_ua, expected_ua)
        self.assertEqual(missing_ops, expected_ops)


class WiringContract(unittest.TestCase):
    def test_gate_is_on_gate_repo_chain(self) -> None:
        self.assertIn(
            "quwoquan_ops/gate/verify_readiness_case_coverage.py",
            GATE_REPO.read_text(encoding="utf-8"),
        )

    def test_companion_test_is_executed(self) -> None:
        self.assertIn(Path(__file__).name, MAKEFILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
