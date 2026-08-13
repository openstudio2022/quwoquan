from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = ROOT / "quwoquan_ops/gate/verify_canonical_recommendation_policy.py"
SPEC_REF = (
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/"
    "local-gamma-mirror/spec.md#GWT-001"
)


def load_gate():
    spec = importlib.util.spec_from_file_location("canonical_recommendation_policy_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_gate()


class CanonicalRecommendationPolicyTest(unittest.TestCase):
    def write_fixture(self, root: Path, policy_text: str) -> tuple[Path, Path]:
        policy_path = root / gate.POLICY_RELATIVE_PATH
        release_path = root / gate.GAMMA_RELEASE_RELATIVE_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        release_path.parent.mkdir(parents=True, exist_ok=True)
        prod_renderer_path = root / gate.PROD_RENDERER_RELATIVE_PATH
        prod_renderer_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(policy_text, encoding="utf-8")
        release_path.write_text(
            "\n".join(
                (
                    f"releaseRef: {gate.CANONICAL_RELEASE_REF}",
                    f"digest: {gate.sha256_file(policy_path)}",
                    "target: runtime/recommendation_policy.yaml",
                    "environmentVariable: QWQ_REC_POLICY_PATH",
                    "",
                )
            ),
            encoding="utf-8",
        )
        prod_renderer_path.write_text(
            'POLICY = "recommendation_policy.yaml"\n',
            encoding="utf-8",
        )
        return policy_path, release_path

    def test_accepts_one_digest_bound_canonical_policy(self) -> None:
        self.assertTrue(SPEC_REF.endswith("#GWT-001"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_fixture(root, "objectCards:\n  enabled: true\n")
            self.assertEqual(gate.validation_issues(root), [])

    def test_rejects_policy_variant_and_manual_version_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy_path, _ = self.write_fixture(
                root,
                "policyVersion: release-one\nobjectCards:\n  enabled: true\n",
            )
            (policy_path.parent / "recommendation_policy_gamma.yaml").write_text(
                "objectCards:\n  enabled: true\n",
                encoding="utf-8",
            )
            issues = gate.validation_issues(root)
            self.assertTrue(any("variants are forbidden" in issue for issue in issues))
            self.assertTrue(any("policyVersion" in issue for issue in issues))

    def test_rejects_release_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, release_path = self.write_fixture(
                root,
                "objectCards:\n  enabled: true\n",
            )
            release_path.write_text(
                release_path.read_text(encoding="utf-8").replace(
                    gate.sha256_file(root / gate.POLICY_RELATIVE_PATH),
                    "sha256:" + "0" * 64,
                ),
                encoding="utf-8",
            )
            issues = gate.validation_issues(root)
            self.assertTrue(any("digest mismatch" in issue for issue in issues))

    def test_rejects_prod_renderer_policy_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_fixture(root, "objectCards:\n  enabled: true\n")
            (root / gate.PROD_RENDERER_RELATIVE_PATH).write_text(
                'POLICY = "recommendation_policy_object_cards_v1.yaml"\n',
                encoding="utf-8",
            )
            issues = gate.validation_issues(root)
            self.assertTrue(
                any("prod renderer recommendation policy variants" in issue for issue in issues)
            )


if __name__ == "__main__":
    unittest.main()
