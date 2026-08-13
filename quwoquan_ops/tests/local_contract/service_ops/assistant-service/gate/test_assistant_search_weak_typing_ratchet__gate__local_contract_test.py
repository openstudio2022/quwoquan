#!/usr/bin/env python3
# spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#open-003
"""The assistant weak-typing ratchet must measure disjoint debt units.

Two prior measures were retired. The original counted raw text occurrences
with two independent regexes, so every `Map<String, dynamic>` incremented both
`map_string_dynamic` and `dynamic_keyword`; of the recorded 209/373 baseline,
209 were double counted. Its replacement kept `Map<String, Object?>` as an
informational metric, which left a laundering channel open: a mechanical
dynamic-to-Object? rewrite moved debt out of the ratchet while every anonymous
Map survived.

These cases pin the current measure: three disjoint buckets, `Object?` Maps
locked by their own bucket so rewriting `dynamic` cannot lower the total, and
comments never move the ratchet.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
GATE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service"
    / "gate/verify_assistant_search_weak_typing_ratchet.py"
)


def load_gate():
    module_name = "verify_assistant_search_weak_typing_ratchet_under_test"
    spec = importlib.util.spec_from_file_location(module_name, GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class AssistantWeakTypingRatchetMeasureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = load_gate()

    def counts(self, source: str):
        return self.gate.count_text(source)

    def test_map_and_bare_dynamic_never_count_the_same_token(self) -> None:
        counts = self.counts("final Map<String, dynamic> payload;")

        self.assertEqual(counts.map_string_dynamic, 1)
        self.assertEqual(
            counts.bare_dynamic,
            0,
            "the dynamic inside Map<String, dynamic> already counted as a Map site",
        )

    def test_standalone_dynamic_counts_once(self) -> None:
        counts = self.counts("dynamic decode(dynamic value) => value;")

        self.assertEqual(counts.map_string_dynamic, 0)
        self.assertEqual(counts.bare_dynamic, 2)

    def test_mixed_source_splits_between_the_buckets(self) -> None:
        counts = self.counts(
            "Map<String, dynamic> toJson();\n"
            "dynamic raw;\n"
            "final Map<String, dynamic> extra;\n"
            "final Map<String, Object?> attributes;\n"
        )

        self.assertEqual(counts.map_string_dynamic, 2)
        self.assertEqual(counts.map_string_object_optional, 1)
        self.assertEqual(counts.bare_dynamic, 1)

    def test_comments_do_not_move_the_ratchet(self) -> None:
        counts = self.counts(
            "// returns a Map<String, dynamic> and a dynamic value\n"
            "/* Map<String, dynamic> dynamic Map<String, Object?> */\n"
            "final int answer = 42;\n"
        )

        self.assertEqual(counts.map_string_dynamic, 0)
        self.assertEqual(counts.map_string_object_optional, 0)
        self.assertEqual(counts.bare_dynamic, 0)

    def test_object_optional_rewrite_cannot_launder_debt(self) -> None:
        """A dynamic-to-Object? rewrite must not lower the summed debt.

        `Object?` values are still an anonymous, schema-less Map behind string
        keys. When this bucket was informational, rewriting `dynamic` to
        `Object?` made the ratchet read lower while removing nothing.
        """

        before = self.counts("final Map<String, dynamic> payload;")
        after = self.counts("final Map<String, Object?> payload;")

        debt_before = (
            before.map_string_dynamic
            + before.map_string_object_optional
            + before.bare_dynamic
        )
        debt_after = (
            after.map_string_dynamic
            + after.map_string_object_optional
            + after.bare_dynamic
        )
        self.assertEqual(debt_before, debt_after)
        self.assertEqual(after.map_string_object_optional, 1)

    def test_object_optional_growth_is_a_regression(self) -> None:
        baseline = {
            "assistant_handwritten": {
                "map_string_dynamic": 5,
                "map_string_object_optional": 2,
                "bare_dynamic": 3,
            }
        }
        current = {
            "assistant_handwritten": {
                "map_string_dynamic": 4,
                "map_string_object_optional": 3,
                "bare_dynamic": 3,
            }
        }

        messages = self.gate.regressions(baseline, current)

        self.assertTrue(
            any(
                "map_string_object_optional" in message and "regression" in message
                for message in messages
            ),
            messages,
        )

    def test_committed_baseline_matches_the_live_measurement(self) -> None:
        baseline = self.gate.load_baseline(self.gate.DEFAULT_BASELINE)
        self.assertIsNotNone(
            baseline, "baseline must exist and declare all three metrics"
        )

        current = self.gate.current_snapshot()

        self.assertEqual(
            self.gate.regressions(baseline, current),
            [],
            "committed baseline drifted from the measured tree",
        )

    def test_search_repository_bucket_is_clean(self) -> None:
        counts = self.gate.scan_search_repository()

        self.assertEqual(counts.map_string_dynamic, 0)
        self.assertEqual(counts.map_string_object_optional, 0)
        self.assertEqual(counts.bare_dynamic, 0)


if __name__ == "__main__":
    unittest.main()
