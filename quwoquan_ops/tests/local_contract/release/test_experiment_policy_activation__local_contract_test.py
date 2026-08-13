# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001

from __future__ import annotations

import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import experiment_policy_activation as activation


class ExperimentPolicyActivationLocalContractTest(unittest.TestCase):
    def test_test_live_is_runtime_bound_without_candidate_or_bearer_persistence(
        self,
    ) -> None:
        attempt_id = "alpha-test-live-" + "c" * 32
        configuration_digest = "sha256:" + "d" * 64
        search_create = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
        }
        rec_create = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
        }
        catalog = {
            "items": [
                {
                    **search_create,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    **rec_create,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 10000},
                        {"key": "model", "allocationBasisPoints": 0},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                side_effect=AssertionError("test_live must not read a candidate"),
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                side_effect=AssertionError("test_live must not read a manifest"),
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                side_effect=AssertionError("loopback HTTP must not read release TLS"),
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-test-live-bearer",
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_test_live_experiment_policies(
                environment="alpha",
                target="alpha-local",
                product_ops_published_port=17250,
                attempt_id=attempt_id,
                configuration_digest=configuration_digest,
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["launchPolicy"], "test_live")
        self.assertIs(receipt["nonPromotable"], True)
        self.assertEqual(receipt["attemptId"], attempt_id)
        self.assertEqual(receipt["configurationDigest"], configuration_digest)
        self.assertRegex(receipt["runtimeIdentityDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-test-live-bearer", json.dumps(receipt))
        for call in request_json.call_args_list:
            self.assertEqual(call.kwargs["cafile"], None)
            self.assertEqual(
                call.kwargs["url"],
                "http://127.0.0.1:17250/control-plane/product/experiments",
            )
        create_call = request_json.call_args_list[0].kwargs
        self.assertTrue(
            create_call["headers"]["Idempotency-Key"].startswith(
                "test-live-runtime-policy/alpha-local/"
            )
        )
        self.assertNotIn("Authorization", create_call["headers"])

    def test_test_live_rolls_existing_model_policy_to_explicit_rule_only(self) -> None:
        attempt_id = "alpha-test-live-" + "e" * 32
        configuration_digest = "sha256:" + "f" * 64
        search = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
            "variants": [
                {"key": "control", "allocationBasisPoints": 5000},
                {"key": "term_heat", "allocationBasisPoints": 5000},
            ],
        }
        recommendation_before = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
            "variants": [
                {"key": "rule", "allocationBasisPoints": 5000},
                {"key": "model", "allocationBasisPoints": 5000},
            ],
        }
        recommendation_after = {
            **recommendation_before,
            "experimentRevision": 2,
            "variants": [
                {"key": "rule", "allocationBasisPoints": 10000},
                {"key": "model", "allocationBasisPoints": 0},
            ],
        }
        catalog_before = {"items": [search, recommendation_before]}
        catalog_after = {"items": [search, recommendation_after]}
        with (
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-test-live-bearer",
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog_before),
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog_before),
                    (200, recommendation_after),
                    (200, catalog_after),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_test_live_experiment_policies(
                environment="alpha",
                target="alpha-local",
                product_ops_published_port=17250,
                attempt_id=attempt_id,
                configuration_digest=configuration_digest,
            )

        self.assertEqual(receipt["operation"], "rolled_out")
        self.assertEqual(
            receipt["policyOperations"],
            {"search_ranking": "reused", "rec_model_vs_rule": "rolled_out"},
        )
        recommendation = next(
            item for item in receipt["policies"] if item["id"] == "rec_model_vs_rule"
        )
        self.assertEqual(recommendation["variants"], recommendation_after["variants"])
        rollout = request_json.call_args_list[4].kwargs
        self.assertEqual(
            rollout["url"],
            "http://127.0.0.1:17250/control-plane/product/experiments/rec_model_vs_rule:rollout",
        )
        self.assertEqual(rollout["headers"]["If-Match"], '"1"')
        self.assertIn("/rollout", rollout["headers"]["Idempotency-Key"])
        self.assertNotIn("sensitive-test-live-bearer", json.dumps(receipt))

    def test_test_live_rejects_wrong_identity_or_port_before_minting(self) -> None:
        valid = {
            "environment": "alpha",
            "target": "alpha-local",
            "product_ops_published_port": 17250,
            "attempt_id": "alpha-test-live-" + "a" * 32,
            "configuration_digest": "sha256:" + "b" * 64,
        }
        cases = (
            ({**valid, "target": "beta-local"}, "Alpha/Beta/Gamma"),
            ({**valid, "product_ops_published_port": 17251}, "does not match"),
            ({**valid, "attempt_id": "alpha-test-live-invalid"}, "attempt identity"),
            ({**valid, "configuration_digest": "sha256:invalid"}, "configuration digest"),
        )
        with mock.patch.object(
            activation,
            "mint_local_product_ops_operator_token",
        ) as mint:
            for arguments, message in cases:
                with self.subTest(arguments=arguments):
                    with self.assertRaisesRegex(
                        activation.ExperimentPolicyActivationError,
                        message,
                    ):
                        activation.activate_test_live_experiment_policies(**arguments)
        mint.assert_not_called()

    def test_create_is_package_bound_exact_and_never_persists_bearer(self) -> None:
        search_create = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
        }
        rec_create = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
        }
        catalog = {
            "items": [
                {
                    **search_create,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    **rec_create,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="alpha",
                target="alpha-local",
                product_ops_base_url="https://ops.alpha.quwoquan.local:17010",
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["operation"], "created")
        self.assertEqual(receipt["caseResult"]["executed"], 2)
        self.assertEqual(receipt["caseResult"]["skipped"], 0)
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-bearer", json.dumps(receipt))
        create_call = request_json.call_args_list[0].kwargs
        self.assertEqual(create_call["method"], "POST")
        self.assertIn("Idempotency-Key", create_call["headers"])
        self.assertNotIn("Authorization", create_call["headers"])

    def test_existing_exact_policy_is_reused_without_second_source(self) -> None:
        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 3,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 2,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={"packageDigest": "sha256:" + "b" * 64},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="token",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog),
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog),
                ],
            ),
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="gamma",
                target="gamma-local",
                product_ops_base_url="https://ops.gamma.quwoquan.local:19010",
            )
        self.assertEqual(receipt["operation"], "reused")
        self.assertEqual(receipt["policy"]["experimentRevision"], 3)
        self.assertEqual(
            receipt["policyOperations"],
            {"search_ranking": "reused", "rec_model_vs_rule": "reused"},
        )

    def test_published_port_bootstrap_uses_loopback_and_canonical_identity(
        self,
    ) -> None:
        """冷启动 policy owner bootstrap 走 loopback published port（此时
        gamma-proxy 尚不存在），且与 up 之后的 activation 共用同一 canonical
        recipes 与 idempotency 身份，暖启动是纯 reuse 而非第二真相源。"""

        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        search_create = dict(catalog["items"][0])
        rec_create = dict(catalog["items"][1])
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(
                activation,
                "load_port_manifest",
                return_value={},
            ),
            mock.patch.object(
                activation,
                "profile_ports",
                return_value={"product-ops-service": 19250, "redis": 19420},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
            ) as certificate_path,
            mock.patch.object(
                activation,
                "stream_field_values",
                return_value=("search_ranking", "rec_model_vs_rule"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["schema"], "qwq.experiment_policy_bootstrap_receipt")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["launchPolicy"], "policy-owner-bootstrap")
        self.assertEqual(receipt["productOpsPublishedPort"], 19250)
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-bearer", json.dumps(receipt))
        # bootstrap 阶段没有 gamma-proxy，不得依赖 public TLS 根证书。
        certificate_path.assert_not_called()
        for call in request_json.call_args_list:
            self.assertTrue(
                call.kwargs["url"].startswith("http://127.0.0.1:19250/"),
                call.kwargs["url"],
            )
            self.assertIsNone(call.kwargs["cafile"])
        create_call = request_json.call_args_list[0].kwargs
        # 与 up 之后 activate_search_experiment_policy 完全相同的幂等身份。
        self.assertTrue(
            create_call["headers"]["Idempotency-Key"].startswith(
                "runtime-policy/gamma-local/" + "a" * 16 + "/search_ranking/"
            ),
            create_call["headers"]["Idempotency-Key"],
        )

    @staticmethod
    def _bootstrap_environment_patches(
        *,
        stream_policy_ids: tuple[str, ...] | None = (
            "search_ranking",
            "rec_model_vs_rule",
        ),
    ) -> tuple[mock._patch, ...]:
        patches = [
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(activation, "load_port_manifest", return_value={}),
            mock.patch.object(
                activation,
                "profile_ports",
                return_value={"product-ops-service": 19250, "redis": 19420},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
        ]
        if stream_policy_ids is not None:
            patches.append(
                mock.patch.object(
                    activation,
                    "stream_field_values",
                    return_value=stream_policy_ids,
                )
            )
        return tuple(patches)

    def test_connection_refused_is_retried_until_listener_accepts(self) -> None:
        """product-ops 进程刚被 bootstrap 拉起时 HTTP 监听尚未就绪，且其
        healthz 在 user-service 缺席时必然 unhealthy；唯一正确的等待信号
        是连接级重试，连接成立后同一幂等 command 必须一次成功。"""

        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        refused = activation.ExperimentPolicyTransportError(
            "experiment policy request transport failed: URLError"
        )
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("time.sleep"))
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=[
                        refused,
                        refused,
                        (201, dict(catalog["items"][0])),
                        (200, catalog),
                        (201, dict(catalog["items"][1])),
                        (200, catalog),
                    ],
                )
            )
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(request_json.call_count, 6)
        first_urls = {
            call.kwargs["url"] for call in request_json.call_args_list[:3]
        }
        # 连接被拒的重试必须停留在同一个幂等 create 上，不得跳过或换目标。
        self.assertEqual(len(first_urls), 1)

    def test_business_http_error_fails_fast_without_retry(self) -> None:
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches():
                stack.enter_context(patcher)
            sleep = stack.enter_context(mock.patch("time.sleep"))
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    return_value=(500, {"code": "OPS.SYSTEM.internal"}),
                )
            )
            with self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "HTTP 500",
            ):
                activation.activate_search_experiment_policy_via_published_port(
                    environment="gamma",
                    target="gamma-local",
                )

        self.assertEqual(request_json.call_count, 1)
        sleep.assert_not_called()

    def test_transport_retry_budget_exhaustion_fails(self) -> None:
        refused = activation.ExperimentPolicyTransportError(
            "experiment policy request transport failed: URLError"
        )
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches():
                stack.enter_context(patcher)
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=refused,
                )
            )
            with self.assertRaises(activation.ExperimentPolicyTransportError):
                activation.activate_search_experiment_policy_via_published_port(
                    environment="gamma",
                    target="gamma-local",
                    timeout_seconds=1.2,
                )

        self.assertGreaterEqual(request_json.call_count, 2)

    @staticmethod
    def _reused_catalog() -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }

    def test_reused_with_missing_stream_fact_re_emits_through_public_rollout(
        self,
    ) -> None:
        """事实流 7 天 retention 会整体过期，而 authoritative 策略永续：
        reused readback 不足以保证下游可见性。缺失事实必须经公开 rollout
        command 等值补发（revision bump），随后事实在流中可见。"""

        catalog = self._reused_catalog()

        def rollout_payload(policy_id: str) -> dict[str, object]:
            variants = next(
                item["variants"]
                for item in catalog["items"]
                if item["id"] == policy_id
            )
            return {
                "id": policy_id,
                "key": policy_id,
                "status": "running",
                "experimentRevision": 2,
                "variants": variants,
            }

        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches(
                stream_policy_ids=None,
            ):
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("time.sleep"))
            stream = stack.enter_context(
                mock.patch.object(
                    activation,
                    "stream_field_values",
                    side_effect=[
                        (),
                        ("search_ranking", "rec_model_vs_rule"),
                    ],
                )
            )
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=[
                        (409, {"code": "OPS.USER.version_conflict"}),
                        (200, catalog),
                        (409, {"code": "OPS.USER.version_conflict"}),
                        (200, catalog),
                        # search_ranking re-emission: readback + rollout
                        (200, catalog),
                        (200, rollout_payload("search_ranking")),
                        # rec_model_vs_rule re-emission: readback + rollout
                        (200, catalog),
                        (200, rollout_payload("rec_model_vs_rule")),
                    ],
                )
            )
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["operation"], "re_emitted")
        self.assertEqual(
            receipt["streamVisibility"],
            {
                "stream": "events.ops.experiment_policy_activated",
                "reEmittedPolicyIds": ["search_ranking", "rec_model_vs_rule"],
            },
        )
        self.assertEqual(
            receipt["policyOperations"],
            {"search_ranking": "re_emitted", "rec_model_vs_rule": "re_emitted"},
        )
        rollout_calls = [
            call
            for call in request_json.call_args_list
            if ":rollout" in call.kwargs["url"]
        ]
        self.assertEqual(len(rollout_calls), 2)
        for call in rollout_calls:
            self.assertEqual(call.kwargs["headers"]["If-Match"], '"1"')
            self.assertIn(
                "runtime-policy-reemit/",
                call.kwargs["headers"]["Idempotency-Key"],
            )
            self.assertEqual(call.kwargs["body"]["status"], "running")
        self.assertEqual(stream.call_count, 2)
        recommendation = next(
            item
            for item in receipt["policies"]
            if item["id"] == "rec_model_vs_rule"
        )
        self.assertEqual(recommendation["experimentRevision"], 2)

    def test_reused_with_visible_stream_fact_takes_no_action(self) -> None:
        catalog = self._reused_catalog()
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches():
                stack.enter_context(patcher)
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=[
                        (409, {"code": "OPS.USER.version_conflict"}),
                        (200, catalog),
                        (409, {"code": "OPS.USER.version_conflict"}),
                        (200, catalog),
                    ],
                )
            )
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["operation"], "reused")
        self.assertEqual(receipt["streamVisibility"]["reEmittedPolicyIds"], [])
        self.assertEqual(request_json.call_count, 4)
        self.assertFalse(
            any(
                ":rollout" in call.kwargs["url"]
                for call in request_json.call_args_list
            )
        )

    def test_created_waits_for_outbox_dispatch_without_re_emission(self) -> None:
        """created 的事实已在 Postgres outbox；可见性验证只等待派发完成，
        不得触发 rollout 补发。"""

        catalog = self._reused_catalog()
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches(
                stream_policy_ids=None,
            ):
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("time.sleep"))
            stream = stack.enter_context(
                mock.patch.object(
                    activation,
                    "stream_field_values",
                    side_effect=[
                        (),
                        ("search_ranking", "rec_model_vs_rule"),
                    ],
                )
            )
            request_json = stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=[
                        (201, dict(catalog["items"][0])),
                        (200, catalog),
                        (201, dict(catalog["items"][1])),
                        (200, catalog),
                    ],
                )
            )
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["operation"], "created")
        self.assertEqual(receipt["streamVisibility"]["reEmittedPolicyIds"], [])
        self.assertEqual(request_json.call_count, 4)
        self.assertEqual(stream.call_count, 2)

    def test_stream_visibility_budget_exhaustion_fails(self) -> None:
        catalog = self._reused_catalog()
        with ExitStack() as stack:
            for patcher in self._bootstrap_environment_patches(
                stream_policy_ids=None,
            ):
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("time.sleep"))
            stack.enter_context(
                mock.patch.object(
                    activation,
                    "stream_field_values",
                    return_value=(),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    activation,
                    "_request_json",
                    side_effect=[
                        (201, dict(catalog["items"][0])),
                        (200, catalog),
                        (201, dict(catalog["items"][1])),
                        (200, catalog),
                    ],
                )
            )
            with self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "not visible",
            ):
                activation.activate_search_experiment_policy_via_published_port(
                    environment="gamma",
                    target="gamma-local",
                    timeout_seconds=1.2,
                )

    def test_request_json_maps_connection_refused_to_transport_error(self) -> None:
        import socket

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        with self.assertRaisesRegex(
            activation.ExperimentPolicyTransportError,
            "transport failed",
        ):
            activation._request_json(
                method="GET",
                url=f"http://127.0.0.1:{port}/control-plane/product/experiments",
                token="redacted",
                cafile=None,
                body=None,
                headers={},
                timeout_seconds=1.0,
            )

    def test_published_port_bootstrap_rejects_prod_before_credentials(self) -> None:
        with (
            mock.patch.object(
                activation, "mint_local_product_ops_operator_token"
            ) as mint,
            self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "Alpha/Beta/Gamma",
            ),
        ):
            activation.activate_search_experiment_policy_via_published_port(
                environment="prod",
                target="prod-sim",
            )
        mint.assert_not_called()

    def test_prod_is_rejected_before_any_credential_is_minted(self) -> None:
        with (
            mock.patch.object(
                activation, "mint_local_product_ops_operator_token"
            ) as mint,
            self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "Alpha/Beta/Gamma",
            ),
        ):
            activation.activate_search_experiment_policy(
                environment="prod",
                target="prod-sim",
                product_ops_base_url="https://ops.quwoquan.com",
            )
        mint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
