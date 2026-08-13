#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002.t2
"""The enum typed-binding gate must fail loudly instead of scanning nothing.

Negative cases come first, because a scanner that silently measures an empty
tree is the failure mode that lets contract enum drift back in:

1. a missing binding report must BLOCK rather than report zero violations;
2. a report with no bindings must BLOCK;
3. a report that stopped covering a renderer must BLOCK, so a renderer which
   quietly drops its bindings cannot turn the gate green;
4. any bare `String` enum field must BLOCK, with no budget to hide behind.

The report is produced by tools/codegen_app_metadata, which is the only place
that knows which contract declaration produced which Dart field. Matching
generated field names against contract `enum_ref` values cannot do this: a name
like `status` binds a different canonical enum in every object that declares
it.

The gate carries no baseline. It once did, under a field-name measure that
reported 215 sites of which only 9 were real; with the precise measure those
nine were paid off, so the budget was retired along with the baseline file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/codegen/verify_app_enum_typed_binding.py"
)
RETIRED_BASELINE_PATH = (
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


def binding(
    *,
    dart_class: str,
    dart_field: str,
    dart_type: str,
    enum_ref: str,
    typed: bool,
    generated_path: str = "packages/quwoquan_cloud_contracts/lib/src/x.g.dart",
    contract_type: str = "enum",
    client_dart_type: str = "",
) -> dict[str, object]:
    return {
        "generatedPath": generated_path,
        "dartClass": dart_class,
        "dartField": dart_field,
        "dartType": dart_type,
        "enumRef": enum_ref,
        "contractType": contract_type,
        "contractSource": "content/content/post/fields.yaml",
        "clientDartType": client_dart_type,
        "typed": typed,
    }


def coverage_bindings(verifier) -> list[dict[str, object]]:
    """One typed binding per required renderer, so coverage checks pass."""

    return [
        binding(
            dart_class="Covered",
            dart_field="visibility",
            dart_type="Visibility",
            enum_ref="Visibility",
            typed=True,
            generated_path=path,
        )
        for path in verifier.REQUIRED_COVERAGE
    ]


class AppEnumTypedBindingGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.root = Path(self.temp_directory.name)
        self.report_path = self.root / "field_binding_report.json"

    def write_report(self, bindings: list[dict[str, object]]) -> Path:
        self.report_path.write_text(
            json.dumps(
                {
                    "generator": "app-only-emitter",
                    "contractGraphSha256": "0" * 64,
                    "bindings": bindings,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return self.report_path

    def scan(self):
        return self.verifier.scan(self.root, report_path=self.report_path)

    # --- negative cases -------------------------------------------------

    def test_missing_report_blocks_instead_of_reporting_zero(self) -> None:
        with self.assertRaises(self.verifier.ScanError) as raised:
            self.verifier.scan(self.root, report_path=self.root / "absent.json")

        self.assertIn("field binding report is missing", str(raised.exception))

    def test_malformed_report_blocks(self) -> None:
        self.report_path.write_text("{not json", encoding="utf-8")

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("malformed", str(raised.exception))

    def test_report_without_bindings_blocks(self) -> None:
        self.write_report([])

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("declares no bindings", str(raised.exception))

    def test_report_that_lost_a_renderer_blocks(self) -> None:
        bindings = coverage_bindings(self.verifier)[:-1]
        self.write_report(bindings)

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("no longer covers", str(raised.exception))

    def test_binding_without_enum_ref_blocks(self) -> None:
        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="Post",
                dart_field="postId",
                dart_type="String",
                enum_ref="",
                typed=False,
            )
        )
        self.write_report(bindings)

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("no enumRef", str(raised.exception))

    def test_binding_without_generated_path_blocks(self) -> None:
        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="Post",
                dart_field="visibility",
                dart_type="Visibility",
                enum_ref="Visibility",
                typed=True,
                generated_path="",
            )
        )
        self.write_report(bindings)

        with self.assertRaises(self.verifier.ScanError) as raised:
            self.scan()

        self.assertIn("no generatedPath", str(raised.exception))

    def test_newly_introduced_bare_string_enum_field_blocks(self) -> None:
        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="ContentPostProjection",
                dart_field="assistantUsePolicy",
                dart_type="String?",
                enum_ref="AssistantUsePolicy",
                typed=False,
            )
        )
        self.write_report(bindings)
        result = self.scan()

        failures = self.verifier.evaluate(result)

        self.assertEqual(
            result.sites_by_key,
            {"ContentPostProjection.assistantUsePolicy": 1},
        )
        self.assertTrue(
            any(
                "`ContentPostProjection.assistantUsePolicy`" in failure
                for failure in failures
            ),
            failures,
        )

    def test_a_single_untyped_binding_blocks_without_any_budget(self) -> None:
        """No baseline means the first regression blocks, not the Nth."""

        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="Post",
                dart_field="visibility",
                dart_type="List<String>",
                enum_ref="Visibility",
                typed=False,
            )
        )
        self.write_report(bindings)

        failures = self.verifier.evaluate(self.scan())

        self.assertTrue(failures, "one untyped binding must be enough to block")

    def test_the_retired_baseline_file_stays_deleted(self) -> None:
        """The gate reached zero, so reintroducing a budget is a regression."""

        self.assertFalse(
            RETIRED_BASELINE_PATH.exists(),
            f"{RETIRED_BASELINE_PATH} was retired when the debt reached zero; "
            "a new untyped binding must be fixed, not budgeted",
        )
        self.assertFalse(
            hasattr(self.verifier, "load_baseline"),
            "the gate must not regain a baseline reader",
        )

    # --- positive cases -------------------------------------------------

    def test_typed_enum_declarations_are_not_reported(self) -> None:
        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="ContentPostProjection",
                dart_field="assistantUsePolicy",
                dart_type="AssistantUsePolicy?",
                enum_ref="AssistantUsePolicy",
                typed=True,
            )
        )
        self.write_report(bindings)
        result = self.scan()

        failures = self.verifier.evaluate(result)

        self.assertEqual(result.untyped_sites, ())
        self.assertEqual(result.sites_by_key, {})
        self.assertEqual(failures, [])
        self.assertGreater(result.typed_bindings, 0)

    def test_same_field_name_in_unrelated_classes_is_not_conflated(self) -> None:
        """The regression the field-name heuristic could not express.

        `RuntimeFailureWire.kind` is a free-form string by contract while
        `CircleFeedItemView.kind` binds CircleKind. Only the latter is debt.
        """

        bindings = coverage_bindings(self.verifier)
        bindings.append(
            binding(
                dart_class="CircleFeedItemView",
                dart_field="kind",
                dart_type="String",
                enum_ref="CircleKind",
                typed=False,
            )
        )
        self.write_report(bindings)
        result = self.scan()

        self.assertEqual(result.sites_by_key, {"CircleFeedItemView.kind": 1})

    def test_the_live_repository_has_no_untyped_enum_binding(self) -> None:
        result = self.verifier.scan(REPO_ROOT)

        self.assertEqual(
            self.verifier.evaluate(result),
            [],
            "every contract enum_ref must reach the App as its enum",
        )
        self.assertEqual(result.untyped_sites, ())
        self.assertEqual(result.total_bindings, result.typed_bindings)


if __name__ == "__main__":
    unittest.main()
