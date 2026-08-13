from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_behavior_event_type_contract.py"
SPEC = importlib.util.spec_from_file_location("behavior_event_type_contract", VERIFIER_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


class BehaviorEventTypeContractTest(unittest.TestCase):
    def test_repository_contract_is_exactly_aligned(self) -> None:
        failures = verifier.validate(
            shared_values=verifier.load_shared_values(verifier.TYPES_PATH),
            content_values=verifier.load_content_event_values(verifier.BEHAVIORS_PATH),
            dart_values=verifier.load_dart_values(verifier.DART_PATH),
            go_values=verifier.load_go_values(verifier.GO_PATH),
        )

        self.assertEqual(failures, [])

    def test_missing_typed_consumer_value_fails_closed(self) -> None:
        failures = verifier.validate(
            shared_values=("impression", "effective_play"),
            content_values=("effective_play",),
            dart_values=("impression",),
            go_values=("impression", "effective_play"),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("Dart BehaviorEventType drift", failures[0])


if __name__ == "__main__":
    unittest.main()
