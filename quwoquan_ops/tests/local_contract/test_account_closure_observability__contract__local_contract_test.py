from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]


class AccountClosureObservabilityContractTest(unittest.TestCase):
    def test_all_resource_services_declare_account_security_authority_slo(
        self,
    ) -> None:
        files = {
            "assistant-service": "account_security_authority_slo.yaml",
            "chat-service": "account_security_authority.yaml",
            "circle-service": "account_security_authority_slo.yaml",
            "content-service": "account_security_authority_slo.yaml",
            "entity-service": "account_security_authority_slo.yaml",
            "integration-service": "account_security_authority_slo.yaml",
            "notification-service": "account_security_authority_slo.yaml",
            "product-ops-service": "account_security_authority_slo.yaml",
            "realtime-gateway": "account_security_slo.yaml",
            "rtc-service": "account_security_authority_slo.yaml",
            "search-service": "account_security_authority_slo.yaml",
        }
        for service, filename in files.items():
            path = (
                ROOT
                / "quwoquan_service/services"
                / service
                / "observability/slo"
                / filename
            )
            slo = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(slo["service"], service)
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                "runtime_auth_account_security_authority_checks_total",
                source,
            )
            self.assertIn(
                "runtime_auth_account_security_authority_check_duration_seconds",
                source,
            )

    def test_all_stateful_consumers_export_canonical_metrics(self) -> None:
        metric_files = {
            "content": ROOT
            / (
                "quwoquan_service/services/content-service/internal/content/"
                "content_account_closure_workflow/infrastructure/accountclosure/metrics.go"
            ),
            "chat": ROOT
            / "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq/user_account_closed_metrics.go",
            "circle": ROOT
            / "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging/user_account_closed_metrics.go",
            "notification": ROOT
            / "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream/user_account_closed_metrics.go",
            "search": ROOT
            / "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/mq/user_account_closed_metrics.go",
        }
        for domain, path in metric_files.items():
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                f'{domain}_user_account_closed_consumer_total',
                source,
            )
            self.assertIn(
                f'{domain}_user_account_closed_cleanup_seconds',
                source,
            )

    def test_retry_dlq_and_latency_alerts_are_blocking_contracts(self) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        )
        groups = yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]
        rules = {
            rule["alert"]: rule
            for group in groups
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        retry = rules["UserAccountClosedConsumerRetrying"]
        dead_letter = rules["UserAccountClosedDeadLetterPresent"]
        latency = rules["UserAccountClosedCleanupP95High"]
        realtime_dead_letter = rules[
            "RealtimeAccountSecurityConsumerDeadLettered"
        ]
        rtc_dead_letter = rules["RtcAccountSecurityConsumerDeadLettered"]

        for rule in (retry, dead_letter, latency):
            self.assertIn("content|chat|circle|notification|search", rule["expr"])
            self.assertEqual(rule["labels"]["domain"], "user-identity")
        self.assertIn('result="retry"', retry["expr"])
        self.assertEqual(retry["labels"]["severity"], "warning")
        self.assertIn('result="dlq"', dead_letter["expr"])
        self.assertIn('result="held_for_recovery"', dead_letter["expr"])
        self.assertEqual(dead_letter["labels"]["severity"], "critical")
        for rule in (realtime_dead_letter, rtc_dead_letter):
            self.assertIn('outcome="dlq"', rule["expr"])
            self.assertIn('outcome="held_for_recovery"', rule["expr"])
            self.assertEqual(rule["labels"]["severity"], "critical")
        self.assertIn("_cleanup_seconds_bucket", latency["expr"])
        self.assertIn("> 60", latency["expr"])

    def test_authority_deny_unavailable_and_latency_alerts_are_blocking(
        self,
    ) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        )
        groups = yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]
        rules = {
            rule["alert"]: rule
            for group in groups
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        unavailable = rules["AccountSecurityAuthorityUnavailable"]
        denied = rules["AccountSecurityAuthorityDeniedSpike"]
        latency = rules["AccountSecurityAuthorityLatencyHigh"]

        for rule in (unavailable, denied, latency):
            self.assertEqual(rule["labels"]["domain"], "user-identity")
        self.assertEqual(unavailable["labels"]["severity"], "critical")
        self.assertIn('outcome="unavailable"', unavailable["expr"])
        self.assertIn("sum by (job, instance)", unavailable["expr"])
        self.assertIn("denied_token_stale", denied["expr"])
        self.assertGreaterEqual(
            denied["expr"].count("sum by (job, instance)"),
            2,
        )
        self.assertIn(
            "account_security_authority_check_duration_seconds_bucket",
            latency["expr"],
        )
        self.assertIn("sum by (le, job, instance)", latency["expr"])


if __name__ == "__main__":
    unittest.main()
