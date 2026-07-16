from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_ops" / "gate" / "scaffold" / "verify_test_no_fake.py"


def _load_gate():
    script_dir = str(SCRIPT.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("verify_test_no_fake", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoFakeGateContractTest(unittest.TestCase):
    def test_api_integration_fake_dependencies_are_rejected(self) -> None:
        gate = _load_gate()
        samples = (
            'import "github.com/alicebob/miniredis/v2"',
            'redis := miniredis.RunT(t)',
            'router := SceneConfig{Mode: "memory"}',
            "client := NewMockProviderClient()",
            "publisher := NoopPublisher()",
            "gate := groupCreationStubRelationshipGate{}",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    any(
                        pattern.search(sample)
                        for pattern in gate.FAKE_INTEGRATION_DEPENDENCY_PATTERNS
                    ),
                    sample,
                )

    def test_business_memory_object_name_is_not_misclassified(self) -> None:
        gate = _load_gate()
        sample = "view := AssistantUserMemoryView{}"
        self.assertFalse(
            any(
                pattern.search(sample)
                for pattern in gate.FAKE_INTEGRATION_DEPENDENCY_PATTERNS
            )
        )

    def test_api_integration_test_double_filename_is_rejected(self) -> None:
        gate = _load_gate()
        self.assertIsNotNone(
            gate.FAKE_INTEGRATION_FILENAME_RE.search(
                "conversation_gateway_test_double.go"
            )
        )
        self.assertIsNone(
            gate.FAKE_INTEGRATION_FILENAME_RE.search("media_oss_spy.go")
        )


if __name__ == "__main__":
    unittest.main()
