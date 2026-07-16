from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service"
    / "scripts"
    / "verify"
    / "verify_service_layering.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_service_layering", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceLayeringContractTest(unittest.TestCase):
    def test_service_layering_has_no_reverse_dependencies(self) -> None:
        issues = _load_gate().collect_issues()
        self.assertEqual([], issues, "\n".join(issues))


if __name__ == "__main__":
    unittest.main()
