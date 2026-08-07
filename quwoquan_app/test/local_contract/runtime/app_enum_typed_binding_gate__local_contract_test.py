#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002
"""The enum typed-binding ratchet must fail loudly instead of scanning nothing.

Negative cases come first, because a scanner that silently measures an empty
tree is the failure mode that lets contract enum drift back in:

1. a missing scan root must BLOCK rather than report zero violations;
2. scanning a real root that yields zero field declarations must BLOCK;
3. a newly introduced bare `String` enum field must BLOCK against the ratchet.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/codegen/verify_app_enum_typed_binding.py"
)
BASELINE_PATH = (
    REPO_ROOT / "quwoquan_ops/policies/gates/app_enum_typed_binding_baseline.yaml"
)


def load_verifier():
    module_name = "verify_app_enum_typed_binding_under_test"
    spec = importlib.util.spec_from_file_location(module_name, VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves annotations through `sys.modules[cls.__module__]`,
    # so the module has to be registered before it is executed.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CANONICAL_TYPES = textwrap.dedent(
    """
    enums:
      AssistantUsePolicy: [inherit, exclude]
      ContentType: [micro, article]
    """
).lstrip()

CONTRACT_FIELDS = textwrap.dedent(
    """
    fields:
      - name: assistantUsePolicy
        source: assistantUsePolicy
        type: enum
        enum_ref: AssistantUsePolicy
      - name: contentType
        source: contentType
        type: string
        enum_ref: ContentType
      - name: postId
        source: postId
        type: string
    """
).lstrip()

TYPED_DTO = textwrap.dedent(
    """
    final class ContentPostProjection {
      const ContentPostProjection();
      final String postId;
      final AssistantUsePolicy assistantUsePolicy;
      final ContentType contentType;
    }
    """
).lstrip()

DRIFTED_DTO = textwrap.dedent(
    """
    final class ContentPostProjection {
      const ContentPostProjection();
      final String postId;
      final String? assistantUsePolicy;
      final ContentType contentType;
    }
    """
).lstrip()


class AppEnumTypedBindingGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.root = Path(self.temp_directory.name)
        self.types_path = self.root / "types.yaml"
        self.contract_root = self.root / "contracts"
        self.generated_root = self.root / "generated"
        self.write(self.types_path, CANONICAL_TYPES)
        self.write(self.contract_root / "content" / "fields.yaml", CONTRACT_FIELDS)

    @staticmethod
    def write(path: Path, source: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def scan(self):
        return self.verifier.scan(
            self.root,
            types_path=self.types_path,
            contract_roots=(self.contract_root,),
            generated_root=self.generated_root,
        )

    # --- negative cases -------------------------------------------------

    def test_missing_generated_root_blocks_instead_of_reporting_zero(self) -> None:
        self.write(self.generated_root / "placeholder.txt", "not dart\n")
        absent = self.root / "does_not_exist"

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.scan(
                self.root,
                types_path=self.types_path,
                contract_roots=(self.contract_root,),
                generated_root=absent,
            )

        self.assertIn("does not exist", str(raised.exception))

    def test_missing_contract_root_blocks(self) -> None:
        self.write(self.generated_root / "dto.g.dart", TYPED_DTO)

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.scan(
                self.root,
                types_path=self.types_path,
                contract_roots=(self.root / "absent_contracts",),
                generated_root=self.generated_root,
            )

        self.assertIn("contract root does not exist", str(raised.exception))

    def test_missing_canonical_types_blocks(self) -> None:
        self.write(self.generated_root / "dto.g.dart", TYPED_DTO)

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.scan(
                self.root,
                types_path=self.root / "absent_types.yaml",
                contract_roots=(self.contract_root,),
                generated_root=self.generated_root,
            )

        self.assertIn("canonical enum source is missing", str(raised.exception))

    def test_zero_scanned_field_declarations_blocks(self) -> None:
        self.write(
            self.generated_root / "empty.g.dart",
            "// generated, no field declarations at all\n",
        )

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("scanned 0 field declarations", str(raised.exception))

    def test_newly_introduced_bare_string_enum_field_blocks(self) -> None:
        self.write(self.generated_root / "dto.g.dart", DRIFTED_DTO)
        result = self.scan()
        baseline = {"untyped_site_total": 0, "untyped_sites_by_field": {}}

        failures, reminders = self.verifier.evaluate(result, baseline)

        self.assertEqual(result.sites_by_field, {"assistantUsePolicy": 1})
        self.assertEqual(reminders, [])
        self.assertTrue(
            any("`assistantUsePolicy`" in failure for failure in failures),
            failures,
        )
        self.assertTrue(
            any("total grew: actual=1 baseline=0" in failure for failure in failures),
            failures,
        )

    def test_missing_baseline_file_blocks(self) -> None:
        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.load_baseline(self.root / "absent_baseline.yaml")

        self.assertIn("ratchet baseline is missing", str(raised.exception))

    def test_baseline_without_total_blocks(self) -> None:
        path = self.write(self.root / "baseline.yaml", "untyped_sites_by_field: {}\n")

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.load_baseline(path)

        self.assertIn("no `untyped_site_total`", str(raised.exception))

    def test_per_field_growth_blocks_even_when_total_sits_under_baseline(self) -> None:
        self.write(self.generated_root / "dto.g.dart", DRIFTED_DTO)
        result = self.scan()
        baseline = {
            "untyped_site_total": 9,
            "untyped_sites_by_field": {"contentType": 9},
        }

        failures, _ = self.verifier.evaluate(result, baseline)

        self.assertTrue(
            any("`assistantUsePolicy`" in failure for failure in failures),
            failures,
        )

    # --- positive cases -------------------------------------------------

    def test_typed_enum_declarations_are_not_reported(self) -> None:
        self.write(self.generated_root / "dto.g.dart", TYPED_DTO)
        result = self.scan()

        failures, reminders = self.verifier.evaluate(
            result, {"untyped_site_total": 0, "untyped_sites_by_field": {}}
        )

        self.assertEqual(result.untyped_sites, ())
        self.assertEqual(result.sites_by_field, {})
        self.assertEqual(failures, [])
        self.assertEqual(reminders, [])
        self.assertGreater(result.scanned_declarations, 0)

    def test_enum_bound_fields_keep_every_canonical_binding(self) -> None:
        self.write(self.generated_root / "dto.g.dart", TYPED_DTO)
        result = self.scan()

        self.assertEqual(
            result.enum_bound_fields,
            {
                "assistantUsePolicy": ("AssistantUsePolicy",),
                "contentType": ("ContentType",),
            },
        )
        self.assertNotIn("postId", result.enum_bound_fields)

    def test_shrinking_below_baseline_reminds_instead_of_blocking(self) -> None:
        self.write(self.generated_root / "dto.g.dart", TYPED_DTO)
        result = self.scan()
        baseline = {
            "untyped_site_total": 3,
            "untyped_sites_by_field": {"assistantUsePolicy": 3},
        }

        failures, reminders = self.verifier.evaluate(result, baseline)

        self.assertEqual(failures, [])
        self.assertTrue(any("ratchet can tighten" in item for item in reminders))
        self.assertTrue(any("stale baseline entry" in item for item in reminders))

    def test_committed_baseline_matches_the_live_repository_measurement(self) -> None:
        result = self.verifier.scan(REPO_ROOT)
        baseline = self.verifier.load_baseline(BASELINE_PATH)

        failures, _ = self.verifier.evaluate(result, baseline)

        self.assertEqual(failures, [])
        self.assertEqual(
            len(result.untyped_sites),
            int(baseline["untyped_site_total"]),
        )


if __name__ == "__main__":
    unittest.main()
