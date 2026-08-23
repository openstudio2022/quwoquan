"""Profile-scoped local App runtime configuration authority contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
    runtime_config_trust_envelope_digest,
)
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    DEFAULT_KEY_ID,
    LOCAL_AUTHORITY_PROFILE,
    LOCAL_AUTHORITY_TARGET,
    prepare_local_app_runtime_config_signing,
)


class LocalAppRuntimeConfigKeysSecurityContractTest(unittest.TestCase):
    def test_material_is_profile_scoped_create_once_and_validated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-runtime-local-keys-") as temporary:
            work_root = Path(temporary)
            calls: list[tuple[str, tuple[str, ...]]] = []

            def resolve(target: str, *parts: str) -> Path:
                calls.append((target, parts))
                return work_root.joinpath(target, *parts)

            with mock.patch(
                "quwoquan_ops.cli.lib.local_app_runtime_config_keys.deployment_target_path",
                side_effect=resolve,
            ):
                first = prepare_local_app_runtime_config_signing(ROOT)
                first_private = first.private_key_path.read_bytes()
                second = prepare_local_app_runtime_config_signing(ROOT)
            self.assertEqual(first, second)
            self.assertEqual(second.private_key_path.read_bytes(), first_private)
            self.assertEqual(first.key_id, DEFAULT_KEY_ID)
            self.assertEqual(first.private_key_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                first.trusted_public_keys_path.stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(
                set(json.loads(first.trusted_public_keys_path.read_text())),
                {DEFAULT_KEY_ID},
            )
            self.assertEqual(
                set(calls),
                {
                    (
                        LOCAL_AUTHORITY_TARGET,
                        ("secrets", "app-runtime-config", LOCAL_AUTHORITY_PROFILE),
                    )
                },
            )
            self.assertEqual(
                first.private_key_path.parent,
                work_root
                / "app-build-products"
                / "secrets"
                / "app-runtime-config"
                / "nonprod",
            )

    def test_alpha_beta_gamma_share_one_envelope_and_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-runtime-local-keys-") as temporary:
            work_root = Path(temporary)
            with mock.patch(
                "quwoquan_ops.cli.lib.local_app_runtime_config_keys.deployment_target_path",
                side_effect=lambda target, *parts: work_root.joinpath(target, *parts),
            ):
                keyrings = []
                for _environment in ("alpha", "beta", "gamma"):
                    signing = prepare_local_app_runtime_config_signing(ROOT)
                    keyrings.append(
                        json.loads(
                            signing.trusted_public_keys_path.read_text(encoding="utf-8")
                        )
                    )
        envelopes = [
            build_runtime_config_trust_envelope("nonprod", keyring)
            for keyring in keyrings
        ]
        digests = [runtime_config_trust_envelope_digest(value) for value in envelopes]
        self.assertEqual(envelopes[0], envelopes[1])
        self.assertEqual(envelopes[1], envelopes[2])
        self.assertEqual(digests[0], digests[1])
        self.assertEqual(digests[1], digests[2])
        self.assertEqual(
            set(envelopes[0]),
            {
                "schema",
                "schemaVersion",
                "buildProfile",
                "signatureAlgorithm",
                "trustedPublicKeys",
            },
        )
        forbidden = {
            "environment",
            "target",
            "endpoint",
            "package",
            "privateKey",
            "secret",
            "rollout",
            "channel",
            "content",
        }
        self.assertTrue(forbidden.isdisjoint(envelopes[0]))

    def test_existing_material_is_never_overwritten_during_issuance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-runtime-local-keys-") as temporary:
            key_dir = Path(temporary) / "secrets/app-runtime-config/nonprod"
            key_dir.mkdir(parents=True)
            private_path = key_dir / "signing.pem"
            keyring_path = key_dir / "trusted_public_keys.json"
            private_path.write_text("existing-private", encoding="utf-8")
            keyring_path.write_text("existing-keyring", encoding="utf-8")
            from quwoquan_ops.cli.lib.local_app_runtime_config_keys import _issue_keypair

            _issue_keypair(key_dir, private_path, keyring_path)
            self.assertEqual(private_path.read_text(), "existing-private")
            self.assertEqual(keyring_path.read_text(), "existing-keyring")

    def test_prod_cannot_be_selected_and_partial_material_is_rejected(self) -> None:
        signature = inspect.signature(prepare_local_app_runtime_config_signing)
        self.assertEqual(tuple(signature.parameters), ("repo_root",))
        with self.assertRaises(TypeError):
            prepare_local_app_runtime_config_signing(ROOT, "prod", "prod-hosted")  # type: ignore[call-arg]

        with tempfile.TemporaryDirectory(prefix="qwq-runtime-local-keys-") as temporary:
            authority_root = Path(temporary) / "app-build-products"
            private_path = (
                authority_root
                / "secrets/app-runtime-config/nonprod/signing.pem"
            )
            private_path.parent.mkdir(parents=True)
            private_path.write_text("partial", encoding="utf-8")
            with mock.patch(
                "quwoquan_ops.cli.lib.local_app_runtime_config_keys.deployment_target_path",
                side_effect=lambda target, *parts: Path(temporary).joinpath(
                    target,
                    *parts,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "partial"):
                    prepare_local_app_runtime_config_signing(ROOT)


if __name__ == "__main__":
    unittest.main()
