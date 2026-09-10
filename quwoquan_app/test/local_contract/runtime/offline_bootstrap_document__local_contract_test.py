"""spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
sys.path[:0] = [str(ROOT), str(APP / "scripts/env"), str(APP / "scripts/device"), str(APP / "test/support/runtime/launcher")]
from launcher_package_fixture import _issue_test_signing_material
from print_app_env_dart_defines import (
    build_offline_bootstrap_document,
    build_runtime_config_package,
    test_live_runtime_values as load_test_live_runtime_values,
)
import build_launcher_handoff as launcher
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope, load_launch_manifest_contract,
    validate_runtime_config_package, build_runtime_config_activation_request,
    validate_runtime_config_activation_request, validate_handoff_against_metadata,
    runtime_config_payload_digest,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import canonical_signed_payload, sign_payload


class OfflineBootstrapContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qwq-offline-contract-")
        self.addCleanup(self.temp.cleanup)
        self.signing = _issue_test_signing_material(Path(self.temp.name))
        self.trust = build_runtime_config_trust_envelope("nonprod", json.loads(self.signing.trusted_public_keys_path.read_text()))
        self.document = build_offline_bootstrap_document(
            environment="alpha", target="alpha-local", launch_policy="test_live",
            source_git_sha="a" * 40, source_tree_digest="sha256:" + "b" * 64, signing=self.signing,
        )

    def resign(self, document):
        document["payloadDigest"] = runtime_config_payload_digest(document)
        document["signature"] = base64.b64encode(sign_payload(
            self.signing.private_key_path.read_bytes(), canonical_signed_payload(document),
        )).decode("ascii")

    def test_offline_signature_survives_next_day_without_endpoints(self):
        self.assertNotIn("expiresAt", self.document)
        self.assertNotIn("issuedAt", self.document)
        self.assertEqual(self.document["runtime"], {"appRuntimeEnv": "alpha"})
        self.assertEqual(validate_runtime_config_package(self.document, self.trust, now=datetime(2040, 1, 1, tzinfo=timezone.utc)), [])

    def test_even_signed_offline_endpoint_and_expiry_fields_are_rejected(self):
        for field in ("gatewayBaseUrl", "expiresAt", "issuedAt"):
            document = deepcopy(self.document)
            if field == "gatewayBaseUrl": document["runtime"][field] = ""
            else: document[field] = "2040-01-01T00:00:00Z"
            self.resign(document)
            self.assertTrue(validate_runtime_config_package(document, self.trust), field)

    def test_offline_cannot_cross_profile_target_or_artifact_trust(self):
        for field, value in (("environment", "beta"), ("target", "beta-local"), ("buildProfile", "prod"), ("contentSource", "remote"), ("trustEnvelopeDigest", "sha256:" + "c" * 64)):
            document = deepcopy(self.document)
            document[field] = value
            self.resign(document)
            self.assertTrue(validate_runtime_config_package(document, self.trust), field)

    def test_handoff_and_activation_share_closed_offline_document(self):
        args = launcher._parser(load_launch_manifest_contract()).parse_args([
            "--env", "alpha", "--target", "alpha-local", "--launch-provenance", "canonical_launcher",
        ])
        with mock.patch.object(launcher, "_runtime_config_trust_envelope", return_value=self.trust):
            handoff = launcher.build_handoff(args, runtime_config_package_loader=lambda _: self.document)
        self.assertEqual(handoff["contentSource"], "bundled_snapshot")
        self.assertFalse(handoff["requiresLocalTransport"])
        self.assertEqual(validate_handoff_against_metadata(handoff, self.trust), [])
        request = build_runtime_config_activation_request(handoff)
        self.assertEqual(validate_runtime_config_activation_request(request), [])
        request["package"]["schema"] = "unknown-document"
        self.assertTrue(validate_runtime_config_activation_request(request))

    def test_offline_cannot_enter_remote_preparation_surface(self):
        with self.assertRaisesRegex(ValueError, "offline hermetic/UAT"):
            launcher.check_remote_launch_surface(["--env", "alpha", "--hermetic"])
        self.assertEqual(launcher.check_remote_launch_surface(["--env", "beta", "--hermetic"]), 0)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            launcher.check_remote_launch_surface(["--env", "alpha", "--target", "beta-local"])

    def test_remote_beta_gamma_prod_freshness_remains_strict(self):
        for environment, target in (("beta", "beta-local"), ("gamma", "gamma-local"), ("prod", "prod-hosted")):
            issued = datetime.now(timezone.utc).replace(microsecond=0)
            values = load_test_live_runtime_values("beta", "beta-local")
            values["appRuntimeEnv"] = environment
            package = build_runtime_config_package(
                environment=environment, target=target,
                launch_policy="prod_release" if environment == "prod" else "test_live", values=values,
                source_git_sha="a" * 40, source_tree_digest="sha256:" + "b" * 64,
                signing=self.signing, issued_at=issued, expires_at=issued + timedelta(hours=1),
            )
            trust = build_runtime_config_trust_envelope("prod" if environment == "prod" else "nonprod", self.trust["trustedPublicKeys"])
            self.assertNotIn("contentSource", package)
            issues = validate_runtime_config_package(package, trust, now=issued + timedelta(days=2))
            self.assertTrue(any("expired" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
