from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
POLICY = ROOT / "quwoquan_ops/policies/cloud_contract_ownership.json"
GENERATOR = ROOT / "quwoquan_service/tools/codegen_app_metadata"


def go_string_list(source: str, variable: str) -> set[str]:
    match = re.search(
        rf"var {re.escape(variable)} = \[\]string\{{(?P<body>.*?)\n\}}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing Go string list {variable}")
    return set(re.findall(r'"([^"\n]+)"', match.group("body")))


class IntersectionGeneratedOwnershipContractTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
    def test_layered_targets_are_owned_while_legacy_is_retired(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        resource = next(
            item
            for item in policy["resources"]
            if item["id"] == "app-generated-output"
        )
        write_paths = set(resource["writePaths"])
        application_root = (
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/application/generated/**"
        )
        presentation_root = (
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/**"
        )
        package_root = (
            "quwoquan_app/packages/quwoquan_cloud_contracts/"
            "lib/src/generated/**"
        )
        canonical_display = (
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/"
            "intersection_display_metadata.g.dart"
        )
        retired_legacy = (
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/generated/"
            "intersection_kind_metadata.g.dart"
        )
        for path in {
            application_root,
            presentation_root,
            package_root,
            canonical_display,
        }:
            self.assertIn(path, write_paths)

        manifest_source = (
            GENERATOR / "generated_manifest.go"
        ).read_text(encoding="utf-8")
        active_roots = go_string_list(
            manifest_source,
            "appGeneratedOutputRoots",
        )
        active_exact = go_string_list(
            manifest_source,
            "appGeneratedExactOutputs",
        )
        retired_exact = go_string_list(
            manifest_source,
            "appRetiredGeneratedExactOutputs",
        )
        self.assertIn(application_root.removeprefix("quwoquan_app/").removesuffix("/**"), active_roots)
        self.assertIn(presentation_root.removeprefix("quwoquan_app/").removesuffix("/**"), active_roots)
        self.assertIn(package_root.removeprefix("quwoquan_app/").removesuffix("/**"), active_roots)
        self.assertIn(canonical_display, write_paths)
        self.assertNotIn(
            "quwoquan_app/lib/cloud/runtime/generated/recommendation/"
            "intersection_kind_metadata.g.dart",
            write_paths,
        )
        retired_runtime_legacy = (
            "lib/cloud/runtime/generated/recommendation/"
            "intersection_kind_metadata.g.dart"
        )
        self.assertIn(retired_runtime_legacy, retired_exact)
        self.assertNotIn(retired_runtime_legacy, active_exact)
        self.assertIn(
            retired_legacy.removeprefix("quwoquan_app/"),
            retired_exact,
            msg="same-object legacy output must be retired after consumer cutover",
        )

    # spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
    def test_feedback_and_layered_writers_have_independent_lifecycles(self) -> None:
        main_source = (GENERATOR / "main.go").read_text(encoding="utf-8")
        for call in (
            "writeIntersectionFeedbackContracts(",
            "writeCanonicalIntersectionMetadata(",
        ):
            self.assertEqual(main_source.count(call), 1)
        self.assertNotIn("writeLegacyIntersectionKindMetadata(", main_source)
        self.assertNotIn("writeIntersectionKindMetadata(", main_source)
        canonical_source = (
            GENERATOR / "intersection_kind_metadata_codegen.go"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            '"intersection_kind_metadata.g.dart"',
            canonical_source,
        )


if __name__ == "__main__":
    unittest.main()
