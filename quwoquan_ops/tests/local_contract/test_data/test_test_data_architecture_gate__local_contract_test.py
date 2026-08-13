"""Companion local_contract for the test-data architecture gate.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t1
spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t2
"""

from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
from pathlib import Path

from quwoquan_ops.gate.verify_test_data_architecture import collect_issues


class TestDataArchitectureGateContractTest(unittest.TestCase):
    def test_weak_dict_and_provider_import_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / "quwoquan_ops/tests/local_contract/example_test.py"
            test.parent.mkdir(parents=True)
            test.write_text(
                "from quwoquan_ops.cli.lib.test_data.providers.chat_service import build_provider\n"
                "from quwoquan_ops.cli.lib.test_data.capabilities.chat_service import DIRECT_CONVERSATION_WITH_MESSAGES\n"
                "request = DIRECT_CONVERSATION_WITH_MESSAGES.bind({'message_count': 3})\n",
                encoding="utf-8",
            )
            issues = collect_issues(root)
            self.assertTrue(any("must not import Provider" in issue for issue in issues))
            self.assertTrue(any("bare dict" in issue for issue in issues))

    def test_fixture_budget_and_scenario_dump_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = (
                root
                / "quwoquan_service/services/chat-service/tests/support/fixtures/scenario.json"
            )
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                '{"seedSets":{"all":['
                + ",".join("1" for _ in range(501))
                + "]}}\n",
                encoding="utf-8",
            )
            issues = collect_issues(root)
            self.assertTrue(any("scalar leaves" in issue for issue in issues))
            self.assertTrue(any("scenario-dump keys" in issue for issue in issues))

    def test_app_support_giant_files_and_const_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = root / "quwoquan_app/test/support/runtime/fixtures"
            support.mkdir(parents=True)
            relocated = support / "relocated_fixture.g.dart"
            relocated.write_text("x" * (65 * 1024), encoding="utf-8")
            const_json = support / "embedded_fixture.dart"
            const_json.write_text(
                "const String payload = r'''["
                + '"fixture",'
                * 1024
                + "]''';\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("App test support file exceeds 64 KiB" in issue for issue in issues)
            )
            self.assertTrue(
                any("oversized single line" in issue for issue in issues)
            )
            self.assertTrue(
                any("const JSON exceeds 8 KiB" in issue for issue in issues)
            )

    def test_user_acceptance_fixture_gateway_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gateway = root / (
                "quwoquan_ops/tests/acceptance/user_acceptance/"
                "service_ops/chat-service/smoke/fake_gateway.py"
            )
            gateway.parent.mkdir(parents=True)
            gateway.write_text(
                "def _fixture_response(path):\n    return {'items': []}\n",
                encoding="utf-8",
            )
            issues = collect_issues(root)
            self.assertTrue(
                any("production Remote composition" in issue for issue in issues)
            )

    def test_user_acceptance_fixed_fixture_conversation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = root / (
                "quwoquan_ops/tests/acceptance/user_acceptance/"
                "service_ops/chat-service/smoke/chat_probe.py"
            )
            probe.parent.mkdir(parents=True)
            probe.write_text(
                "parser.add_argument('--fixture-conversation-id')\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("fixed fixture conversation identity" in issue for issue in issues)
            )

    def test_chat_user_acceptance_fixed_actor_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = root / (
                "quwoquan_ops/tests/acceptance/user_acceptance/"
                "service_ops/chat-service/smoke/chat_probe.py"
            )
            probe.parent.mkdir(parents=True)
            probe.write_text(
                'creator_id = "user_test_001"\n',
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("active test-data lease" in issue for issue in issues)
            )

    def test_chat_api_integration_fixed_actor_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / (
                "quwoquan_app/test/api_integration/service/chat_service/chat/"
                "message/message_remote__api_integration_test.dart"
            )
            test.parent.mkdir(parents=True)
            test.write_text(
                "const senderId = 'user_test_sender_001';\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("typed test-data session" in issue for issue in issues)
            )

    def test_local_contract_deterministic_object_id_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / (
                "quwoquan_app/test/local_contract/service/chat_service/chat/"
                "message/message_builder__local_contract_test.dart"
            )
            test.parent.mkdir(parents=True)
            test.write_text(
                "const messageId = 'message-local-contract-001';\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertFalse(
                any("Actor identities" in issue or "business ID" in issue for issue in issues)
            )

    def test_content_user_acceptance_default_fixture_actor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = root / (
                "quwoquan_ops/tests/acceptance/user_acceptance/"
                "service_ops/content-service/smoke/feed_probe.py"
            )
            probe.parent.mkdir(parents=True)
            probe.write_text(
                "parser.add_argument('--viewer-id', default='fixture_user_current')\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("resolve Actor identity" in issue for issue in issues)
            )

    def test_generated_user_provider_state_rejects_direct_storage_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider_state = root / (
                "quwoquan_service/services/user-service/tests/api_integration/"
                "account/user_account/"
                "generated_user_pool_provider_state__api_integration_test.go"
            )
            provider_state.parent.mkdir(parents=True)
            provider_state.write_text(
                "package api_integration\nfunc setup() { pgPool.Exec() }\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("must use public commands" in issue for issue in issues)
            )

    def test_eval_corpus_requires_digest_and_case_count_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / (
                "quwoquan_service/services/assistant-service/tests/support/"
                "eval_corpora/assistant.json"
            )
            corpus.parent.mkdir(parents=True)
            corpus.write_text('{"scenarios":[{"id":"one"}]}\n', encoding="utf-8")
            digest = hashlib.sha256(corpus.read_bytes()).hexdigest()
            manifest = corpus.with_name("assistant.manifest.json")
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "qwq.eval_corpus_manifest",
                        "corpusFile": corpus.name,
                        "sha256": digest,
                        "caseCount": 2,
                    }
                ),
                encoding="utf-8",
            )
            issues = collect_issues(root)
            self.assertTrue(any("caseCount drift" in issue for issue in issues))

    def test_scenario_dump_keys_are_rejected_in_app_builders_and_corpora(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builder = root / (
                "quwoquan_app/test/support/runtime/fixtures/example_builder.dart"
            )
            builder.parent.mkdir(parents=True)
            builder.write_text(
                "final document = {'seedSets': <String, Object?>{}};\n",
                encoding="utf-8",
            )
            corpus = root / (
                "quwoquan_service/services/assistant-service/tests/support/"
                "eval_corpora/assistant.json"
            )
            corpus.parent.mkdir(parents=True)
            corpus.write_text(
                '{"repositoryExpectations":{},"scenarios":[]}\n',
                encoding="utf-8",
            )
            manifest = corpus.with_name("assistant.manifest.json")
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "qwq.eval_corpus_manifest",
                        "corpusFile": corpus.name,
                        "sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                        "caseCount": 0,
                    }
                ),
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(any("in-memory builder" in issue for issue in issues))
            self.assertTrue(any("eval corpus contains retired" in issue for issue in issues))

    def test_cross_domain_object_contract_reader_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reader = root / (
                "quwoquan_app/test/support/runtime/fixtures/"
                "object_contract_example_reader.dart"
            )
            reader.parent.mkdir(parents=True)
            reader.write_text("final class Reader {}\n", encoding="utf-8")

            issues = collect_issues(root)

            self.assertTrue(
                any("fixture reader must be deleted" in issue for issue in issues)
            )

    def test_cross_domain_object_contract_reader_import_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / "quwoquan_app/test/local_contract/example.dart"
            test.parent.mkdir(parents=True)
            test.write_text(
                "import '../support/runtime/fixtures/"
                "object_contract_example_reader.dart';\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("retired cross-domain fixture reader" in issue for issue in issues)
            )

    def test_filesystem_backed_cross_domain_fixture_matrix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = root / (
                "quwoquan_app/test/support/runtime/fixtures/example_reader.dart"
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "import 'dart:io';\n"
                "Map<String, Object?> document(String domain) => {};\n"
                "Object requireExample(String domain, String id) => Object();\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("runtime filesystem" in issue for issue in issues)
            )
            self.assertTrue(
                any("named-example fixture matrix" in issue for issue in issues)
            )

    def test_retired_app_aggregate_mock_symbols_are_zero_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / "quwoquan_app/test/local_contract/example.dart"
            test.parent.mkdir(parents=True)
            test.write_text(
                "final repository = MockContentRepository(ContentMockData.all);\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("retired aggregate test-data symbol" in issue for issue in issues)
            )

    def test_aggregate_chat_repository_double_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / "quwoquan_app/test/local_contract/chat_example.dart"
            test.parent.mkdir(parents=True)
            test.write_text(
                "class LegacyChatDouble implements ChatRepository {}\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("aggregate ChatRepository test double" in issue for issue in issues)
            )

    def test_data_support_scenario_writer_and_cli_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = (
                root
                / "quwoquan_data/tests/support/entity_introduction_fixture.py"
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "document = {'seedSets': {}}\n"
                "def merge_into_scenarios(): pass\n"
                "def register_parser(subparsers): pass\n"
                "target = 'entity_scenarios.json'\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(
                any("Data test support contains retired" in issue for issue in issues)
            )
            self.assertTrue(
                any("fixture writer/CLI remains" in issue for issue in issues)
            )

    def test_retired_recipe_and_test_live_business_data_track_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retired = root / "quwoquan_ops/cli/lib/nonprod_data_provisioner.py"
            retired.parent.mkdir(parents=True)
            retired.write_text("# retired\n", encoding="utf-8")
            stackctl = root / "quwoquan_ops/cli/stackctl.py"
            stackctl.parent.mkdir(parents=True, exist_ok=True)
            stackctl.write_text(
                "flag = '--apply-business-data'\n",
                encoding="utf-8",
            )

            issues = collect_issues(root)

            self.assertTrue(any("must be deleted" in issue for issue in issues))
            self.assertTrue(any("retired test-data token" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
