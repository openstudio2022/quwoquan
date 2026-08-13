"""场景：环境集成 probe——test auth token 解析与 fail-closed、检查项与 search
商用信封、actor header 不伪造、token/CA 经 env 传递、hosted DNS 不覆盖、
local gamma 临时会话铸造以及 verify integration 的只读 health preflight。"""

from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.probes import run_environment_integration_probe as integration_probe


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_integration_probe_resolves_test_auth_token_from_env(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"GAMMA_TEST_AUTH_TOKEN": "-starts-with-dash", "TEST_AUTH_TOKEN": ""},
            clear=False,
        ):
            self.assertEqual(
                integration_probe._resolve_test_auth_token("gamma", ""),
                "-starts-with-dash",
            )

    def test_post_deploy_probe_blocks_without_verified_test_token(self) -> None:
        args = argparse.Namespace(
            env="gamma",
            mode="post-deploy",
            test_auth_token="",
            base_url="https://gamma.example",
            product_ops_base_url="",
            media_base_url="",
            request_timeout_seconds=12,
            retry_attempts=1,
            retry_sleep_seconds=0.0,
            require_non_empty_content_feed=False,
        )
        with mock.patch.object(integration_probe, "build_checks", return_value=[]):
            report = integration_probe.run_checks(args)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(
            report["findings"],
            [
                "GATE_BLOCK: post-deploy integration requires a valid environment test auth token"
            ],
        )

    def test_environment_probe_uses_ready_entity_operation_not_blocked_chat(self) -> None:
        args = argparse.Namespace(
            env="gamma",
            test_auth_token="runtime-bearer",
            base_url="https://gamma.example",
            product_ops_base_url="",
            media_base_url="",
        )

        checks = integration_probe.build_checks(args)
        by_name = {check["name"]: check for check in checks}

        self.assertNotIn("chat_inbox", by_name)
        self.assertEqual(
            by_name["entity_homepage_search"]["url"],
            "https://gamma.example/homepages/search?query=%E8%A5%BF%E6%B9%96&limit=1",
        )
        search = by_name["global_search"]
        self.assertEqual(search["method"], "POST")
        self.assertEqual(search["url"], "https://gamma.example/search")
        self.assertEqual(search["headers"]["X-Session-Id"], "stackctl-environment-probe")
        self.assertEqual(
            json.loads(search["body"].decode("utf-8")),
            {"query": "西湖", "mode": "result", "limit": 1},
        )

    def test_environment_probe_requires_search_commercial_envelope(self) -> None:
        issue, hit_count = integration_probe._search_semantic_issue(
            json.dumps(
                {
                    "requestId": "search-probe-1",
                    "hits": [],
                }
            )
        )
        self.assertIsNone(issue)
        self.assertEqual(hit_count, 0)

        issue, hit_count = integration_probe._search_semantic_issue(
            json.dumps({"requestId": "search-probe-1", "hits": {}})
        )
        self.assertIn("hits", issue or "")
        self.assertIsNone(hit_count)

    def test_environment_probe_can_gate_only_global_search(self) -> None:
        args = argparse.Namespace(
            env="beta",
            test_auth_token="",
            base_url="https://beta.example",
            product_ops_base_url="",
            media_base_url="",
            request_timeout_seconds=12,
            retry_attempts=1,
            retry_sleep_seconds=0.0,
            require_non_empty_content_feed=False,
            only_check=["global_search"],
            mode="readonly",
        )
        response = json.dumps(
            {
                "requestId": "search-probe-2",
                "hits": [],
            }
        )
        with mock.patch.object(
            integration_probe,
            "request",
            return_value=(True, 200, response),
        ):
            report = integration_probe.run_checks(args)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["onlyChecks"], ["global_search"])
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            ["global_search"],
        )

    def test_environment_probe_does_not_forge_actor_headers(self) -> None:
        anonymous_headers = integration_probe._common_headers("")
        authenticated_headers = integration_probe._common_headers("local-test-bearer")

        self.assertNotIn("X-Client-User-Id", anonymous_headers)
        self.assertNotIn("X-Test-Auth-Token", authenticated_headers)
        self.assertEqual(authenticated_headers["Authorization"], "Bearer local-test-bearer")

    def test_run_environment_integration_probe_passes_token_and_release_ca_via_env(
        self,
    ) -> None:
        topology = {"targets": []}
        target = {
            "env": "gamma",
            "backend": "local",
            "publicBases": {
                "api": "https://api.gamma.example.invalid",
                "productOps": "https://ops.gamma.example.invalid",
            },
        }

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="-starts-with-dash",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
            mock.patch(
                "quwoquan_ops.cli.stackctl.root_certificate_path",
                return_value=Path("/tmp/gamma-local-root.crt"),
            ),
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "gamma-local",
                Path("/tmp/report"),
                release_readiness_path=Path("/tmp/release-readiness.json"),
            )

        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertNotIn("--resolve-host", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(
            kwargs["env"]["SSL_CERT_FILE"],
            "/tmp/gamma-local-root.crt",
        )

    def test_run_environment_integration_probe_uses_canonical_dns_target(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "beta",
            "backend": "local",
            "publicBases": {
                "api": "https://api.beta.quwoquan.com:18000",
                "productOps": "https://ops.beta.quwoquan.com:18010",
            },
        }

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="beta-bearer",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
            mock.patch(
                "quwoquan_ops.cli.lib.public_domain_tls.root_certificate_path",
                return_value=Path("/tmp/beta-local-root.crt"),
            ),
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "beta-local",
                Path("/tmp/report"),
            )

        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--resolve-host", kwargs["argv"])
        self.assertEqual(kwargs["env"]["BETA_TEST_AUTH_TOKEN"], "beta-bearer")

    def test_run_environment_integration_probe_does_not_override_hosted_dns(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "prod",
            "backend": "ssh-hosted",
            "publicBases": {
                "api": "https://api.quwoquan.com",
                "productOps": "https://product-ops.quwoquan.com",
            },
        }

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="prod-bearer",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "prod-hosted",
                Path("/tmp/report"),
            )

        self.assertNotIn("--resolve-host", run_probe.call_args.kwargs["argv"])

    def test_run_environment_integration_probe_mints_local_gamma_session(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "gamma",
            "backend": "local",
            "publicBases": {
                "api": "https://api.gamma.quwoquan.com:19000",
                "productOps": "https://ops.gamma.example.invalid",
            },
        }
        actor = mock.Mock()
        actor.session.access_token = "ephemeral-local-bearer"

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl.open_test_data_acceptance_session",
                return_value=actor,
            ) as login,
            mock.patch(
                "quwoquan_ops.cli.stackctl.close_test_data_acceptance_actor",
            ) as close_actor,
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
            mock.patch(
                "quwoquan_ops.cli.lib.public_domain_tls.root_certificate_path",
                return_value=Path("/tmp/gamma-local-root.crt"),
            ),
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "gamma-local",
                Path("/tmp/report"),
            )

        login.assert_called_once_with(
            "https://api.gamma.quwoquan.com:19000",
            environment="gamma",
            target_name="gamma-local",
            test_data_instance_id=mock.ANY,
            actor_role="primary",
            actor_index=0,
        )
        close_actor.assert_called_once_with(
            "https://api.gamma.quwoquan.com:19000",
            actor=actor,
            test_data_instance_id=mock.ANY,
        )
        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "ephemeral-local-bearer")
        self.assertEqual(
            kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"],
            "ephemeral-local-bearer",
        )

    def test_verify_integration_never_starts_gamma_when_dependency_port_is_missing(self) -> None:
        manifest = stackctl.load_port_manifest()
        target = {"env": "gamma", "portProfile": "gamma-local"}
        mongo_port = stackctl.canonical_port(manifest, "gamma-local", "mongodb")

        with (
            mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value={}),
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch("quwoquan_ops.cli.stackctl.load_port_manifest", return_value=manifest),
            mock.patch(
                "quwoquan_ops.cli.stackctl.socket_probe",
                side_effect=lambda port: port != mongo_port,
            ) as socket_probe,
        ):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                VerificationProfile.INTEGRATION,
            )

        self.assertEqual(commands[0]["name"], "gamma-local-health-preflight")
        self.assertIn("health", commands[0]["argv"])
        self.assertNotIn("up", commands[0]["argv"])
        socket_probe.assert_not_called()

    def test_verify_integration_uses_read_only_health_when_runtime_ports_are_ready(self) -> None:
        manifest = stackctl.load_port_manifest()
        target = {"env": "gamma", "portProfile": "gamma-local"}

        with (
            mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value={}),
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch("quwoquan_ops.cli.stackctl.load_port_manifest", return_value=manifest),
            mock.patch("quwoquan_ops.cli.stackctl.socket_probe", return_value=True) as socket_probe,
        ):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                VerificationProfile.INTEGRATION,
            )

        self.assertEqual(commands[0]["name"], "gamma-local-health-preflight")
        self.assertIn("health", commands[0]["argv"])
        self.assertNotIn("up", commands[0]["argv"])
        socket_probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
