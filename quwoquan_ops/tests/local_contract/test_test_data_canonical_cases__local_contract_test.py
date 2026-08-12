from __future__ import annotations

import unittest

from quwoquan_ops.cli.lib.test_data.cases import (
    assistant_prompt_case,
    canonical_acceptance_suite,
    chat_recall_case,
    circle_membership_case,
    content_comments_case,
    notification_delivery_case,
    rtc_completed_call_case,
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
    def test_in_app_notification_readback_has_no_external_push_prerequisite(self) -> None:
        self.assertEqual(
            NOTIFICATION_DELIVERY.required_provider_capabilities,
            (),
        )

    def test_each_domain_case_loads_only_its_typed_dependency_closure(self) -> None:
        expected = (
            (user_relationship_case(), {"user_service"}),
            (content_comments_case(), {"user_service", "content_service"}),
            (circle_membership_case(), {"user_service", "circle_service"}),
            (chat_recall_case(), {"user_service", "chat_service"}),
            (assistant_prompt_case(), {"user_service", "assistant_service"}),
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
        self.assertEqual(len(document["cases"]), 7)
        self.assertEqual(len(document["requests"]), 17)

    def test_canonical_suite_serialization_is_byte_stable(self) -> None:
        first = case_request_document(canonical_acceptance_suite())
        second = case_request_document(canonical_acceptance_suite())

        self.assertEqual(first, second)
        self.assertEqual(first["requestDigest"], second["requestDigest"])
        self.assertEqual(
            [row["requestId"] for row in first["requests"]],
            [f"request-{index:06d}" for index in range(1, 18)],
        )


if __name__ == "__main__":
    unittest.main()
