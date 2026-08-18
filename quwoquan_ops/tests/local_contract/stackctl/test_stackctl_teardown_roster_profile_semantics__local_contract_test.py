"""拆除期望 roster 必须按已激活 Compose profile 计算。

profile 门控的服务在 profile 未激活时按 Compose 设计就没有容器。把它算进期望
roster 会把「按设计投影掉」误判成漂移，让 down 与 bind-content 双双永久
GATE_BLOCK——即「起得来但拆不掉」。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import unittest

from quwoquan_ops.cli.commands.down_shared import (
    _compose_activated_services,
    _compose_service_profiles,
)


class StackctlTeardownRosterProfileSemanticsTest(unittest.TestCase):
    def test_inactive_profile_gated_service_is_not_expected(self) -> None:
        payloads = [
            {
                "services": {
                    "service-core": {"image": "core"},
                    "platform-ops-service": {"profiles": ["control-plane"]},
                }
            }
        ]
        self.assertEqual(
            _compose_activated_services(payloads, activated_profiles=[]),
            {"service-core"},
        )

    def test_active_profile_gated_service_is_expected(self) -> None:
        payloads = [
            {
                "services": {
                    "service-core": {"image": "core"},
                    "platform-ops-service": {"profiles": ["control-plane"]},
                }
            }
        ]
        self.assertEqual(
            _compose_activated_services(
                payloads,
                activated_profiles=["control-plane"],
            ),
            {"service-core", "platform-ops-service"},
        )

    def test_profiles_declared_in_one_overlay_gate_the_merged_service(self) -> None:
        """Compose keeps the declaring overlay's profiles after the merge."""
        payloads = [
            {"services": {"platform-ops-service": {"profiles": ["control-plane"]}}},
            {"services": {"platform-ops-service": {"build": {"context": "."}}}},
        ]
        self.assertEqual(
            _compose_service_profiles(payloads),
            {"platform-ops-service": {"control-plane"}},
        )
        self.assertEqual(
            _compose_activated_services(payloads, activated_profiles=["edge-media"]),
            set(),
        )

    def test_service_with_no_profile_is_always_expected(self) -> None:
        payloads = [{"services": {"redis": {"image": "redis"}}}]
        self.assertEqual(
            _compose_activated_services(payloads, activated_profiles=["edge-media"]),
            {"redis"},
        )

    def test_invalid_profiles_declaration_is_refused(self) -> None:
        payloads = [{"services": {"redis": {"profiles": "edge-media"}}}]
        with self.assertRaises(ValueError):
            _compose_activated_services(payloads, activated_profiles=[])

    def test_invalid_services_declaration_is_refused(self) -> None:
        payloads = [{"services": ["redis"]}]
        with self.assertRaises(ValueError):
            _compose_activated_services(payloads, activated_profiles=[])


if __name__ == "__main__":
    unittest.main()
