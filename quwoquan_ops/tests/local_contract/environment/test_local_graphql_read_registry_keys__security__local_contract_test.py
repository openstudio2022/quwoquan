"""Target-scoped local GraphQL signing authority contracts.

spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_graphql_read_registry_keys import (
    DEFAULT_KEY_ID,
    prepare_local_graphql_read_registry_signing,
)


class LocalGraphQLReadRegistryKeysSecurityContractTest(unittest.TestCase):
    def test_material_is_target_scoped_create_once_and_validated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-graphql-local-keys-") as temporary:
            target_root = Path(temporary) / "alpha-local"
            with mock.patch(
                "quwoquan_ops.cli.lib.local_graphql_read_registry_keys.deployment_target_path",
                side_effect=lambda target, *parts: target_root.joinpath(*parts),
            ):
                first = prepare_local_graphql_read_registry_signing(
                    ROOT, "alpha", "alpha-local"
                )
                first_private = first.private_key_path.read_bytes()
                second = prepare_local_graphql_read_registry_signing(
                    ROOT, "alpha", "alpha-local"
                )
            self.assertEqual(first, second)
            self.assertEqual(second.private_key_path.read_bytes(), first_private)
            self.assertEqual(first.key_id, DEFAULT_KEY_ID)
            self.assertEqual(first.private_key_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(first.trusted_public_keys_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                set(json.loads(first.trusted_public_keys_path.read_text())),
                {DEFAULT_KEY_ID},
            )

    def test_prod_and_cross_target_bootstrap_are_rejected(self) -> None:
        for environment, target in (
            ("prod", "prod-hosted"),
            ("alpha", "beta-local"),
        ):
            with self.subTest(environment=environment, target=target):
                with self.assertRaises(ValueError):
                    prepare_local_graphql_read_registry_signing(
                        ROOT, environment, target
                    )
