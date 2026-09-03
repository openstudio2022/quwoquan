"""Exact semantic-fingerprint ratchet contract tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.single_track_contracts import report
from quwoquan_ops.gate.single_track_contracts.baseline import (
    BASELINE_PATH,
    BASELINE_REVISION,
    BASELINE_SCHEMA,
    FINGERPRINT_ALGORITHM,
    GOVERNANCE,
    BaselineError,
    Fingerprint,
    baseline_document,
    compare_inventory,
    load_baseline,
)
from quwoquan_ops.gate.single_track_contracts.scanner import Finding, Inventory


def _inventory(*findings: Finding) -> Inventory:
    inventory = Inventory()
    inventory.findings.extend(findings)
    for finding in findings:
        inventory.counts[finding.category] += 1
    return inventory


def _write_baseline(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


class SingleTrackFingerprintRatchetContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.baseline = self.root / "baseline.json"
        self.existing = Finding(
            "T1_example",
            "quwoquan_app/lib/example.dart",
            "L12: retiredIdentity",
        )
        self.fingerprint = Fingerprint(
            self.existing.category,
            self.existing.path,
            "retiredIdentity",
        )

    def write_counts(self, counts: Counter[Fingerprint]) -> None:
        _write_baseline(
            self.baseline,
            baseline_document(counts, baseline_revision="b227730d2a43eefe3a676e9cec0473e4b7537869"),
        )

    def test_canonical_baseline_metadata_is_versioned(self) -> None:
        self.assertEqual(BASELINE_SCHEMA, "single-track-exact-fingerprint-baseline")
        self.assertEqual(BASELINE_REVISION, "b227730d2a43eefe3a676e9cec0473e4b7537869")
        self.assertIn("category", FINGERPRINT_ALGORITHM)
        self.assertTrue(str(BASELINE_PATH).endswith("policies/baselines/single_track_contracts_fingerprint_baseline.json"))
        self.assertIn("semantic-detail", GOVERNANCE["measure"])

    def test_exact_semantic_multiset_passes(self) -> None:
        self.write_counts(Counter({self.fingerprint: 1}))
        result = compare_inventory(_inventory(self.existing), load_baseline(self.baseline))
        self.assertTrue(result.passed)
        self.assertEqual(result.reductions, 0)
        self.assertEqual(result.current_count, 1)

    def test_new_semantic_fingerprint_blocks(self) -> None:
        self.write_counts(Counter({self.fingerprint: 1}))
        added = Finding(
            "T1_example",
            "quwoquan_app/lib/example.dart",
            "L20: anotherRetiredIdentity",
        )
        result = compare_inventory(
            _inventory(self.existing, added),
            load_baseline(self.baseline),
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.additions[0][1:], (0, 1))

    def test_existing_fingerprint_count_increase_blocks(self) -> None:
        self.write_counts(Counter({self.fingerprint: 1}))
        result = compare_inventory(
            _inventory(self.existing, self.existing),
            load_baseline(self.baseline),
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.additions[0][1:], (1, 2))

    def test_reduction_and_zero_findings_pass(self) -> None:
        self.write_counts(Counter({self.fingerprint: 2}))
        baseline = load_baseline(self.baseline)
        reduced = compare_inventory(_inventory(self.existing), baseline)
        empty = compare_inventory(_inventory(), baseline)
        self.assertTrue(reduced.passed)
        self.assertEqual(reduced.reductions, 1)
        self.assertTrue(empty.passed)
        self.assertEqual(empty.reductions, 2)
        self.assertEqual(empty.removed_identities, 1)

    def test_line_number_only_movement_is_the_same_fingerprint(self) -> None:
        self.write_counts(Counter({self.fingerprint: 1}))
        moved = Finding(
            self.existing.category,
            self.existing.path,
            "L9876: retiredIdentity",
        )
        result = compare_inventory(_inventory(moved), load_baseline(self.baseline))
        self.assertTrue(result.passed)
        self.assertEqual(result.reductions, 0)

    def test_malformed_json_fails_closed(self) -> None:
        self.baseline.write_text("{not-json", encoding="utf-8")
        with self.assertRaisesRegex(BaselineError, "无法读取 baseline"):
            load_baseline(self.baseline)

    def test_stale_algorithm_fails_closed(self) -> None:
        document = baseline_document(
            Counter({self.fingerprint: 1}),
            baseline_revision=BASELINE_REVISION,
        )
        document["fingerprintAlgorithm"] = "line-number-v0"
        _write_baseline(self.baseline, document)
        with self.assertRaisesRegex(BaselineError, "已过期|stale"):
            load_baseline(self.baseline)

    def test_tampered_fingerprint_fails_closed(self) -> None:
        document = baseline_document(
            Counter({self.fingerprint: 1}),
            baseline_revision=BASELINE_REVISION,
        )
        document["findings"][0]["fingerprint"] = "sha256:" + "0" * 64
        _write_baseline(self.baseline, document)
        with self.assertRaisesRegex(BaselineError, "stale"):
            load_baseline(self.baseline)

    def test_duplicate_entry_fails_closed(self) -> None:
        document = baseline_document(
            Counter({self.fingerprint: 1}),
            baseline_revision=BASELINE_REVISION,
        )
        document["findings"].append(dict(document["findings"][0]))
        _write_baseline(self.baseline, document)
        with self.assertRaisesRegex(BaselineError, "重复 fingerprint"):
            load_baseline(self.baseline)

    def test_cli_passes_zero_findings_without_writing_baseline(self) -> None:
        self.write_counts(Counter({self.fingerprint: 1}))
        before = self.baseline.read_bytes()
        inventory_path = self.root / "inventory.md"
        with (
            mock.patch.object(report, "DEFAULT_BASELINE", self.baseline),
            mock.patch.object(report, "_scan", return_value=_inventory()),
        ):
            exit_code = report.main(
                ["--root", str(_REPO_ROOT), "--baseline", str(self.baseline), "--inventory-out", str(inventory_path)]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(self.baseline.read_bytes(), before)
        self.assertTrue(inventory_path.is_file())

    def test_cli_invalid_baseline_fails_closed(self) -> None:
        self.baseline.write_text("{}\n", encoding="utf-8")
        with (
            mock.patch.object(report, "DEFAULT_BASELINE", self.baseline),
            mock.patch.object(report, "_scan", return_value=_inventory()),
        ):
            exit_code = report.main(
                ["--root", str(_REPO_ROOT), "--baseline", str(self.baseline), "--inventory-out", str(self.root / "inventory.md")]
            )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
