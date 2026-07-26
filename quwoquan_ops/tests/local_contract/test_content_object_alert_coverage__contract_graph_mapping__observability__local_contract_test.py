from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service/scripts/verify/verify_content_object_alert_coverage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_content_object_alert_coverage",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage
SPEC.loader.exec_module(coverage)


def operation(status: str) -> dict[str, object]:
    return {
        "id": "content.post.GetPost",
        "domain": "content",
        "objectId": "content.post",
        "method": "GET",
        "pathTemplate": "/content/content/posts/{postId}",
        "commercial": {"status": status, "explicit": True},
        "telemetry": {"metric": "content_post_get", "trace": True},
        "slo": {
            "latencyP95Milliseconds": 500,
            "availabilityPercent": 99.9,
        },
    }


class ContentObjectAlertCoverageTest(unittest.TestCase):
    def write_graph(self, root: Path, status: str) -> Path:
        path = root / "contract_graph.json"
        path.write_text(
            json.dumps({"operations": [operation(status)]}),
            encoding="utf-8",
        )
        return path

    def test_missing_ready_operation_is_blocked_and_comments_do_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = self.write_graph(root, "ready")
            alerts = root / "alerts"
            alerts.mkdir()
            (alerts / "comments_only.yaml").write_text(
                """
groups:
  - name: comments_only
    rules:
      - alert: PretendCoverage
        expr: vector(1)
        annotations:
          description: content.post.GetPost content_post_get
""",
                encoding="utf-8",
            )

            report = coverage.verify_coverage(
                graph,
                alerts,
                root / "dashboards",
            )

            self.assertTrue(report.issues)
            self.assertTrue(
                any("availability recording rule" in issue for issue in report.issues)
            )
            self.assertTrue(
                any("latency_p95 recording rule" in issue for issue in report.issues)
            )

    def test_ready_operation_is_covered_by_mapped_promql(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = self.write_graph(root, "ready")
            alerts = root / "alerts"
            dashboards = root / "dashboards"
            content_operations = coverage.load_content_operations(graph)
            coverage.write_recording_rule_files(
                content_operations,
                alerts / "content_contract",
            )
            dashboards.mkdir()
            (dashboards / "content.json").write_text(
                json.dumps(
                    {
                        "dashboard": {
                            "panels": [
                                {
                                    "targets": [
                                        {
                                            "expr": (
                                                "rate("
                                                f"{coverage.REQUEST_RECORD_METRIC}"
                                                '{operation="content.post.GetPost",'
                                                'contract_metric="content_post_get"}'
                                                "[5m])"
                                            )
                                        },
                                        {
                                            "expr": (
                                                "histogram_quantile(0.95, rate("
                                                f"{coverage.DURATION_RECORD_METRIC}"
                                                '{operation="content.post.GetPost",'
                                                'contract_metric="content_post_get"}'
                                                "[5m]))"
                                            )
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            report = coverage.verify_coverage(graph, alerts, dashboards)

            self.assertEqual(report.ready_operations, 1)
            self.assertEqual(report.issues, ())

    def test_blocked_operation_does_not_require_mapping_or_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = self.write_graph(root, "blocked")

            report = coverage.verify_coverage(
                graph,
                root / "alerts",
                root / "dashboards",
            )

            self.assertEqual(report.content_operations, 1)
            self.assertEqual(report.ready_operations, 0)
            self.assertEqual(report.issues, ())

    def test_consumer_selector_with_stale_object_id_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = self.write_graph(root, "blocked")
            alerts = root / "alerts"
            alerts.mkdir()
            (alerts / "stale_operation.yaml").write_text(
                f"""
groups:
  - name: stale_operation
    rules:
      - alert: StaleObjectOwner
        expr: |
          sum(rate({coverage.REQUEST_RECORD_METRIC}{{
            operation="content.legacy_post.GetPost",
            contract_metric="content_post_get"
          }}[5m])) > 0
""",
                encoding="utf-8",
            )

            report = coverage.verify_coverage(
                graph,
                alerts,
                root / "dashboards",
            )

            self.assertTrue(
                any(
                    "不匹配 ContractGraph 中任何 content operation" in issue
                    for issue in report.issues
                )
            )

    def test_prometheus_loads_generated_content_contract_rules(self) -> None:
        monitoring = ROOT / "quwoquan_ops/observability/monitoring"
        prometheus = yaml.safe_load(
            (monitoring / "prometheus.yml").read_text(encoding="utf-8")
        )
        self.assertIn(
            "/etc/prometheus/rules/content_contract/*.yaml",
            prometheus["rule_files"],
        )

        compose = yaml.safe_load(
            (monitoring / "docker-compose.prod.yml").read_text(encoding="utf-8")
        )
        self.assertIn(
            "./alerts:/etc/prometheus/rules:ro",
            compose["services"]["prometheus"]["volumes"],
        )


if __name__ == "__main__":
    unittest.main()
