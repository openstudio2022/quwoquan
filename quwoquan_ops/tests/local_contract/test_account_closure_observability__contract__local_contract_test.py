from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]


class AccountClosureObservabilityContractTest(unittest.TestCase):
    def test_all_stateful_consumers_export_canonical_metrics(self) -> None:
        metric_files = {
            "content": ROOT
            / "quwoquan_service/services/content-service/internal/infrastructure/accountclosure/metrics.go",
            "chat": ROOT
            / "quwoquan_service/services/chat-service/internal/adapters/mq/user_account_closed_metrics.go",
            "circle": ROOT
            / "quwoquan_service/services/circle-service/internal/infrastructure/messaging/user_account_closed_metrics.go",
            "notification": ROOT
            / "quwoquan_service/services/notification-service/internal/adapters/stream/user_account_closed_metrics.go",
            "search": ROOT
            / "quwoquan_service/services/search-service/internal/adapters/mq/user_account_closed_metrics.go",
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

        for rule in (retry, dead_letter, latency):
            self.assertIn("content|chat|circle|notification|search", rule["expr"])
            self.assertEqual(rule["labels"]["domain"], "user-identity")
        self.assertIn('result="retry"', retry["expr"])
        self.assertEqual(retry["labels"]["severity"], "warning")
        self.assertIn('result="dlq"', dead_letter["expr"])
        self.assertEqual(dead_letter["labels"]["severity"], "critical")
        self.assertIn("_cleanup_seconds_bucket", latency["expr"])
        self.assertIn("> 60", latency["expr"])


if __name__ == "__main__":
    unittest.main()
