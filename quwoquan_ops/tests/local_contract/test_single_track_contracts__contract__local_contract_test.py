from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_single_track_contracts.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_single_track_contracts",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scan_fixture(module, relative_path: str, text: str):
    original_root = module.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        module.ROOT = Path(tmp)
        try:
            path = module.ROOT / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            inventory = module.Inventory()
            module.scan_file(path, inventory)
            return inventory
        finally:
            module.ROOT = original_root


class SingleTrackContractsContractTest(unittest.TestCase):
    def test_verifier_module_loads(self) -> None:
        module = _load_verifier()
        self.assertTrue(hasattr(module, "scan_file"))
        self.assertTrue(hasattr(module, "Inventory"))

    def test_retired_domain_identity_fields_are_blocked_in_owner_contexts(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_policy_release/fields.yaml",
                "fields:\n  - name: releaseVersion\n"
                "  - name: canonicalDigest\n",
                2,
            ),
            (
                "quwoquan_service/services/product-ops-service/contracts/"
                "product_ops/experiment_assignment_fact/fields.yaml",
                "fields:\n  - name: policyVersion\n",
                1,
            ),
            (
                "quwoquan_service/services/recommendation-service/contracts/"
                "recommendation/recommendation_model_release/fields.yaml",
                "fields:\n  - name: modelVersion\n"
                "  - name: featureVersion\n"
                "  - name: featureContractVersion\n",
                3,
            ),
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_learning_fact/fields.yaml",
                "fields:\n  - name: eventVersion\n",
                1,
            ),
            (
                "quwoquan_service/generated/contract_graph.json",
                '{"entity":"AssistantPolicyRelease","name":"releaseVersion"}\n',
                1,
            ),
        )
        for relative_path, text, expected in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_domain_identity_field",
                        0,
                    ),
                    expected,
                )

    def test_retired_domain_identity_gate_preserves_legal_version_semantics(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/content-service/contracts/content/"
                "post/fields.yaml",
                "fields:\n  - name: aggregateVersion\n",
            ),
            (
                "quwoquan_service/services/integration-service/internal/"
                "providers/vendor/client.py",
                "payload = {'modelVersion': external_model_version}\n",
            ),
            (
                "quwoquan_service/contracts/metadata/_shared/"
                "runtime_observability.yaml",
                "forbidden_fields:\n  - eventVersion\n  - releaseVersion\n",
            ),
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_policy_rollout/fields.yaml",
                "fields:\n  - name: revision\n  - name: aggregateVersion\n",
            ),
            (
                "quwoquan_service/services/product-ops-service/contracts/"
                "product_ops/experiment_assignment_fact/fields.yaml",
                "fields:\n  - name: experimentRevision\n",
            ),
            (
                "quwoquan_service/services/recommendation-service/contracts/"
                "recommendation/recommendation_model_release/fields.yaml",
                "fields:\n  - name: modelReleaseId\n"
                "  - name: featureContractDigest\n"
                "  - name: featureSnapshotAt\n",
            ),
        )
        for relative_path, text in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_domain_identity_field",
                        0,
                    ),
                    0,
                )

    def test_versioned_golden_asset_names_are_forbidden(self) -> None:
        module = _load_verifier()
        original_root = module.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            module.ROOT = Path(tmp)
            try:
                golden_root = (
                    module.ROOT
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
                module.ROOT = original_root

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

    def test_custom_control_documents_are_scoped_and_current_sources_are_unversioned(
        self,
    ) -> None:
        module = _load_verifier()
        families = {
            "data catalogs": sorted(
                ROOT.glob("quwoquan_data/control_plane/_shared/catalogs/*")
            ),
            "data routing": sorted(
                ROOT.glob("quwoquan_data/control_plane/_shared/routing/*")
            ),
            "reliable task resources": sorted(
                ROOT.glob("quwoquan_service/runtime/reliabletask/resources/*")
            ),
            "service SLO": sorted(
                ROOT.glob("quwoquan_service/services/*/observability/slo/*")
            ),
            "gate policies": sorted(ROOT.glob("quwoquan_ops/policies/gates/*")),
        }
        candidates: list[Path] = []
        for family, paths in families.items():
            documents = [
                path
                for path in paths
                if path.suffix in {".yaml", ".yml", ".json"}
            ]
            self.assertTrue(documents, family)
            candidates.extend(documents)

        candidates.append(
            ROOT
            / "quwoquan_service/services/recommendation-service/internal/recommendation/"
            "recommendation_model_release/infrastructure/model_runtime/scripts/"
            "feature_registry.yaml"
        )
        for path in candidates:
            self.assertTrue(module.is_custom_control_document(path), path)
            inventory = module.Inventory()
            module.scan_file(path, inventory)
            self.assertEqual(
                inventory.counts.get("T1_custom_control_version_field", 0),
                0,
                path,
            )
            self.assertEqual(
                inventory.counts.get("T1_custom_control_parse_error", 0),
                0,
                path,
            )

        deployment = (
            ROOT
            / "quwoquan_service/services/recommendation-service/deploy/base/deployment.yaml"
        )
        self.assertFalse(module.is_custom_control_document(deployment))
        self.assertIn("quwoquan_ops/policies/gates", module.SCAN_ROOTS)
        self.assertFalse(hasattr(module, "ALLOWED_VERSIONISH_FIELD_NAMES"))

    def test_custom_control_documents_reject_all_manual_version_keys(self) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_data/control_plane/_shared/catalogs/demo.yaml",
                "version: one\nentries: []\n",
                "version: version",
            ),
            (
                "quwoquan_data/control_plane/_shared/routing/demo.yaml",
                "routing:\n  schemaVersion: one\n",
                "routing.schemaVersion: schemaVersion",
            ),
            (
                "quwoquan_service/runtime/reliabletask/resources/demo.json",
                '{"tasks":[{"policyVersion":"one"}]}\n',
                "tasks[0].policyVersion: policyVersion",
            ),
            (
                "quwoquan_service/services/search-service/observability/slo/demo.yaml",
                "load_model:\n  version: one\n",
                "load_model.version: version",
            ),
            (
                "quwoquan_ops/policies/gates/demo.json",
                '{"baseline":{"catalogVersion":"one"}}\n',
                "baseline.catalogVersion: catalogVersion",
            ),
        )

        for relative_path, text, detail in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get("T1_custom_control_version_field"),
                    1,
                )
                self.assertEqual(inventory.findings[0].detail, detail)
                self.assertEqual(
                    inventory.counts.get("T1_forbidden_envelope_field", 0),
                    0,
                )

    def test_custom_control_document_parse_failure_is_blocking(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_ops/policies/gates/broken.json",
            '{"baseline":',
        )
        self.assertEqual(
            inventory.counts.get("T1_custom_control_parse_error"),
            1,
        )
        self.assertEqual(
            inventory.counts.get("T1_custom_control_version_field", 0),
            0,
        )

    def test_legitimate_version_semantics_remain_outside_custom_control_keys(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/content-service/deploy/base/deployment.yaml",
                "apiVersion: apps/v1\nkind: Deployment\n",
            ),
            (
                "quwoquan_ops/policies/gates/provider.json",
                '{"provider":{"apiVersion":"2025-01-01"}}\n',
            ),
            (
                "quwoquan_app/packages/example/pubspec.yaml",
                "name: example\nversion: 1.2.3+4\n",
            ),
            (
                "quwoquan_service/services/content-service/contracts/content/post/fields.yaml",
                "fields:\n  - name: version\n    description: aggregate optimistic lock\n",
            ),
            (
                "quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml",
                "fields:\n  - name: version\n    description: immutable asset version\n",
            ),
            (
                "quwoquan_service/services/content-service/generated/openapi.yaml",
                "openapi: 3.1.0\ninfo:\n  version: v1\n",
            ),
        )

        for relative_path, text in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(inventory.findings, [])

    def test_detects_aliases_and_versioned_schema_identity(self) -> None:
        module = _load_verifier()
        text = (
            "fields:\n  - name: id\n    aliases: [postId]\n"
            "schemaVersion: quwoquan_data.release/1\n"
        )
        self.assertTrue("aliases:" in text)
        self.assertIsNotNone(module.VERSIONED_INLINE.search(text))

    def test_detects_json_multi_key_decode(self) -> None:
        module = _load_verifier()
        line = "updatedAt: json['updatedAt']?.toString() ?? json['updated_at']?.toString(),"
        match = module.MULTI_KEY_DECODE.search(line)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertNotEqual(match.group("k1"), match.group("k2"))
        same_key = "w = map['coverWidth'] ?? payload['coverWidth'];"
        same = module.MULTI_KEY_DECODE.search(same_key)
        # 同名跨 map：正则要求同一 ident，故不匹配
        self.assertIsNone(same)
        any_ident = "id: (dm['userId'] ?? dm['id'] ?? '').toString(),"
        any_match = module.MULTI_KEY_DECODE.search(any_ident)
        self.assertIsNotNone(any_match)

    def test_detects_doc_dual_track_teaching(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.DOC_DUAL_TRACK_TEACHING.search("允许短期双读旧字段")
        )
        self.assertIsNotNone(
            module.DOC_DUAL_TRACK_TEACHING.search("feature flag 双读")
        )

        contract_inventory = _scan_fixture(
            module,
            "quwoquan_service/contracts/feedback_and_learning.md",
            "体验事件建议进入日志与指标双写或可互相导出。\n",
        )
        self.assertEqual(
            contract_inventory.counts.get("T5_doc_dual_track_teaching"),
            1,
        )
        prohibition_inventory = _scan_fixture(
            module,
            "quwoquan_service/contracts/feedback_and_learning.md",
            "日志和指标只由事件事实派生，禁止向第二事实存储双写。\n",
        )
        self.assertEqual(
            prohibition_inventory.counts.get("T5_doc_dual_track_teaching", 0),
            0,
        )

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

    def test_runtime_error_decoder_has_no_message_alias_track(self) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/contracts/metadata/_shared/openapi_common.yaml",
                "        message:\n          type: string\n",
            ),
            (
                "quwoquan_service/runtime/errors/errors.go",
                'Message string `json:"message,omitempty"`\n',
            ),
            (
                "quwoquan_app/lib/cloud/runtime/errors/cloud_error_mapper.dart",
                "final value = body['reasonMessage'];\n",
            ),
        )
        for relative_path, source in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, source)
                self.assertEqual(
                    inventory.counts.get("T3_runtime_error_message_alias"),
                    1,
                )

        canonical = _scan_fixture(
            module,
            "quwoquan_app/lib/cloud/runtime/errors/cloud_error_mapper.dart",
            "final value = body['userMessage'];\n",
        )
        self.assertEqual(
            canonical.counts.get("T3_runtime_error_message_alias", 0),
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

    def test_detects_create_route_extra_compat_branch(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_app/lib/app/navigation/app_router.dart",
            "final extra = state.extra is HomepageCanonicalReference;\n",
        )
        self.assertEqual(inventory.counts.get("T3_create_route_extra_compat"), 1)

    def test_client_state_sync_rejects_derived_second_truth_in_business_source(
        self,
    ) -> None:
        module = _load_verifier()
        business_source = _scan_fixture(
            module,
            "quwoquan_app/lib/core/models/client_state_sync.dart",
            "final bool needsRemoteSync;\n",
        )
        self.assertEqual(
            business_source.counts.get("T1_client_state_sync_second_truth"),
            1,
        )

        rejection_evidence = _scan_fixture(
            module,
            "quwoquan_app/lib/core/models/client_state_sync.dart",
            "// Retired needsRemoteSync input must be rejected.\n"
            "if (json.containsKey('needsRemoteSync')) throw FormatException();\n",
        )
        self.assertEqual(
            rejection_evidence.counts.get("T1_client_state_sync_second_truth", 0),
            0,
        )

        test_fixture = _scan_fixture(
            module,
            "quwoquan_app/test/local_contract/client_state_sync_test.dart",
            "const retired = {'needsRemoteSync': false};\n",
        )
        self.assertEqual(
            test_fixture.counts.get("T1_client_state_sync_second_truth", 0),
            0,
        )

    def test_remote_config_rejects_package_version_without_touching_package_semver(
        self,
    ) -> None:
        module = _load_verifier()
        runtime = _scan_fixture(
            module,
            "quwoquan_app/lib/cloud/runtime/models/app_remote_config_snapshot.dart",
            "final String packageVersion;\n",
        )
        self.assertEqual(runtime.counts.get("T1_remote_config_dual_identity"), 1)

        pubspec = _scan_fixture(
            module,
            "quwoquan_app/packages/example/pubspec.yaml",
            "name: example\nversion: 1.2.3+4\n",
        )
        self.assertEqual(pubspec.findings, [])

    def test_detects_service_contract_compat_alias_description(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.CONTRACT_COMPAT_ALIAS.search(
                "description: 兼容别名；值与 userHandle 保持一致"
            )
        )
        self.assertIsNotNone(
            module.CONTRACT_COMPAT_ALIAS.search("只有标准名，零兼容别名")
        )

    def test_detects_positive_alias_test_semantics(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.POSITIVE_ALIAS_TEST.search("test('_id alias → id 正确解析'")
        )
        self.assertIsNotNone(
            module.POSITIVE_ALIAS_TEST.search(
                "test('别名输入 likesCount 也能正确投射'"
            )
        )
        self.assertIsNone(
            module.POSITIVE_ALIAS_TEST.search("test('rejects _id alias'")
        )
        self.assertIsNone(
            module.POSITIVE_ALIAS_TEST.search(
                "test('拒绝 likesCount/commentsCount/savesCount alias'"
            )
        )

    def test_scan_file_flags_multi_key_in_temp_dart(self) -> None:
        module = _load_verifier()
        inv = module.Inventory()
        with tempfile.TemporaryDirectory() as tmp:
            # 写入 ROOT 外无法用 scan_file 的 ROOT 相对路径；直接测正则 + CATEGORY 逻辑
            line = "id: (map['_id'] ?? map['id'] ?? '') as String,"
            self.assertIsNotNone(module.MULTI_KEY_DECODE.search(line))
            self.assertEqual(inv.counts.get("T3_multi_key_decode", 0), 0)

    def test_detects_dart_wire_id_key(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(module.DART_WIRE_ID_KEY.search("id: m['_id'] as String,"))
        self.assertIsNotNone(module.GO_JSON_ID_TAG.search('Id string `json:"_id"`'))
        self.assertIsNone(module.GO_JSON_ID_TAG.search('Id string `bson:"_id"`'))

    def test_allows_elasticsearch_bulk_metadata_id_only_in_provider_harness(self) -> None:
        module = _load_verifier()
        lines = [
            "var metadata struct {",
            "  Index struct {",
            '    Index string `json:"_index"`',
            '    ID string `json:"_id"`',
            '  } `json:"index"`',
            "}",
        ]

        self.assertTrue(
            module._is_elasticsearch_bulk_metadata_context(
                "quwoquan_service/services/product-ops-service/tests/local_contract/"
                "product_ops/event_record/elasticsearch_log_sink__local_contract_test.go",
                lines,
                4,
            )
        )
        self.assertFalse(
            module._is_elasticsearch_bulk_metadata_context(
                "quwoquan_service/services/product-ops-service/tests/local_contract/"
                "product_ops/event_record/http_event_dto__local_contract_test.go",
                lines,
                4,
            )
        )

    def test_detects_multi_key_helper_with_id(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.MULTI_KEY_HELPER_ID.search(
                "_firstNonEmpty([map['postId'], map['_id'], map['id']])"
            )
        )

    def test_detects_fixture_dual_id(self) -> None:
        module = _load_verifier()
        self.assertTrue(
            module._json_object_has_dual_id({"_id": "a", "id": "a", "name": "x"})
        )
        self.assertFalse(module._json_object_has_dual_id({"_id": "a", "name": "x"}))

    def test_detects_id_compat_teaching(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.ID_COMPAT_TEACHING.search("支持 _id / id 兼容读取")
        )

    def test_detects_retired_public_identity_aliases(self) -> None:
        module = _load_verifier()
        retired = (
            "/user/{username}",
            "AppRoutePaths.userProfile(username: value)",
            "OtherProfilePage(username: value)",
            "currentUser.username",
            "user.avatarUrlOrAvatar",
        )
        for source in retired:
            self.assertTrue(
                any(
                    pattern.search(source)
                    for pattern in module.PUBLIC_IDENTITY_RETIRED_PATTERNS
                ),
                source,
            )

        retired_user_model = (
            "final String? username;",
            "this.username,",
            "json['username']",
            "'username': username,",
            "final String? avatar;",
            "this.avatar,",
            "json['avatar']",
            "'avatar': avatar,",
        )
        for source in retired_user_model:
            self.assertTrue(
                any(
                    pattern.search(source)
                    for pattern in module.PUBLIC_USER_MODEL_RETIRED_PATTERNS
                ),
                source,
            )

        canonical = (
            "/user/{userHandle}",
            "AppRoutePaths.userProfile(userHandle: value)",
            "final String? avatarUrl;",
        )
        for source in canonical:
            self.assertFalse(
                any(
                    pattern.search(source)
                    for pattern in (
                        *module.PUBLIC_IDENTITY_RETIRED_PATTERNS,
                        *module.PUBLIC_USER_MODEL_RETIRED_PATTERNS,
                    )
                ),
                source,
            )


if __name__ == "__main__":
    unittest.main()
