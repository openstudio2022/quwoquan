#!/usr/bin/env python3
"""Tests for es_cli triage fallback and API preference.

Run: python3 quwoquan_service/scripts/runtime/observability/test_es_cli.py
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("es_cli", _HERE / "es_cli.py")
assert _SPEC and _SPEC.loader
es_cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(es_cli)


class EsCliTriageTests(unittest.TestCase):
    def test_triage_prefers_control_plane_api(self) -> None:
        buffer = io.StringIO()
        with (
            patch.dict(os.environ, {"PRODUCT_OPS_BASE_URL": "http://product.test"}, clear=False),
            patch.object(
                es_cli,
                "query_control_plane_triage",
                return_value={
                    "backlogCandidates": [
                        {
                            "id": "product-l1l4-card-gap",
                            "category": "metric_gap",
                            "severity": "warning",
                            "title": "补齐四层指标注册表",
                            "nextAction": "打开 /product/l1-l4/environment 补齐缺失层级指标",
                            "runbookRoute": "/platform/runbook",
                            "repairEntry": "/product/l1-l4/environment",
                            "alertId": "HighP95Latency",
                        }
                    ]
                },
            ),
            patch.object(sys, "argv", ["es_cli.py", "triage", "--domain", "product", "--output", "markdown"]),
            redirect_stdout(buffer),
        ):
            self.assertEqual(es_cli.main(), 0)
        out = buffer.getvalue()
        self.assertIn("# product triage", out)
        self.assertIn("补齐四层指标注册表", out)
        self.assertIn("打开 /product/l1-l4/environment", out)
        self.assertIn("runbook=/platform/runbook", out)
        self.assertIn("repair=/product/l1-l4/environment", out)
        self.assertIn("alert=HighP95Latency", out)

    def test_triage_falls_back_to_es_manual_report(self) -> None:
        buffer = io.StringIO()
        with (
            patch.dict(os.environ, {"PLATFORM_OPS_BASE_URL": ""}, clear=False),
            patch.object(es_cli, "query_control_plane_triage", return_value=None),
            patch.object(
                es_cli,
                "query_report_docs",
                return_value=[
                    {
                        "occurredAt": "2026-06-07T08:00:00Z",
                        "errorCode": "OPS.NETWORK.fetch_failed",
                        "requestId": "req-1",
                        "traceId": "trace-1",
                        "failurePoint": "service.http",
                        "stackHash": "stack-1",
                        "businessObject": "event_record",
                        "functionModule": "observability",
                        "nature": "bug",
                    }
                ],
            ),
            patch.object(
                sys,
                "argv",
                ["es_cli.py", "triage", "--domain", "platform", "--env", "beta", "--output", "markdown"],
            ),
            redirect_stdout(buffer),
        ):
            self.assertEqual(es_cli.main(), 0)
        out = buffer.getvalue()
        self.assertIn("# 异常日报", out)
        self.assertIn("OPS.NETWORK.fetch_failed", out)

    def test_triage_json_emits_stable_repair_contract(self) -> None:
        buffer = io.StringIO()
        with (
            patch.dict(os.environ, {"PLATFORM_OPS_BASE_URL": "http://platform.test"}, clear=False),
            patch.object(
                es_cli,
                "query_control_plane_triage",
                return_value={
                    "backlogCandidates": [
                        {
                            "id": "platform-config-drift-content-service",
                            "category": "config_drift",
                            "severity": "critical",
                            "title": "修复 content-service 的配置漂移",
                            "nextAction": "打开 /platform/config/drift 对比 desiredHash 与 effectiveHash",
                            "drilldownRoute": "/platform/config/drift",
                            "runbookRoute": "/platform/runbook",
                            "repairEntry": "/platform/rollout",
                            "alertId": "config_release_error_rate",
                        }
                    ]
                },
            ),
            patch.object(sys, "argv", ["es_cli.py", "triage", "--domain", "platform", "--output", "json"]),
            redirect_stdout(buffer),
        ):
            self.assertEqual(es_cli.main(), 0)
        out = buffer.getvalue()
        self.assertIn('"backlogCandidates"', out)
        self.assertIn('"runbookRoute": "/platform/runbook"', out)
        self.assertIn('"repairEntry": "/platform/rollout"', out)
        self.assertIn('"alertId": "config_release_error_rate"', out)


if __name__ == "__main__":
    unittest.main()
