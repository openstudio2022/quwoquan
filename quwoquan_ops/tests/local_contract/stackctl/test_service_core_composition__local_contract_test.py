from __future__ import annotations

import unittest

from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULES,
    SERVICE_CORE_WORKLOAD,
    module_config_environment_key,
    module_instance_environment_key,
    project_compose_document,
    service_core_source_digest,
)


class ServiceCoreCompositionContractTest(unittest.TestCase):
    """spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/service-core-composition/spec.md#gwt-001.t1"""

    def test_core_modules_project_to_one_runtime_with_search(self) -> None:
        services = {
            service: {
                "image": f"${{{service}_IMAGE}}",
                "build": {
                    "context": "/repo/quwoquan_service",
                    "dockerfile": f"services/{service}/build/Dockerfile",
                    "args": {"GO_BUILD_FLAGS": "--p=1"},
                },
                "environment": {
                    "SERVICE_NAME": service,
                    "CONFIG_VERSION": f"${{{service}_CONFIG_VERSION}}",
                    "APP_ENV": "gamma",
                },
            }
            for service in SERVICE_CORE_MODULES
        }
        services["recommendation-service"] = {
            "image": "recommendation@sha256:" + "1" * 64
        }

        projected = project_compose_document({"services": services})

        self.assertIn(SERVICE_CORE_WORKLOAD, projected["services"])
        self.assertIn("recommendation-service", projected["services"])
        for service in SERVICE_CORE_MODULES:
            self.assertNotIn(service, projected["services"])
        core = projected["services"][SERVICE_CORE_WORKLOAD]
        self.assertIn("search-service", core["networks"]["default"]["aliases"])
        self.assertEqual(
            core["build"]["dockerfile"],
            "cmd/service-core/Dockerfile",
        )
        self.assertNotIn("SERVICE_NAME", core["environment"])
        self.assertNotIn("CONFIG_VERSION", core["environment"])
        self.assertEqual(
            module_config_environment_key("search-service"),
            "SERVICE_CORE_SEARCH_SERVICE_CONFIG_VERSION",
        )
        self.assertEqual(
            module_instance_environment_key("search-service"),
            "SERVICE_CORE_SEARCH_SERVICE_SERVICE_INSTANCE_ID",
        )
        for service in SERVICE_CORE_MODULES:
            self.assertIn(
                module_config_environment_key(service),
                core["environment"],
            )
        self.assertEqual(
            set(projected["x-qwq-service-core"]["modules"]),
            set(SERVICE_CORE_MODULES),
        )

    def test_source_digest_requires_exact_core_closure(self) -> None:
        digests = {
            service: "sha256:" + f"{index:064x}"
            for index, service in enumerate(SERVICE_CORE_MODULES, start=1)
        }
        first = service_core_source_digest(digests)
        changed = dict(digests)
        changed["search-service"] = "sha256:" + "f" * 64
        self.assertNotEqual(first, service_core_source_digest(changed))
        del changed["api-edge"]
        with self.assertRaisesRegex(ValueError, "every module exactly once"):
            service_core_source_digest(changed)


if __name__ == "__main__":
    unittest.main()
