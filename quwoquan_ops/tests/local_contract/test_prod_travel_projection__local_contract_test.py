from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest import mock

import yaml

from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files
from quwoquan_ops.cli.prod import render_prod_plane_stack as render


ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
TRAVEL_COMPOSE = (
    ROOT / "quwoquan_service/services/travel-service/deploy/compose.yaml"
)


class ProdTravelProjectionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.access = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
        cls.service_plane = next(
            item
            for item in cls.access["planes"]
            if item["plane"] == "service"
        )
        cls.travel = yaml.safe_load(
            TRAVEL_COMPOSE.read_text(encoding="utf-8")
        )["services"]["travel-service"]

    def test_travel_is_in_every_service_plane_projection(self) -> None:
        prevalidation = self.access["prevalidation"]["planes"]["service"]
        self.assertIn("travel-service", prevalidation["startupServices"])
        self.assertIn(39330, prevalidation["exposedPorts"])
        for field in (
            "governedWorkloads",
            "rootlessGovernedComposeServices",
            "rootlessConfigServices",
        ):
            self.assertIn("travel-service", self.service_plane[field])
        bindings = {
            item["composeService"]: item["ownerWorkload"]
            for item in self.service_plane["rootlessProjectionBindings"]
        }
        self.assertEqual(bindings["travel-service"], "travel-service")
        self.assertEqual(
            set(self.service_plane["rootlessConfigServices"]),
            set(self.service_plane["rootlessGovernedComposeServices"]),
        )

    def test_compose_scan_and_prod_rewrite_preserve_travel_truth(self) -> None:
        self.assertIn(TRAVEL_COMPOSE, domain_service_compose_files(ROOT))
        rendered = render._rewrite_service(
            "travel-service",
            self.travel,
            {
                "travel-service",
                "user-service",
                "content-service",
                "entity-service",
                "chat-service",
                "circle-service",
                "product-ops-service",
            },
            image_version="candidate-tag",
            config_version="sha256:" + "a" * 64,
            release_evidence_digest="sha256:" + "b" * 64,
            versioned_image=True,
            instance="prod",
            replica_id="r0",
            config_root="runtime/config-root",
            media_root="/runtime/media",
            legal_root="runtime/legal",
            portal_root="runtime/portal",
            web_root="runtime/web",
            caddyfile_path="runtime/Caddyfile",
            model_cache_root="runtime/model-cache",
            data_mode="external",
        )
        environment = rendered["environment"]
        self.assertEqual(environment["APP_ENV"], "prod")
        self.assertEqual(environment["CONFIG_VERSION"], "sha256:" + "a" * 64)
        self.assertEqual(
            environment["TRAVEL_MONGO_URI"],
            "mongodb://host.containers.internal:19410/?directConnection=true",
        )
        self.assertEqual(
            environment["TRAVEL_REDIS_GENERAL_ADDR"],
            "host.containers.internal:19420",
        )
        self.assertEqual(
            environment["AUTH_JWT_SECRET"],
            "${AUTH_JWT_SECRET:?AUTH_JWT_SECRET is required}",
        )
        self.assertEqual(
            rendered["ports"],
            ["${QWQ_COMPOSE_TRAVEL_PORT:-19460}:18093"],
        )
        self.assertIn(
            "runtime-log-spool:/var/lib/quwoquan/runtime-log-spool",
            rendered["volumes"],
        )

    def test_instance_env_projects_unique_travel_ports_and_auth_material(self) -> None:
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

        self.assertIn("QWQ_COMPOSE_TRAVEL_PORT=39330", prevalidate)
        self.assertIn("AUTH_JWT_SECRET=test-auth_jwt_secret", prevalidate)
        self.assertIn("QWQ_COMPOSE_TRAVEL_PORT=29330", gray)
        self.assertNotIn("AUTH_JWT_SECRET=", gray)


if __name__ == "__main__":
    unittest.main()
