#!/usr/bin/env python3
"""启动环境矩阵 CaseResult 证据门禁的 local_contract。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime" / "platform" / "verify_startup_environment_matrix.py"
)

#: 稳定 CLI 入口对既有消费者（startup probe parser、iOS runtime dart defines 等）
#: 承诺的 re-export 面，缺一个就是下游的 import 断裂。
REEXPORTED_NAMES = (
    "DEVICE_PROFILES",
    "ENVIRONMENTS",
    "REQUIRED_RUNTIME_FIELDS",
    "RUNTIME_CASES",
    "RUNTIME_TARGETS",
    "SHA256_PATTERN",
    "SPEC_REFS",
    "_case",
    "_case_counts",
    "_report_status",
    "_missing_spec_refs",
    "_validate_runtime_evidence",
    "_validate_readback_evidence",
    "_validate_observability_evidence",
    "cli",
    "main",
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_startup_environment_matrix", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StartupEnvironmentMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def required(self, status: str) -> dict[str, object]:
        return self.verifier._case(
            "case", kind="runtime", status=status, required=True
        )

    def test_stable_entrypoint_reexports_the_consumer_surface(self) -> None:
        for name in REEXPORTED_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(self.verifier, name))

    def test_optional_cases_do_not_enter_the_counts(self) -> None:
        counts = self.verifier._case_counts(
            [
                self.required("passed"),
                self.required("skipped"),
                self.required("failed"),
                self.verifier._case(
                    "optional", kind="runtime", status="failed", required=False
                ),
            ]
        )
        self.assertEqual(
            counts, {"required": 3, "executed": 2, "skipped": 1, "failed": 1}
        )

    def test_component_ready_counts_as_executed(self) -> None:
        counts = self.verifier._case_counts([self.required("component_ready")])
        self.assertEqual(counts["executed"], 1)

    def test_failed_required_case_fails_the_report(self) -> None:
        self.assertEqual(
            self.verifier._report_status(
                [self.required("passed"), self.required("failed")],
                release_gate=True,
            ),
            "failed",
        )

    def test_unexecuted_required_case_blocks_instead_of_passing(self) -> None:
        for status in ("gate_block", "missing", "skipped"):
            with self.subTest(status=status):
                self.assertEqual(
                    self.verifier._report_status(
                        [self.required(status)], release_gate=True
                    ),
                    "gate_block",
                )

    def test_release_gate_separates_passed_from_component_ready(self) -> None:
        cases = [self.required("passed")]
        self.assertEqual(
            self.verifier._report_status(cases, release_gate=True), "passed"
        )
        self.assertEqual(
            self.verifier._report_status(cases, release_gate=False),
            "component_ready",
        )

    def test_absent_or_malformed_spec_refs_report_every_required_ref(self) -> None:
        self.assertEqual(
            self.verifier._missing_spec_refs({}), list(self.verifier.SPEC_REFS)
        )
        self.assertEqual(
            self.verifier._missing_spec_refs({"specRefs": [1, 2]}),
            list(self.verifier.SPEC_REFS),
        )
        self.assertEqual(
            self.verifier._missing_spec_refs(
                {"specRefs": list(self.verifier.SPEC_REFS)}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
