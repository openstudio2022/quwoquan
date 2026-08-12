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
                        "schema": "qwq.eval_corpus_manifest.v1",
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
                        "schema": "qwq.eval_corpus_manifest.v1",
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
