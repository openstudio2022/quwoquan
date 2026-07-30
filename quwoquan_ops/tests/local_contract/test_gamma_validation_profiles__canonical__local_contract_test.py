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


ROOT = Path(__file__).resolve().parents[3]
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

    def test_story_requires_candidate_bound_gamma_receipt(self) -> None:
        source = GAMMA_SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn("main 正式阻断回执", source)
        self.assertIn("candidate digest 不一致时必须 `GATE_BLOCK`", source)
        self.assertIn("仓库不定义 hosted gamma 环境", source)
        self.assertNotIn(
            "gamma-local 通过仅证明提交前左移质量，不替代也不成为 main required check",
            source,
        )


if __name__ == "__main__":
    unittest.main()
