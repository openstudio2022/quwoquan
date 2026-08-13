from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import yaml

from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files
from quwoquan_ops.cli.prod import render_prod_plane_stack as render
from quwoquan_service.scripts.contracts.build_service_contract_view import (
    ContractViewSnapshot,
    build_config_views,
    contract_roots,
)


ROOT = Path(__file__).resolve().parents[4]
ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
TRAVEL_COMPOSE = (
    ROOT / "quwoquan_service/services/travel-service/deploy/compose.yaml"
)


class ProdTravelSunsetProjectionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.access = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
        cls.service_plane = next(
            item
            for item in cls.access["planes"]
            if item["plane"] == "service"
        )
    def test_travel_is_absent_from_every_service_plane_projection(self) -> None:
        prevalidation = self.access["prevalidation"]["planes"]["service"]
        self.assertNotIn("travel-service", prevalidation["startupServices"])
        self.assertNotIn(39330, prevalidation["exposedPorts"])
        for field in (
            "governedWorkloads",
            "rootlessGovernedComposeServices",
            "rootlessConfigServices",
        ):
            self.assertNotIn("travel-service", self.service_plane[field])
        bindings = {
            item["composeService"]: item["ownerWorkload"]
            for item in self.service_plane["rootlessProjectionBindings"]
        }
        self.assertNotIn("travel-service", bindings)
        self.assertEqual(
            set(self.service_plane["rootlessConfigServices"]),
            set(self.service_plane["rootlessGovernedComposeServices"]),
        )

    def test_compose_and_log_projections_reject_retired_source_tree(self) -> None:
        self.assertFalse(TRAVEL_COMPOSE.exists())
        self.assertNotIn(TRAVEL_COMPOSE, domain_service_compose_files(ROOT))
        self.assertNotIn("travel-service", render.RUNTIME_LOG_EXPORT_SERVICES)

    def test_instance_env_never_projects_travel_ports(self) -> None:
        auth = {
            key: f"test-{key.lower()}"
            for key in render.PREVALIDATION_AUTH_SECRET_KEYS
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(
                render,
                "_prevalidation_secret_environment",
                return_value=auth,
            ):
                render._write_env_file(
                    root,
                    "sha256:" + "a" * 64,
                    "candidate-tag",
                    "prevalidate",
                )
            prevalidate = (root / "stack.env").read_text(encoding="utf-8")
            render._write_env_file(
                root,
                "sha256:" + "a" * 64,
                "candidate-tag",
                "gray",
            )
            gray = (root / "stack.env").read_text(encoding="utf-8")

        self.assertNotIn("QWQ_COMPOSE_TRAVEL_PORT", prevalidate)
        self.assertIn("AUTH_JWT_SECRET=test-auth_jwt_secret", prevalidate)
        self.assertNotIn("QWQ_COMPOSE_TRAVEL_PORT", gray)
        self.assertNotIn("AUTH_JWT_SECRET=", gray)

    def test_canonical_config_view_omits_travel_service_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            build_config_views(
                ROOT,
                output,
                contract_roots(ROOT),
                ContractViewSnapshot(ROOT, output),
            )
            platform = yaml.safe_load(
                (output / "platform/config.yaml").read_text(encoding="utf-8")
            )

        keys = {entry["key"] for entry in platform["configs"]}
        self.assertFalse(
            any(key.startswith("sys.travel-service.") for key in keys)
        )

    def test_observability_drops_workload_rules_but_keeps_travel_scenario_metrics(
        self,
    ) -> None:
        workload_rules = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/travel_contract"
        )
        self.assertEqual(list(workload_rules.glob("*.yaml")), [])

        recommendation_alerts = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "recommendation_behavior_by_attribution_total", recommendation_alerts
        )
        self.assertIn('channel=~"travel|premium_stream"', recommendation_alerts)

    def test_coverage_baseline_has_no_retired_cloud_unit(self) -> None:
        baseline_path = (
            ROOT
            / "quwoquan_ops/policies/gates/canonical_coverage_baseline.json"
        )
        if not baseline_path.is_file():
            return
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

        self.assertNotIn("cloud:travel", baseline["units"])


if __name__ == "__main__":
    unittest.main()
