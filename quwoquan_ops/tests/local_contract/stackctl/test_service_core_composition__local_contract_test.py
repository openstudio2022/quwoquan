from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULES,
    SERVICE_CORE_WORKLOAD,
    ServiceCoreCompositionError,
    _service_core_module_target_ports,
    module_config_environment_key,
    module_instance_environment_key,
    project_compose_document,
    service_core_module_target_ports,
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
        services["user-service"]["ports"] = ["17210:18081"]
        services["chat-service"]["ports"] = ["17200:18081"]
        services["assistant-service"]["ports"] = ["17230:18087"]
        services["notification-service"]["ports"] = ["17320:18087"]
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
        # 容器侧 target 原样透传：user/chat 共用 18081、assistant/notification 共用
        # 18087，主机端口不同故四条发布口互不合并，归属由 publisher 四元组区分。
        self.assertEqual(
            core["ports"],
            [
                "17210:18081",
                "17320:18087",
                "17200:18081",
                "17230:18087",
            ],
        )
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

    def test_core_module_long_port_syntax_passes_the_container_target_through(
        self,
    ) -> None:
        projected = project_compose_document(
            {
                "services": {
                    "user-service": {
                        "ports": [
                            {
                                "name": "user-api",
                                "target": 18081,
                                "published": "17210",
                                "host_ip": "127.0.0.1",
                                "protocol": "tcp",
                                "mode": "host",
                            }
                        ]
                    }
                }
            }
        )

        self.assertEqual(
            projected["services"][SERVICE_CORE_WORKLOAD]["ports"],
            [
                {
                    "name": "user-api",
                    "target": 18081,
                    "published": "17210",
                    "host_ip": "127.0.0.1",
                    "protocol": "tcp",
                    "mode": "host",
                }
            ],
        )

    def test_core_module_target_ports_are_the_declared_module_ports(self) -> None:
        """`internalAddress` 是容器内回环上游，不是可被 Docker 转发的发布目标。"""
        self.assertEqual(
            service_core_module_target_ports(),
            {
                "user-service": 18081,
                "integration-service": 18086,
                "notification-service": 18087,
                "entity-service": 18084,
                "tag-service": 18092,
                "search-service": 18095,
                "content-service": 18080,
                "circle-service": 18082,
                "chat-service": 18081,
                "assistant-service": 18087,
                "api-edge": 18079,
            },
        )

    def test_composition_parser_rejects_invalid_internal_address(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "internal address is invalid",
        ):
            _service_core_module_target_ports(
                [
                    {
                        "name": "user-service",
                        "port": 18081,
                        "internalAddress": "invalid-address",
                    }
                ]
            )

    def test_composition_parser_accepts_modules_sharing_one_container_port(
        self,
    ) -> None:
        """共用容器口合法：归属由 publisher 四元组的 canonical hostPort 区分。"""
        self.assertEqual(
            _service_core_module_target_ports(
                [
                    {
                        "name": "user-service",
                        "port": 18081,
                        "internalAddress": "127.0.0.1:28081",
                    },
                    {
                        "name": "chat-service",
                        "port": 18081,
                        "internalAddress": "127.0.0.1:28082",
                    },
                ]
            ),
            {"user-service": 18081, "chat-service": 18081},
        )

    def test_unreadable_composition_becomes_a_structured_issue_not_an_import_error(
        self,
    ) -> None:
        """装载失败必须落进门禁的 issue 通道，而不是在 import 期抛裸异常。"""
        import quwoquan_ops.cli.lib.service_core_composition as module
        from quwoquan_ops.cli.lib.port_manifest import (
            load_port_manifest,
            validate_port_manifest,
        )

        cached = module._COMPOSITION_CACHE
        module._COMPOSITION_CACHE = None
        try:
            with mock.patch.object(
                module,
                "_MANIFEST_PATH",
                Path("/nonexistent/service-core/composition.yaml"),
            ):
                issues = module.service_core_composition_issues()
                self.assertTrue(issues)
                self.assertIn("unreadable", issues[0])

                manifest_issues = validate_port_manifest(load_port_manifest())
                self.assertTrue(manifest_issues)
                self.assertIn("unreadable", " ".join(manifest_issues))

                with self.assertRaises(ServiceCoreCompositionError):
                    service_core_module_target_ports()
        finally:
            module._COMPOSITION_CACHE = cached

    def test_composition_parser_rejects_duplicate_module_names(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "module port is invalid",
        ):
            _service_core_module_target_ports(
                [
                    {"name": "user-service", "port": 18081},
                    {"name": "user-service", "port": 18082},
                ]
            )

    def test_unknown_service_core_module_published_port_fails_closed(self) -> None:
        """未在 composition 声明的模块不得静默透传发布口，否则绕过 target drift 判否。"""
        from quwoquan_ops.cli.lib.service_core_composition import (
            _verified_published_port,
        )

        with self.assertRaisesRegex(
            ServiceCoreCompositionError,
            "unknown service-core module published port: not-a-module",
        ):
            _verified_published_port("not-a-module", "17210:18081")

    def test_core_module_port_target_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ServiceCoreCompositionError,
            "published port target drift: user-service",
        ):
            project_compose_document(
                {"services": {"user-service": {"ports": ["17210:18082"]}}}
            )

        with self.assertRaisesRegex(
            ServiceCoreCompositionError,
            "published port target drift: integration-service",
        ):
            project_compose_document(
                {
                    "services": {
                        "integration-service": {"ports": ["17310:18085"]}
                    }
                }
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

    def test_assistant_injected_runtime_keys_merge_into_service_core_environment(
        self,
    ) -> None:
        services = {
            service: {
                "image": f"${{{service}_IMAGE}}",
                "environment": {"APP_ENV": "alpha"},
            }
            for service in SERVICE_CORE_MODULES
        }
        services["assistant-service"]["environment"].update(
            {
                "ASSISTANT_MODEL_COMPLETION_URL": (
                    "${ASSISTANT_MODEL_COMPLETION_URL:-}"
                ),
                "ASSISTANT_PUBLIC_SEARCH_URL": "${ASSISTANT_PUBLIC_SEARCH_URL:-}",
                "ASSISTANT_WEATHER_GEOCODING_URL": (
                    "${ASSISTANT_WEATHER_GEOCODING_URL:-}"
                ),
                "ASSISTANT_WEATHER_FORECAST_URL": (
                    "${ASSISTANT_WEATHER_FORECAST_URL:-}"
                ),
                "ASSISTANT_FINANCE_CHART_URL": "${ASSISTANT_FINANCE_CHART_URL:-}",
            }
        )

        projected = project_compose_document({"services": services})
        core_env = projected["services"][SERVICE_CORE_WORKLOAD]["environment"]

        self.assertNotIn("assistant-service", projected["services"])
        for key in (
            "ASSISTANT_MODEL_COMPLETION_URL",
            "ASSISTANT_PUBLIC_SEARCH_URL",
            "ASSISTANT_WEATHER_GEOCODING_URL",
            "ASSISTANT_WEATHER_FORECAST_URL",
            "ASSISTANT_FINANCE_CHART_URL",
        ):
            self.assertIn(key, core_env)
            self.assertEqual(core_env[key], f"${{{key}:-}}")

    def test_assistant_skill_release_and_trust_share_the_config_mount(self) -> None:
        services = {
            service: {
                "image": f"${{{service}_IMAGE}}",
                "environment": {"APP_ENV": "alpha"},
            }
            for service in SERVICE_CORE_MODULES
        }
        services["assistant-service"].update(
            {
                "environment": {
                    "APP_ENV": "alpha",
                    "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON": (
                        "${ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON:?required}"
                    ),
                },
                "volumes": ["${QWQ_COMPOSE_CONFIG_ROOT}:/etc/qwq-config:ro"],
            }
        )

        projected = project_compose_document({"services": services})
        core = projected["services"][SERVICE_CORE_WORKLOAD]

        self.assertEqual(
            core["environment"]["ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"],
            "${ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON:?required}",
        )
        self.assertIn(
            "${QWQ_COMPOSE_CONFIG_ROOT}:/etc/qwq-config:ro",
            core["volumes"],
        )


if __name__ == "__main__":
    unittest.main()
