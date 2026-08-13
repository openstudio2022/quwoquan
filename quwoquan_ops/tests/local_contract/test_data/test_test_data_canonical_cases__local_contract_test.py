from __future__ import annotations

import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.test_data.cases import (
    assistant_prompt_case,
    assistant_skill_subscription_case,
    canonical_acceptance_suite,
    chat_group_governance_case,
    chat_recall_case,
    circle_gathering_case,
    circle_membership_case,
    circle_pending_approval_case,
    content_comments_case,
    content_reaction_case,
    notification_delivery_case,
    rtc_completed_call_case,
    user_following_subject_case,
    user_greeting_inbox_case,
    user_relationship_case,
)
from quwoquan_ops.cli.lib.test_data.capabilities.notification_service import (
    NOTIFICATION_DELIVERY,
)
from quwoquan_ops.cli.lib.test_data.serialization import (
    case_request_document,
    collect_request_graph,
    load_case_requests,
)


class TestDataCanonicalCasesContractTest(unittest.TestCase):
    def test_canonical_module_is_a_composition_root_without_business_assertions(self) -> None:
        source = (
            Path(__file__).parents[3]
            / "cli/lib/test_data/cases/canonical.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("BusinessCaseRunner", source)
        self.assertNotIn("CaseAssertion", source)
        self.assertNotIn("\nclass ", source)
        self.assertEqual(source.count("_case()"), 15)

    def test_in_app_notification_readback_has_no_external_push_prerequisite(self) -> None:
        self.assertEqual(
            NOTIFICATION_DELIVERY.required_provider_capabilities,
            (),
        )

    def test_each_domain_case_loads_only_its_typed_dependency_closure(self) -> None:
        expected = (
            (user_relationship_case(), {"user_service"}),
            (
                user_following_subject_case(),
                {"user_service", "content_service"},
            ),
            (user_greeting_inbox_case(), {"user_service"}),
            (content_comments_case(), {"user_service", "content_service"}),
            (content_reaction_case(), {"user_service", "content_service"}),
            (circle_membership_case(), {"user_service", "circle_service"}),
            (circle_gathering_case(), {"user_service", "circle_service"}),
            (
                circle_pending_approval_case(),
                {"user_service", "circle_service"},
            ),
            (chat_recall_case(), {"user_service", "chat_service"}),
            (
                chat_group_governance_case(),
                {"user_service", "chat_service"},
            ),
            (assistant_prompt_case(), {"user_service", "assistant_service"}),
            (
                assistant_skill_subscription_case(),
                {"user_service", "assistant_service"},
            ),
            (
                notification_delivery_case(),
                {"user_service", "chat_service", "notification_service"},
            ),
            (
                rtc_completed_call_case(),
                {"user_service", "chat_service", "rtc_service"},
            ),
        )
        for case, expected_owners in expected:
            with self.subTest(case=case.case_id.value):
                graph = collect_request_graph((case.request,))
                self.assertEqual(
                    {
                        request.capability.owner_service
                        for request in graph.values()
                    },
                    expected_owners,
                )

    def test_selected_cases_round_trip_without_a_string_registry(self) -> None:
        cases = canonical_acceptance_suite()
        document = case_request_document(cases)
        loaded = load_case_requests(document)

        self.assertEqual(
            [case.case_id for case in loaded],
            [case.case_id for case in cases],
        )
        self.assertEqual(len(document["cases"]), 15)
        self.assertEqual(len(document["requests"]), 39)

    def test_serialized_runner_paths_match_source_owned_physical_modules(self) -> None:
        document = case_request_document(canonical_acceptance_suite())
        expected_runner_modules = {
            "user-relationship": (
                "quwoquan_ops.cli.lib.test_data.cases.user_service"
            ),
            "user-following-subject": (
                "quwoquan_ops.cli.lib.test_data.cases.user_service"
            ),
            "user-greeting-inbox": (
                "quwoquan_ops.cli.lib.test_data.cases.user_service"
            ),
            "content-comments": (
                "quwoquan_ops.cli.lib.test_data.cases.content_service"
            ),
            "content-reaction": (
                "quwoquan_ops.cli.lib.test_data.cases.content_service"
            ),
            "content-footprint": (
                "quwoquan_ops.cli.lib.test_data.cases.content_service"
            ),
            "circle-membership": (
                "quwoquan_ops.cli.lib.test_data.cases.circle_service"
            ),
            "circle-gathering": (
                "quwoquan_ops.cli.lib.test_data.cases.circle_service"
            ),
            "circle-pending-approval": (
                "quwoquan_ops.cli.lib.test_data.cases.circle_service"
            ),
            "chat-recall": "quwoquan_ops.cli.lib.test_data.cases.chat_service",
            "chat-group-governance": (
                "quwoquan_ops.cli.lib.test_data.cases.chat_service"
            ),
            "assistant-prompt": (
                "quwoquan_ops.cli.lib.test_data.cases.assistant_service"
            ),
            "assistant-skill-subscription": (
                "quwoquan_ops.cli.lib.test_data.cases.assistant_service"
            ),
            "notification-delivery": (
                "quwoquan_ops.cli.lib.test_data.cases.notification_service"
            ),
            "rtc-completed-call": (
                "quwoquan_ops.cli.lib.test_data.cases.rtc_service"
            ),
        }

        self.assertEqual(
            {
                row["caseId"]: row["runnerModule"]
                for row in document["cases"]
            },
            expected_runner_modules,
        )
        self.assertEqual(
            {row["caseIdModule"] for row in document["cases"]},
            {"quwoquan_ops.cli.lib.test_data.cases.ids"},
        )
        self.assertNotIn(
            "quwoquan_ops.cli.lib.test_data.cases.canonical",
            {
                value
                for row in document["cases"]
                for value in (row["caseIdModule"], row["runnerModule"])
            },
        )
        self.assertEqual(
            [case.case_id.value for case in load_case_requests(document)],
            [row["caseId"] for row in document["cases"]],
        )

    def test_canonical_suite_serialization_is_byte_stable(self) -> None:
        first = case_request_document(canonical_acceptance_suite())
        second = case_request_document(canonical_acceptance_suite())

        self.assertEqual(first, second)
        self.assertEqual(first["requestDigest"], second["requestDigest"])
        self.assertEqual(
            [row["requestId"] for row in first["requests"]],
            [f"request-{index:06d}" for index in range(1, 40)],
        )


if __name__ == "__main__":
    unittest.main()
