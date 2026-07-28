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

    def test_app_user_acceptance_local_injection_is_rejected(self) -> None:
        gate = _load_gate()
        samples = (
            "ProviderScope(overrides: [])",
            "profileQueryProvider.overrideWithValue(query)",
            "await tester.pumpWidget(app)",
            "final query = FakeLocationQueryAdapter()",
            "import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';",
            "buildAlphaCloudOverrides()",
            "providerScopeOverrides: businessOverrides",
            "import '../cloud_services/repository_mock_reexports.dart';",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    any(
                        pattern.search(sample)
                        for pattern in gate.APP_USER_ACCEPTANCE_FAKE_PATTERNS
                    ),
                    sample,
                )

    def test_local_contract_object_typed_double_is_allowed_by_layer(self) -> None:
        gate = _load_gate()
        local_contract = Path(
            "quwoquan_app/test/local_contract/user/profile_query__local_contract_test.dart"
        )
        user_acceptance = Path(
            "quwoquan_app/test/user_acceptance/user/profile_query__user_acceptance_test.dart"
        )

        self.assertFalse(gate.is_app_user_acceptance_source(local_contract))
        self.assertTrue(gate.is_app_user_acceptance_source(user_acceptance))

    def test_app_user_acceptance_evidence_checklist_is_rejected(self) -> None:
        gate = _load_gate()
        samples = (
            "test('page coverage evidence is declared', () {})",
            "const sourceEvidence = <String>[];",
            "const requiredCaseIds = <String>[];",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    any(
                        pattern.search(sample)
                        for pattern in gate.APP_USER_ACCEPTANCE_FAKE_PATTERNS
                    ),
                    sample,
                )


if __name__ == "__main__":
    unittest.main()
