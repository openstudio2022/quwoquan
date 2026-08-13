# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
"""verify_single_track_contracts 的版本化身份单轨合约。

由 test_single_track_contracts__contract__local_contract_test.py（Python 1000
行硬顶治理）按场景拆出：golden 资产/观测维度/本地与迁移身份/schema 值的
versioned 命名拦截、sha256 与 policy digest 的 canonical 形态、冻结身份字节
守恒。测试逐字搬移；共享 harness 见 tests/support。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.single_track_contracts_test_support import (
    ROOT,
    _load_verifier,
    _scan_fixture,
    _scanner_module,
)

class SingleTrackContractsContractTest(unittest.TestCase):
    def test_versioned_golden_asset_names_are_forbidden(self) -> None:
        module = _load_verifier()
        scanner = _scanner_module()
        original_root = scanner.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            scanner.ROOT = Path(tmp)
            try:
                golden_root = (
                    scanner.ROOT
                    / "quwoquan_app/test/local_contract/ui/user/goldens"
                )
                golden_root.mkdir(parents=True)
                (golden_root / "login_v2_state.png").write_bytes(b"golden")
                inventory = module.Inventory()
                module.scan_versioned_golden_assets(inventory)
                self.assertEqual(
                    inventory.counts.get("T1_versioned_golden_identity"),
                    1,
                )

                (golden_root / "login_v2_state.png").rename(
                    golden_root / "login_state.png"
                )
                canonical_inventory = module.Inventory()
                module.scan_versioned_golden_assets(canonical_inventory)
                self.assertEqual(canonical_inventory.findings, [])
            finally:
                scanner.ROOT = original_root

    def test_versioned_quota_shard_observability_is_forbidden(self) -> None:
        module = _load_verifier()
        versioned = _scan_fixture(
            module,
            "quwoquan_ops/observability/monitoring/alerts/demo.yaml",
            'description: "按 v2 quota shard 执行巡检"\n',
        )
        self.assertEqual(
            versioned.counts.get("T1_versioned_observability_dimension"),
            1,
        )

        canonical = _scan_fixture(
            module,
            "quwoquan_ops/observability/monitoring/alerts/demo.yaml",
            'description: "按 canonical quota shard 执行巡检"\n',
        )
        self.assertEqual(canonical.findings, [])

    def test_grafana_schema_version_is_external_format_only(self) -> None:
        module = _load_verifier()
        dashboard = _scan_fixture(
            module,
            "quwoquan_ops/observability/monitoring/dashboards/demo.json",
            '{"schemaVersion": 39, "title": "Demo"}\n',
        )
        self.assertEqual(dashboard.findings, [])

    def test_detects_metadata_top_level_version(self) -> None:
        module = _load_verifier()
        text = "version: 1\ndomain: demo\n"
        self.assertIsNotNone(module.TOP_LEVEL_VERSION.search(text))

    def test_catalog_version_is_forbidden_but_rejection_tests_are_allowed(self) -> None:
        module = _load_verifier()
        self.assertIn("catalogVersion", module.FORBIDDEN_ENVELOPE_FIELDS)

        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            positive = Path(tmp) / "positive.dart"
            positive.write_text(
                "final value = json['catalogVersion'];\n",
                encoding="utf-8",
            )
            positive_inventory = module.Inventory()
            module.scan_file(positive, positive_inventory)
            self.assertEqual(
                positive_inventory.counts.get("T1_forbidden_envelope_field"),
                1,
            )

            negative = Path(tmp) / "negative.dart"
            negative.write_text(
                "// Retired catalogVersion input must be rejected.\n"
                "if (json.containsKey('catalogVersion')) {\n"
                "  throw const FormatException('retired field');\n"
                "}\n",
                encoding="utf-8",
            )
            negative_inventory = module.Inventory()
            module.scan_file(negative, negative_inventory)
            self.assertEqual(
                negative_inventory.counts.get("T1_forbidden_envelope_field", 0),
                0,
            )

    def test_learning_projection_version_identity_is_forbidden(self) -> None:
        module = _load_verifier()
        self.assertIn("definitionVersion", module.FORBIDDEN_ENVELOPE_FIELDS)

        field_inventory = _scan_fixture(
            module,
            "quwoquan_service/services/assistant-service/contracts/assistant/"
            "assistant_learning_fact/projections/demo.yaml",
            "fields:\n  - name: definitionVersion\n",
        )
        self.assertEqual(
            field_inventory.counts.get("T1_forbidden_envelope_field"),
            1,
        )

        identity_inventory = _scan_fixture(
            module,
            "quwoquan_service/services/assistant-service/internal/demo.go",
            'const projectionIdentity = "assistant_learning_projection_v2"\n',
        )
        self.assertEqual(
            identity_inventory.counts.get("T1_versioned_local_identity"),
            1,
        )

    def test_user_identity_preserves_canonical_bytes_and_rejects_rule_keys(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/user-service/internal/demo.go",
                'const identityRuleVersion = "01"\n',
            ),
            (
                "quwoquan_service/services/user-service/contracts/account/"
                "user_account/shard_directory.yaml",
                "rule_version: '01'\n",
            ),
            (
                "quwoquan_service/generated/contract_graph.json",
                '{\n  "rule_version": "01"\n}\n',
            ),
        )
        for relative_path, source in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, source)
                self.assertEqual(
                    inventory.counts.get("T1_retired_user_identity"),
                    1,
                )

        canonical = _scan_fixture(
            module,
            "quwoquan_service/services/user-service/internal/demo.go",
            'const ownerID = "uo_01_ph_32f3_01j00000000000000000000000"\n'
            'const personaID = "us_01_32f3_01j00000000000000000000001"\n',
        )
        self.assertEqual(
            canonical.counts.get("T1_retired_user_identity", 0),
            0,
        )

    def test_search_and_recommendation_use_one_digest_identity(self) -> None:
        module = _load_verifier()
        retired = (
            ("demo.go", 'const IndexVersion = "search-v1"\n'),
            ("demo.dart", "final rankingVersion = 'current';\n"),
            ("demo.yaml", "reasonVersion: current\n"),
            ("demo.go", 'const runtime = "runtime-search-v2"\n'),
        )
        for name, source in retired:
            with self.subTest(source=source):
                inventory = _scan_fixture(
                    module,
                    f"quwoquan_service/runtime/search/{name}",
                    source,
                )
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_search_recommendation_identity"
                    ),
                    1,
                )

        invalid_digest = _scan_fixture(
            module,
            "quwoquan_app/test/local_contract/recommendation_test.dart",
            "final event = BehaviorEvent(policyDigest: 'rank-v3');\n",
        )
        self.assertEqual(
            invalid_digest.counts.get(
                "T1_noncanonical_policy_digest_literal"
            ),
            1,
        )

        canonical = _scan_fixture(
            module,
            "quwoquan_app/test/local_contract/recommendation_test.dart",
            "final event = BehaviorEvent(\n"
            "  policyDigest: "
            "'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',\n"
            ");\n",
        )
        self.assertEqual(canonical.findings, [])

        rejection = _scan_fixture(
            module,
            "quwoquan_service/runtime/search/core_wire_contract_test.go",
            '// retired rankingVersion must be rejected\n',
        )
        self.assertEqual(rejection.findings, [])

    def test_persona_migration_type_has_one_semantic_identity(self) -> None:
        module = _load_verifier()
        for retired in ("LegacyPersona", "CurrentPersona"):
            with self.subTest(retired=retired):
                inventory = _scan_fixture(
                    module,
                    "quwoquan_service/runtime/persona/rollout.go",
                    f"type {retired} struct {{}}\n",
                )
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_persona_migration_type",
                    ),
                    1,
                )

        canonical = _scan_fixture(
            module,
            "quwoquan_service/runtime/persona/rollout.go",
            "type PersonaMigrationSource struct {}\n",
        )
        self.assertEqual(
            canonical.counts.get("T1_retired_persona_migration_type", 0),
            0,
        )

    def test_sha256_literals_are_canonical_or_explicit_negative_fixtures(self) -> None:
        module = _load_verifier()
        positive = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/tests/"
            "local_contract/content/post/digest_test.go",
            'const digest = "sha256:test"\n',
        )
        self.assertEqual(
            positive.counts.get("T1_noncanonical_sha256_literal"),
            1,
        )

        canonical = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/tests/"
            "local_contract/content/post/digest_test.go",
            'const digest = "sha256:' + "a" * 64 + '"\n',
        )
        self.assertEqual(
            canonical.counts.get("T1_noncanonical_sha256_literal", 0),
            0,
        )

        explicit_negative = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/tests/"
            "local_contract/content/post/digest_test.go",
            "func TestRejectsInvalidDigest(t *testing.T) {\n"
            '  got := invalidSHA256Fixture("sha256:not-a-digest")\n'
            "  requireRejected(t, got)\n"
            "}\n",
        )
        self.assertEqual(
            explicit_negative.counts.get("T1_noncanonical_sha256_literal", 0),
            0,
        )

        algorithm_identity = "sha256:qwq-filter-catalog-canonical-json"
        canonical_algorithm = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/internal/demo.go",
            f'const DigestAlgorithm = "{algorithm_identity}"\n',
        )
        self.assertEqual(
            canonical_algorithm.counts.get("T1_noncanonical_sha256_literal", 0),
            0,
        )
        digest_field_is_not_an_algorithm_identity = _scan_fixture(
            module,
            "quwoquan_service/services/user-service/internal/demo.go",
            f'const digest = "{algorithm_identity}"\n',
        )
        self.assertEqual(
            digest_field_is_not_an_algorithm_identity.counts.get(
                "T1_noncanonical_sha256_literal"
            ),
            1,
        )

        explicit_tamper = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/tests/"
            "local_contract/content/post/digest_test.go",
            "func TestDigestTamperingFailsClosed(t *testing.T) {\n"
            '  got.AssetDigest = "sha256:tampered"\n'
            "  if err == nil { t.Fatal(\"expected digest error\") }\n"
            "}\n",
        )
        self.assertEqual(
            explicit_tamper.counts.get("T1_noncanonical_sha256_literal", 0),
            0,
        )

        incidental_placeholder_in_negative_test = _scan_fixture(
            module,
            "quwoquan_data/tests/local_contract/content_plan_test.py",
            "def test_rejects_missing_rights():\n"
            '    asset = {"sha256": "sha256:test", "rights": "missing"}\n'
            "    assert reject_missing_rights(asset)\n",
        )
        self.assertEqual(
            incidental_placeholder_in_negative_test.counts.get(
                "T1_noncanonical_sha256_literal"
            ),
            1,
        )

        documentation_placeholder = _scan_fixture(
            module,
            "specs/feature-tree/runtime/example/spec.md",
            "Digest format is `sha256:...` and must be supplied.\n",
        )
        self.assertEqual(
            documentation_placeholder.counts.get(
                "T1_noncanonical_sha256_literal", 0
            ),
            0,
        )

        concatenated_digest = _scan_fixture(
            module,
            "quwoquan_data/tests/local_contract/source_digest_test.py",
            'digest = ("sha256:'
            + "a" * 32
            + '"\n          "'
            + "b" * 32
            + '")\n',
        )
        self.assertEqual(
            concatenated_digest.counts.get(
                "T1_noncanonical_sha256_literal", 0
            ),
            0,
        )

    def test_detects_numeric_and_v_suffix_schema(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.NUMERIC_SCHEMA_LITERAL.search('"schema": 1')
        )
        self.assertIsNotNone(
            module.NUMERIC_SCHEMA_LITERAL.search("schema: 1")
        )
        self.assertIsNotNone(
            module.SCHEMA_VALUE_V_SUFFIX.search(
                '"schema": "geo_resolution_config_v1"'
            )
        )
        for text in (
            '"schema": "assistant.policy_release.v1"',
            'schema: assistant-policy-v2',
            'schema: "assistant_turn_v4"',
            'schema: qwq.runtime/3',
            'schema: quwoquan.release-migration-receipt/v1',
            'schema: artifact.m2',
        ):
            match = module.SCHEMA_VALUE_V_SUFFIX.search(text)
            self.assertIsNotNone(match, text)
            assert match is not None
            self.assertIsNotNone(
                module.VERSIONED_SCHEMA_VALUE.search(match.group("value")),
                text,
            )
        self.assertIsNone(
            module.SCHEMA_VALUE_V_SUFFIX.search('schema: assistant_turn')
        )

    def test_detects_versioned_local_identity_literals(self) -> None:
        module = _load_verifier()
        for source in (
            "'qwq.content_query_snapshots.v2'",
            "'comment_draft:v2:'",
            "'post_publication_intents_v1'",
            "'ops.user.persona_management_v1'",
            "'qwq_recovery_failure_queue_v1'",
            '"recovery-failure-queue-key-v1"',
        ):
            self.assertIsNotNone(
                module.VERSIONED_LOCAL_IDENTITY_LITERAL.search(source),
                source,
            )
        for source in (
            "'qwq.content_query_snapshots'",
            "'comment_draft:'",
            "'media/comment/id/v1/comment.png'",
            "const Uuid().v4()",
        ):
            self.assertIsNone(
                module.VERSIONED_LOCAL_IDENTITY_LITERAL.search(source),
                source,
            )

    def test_actor_queue_box_name_rejects_versioned_interpolated_identity(
        self,
    ) -> None:
        module = _load_verifier()
        relative_path = (
            "quwoquan_app/lib/cloud/runtime/context/actor_queue_partition.dart"
        )
        versioned = _scan_fixture(
            module,
            relative_path,
            "String boxName(String baseName) => '${baseName}_v3_$key';\n",
        )
        self.assertEqual(
            versioned.counts.get("T1_versioned_local_identity"),
            1,
        )

        stable = _scan_fixture(
            module,
            relative_path,
            "String boxName(String queueName) => '${queueName}_actor_$key';\n",
        )
        self.assertEqual(stable.findings, [])

    def test_detects_versioned_migration_identity(self) -> None:
        module = _load_verifier()
        for source in (
            '"user-service.canonical-enums.release-v1"',
            '"chat.migration-lock.v2"',
        ):
            self.assertIsNotNone(
                module.VERSIONED_MIGRATION_IDENTITY.search(source),
                source,
            )
        self.assertIsNone(
            module.VERSIONED_MIGRATION_IDENTITY.search(
                '"user-service.canonical-enums"'
            )
        )

    def test_detects_retired_first_party_runtime_identities(self) -> None:
        module = _load_verifier()
        retired = (
            "content_processing_progressive_mp4_v1",
            "premium_pool_projection_v1",
            "global_premium_pool_v1:item",
            "opaque_aes_gcm_v1",
            "otpref.v1.key.nonce.ciphertext",
            "sourced-video-attribution-v1",
            "replay-v1",
            "m6.replay",
            "md.v1",
            "tool_observation_v1",
        )
        for identity in retired:
            self.assertIsNotNone(module.RETIRED_CUSTOM_IDENTITY.search(identity), identity)

        canonical = (
            "qq_mobile_v1.payload",
            "qwq-readiness-guest-v1",
            "content_processing_progressive_mp4",
            "premium_pool_projection",
            "global_premium_pool:item",
            "opaque_aes_gcm",
            "otpref.key.nonce.ciphertext",
            "sourced-video-attribution",
            "replay",
        )
        for identity in canonical:
            self.assertIsNone(module.RETIRED_CUSTOM_IDENTITY.search(identity), identity)

    def test_frozen_identity_scanner_allows_only_the_existing_bytes(self) -> None:
        module = _load_verifier()
        for source in (
            'namespace = "qwq-device-actor"\n',
            'namespace = "qwq-device-actor-v2"\n',
        ):
            mutated = _scan_fixture(
                module,
                "quwoquan_data/scripts/content/example.py",
                source,
            )
            self.assertEqual(
                mutated.counts.get("T1_mutated_frozen_identity"),
                1,
            )

        canonical = _scan_fixture(
            module,
            "quwoquan_data/scripts/content/example.py",
            'namespace = "qwq-device-actor-v1"\n',
        )
        self.assertEqual(canonical.findings, [])

        negative = _scan_fixture(
            module,
            "quwoquan_service/services/user-service/tests/local_contract/reject_test.go",
            '// qq_mobile_v2. input must be rejected\n',
        )
        self.assertEqual(negative.counts.get("T1_retired_custom_identity", 0), 0)
        self.assertEqual(negative.counts.get("T1_mutated_frozen_identity", 0), 0)


if __name__ == "__main__":
    unittest.main()
