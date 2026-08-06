"""verify_object_alert_coverage 的判定口径合约。

覆盖 domain-agnostic 行为：域参数只从 contracts/domain.yaml 推导、ready operation
必须同时被 alerting rule 与 dashboard 消费、注释不计证据、blocked operation 不误伤、
对象改名后的死 selector 必须阻断。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_service/scripts/verify/verify_object_alert_coverage.py"
SPEC = importlib.util.spec_from_file_location("verify_object_alert_coverage", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage
SPEC.loader.exec_module(coverage)

MONITORING = ROOT / "quwoquan_ops/observability/monitoring"


def operation(
    domain: str = "content",
    object_name: str = "post",
    local_id: str = "GetPost",
    status: str = "ready",
    metric: str = "content_post_get",
) -> dict[str, object]:
    return {
        "id": f"{domain}.{object_name}.{local_id}",
        "domain": domain,
        "objectId": f"{domain}.{object_name}",
        "method": "GET",
        "pathTemplate": f"/{domain}/{object_name}s/{{id}}",
        "commercial": {"status": status, "explicit": True, "gapId": "GAP_X"},
        "telemetry": {"metric": metric, "trace": True},
        "slo": {"latencyP95Milliseconds": 500, "availabilityPercent": 99.9},
    }


class ObjectAlertCoverageContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.services = self.root / "services"
        self.alerts = self.root / "alerts"
        self.dashboards = self.root / "dashboards"
        self.addCleanup(self._directory.cleanup)

    def write_service(self, service: str, domain: str) -> None:
        path = self.services / service / "contracts" / "domain.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"domain: {domain}\n", encoding="utf-8")

    def write_graph(
        self,
        operations: list[dict[str, object]],
        extra_objects: list[dict[str, object]] | None = None,
        runtime_entrypoints: list[dict[str, object]] | None = None,
    ) -> Path:
        path = self.root / "contract_graph.json"
        objects = [
            {"id": object_id, "domain": object_id.split(".", maxsplit=1)[0], "kind": "aggregate"}
            for object_id in sorted({str(item["objectId"]) for item in operations})
        ]
        objects.extend(extra_objects or [])
        path.write_text(
            json.dumps(
                {
                    "objects": objects,
                    "operations": operations,
                    "runtimeEntrypoints": runtime_entrypoints or [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def verify(self, graph: Path, check_drift: bool = False) -> coverage.VerificationReport:
        return coverage.verify_coverage(
            contract_graph=graph,
            alerts_root=self.alerts,
            dashboards_root=self.dashboards,
            services_root=self.services,
            prometheus_config=None,
            check_drift=check_drift,
        )

    def write_consumers(self, domain: str, service: str) -> None:
        """把域内 ready operation 同时接入 alerting rule 与 dashboard。"""
        request_metric, duration_metric = coverage.record_metrics(domain)
        selector = coverage.domain_ready_selector(domain, service)
        self.alerts.mkdir(parents=True, exist_ok=True)
        (self.alerts / "coverage.yaml").write_text(
            yaml.safe_dump(
                {
                    "groups": [
                        {
                            "name": f"{domain}_coverage",
                            "rules": [
                                {
                                    "alert": "Availability",
                                    "expr": (
                                        f'sum(rate({request_metric}{{{selector},'
                                        'status=~"5.."}[10m])) > 0'
                                    ),
                                },
                                {
                                    "alert": "Latency",
                                    "expr": (
                                        "histogram_quantile(0.95, sum(rate("
                                        f"{duration_metric}{{{selector}}}[5m])) by (le)) > 1"
                                    ),
                                },
                            ],
                        }
                    ]
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        self.dashboards.mkdir(parents=True, exist_ok=True)
        (self.dashboards / f"{domain}.json").write_text(
            json.dumps(
                {
                    "dashboard": {
                        "panels": [
                            {
                                "targets": [
                                    {"expr": f"rate({request_metric}{{{selector}}}[5m])"},
                                    {
                                        "expr": (
                                            "histogram_quantile(0.95, rate("
                                            f"{duration_metric}{{{selector}}}[5m]))"
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

    def test_domain_without_service_owner_is_blocked(self) -> None:
        self.write_service("content-service", "content")
        graph = self.write_graph([operation(domain="travel", object_name="trip_plan")])

        report = self.verify(graph)

        self.assertTrue(
            any("没有服务 contracts/domain.yaml 归属" in issue for issue in report.issues),
            report.issues,
        )

    def test_ready_operation_without_recording_rule_is_blocked(self) -> None:
        self.write_service("content-service", "content")
        graph = self.write_graph([operation()])
        self.alerts.mkdir(parents=True, exist_ok=True)
        (self.alerts / "comments_only.yaml").write_text(
            "groups:\n"
            "  - name: comments_only\n"
            "    rules:\n"
            "      - alert: PretendCoverage\n"
            "        expr: vector(1)\n"
            "        annotations:\n"
            "          description: content.post.GetPost content_post_get\n",
            encoding="utf-8",
        )

        report = self.verify(graph)

        self.assertTrue(
            any("缺少 availability recording rule" in issue for issue in report.issues),
            report.issues,
        )
        self.assertTrue(
            any("缺少 latency_p95 recording rule" in issue for issue in report.issues),
            report.issues,
        )

    def test_dashboard_only_coverage_is_blocked(self) -> None:
        """entity 域曾要求真实 alerting rule；泛化后所有域都必须有告警而不只有看板。"""
        self.write_service("content-service", "content")
        operations = [operation()]
        graph = self.write_graph(operations)
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)
        (self.alerts / coverage.COVERAGE_ALERTS_NAME).write_text(
            "groups: []\n", encoding="utf-8"
        )

        report = self.verify(graph)

        self.assertTrue(
            any("未被 alerting rule PromQL 消费" in issue for issue in report.issues),
            report.issues,
        )
        self.assertFalse(
            any("未被 dashboard PromQL 消费" in issue for issue in report.issues),
            report.issues,
        )

    def test_generated_artifacts_cover_every_ready_operation(self) -> None:
        self.write_service("content-service", "content")
        self.write_service("entity-service", "entity")
        graph = self.write_graph(
            [
                operation(),
                operation(
                    domain="entity",
                    object_name="homepage",
                    local_id="GetHomepage",
                    metric="entity_homepage_get",
                ),
            ]
        )
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)

        report = self.verify(graph, check_drift=True)

        self.assertEqual(report.ready_operations, 2)
        self.assertEqual(report.issues, ())

    def test_blocked_operation_is_classified_without_alert_requirement(self) -> None:
        self.write_service("travel-service", "travel")
        graph = self.write_graph(
            [
                operation(
                    domain="travel",
                    object_name="trip_plan",
                    local_id="GetTripPlan",
                    status="blocked",
                    metric="travel_trip_plan_get",
                )
            ]
        )
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)

        report = self.verify(graph, check_drift=True)

        self.assertEqual(report.ready_operations, 0)
        self.assertEqual(report.issues, ())
        self.assertEqual(report.domains[0].blocked_by_gap, (("GAP_X", 1),))

    def test_stale_operation_selector_is_blocked(self) -> None:
        self.write_service("content-service", "content")
        graph = self.write_graph([operation(status="blocked")])
        self.alerts.mkdir(parents=True, exist_ok=True)
        request_metric, _ = coverage.record_metrics("content")
        (self.alerts / "stale.yaml").write_text(
            "groups:\n"
            "  - name: stale\n"
            "    rules:\n"
            "      - alert: StaleObjectOwner\n"
            "        expr: |\n"
            f'          sum(rate({request_metric}{{operation="content.legacy_post.GetPost",'
            'contract_metric="content_post_get"}[5m])) > 0\n',
            encoding="utf-8",
        )

        report = self.verify(graph)

        self.assertTrue(
            any(
                "不匹配 ContractGraph 中任何 content operation" in issue
                for issue in report.issues
            ),
            report.issues,
        )

    def test_object_without_any_contract_surface_is_blocked(self) -> None:
        """对象分母是 ContractGraph 全集；既无 operation 又无 runtimeEntrypoint 必须阻断。"""
        self.write_service("content-service", "content")
        graph = self.write_graph(
            [operation()],
            extra_objects=[
                {"id": "content.orphan_view", "domain": "content", "kind": "projection"}
            ],
        )

        report = self.verify(graph)

        self.assertTrue(
            any(
                "既没有 operation 也没有 runtimeEntrypoint" in issue for issue in report.issues
            ),
            report.issues,
        )
        classifications = {
            surface.object_id: surface.classification for surface in report.object_surfaces
        }
        self.assertEqual(
            classifications["content.orphan_view"], coverage.OBJECT_SURFACE_NONE
        )

    def test_runtime_surface_only_object_is_classified_not_exempted(self) -> None:
        """无 HTTP operation 的 runtime 对象按 kind/契约面判定，一旦声明 telemetry 即要求覆盖。"""
        self.write_service("content-service", "content")
        runtime_object = {
            "id": "content.feed_delivery_page",
            "domain": "content",
            "kind": "append_only_fact",
        }
        entrypoint = {
            "id": "content.feed_delivery_page.ProjectFeedDeliveryPage",
            "domain": "content",
            "objectId": "content.feed_delivery_page",
            "runtimeKind": "projector",
        }
        graph = self.write_graph(
            [operation()], extra_objects=[runtime_object], runtime_entrypoints=[entrypoint]
        )
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)

        report = self.verify(graph, check_drift=True)
        classifications = {
            surface.object_id: surface.classification for surface in report.object_surfaces
        }

        self.assertEqual(
            classifications["content.feed_delivery_page"],
            coverage.OBJECT_SURFACE_RUNTIME_ONLY,
        )
        self.assertEqual(report.issues, ())

        graph = self.write_graph(
            [operation()],
            extra_objects=[runtime_object],
            runtime_entrypoints=[
                {**entrypoint, "telemetry": {"metric": "content_feed_delivery_page_project"}}
            ],
        )

        report = self.verify(graph, check_drift=True)

        self.assertTrue(
            any(
                "runtimeEntrypoint telemetry.metric" in issue
                and "未被 alert/dashboard PromQL 消费" in issue
                for issue in report.issues
            ),
            report.issues,
        )

    def test_internal_service_principal_operation_is_not_exempted(self) -> None:
        """/internal/ + principal: service 的服务间 operation 与 App 面 operation 同等要求。"""
        self.write_service("assistant-service", "assistant")
        internal = operation(
            domain="assistant",
            object_name="assistant_learning_fact",
            local_id="AppendAssistantServiceLearningFact",
            metric="assistant_learning_fact_append",
        )
        internal["method"] = "POST"
        internal["pathTemplate"] = "/internal/assistant/learning/facts"
        internal["principal"] = "service"
        graph = self.write_graph([internal])

        report = self.verify(graph)

        self.assertEqual(report.ready_operations, 1)
        self.assertTrue(
            any("缺少 availability recording rule" in issue for issue in report.issues),
            report.issues,
        )

    def _write_extra_alert(self, expr: str, **rule: object) -> None:
        self.alerts.mkdir(parents=True, exist_ok=True)
        (self.alerts / "extra.yaml").write_text(
            yaml.safe_dump(
                {
                    "groups": [
                        {
                            "name": "extra",
                            "rules": [{"alert": "Extra", "expr": expr, **rule}],
                        }
                    ]
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

    def test_contract_metric_used_as_series_name_is_blocked(self) -> None:
        """telemetry.metric 是契约层逻辑标识；放在 series 位置且无同名 series 即 BLOCK。"""
        self.write_service("content-service", "content")
        graph = self.write_graph([operation()])
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)
        self._write_extra_alert('sum(rate(content_post_get{status=~"5.."}[5m])) > 0')

        report = self.verify(graph)

        self.assertTrue(
            any(
                "当作 series 名消费" in issue and "content_post_get" in issue
                for issue in report.issues
            ),
            report.issues,
        )

    def test_contract_metric_as_label_value_and_annotation_text_are_allowed(self) -> None:
        """label 形式是唯一合法消费形式；annotation 文本既不计证据也不触发 BLOCK。"""
        self.write_service("content-service", "content")
        graph = self.write_graph([operation()])
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)
        request_metric, _ = coverage.record_metrics("content")
        self._write_extra_alert(
            f'sum(rate({request_metric}{{contract_metric="content_post_get"}}[5m])) > 0',
            annotations={"description": "metric content_post_get 退化"},
        )

        report = self.verify(graph, check_drift=True)

        self.assertEqual(report.issues, ())
        self.assertEqual(report.declared_metrics, 1)
        self.assertEqual(report.emitted_metrics, ())

    def test_series_name_is_allowed_when_a_service_really_registers_it(self) -> None:
        """例外只有可判定的一条：确实有服务注册同名 series。判据现场扫描实现代码。"""
        self.write_service("content-service", "content")
        graph = self.write_graph([operation()])
        contracts = coverage.load_operations(graph, coverage.load_domain_services(self.services))
        coverage.write_generated_documents(contracts, self.alerts, self.dashboards)
        self._write_extra_alert('sum(rate(content_post_get{status=~"5.."}[5m])) > 0')
        emitter = self.services / "content-service" / "internal" / "metrics.go"
        emitter.parent.mkdir(parents=True, exist_ok=True)
        emitter.write_text(
            "package internal\n\n"
            "var c = promauto.NewCounterVec(prometheus.CounterOpts{\n"
            '\tName: "content_post_get",\n'
            '\tHelp: "real series",\n'
            "})\n",
            encoding="utf-8",
        )

        report = self.verify(graph, check_drift=True)

        self.assertEqual(report.issues, ())
        self.assertEqual(report.emitted_metrics, ("content_post_get",))

    def test_prometheus_loads_generated_contract_rules(self) -> None:
        prometheus = yaml.safe_load((MONITORING / "prometheus.yml").read_text(encoding="utf-8"))
        self.assertIn(coverage.PROMETHEUS_RULE_GLOB, prometheus["rule_files"])
        self.assertIn(coverage.PROMETHEUS_COVERAGE_RULE, prometheus["rule_files"])

        compose = yaml.safe_load(
            (MONITORING / "docker-compose.prod.yml").read_text(encoding="utf-8")
        )
        self.assertIn(
            "./alerts:/etc/prometheus/rules:ro",
            compose["services"]["prometheus"]["volumes"],
        )


if __name__ == "__main__":
    unittest.main()
