"""N2-5 契约：prod gray readback 的推荐业务指标与发布 profile 的推荐旅程。

历史断裂：prod gray readback 只有基础设施指标（error_rate/p95/redis），
推荐质量退化（空 feed / 负反馈暴涨）不阻断放量；home_recommendation_journey
patrol 无自动执行点。

防回归断言：
 1. slo_thresholds.yaml 声明 recommendation readback 段（含 critical 阈值）；
 2. stackctl 的推荐 readback 查询只引用真实 emitter 指标名
    （与 runtime/recommendation/observability.go 对齐，杜绝死查询）；
 3. release_candidate / nightly_full profile 必须包含
    home_recommendation_journey_patrol 旅程。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
import unittest
from unittest import mock

import yaml

from quwoquan_ops.cli import stackctl

ROOT = Path(__file__).resolve().parents[4]

# 与 recommendation_alert_metric_existence__local_contract_test.go 的注册表同源。
REGISTERED_REC_METRICS = {
    "rec_pipeline_requests_total",
    "rec_pipeline_empty_results_total",
    "recommendation_feed_negative_feedback_total",
    "recommendation_feed_impressed_total",
    "recommendation_feed_engagement_total",
}

REC_METRIC_PATTERN = re.compile(r"\b(rec_[a-z0-9_]+|recommendation_[a-z0-9_]+)\b")


class ProdGrayRecommendationReadbackContractTest(unittest.TestCase):
    def test_slo_policy_declares_recommendation_readback(self) -> None:
        policy = yaml.safe_load(
            (ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml").read_text(
                encoding="utf-8"
            )
        )
        rec = policy["readback"]["recommendation"]
        self.assertEqual(rec["service"], "content-service")
        self.assertGreater(float(rec["empty_feed_rate"]["critical"]), 0)
        self.assertGreater(float(rec["negative_feedback_rate"]["critical"]), 0)
        self.assertGreater(int(rec["min_impressions"]), 0)

    def test_stackctl_readback_queries_use_registered_metrics(self) -> None:
        # 观察真实行为而不是扫源码：readback 回执自带 queries 段，
        # 直接读它就不会随函数迁移（stackctl -> commands/**）而断。
        policy = yaml.safe_load(
            (ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml").read_text(
                encoding="utf-8"
            )
        )
        rec_policy = policy["readback"]["recommendation"]
        with mock.patch.object(
            stackctl, "_prometheus_query_value", return_value=0.0
        ) as query_value:
            readback = stackctl._read_recommendation_slo(
                "http://127.0.0.1:9090",
                rec_policy["service"],
                "5m",
                rec_policy,
                deadline_epoch=int(time.time()) + 60,
            )
        self.assertIsNotNone(readback, "推荐 readback 函数缺失或未对策略服务生效（N2-5 回归）")
        queries = readback["queries"]
        self.assertTrue(queries)
        # 每条查询都真的发到 Prometheus，不允许只声明不执行。
        self.assertEqual(len(query_value.call_args_list), len(queries))
        body = "\n".join(queries.values())
        for metric in REC_METRIC_PATTERN.findall(body):
            self.assertIn(
                metric,
                REGISTERED_REC_METRICS,
                f"推荐 readback 引用了未注册指标 {metric}（死查询——先在 "
                "runtime/recommendation 注册 emitter 再登记）",
            )
        # 关键分子/分母必须在查询里出现（防止查询整段被删空）。
        self.assertIn("rec_pipeline_empty_results_total", body)
        self.assertIn("recommendation_feed_negative_feedback_total", body)
        self.assertIn("recommendation_feed_impressed_total", body)

    def test_release_profiles_include_recommendation_journey(self) -> None:
        suites = json.loads(
            (ROOT / "quwoquan_ops/environments/gamma/validation_suites.json").read_text(
                encoding="utf-8"
            )
        )
        journeys = suites["uiJourneys"]
        self.assertIn(
            "home_recommendation_journey_patrol",
            journeys,
            "推荐主链路旅程必须登记在 uiJourneys",
        )
        for profile_name in ("release_candidate", "nightly_full"):
            profile = suites["profiles"][profile_name]
            self.assertIn(
                "home_recommendation_journey_patrol",
                profile.get("uiJourneys", []),
                f"{profile_name} profile 必须执行推荐主链路 patrol（N2-5）",
            )


if __name__ == "__main__":
    unittest.main()
