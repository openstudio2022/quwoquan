from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]


class RelationshipObservabilityContractTest(unittest.TestCase):
    def test_dashboard_covers_relationship_greeting_and_discovery(self) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/dashboards/l2_relationship_commercial.json"
        )
        dashboard = json.loads(path.read_text(encoding="utf-8"))["dashboard"]
        self.assertEqual(
            dashboard["uid"],
            "qwq-l2-relationship-commercial",
        )
        expressions = "\n".join(
            target["expr"]
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        )
        for required in (
            "http_server_requests_total",
            "http_server_error_codes_total",
            "greeting-request",
            "contact-discovery",
            "following-subjects",
            "quwoquan_persona_relationship_command_latency_ms_bucket",
            "quwoquan_persona_relationship_list_latency_ms_bucket",
            "quwoquan_persona_relationship_counter_projection_lag_ms_bucket",
            "quwoquan_persona_relationship_events_total",
            "quwoquan_profile_subject_public_read_latency_ms_bucket",
            "quwoquan_profile_subject_events_total",
            "quwoquan_persona_switch_latency_ms_bucket",
            "quwoquan_persona_rollout_events_total",
        ):
            self.assertIn(required, expressions)

        text = "\n".join(
            str(panel.get("options", {}).get("content", ""))
            for panel in dashboard["panels"]
        )
        self.assertIn("product_action", text)
        self.assertIn("禁止", text)

    def test_relationship_alerts_keep_contract_thresholds(self) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        )
        groups = yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]
        group = next(
            item
            for item in groups
            if item["name"] == "quwoquan_l2_relationship_objects"
        )
        rules = {item["alert"]: item for item in group["rules"]}
        self.assertEqual(
            set(rules),
            {
                "PersonaFollowCommandErrorRateHigh",
                "PersonaRelationshipCommandLatencyHigh",
                "PersonaRelationshipCounterProjectionLagHigh",
                "PersonaRelationshipConsistencyMismatchDetected",
                "ProfileSubjectReadLatencyHigh",
                "PersonaSwitchLatencyHigh",
                "SubjectFollowCommandErrorRateHigh",
                "FollowingSubjectReadErrorRateHigh",
                "GreetingCommandErrorRateHigh",
            },
        )
        self.assertIn("> 0.02", rules["PersonaFollowCommandErrorRateHigh"]["expr"])
        self.assertIn(
            "> 500",
            rules["PersonaRelationshipCommandLatencyHigh"]["expr"],
        )
        self.assertIn(
            "> 5000",
            rules["PersonaRelationshipCounterProjectionLagHigh"]["expr"],
        )
        self.assertIn(
            "> 0",
            rules["PersonaRelationshipConsistencyMismatchDetected"]["expr"],
        )
        self.assertIn("> 500", rules["ProfileSubjectReadLatencyHigh"]["expr"])
        self.assertIn("> 1500", rules["PersonaSwitchLatencyHigh"]["expr"])
        self.assertIn("> 0.02", rules["SubjectFollowCommandErrorRateHigh"]["expr"])
        self.assertIn("> 0.05", rules["FollowingSubjectReadErrorRateHigh"]["expr"])
        self.assertIn("> 0.02", rules["GreetingCommandErrorRateHigh"]["expr"])
        for rule in rules.values():
            self.assertEqual(rule["for"], "10m")
            self.assertEqual(rule["labels"]["domain"], "user-relationship")

    def test_profile_pages_use_route_lifecycle_and_do_not_double_count(self) -> None:
        app_pages_path = (
            ROOT
            / "quwoquan_service/contracts/metadata/_shared/app_pages.yaml"
        )
        pages = yaml.safe_load(app_pages_path.read_text(encoding="utf-8"))["pages"]
        by_name = {item["page_name"]: item for item in pages}
        for page_name in ("profile_edit", "my_intersections", "my_qr_code"):
            self.assertTrue(by_name[page_name]["collect_page_access"])

        edit_source = (
            ROOT
            / "quwoquan_app/lib/ui/user/pages/edit_profile_page_sections.dart"
        ).read_text(encoding="utf-8")
        qr_source = (
            ROOT / "quwoquan_app/lib/ui/user/pages/my_qr_code_page.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("action: 'enter'", edit_source)
        self.assertNotIn("action: 'exit'", edit_source)
        self.assertNotIn("enter_my_qr_code", qr_source)
        self.assertNotIn("exit_my_qr_code", qr_source)
        self.assertIn("action: 'open_scanner_from_my_qr'", qr_source)

    def test_contact_tab_records_filter_and_open_actions(self) -> None:
        recorder = (
            ROOT
            / "quwoquan_app/lib/ui/chat/pages/chat_page_visit_recorder.dart"
        ).read_text(encoding="utf-8")
        page = (
            ROOT / "quwoquan_app/lib/ui/chat/pages/chat_page_state.dart"
        ).read_text(encoding="utf-8")
        self.assertIn("action: 'view_contact_filter'", recorder)
        self.assertIn("action: 'open_contact'", page)
        self.assertIn("journey: 'relationship'", recorder)
        self.assertIn("journey: 'relationship'", page)


if __name__ == "__main__":
    unittest.main()
