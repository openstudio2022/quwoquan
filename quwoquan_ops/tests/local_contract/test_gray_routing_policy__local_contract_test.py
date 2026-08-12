"""Production rollout policy and transport-only Caddy contracts."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "quwoquan_ops/environments/prod/rollout/routing_policy.yaml"
RENDER_PATH = ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
VERIFY_PATH = ROOT / "quwoquan_ops/environments/verify/verify_gray_routing_policy.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RolloutPolicyContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.verify = _load_module("verify_rollout_policy", VERIFY_PATH)
        self.render = _load_module("render_prod_plane_stack", RENDER_PATH)
        self.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["policy"]

    def test_repo_policy_passes_gate(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERIFY_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixed_platform_percentages_and_terminal_audience(self) -> None:
        self.assertEqual(
            [self.policy["stages"][stage]["basisPoints"] for stage in ("canary", "5", "20", "50", "100")],
            [0, 500, 2000, 5000, 10000],
        )
        terminal = self.policy["stages"]["100"]
        self.assertEqual(set(terminal["platforms"]["values"]), {"android", "ios", "web"})
        self.assertEqual(terminal["regions"]["mode"], "all")
        self.assertEqual(terminal["carriers"]["mode"], "all")
        self.assertEqual(terminal["appVersions"]["mode"], "supported")

    def test_shrinking_audience_fails_closed(self) -> None:
        policy = deepcopy(self.policy)
        policy["stages"]["5"]["platforms"]["values"] = ["android", "ios"]
        policy["stages"]["20"]["platforms"]["values"] = ["android"]
        failures = self.verify.validate_policy(policy)
        self.assertTrue(any("must not shrink" in failure for failure in failures), failures)

    def test_identity_and_subject_are_immutable_contract_fields(self) -> None:
        self.assertEqual(self.policy["subjectKind"], "device_actor")
        self.assertRegex(self.policy["candidateDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(self.policy["campaignId"])
        self.assertTrue(self.policy["allocationKeyId"])

    def test_caddy_renderer_emits_no_business_rollout_matchers(self) -> None:
        with patch.object(self.render, "_load_yaml", return_value={"policy": self.policy}):
            for stage in ("canary", "5", "20", "50", "100"):
                self.assertEqual(self.render._render_gray_routing_block(stage), "")

    def test_renderer_mounts_identical_policy_for_api_edge_and_portal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            self.render._write_config_tree(
                config_services=[],
                candidate_digest="sha256:" + "a" * 64,
                output_root=output_root,
            )
            runtime_policy = output_root / "runtime/config-root/rollout/routing_policy.yaml"
            portal_policy = output_root / "runtime/config-root/gray-routing/policy.yaml"
            self.assertEqual(runtime_policy.read_bytes(), POLICY_PATH.read_bytes())
            self.assertEqual(portal_policy.read_bytes(), POLICY_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
