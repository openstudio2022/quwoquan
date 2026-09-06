"""Gamma-local validation registry and blocking receipt contract."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    ROOT / "quwoquan_ops/cli/gamma/verify_gamma_validation_profiles.py"
)
REGISTRY_PATH = (
    ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
)
GAMMA_SPEC_PATH = (
    ROOT
    / "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/"
    "local-gamma-mirror/spec.md"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_gamma_validation_profiles",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GammaValidationProfilesCanonicalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_repository_registry_matches_the_only_canonical_shape(self) -> None:
        self.assertEqual(
            self.verifier.verify_canonical_structure(self.registry), []
        )

    def test_assistant_scenario_uses_the_real_remote_api_integration(self) -> None:
        scenario = self.registry["smokeCases"][
            "assistant_alpha_beta_ui_simulator"
        ]
        expected_path = (
            "quwoquan_app/test/api_integration/service/assistant_service/assistant/"
            "assistant_run/assistant_scenario_simulator__api_integration_test.dart"
        )

        self.assertEqual(scenario["path"], expected_path)
        self.assertEqual(scenario["runner"], "flutter_test")
        source = (ROOT / expected_path).read_text(encoding="utf-8")
        self.assertIn("AssistantRunRemoteApiHarness.fromEnvironment", source)
        self.assertIn("harness.execute", source)
        for forbidden in (
            "ProviderScope",
            "testWidgets(",
            "Mock",
            "Fake",
            "overrideWith",
        ):
            self.assertNotIn(forbidden, source)

    def test_numbered_top_level_envelope_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.registry)
        candidate["version"] = 5

        self.assertIn(
            "registry: unexpected fields: version",
            self.verifier.verify_canonical_structure(candidate),
        )

    def test_cli_fails_closed_for_numbered_top_level_envelope(self) -> None:
        candidate = copy.deepcopy(self.registry)
        candidate["version"] = 5
        output = io.StringIO()
        original_path = self.verifier.SUITES_PATH
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "validation_suites.json"
            fixture.write_text(
                json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
            )
            self.verifier.SUITES_PATH = fixture
            try:
                with contextlib.redirect_stdout(output):
                    result = self.verifier.main()
            finally:
                self.verifier.SUITES_PATH = original_path

        self.assertEqual(result, 1)
        self.assertIn("unexpected fields: version", output.getvalue())

    def test_alternate_profile_key_is_rejected_without_fallback(self) -> None:
        candidate = copy.deepcopy(self.registry)
        candidate["validationProfiles"] = candidate.pop("profiles")

        errors = self.verifier.verify_canonical_structure(candidate)
        self.assertIn("registry: missing fields: profiles", errors)
        self.assertIn(
            "registry: unexpected fields: validationProfiles", errors
        )

    def test_success_output_has_no_registry_revision_marker(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.verifier.main()

        self.assertEqual(result, 0)
        self.assertIn("OK: gamma validation suites", output.getvalue())
        self.assertNotIn("validation_suites.json v", output.getvalue())

    def test_story_requires_current_candidate_and_tree_bound_gamma_receipt(self) -> None:
        source = GAMMA_SPEC_PATH.read_text(encoding="utf-8")
        req_start = source.index("### REQ-001")
        req_end = source.index('<a id="req-002">', req_start)
        requirement = source[req_start:req_end]
        blocking_lines = [
            line for line in requirement.splitlines() if "`GATE_BLOCK`" in line
        ]

        for semantic_anchor in (
            "exact dev head",
            "current exact head",
            "IntegrationQualificationFact",
            "main promotion",
        ):
            self.assertIn(semantic_anchor, requirement)
        self.assertTrue(
            any(
                all(
                    semantic_anchor in line
                    for semantic_anchor in (
                        "current dev head",
                        "candidate/tree/predecessor",
                        "`GATE_BLOCK`",
                    )
                )
                for line in blocking_lines
            ),
            "current dev head、candidate/tree/predecessor mismatch 必须同轨 GATE_BLOCK",
        )
        self.assertIn("仓库不定义 hosted gamma 环境", source)


if __name__ == "__main__":
    unittest.main()
